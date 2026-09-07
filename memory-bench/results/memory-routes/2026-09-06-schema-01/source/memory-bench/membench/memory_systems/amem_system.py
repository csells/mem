"""`a-mem` — the A-MEM competitive arm (mem-lvp.9).

A-MEM (``agentic_memory.AgenticMemorySystem``) is an LLM-augmented vector store:
each note is embedded into ChromaDB and linked to related notes via a local LLM.
Against this harness it is the same translation as every semantic arm — ``write``
-> ``add_note``, ``retrieve`` -> ``search``, ``reset`` -> drop the scope — so the
arm itself only sets ``name`` + ``backend`` and inherits ``AbstractSemanticArm``.

The backend specifics live in ``_AMemClient``:

- A-MEM mints its own UUID per note and ignores any caller id, so the adapter
  keeps a per-scope ``{memory_id: minted_id}`` side map and returns the minted id
  (which retrieval then keys its payloads off).
- ``search`` returns ChromaDB hits whose score is an L2 **distance** (lower =
  closer); the adapter normalizes it to a higher-is-better similarity so the base
  ranks every arm identically.
- Per-scope (per-trial) isolation is modelled the way the real reset works —
  rebuild the instance with a fresh ``collection_name`` and empty ``memories`` —
  but the adapter holds one native instance per scope so ``clear(scope)`` wipes
  only that scope.

The real ``AgenticMemorySystem`` (ChromaDB embedded + sentence-transformers +
Ollama LLM) is built LAZILY inside the default factory, so this module imports
with no SDK installed and the suite stays green under the no-paid-API contract.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol, cast

from membench.memory_systems.local_stack import LocalModelStack
from membench.memory_systems.semantic_base import (
    DEFAULT_TOP_K,
    AbstractSemanticArm,
    SemanticHit,
    l2_distance_to_similarity,
)
from membench.schemas.memory_event import MemoryBackend

# Keys A-MEM/ChromaDB use on a search hit. ``score`` is the L2 distance; A-MEM has
# historically also surfaced it as ``distance``, so accept either, lower = closer.
_DISTANCE_KEYS = ("score", "distance")


class _AMemNative(Protocol):
    """The slice of ``agentic_memory.AgenticMemorySystem`` the adapter drives. A
    fresh instance owns one ChromaDB collection; A-MEM mints the note id."""

    def add_note(self, content: str, **kwargs: Any) -> str: ...

    def search(self, query: str, k: int) -> list[dict[str, Any]]: ...


# Builds one fresh native instance for a given scope (per-trial collection). The
# default factory binds the real SDK constructor; tests bind a fake.
_NativeFactory = Callable[[str], _AMemNative]


def _distance(hit: dict[str, Any]) -> float:
    for key in _DISTANCE_KEYS:
        if key in hit:
            return float(hit[key])
    raise KeyError(
        f"A-MEM search hit has no distance field (expected one of {_DISTANCE_KEYS}); "
        f"got keys {sorted(hit)}."
    )


# The ChromaDB L2 distance → similarity mapping is the shared, validated one
# (mem-lvp.16); aliased so the query() call site and arm tests keep a module-local name.
_similarity = l2_distance_to_similarity


class _AMemClient:
    """Adapts ``agentic_memory.AgenticMemorySystem`` to ``SemanticMemoryClient``.

    Holds one native instance per scope (per trial) so ``clear`` can wipe a single
    scope without touching others, and keeps a ``{memory_id: minted_id}`` side map
    per scope because A-MEM ignores the caller's id and mints its own UUID."""

    def __init__(self, native_factory: _NativeFactory) -> None:
        self._native_factory = native_factory
        self._scopes: dict[str, _AMemNative] = {}
        # scope -> {requested memory_id: A-MEM-minted id}
        self._minted: dict[str, dict[str, str]] = {}

    def _instance(self, scope: str) -> _AMemNative:
        native = self._scopes.get(scope)
        if native is None:
            native = self._native_factory(scope)
            self._scopes[scope] = native
            self._minted[scope] = {}
        return native

    def store(self, *, scope: str, content: str, memory_id: str) -> str:
        minted = self._instance(scope).add_note(content)
        self._minted[scope][memory_id] = minted
        return minted

    def query(self, *, scope: str, query_text: str, top_k: int) -> Sequence[SemanticHit]:
        native = self._scopes.get(scope)
        if native is None:
            return []
        hits = native.search(query_text, top_k)
        return [
            SemanticHit(
                memory_id=hit["id"],
                content=hit["content"],
                score=_similarity(_distance(hit)),
            )
            for hit in hits
        ]

    def clear(self, *, scope: str) -> None:
        # Drop this scope's native instance + side map; the next store rebuilds a
        # fresh per-trial collection (the real reset semantics), leaving every other
        # scope untouched.
        self._scopes.pop(scope, None)
        self._minted.pop(scope, None)


def build_amem_kwargs(scope: str, *, stack: LocalModelStack | None = None) -> dict[str, Any]:
    """The ``AgenticMemorySystem`` constructor kwargs for one per-trial collection,
    pinned to the shared local stack. ``llm_backend="ollama"`` is the load-bearing
    field: A-MEM defaults ``llm_backend="openai"``, so omitting it (the pre-mem-lvp.5
    behaviour) silently routed ingest through a PAID OpenAI call — violating the scix
    no-paid-API constraint. ``model_name`` is the bundled sentence-transformers
    embedder and ``llm_model`` the local chat model, both from the shared stack so the
    V2 confound pin matches every other arm."""
    stack = stack or LocalModelStack.from_env()
    return {
        "collection_name": f"membench_{scope}",
        "memories": {},
        "model_name": stack.sentence_transformer_model,
        "llm_backend": "ollama",
        "llm_model": stack.chat_model,
    }


def _default_native_factory(stack: LocalModelStack | None = None) -> _NativeFactory:
    """Bind the real A-MEM SDK, imported LAZILY so this module loads without it.

    Each scope gets its own ``AgenticMemorySystem`` with a per-trial
    ``collection_name`` and an empty ``memories`` map (ChromaDB embedded +
    sentence-transformers + a local Ollama LLM — all local, no paid API), with the
    model identity pinned by the shared ``LocalModelStack``."""

    # Imported lazily (not at module top level) so the suite is green with no SDK.
    from agentic_memory import AgenticMemorySystem

    resolved = stack or LocalModelStack.from_env()

    def build(scope: str) -> _AMemNative:
        # The A-MEM SDK ships no types, so its constructor is Any; cast to the
        # structural Protocol the arm relies on (the SDK is the override-ignored import).
        return cast(_AMemNative, AgenticMemorySystem(**build_amem_kwargs(scope, stack=resolved)))

    return build


class AMemMemory(AbstractSemanticArm):
    """A-MEM arm. Sets identity only; all translation is inherited."""

    name = "a-mem"
    backend = MemoryBackend.VECTOR_DB

    def __init__(
        self,
        client: _AMemClient | None = None,
        *,
        top_k: int = DEFAULT_TOP_K,
    ) -> None:
        # Build the real SDK-backed client only when none is injected, so tests and
        # the suite never require the (local-model) SDK to be installed.
        super().__init__(client or _AMemClient(_default_native_factory()), top_k=top_k)
