"""`nat` — the NeMo Agent Toolkit competitive arm (mem-lvp.3).

`NatMemory` is a pure ``name`` + ``backend`` subclass of ``AbstractSemanticArm``;
all the translation lives in ``_NatClient``, which adapts NAT's async
``nat.memory.interfaces.MemoryEditor`` to the SYNC ``SemanticMemoryClient`` seam
through an injected ``AsyncClientBridge`` (mem-lvp.5a) — ``MemoryEditor`` is async,
the Protocol is not, so the bridge holds one persistent loop and the seam (and the
fakes) stay sync.

- ``store`` -> ``add_items([MemoryItem(user_id=scope, memory=content, metadata=...)])``.
  ``MemoryItem`` has NO native id field, so the adapter mints its own id and
  round-trips it through ``metadata['memory_id']``; that minted id is returned and
  is what retrieval keys its payloads off.
- ``query`` -> ``search(query, top_k, user_id=scope)``; maps ``MemoryItem.memory`` ->
  content and reads the minted id back out of ``metadata``. RedisEditor's
  ``similarity_score`` is an L2/Euclidean **distance** (lower = closer), so the
  adapter normalizes it to a higher-is-better similarity via ``1 / (1 + d)`` — the
  same convention the A-MEM arm uses, so the base ranks every arm identically. When
  the backend omits the score (it is optional on ``MemoryItem``) the hit carries
  ``None`` and the base trusts the editor's list order.
- ``clear`` -> ``remove_items(user_id=scope)``; scrubs one scope only, never resets
  the whole store across trials.

The real ``RedisEditor`` (redis-stack + a local sentence-transformers embedder, no
paid API) is built LAZILY in ``default_nat_client`` so importing this module — and
the whole test suite — needs neither the SDK nor a live Redis. Tests inject a fake.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from membench.memory_systems.async_bridge import AsyncClientBridge, trial_timeout
from membench.memory_systems.semantic_base import (
    DEFAULT_TOP_K,
    AbstractSemanticArm,
    SemanticHit,
    SemanticMemoryClient,
    l2_distance_to_similarity,
)
from membench.schemas.memory_event import MemoryBackend


class _NatItem(Protocol):
    """The slice of ``nat.memory.models.MemoryItem`` the adapter reads off a search
    hit. Declared as a Protocol so the adapter is typed against behaviour, not the
    pydantic model, and the in-test fake stands in without importing nat."""

    memory: str | None
    metadata: dict[str, Any]
    similarity_score: float | None


class _NatEditor(Protocol):
    """The async slice of ``nat.memory.interfaces.MemoryEditor`` the adapter drives.
    A Protocol so the fake editor stands in without the SDK; all three verbs are
    coroutines, run through the bridge."""

    async def add_items(self, items: list[Any]) -> None: ...

    # Returns ``list[Any]`` (not ``list[_NatItem]``) so a stand-in editor returning
    # its own concrete item type satisfies this Protocol — ``list`` is invariant, so a
    # ``list[_NatItem]`` return would reject a structurally-valid fake. The adapter
    # reads the ``_NatItem`` field slice off each hit at the ``query`` call site.
    async def search(self, query: str, top_k: int = 5, **kwargs: Any) -> list[Any]: ...

    async def remove_items(self, **kwargs: Any) -> None: ...


# Builds one ``MemoryItem`` to add. Injected so ``store`` constructs the editor's
# native item type without this module importing nat; the default binds the real
# ``MemoryItem`` lazily, tests bind a fake item dataclass.
_ItemFactory = Callable[..., Any]


def _default_item_factory(*, user_id: str, memory: str, metadata: dict[str, Any]) -> Any:
    """Build a real ``nat.memory.models.MemoryItem``, importing nat LAZILY so this
    module loads without the SDK; only the real (no-arg-default) client reaches here."""
    from nat.memory.models import MemoryItem

    return MemoryItem(user_id=user_id, memory=memory, metadata=metadata)


# The RedisEditor L2 distance → similarity mapping is the shared, validated one
# (mem-lvp.16); aliased so the query() call site and arm tests keep a module-local name.
_similarity = l2_distance_to_similarity


class _NatClient:
    """Adapts NAT's async ``MemoryEditor`` to ``SemanticMemoryClient``. ``scope`` maps
    to NAT's ``user_id``. The async editor is driven through ``bridge`` (one persistent
    loop for the client's lifetime); the bridge is injected so the same seam serves the
    fake and the real RedisEditor."""

    def __init__(
        self,
        editor: _NatEditor,
        bridge: AsyncClientBridge,
        *,
        item_factory: _ItemFactory = _default_item_factory,
    ) -> None:
        self._editor = editor
        self._bridge = bridge
        self._item_factory = item_factory

    def store(self, *, scope: str, content: str, memory_id: str) -> str:
        # MemoryItem has no id field, so mint our own and round-trip it through
        # metadata; the returned id is what retrieval keys its payloads off.
        minted = uuid.uuid4().hex
        item = self._item_factory(user_id=scope, memory=content, metadata={"memory_id": minted})
        self._bridge.run(self._editor.add_items([item]))
        return minted

    def query(self, *, scope: str, query_text: str, top_k: int) -> Sequence[SemanticHit]:
        # Editor returns ``list[Any]`` (invariance, see _NatEditor.search); read each
        # hit as the _NatItem field slice the adapter relies on.
        items: list[_NatItem] = self._bridge.run(
            self._editor.search(query_text, top_k=top_k, user_id=scope)
        )
        return [
            SemanticHit(
                memory_id=item.metadata["memory_id"],
                content=item.memory or "",
                # similarity_score is optional; None means no score, so the base
                # falls back to the editor's list order (Graphiti path).
                score=None if item.similarity_score is None else _similarity(item.similarity_score),
            )
            for item in items
        ]

    def clear(self, *, scope: str) -> None:
        # RedisEditor.remove_items() with no user_id wipes the WHOLE store, so a blank
        # scope would clear-all across trials. Refuse before reaching the editor — a
        # missing scope is a harness bug, not a request to reset every trial (mem-lvp.16).
        if not scope.strip():
            raise ValueError(
                "nat clear requires a non-blank scope (maps to RedisEditor user_id); a "
                "blank scope would clear the whole store, not one trial."
            )
        self._bridge.run(self._editor.remove_items(user_id=scope))

    def close(self) -> None:
        """Tear down the persistent bridge — its event loop and default executor
        (mem-lvp.15). The editor holds no loop; the bridge does, and without this it
        leaks the loop + self-pipe sockets and any RedisEditor ``run_in_executor``
        threads for the process's lifetime. Idempotent (``AsyncClientBridge.close``
        no-ops once closed), so ``NatMemory.close`` is safe to call repeatedly."""
        self._bridge.close()


def default_nat_client() -> SemanticMemoryClient:
    """Build the real RedisEditor-backed client over its own persistent bridge. The
    SDK (``nat.plugins.redis``) is imported HERE, lazily, so the module (and the suite)
    loads without it; the arm depends only on the Protocol. The SaaS-backed mem0ai/zep
    NAT plugins are intentionally excluded — only the self-hostable RedisEditor."""
    from nat.plugins.redis.redis_editor import RedisEditor

    return _NatClient(RedisEditor(), AsyncClientBridge(timeout=trial_timeout()))


class NatMemory(AbstractSemanticArm):
    """NeMo Agent Toolkit arm. Sets identity only; all translation is inherited from
    ``AbstractSemanticArm`` and adaptation lives in ``_NatClient``."""

    name = "nat"
    backend = MemoryBackend.VECTOR_DB

    def __init__(
        self,
        client: SemanticMemoryClient | None = None,
        *,
        top_k: int = DEFAULT_TOP_K,
    ) -> None:
        # Build the real RedisEditor-backed client only when none is injected, so tests
        # and the suite never require the SDK or a live Redis.
        super().__init__(client if client is not None else default_nat_client(), top_k=top_k)
