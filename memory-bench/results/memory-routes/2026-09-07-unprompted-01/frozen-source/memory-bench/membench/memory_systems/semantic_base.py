"""AbstractSemanticArm — the shared base for embedding/semantic competitive arms.

The competitive systems (mem0 / NAT / A-MEM / Graphiti, mem-lvp.2-.4) are all the
same translation against this harness: ``write`` -> the backend's ``add``,
``retrieve`` over ``request.query_text`` -> the backend's ``search(query, top_k)``,
``reset`` -> the backend's clear. The concrete vector/LLM client is INJECTED behind
``SemanticMemoryClient``, so the arm wiring, event normalization, and payload
shaping are testable against a deterministic fake with no network and no model —
the scix no-paid-API contract holds in CI, and the real (local-model) client plugs
in behind the same seam when the infra (mem-lvp.5) lands.

A concrete arm only sets ``name`` + ``backend`` and is registered in
``build_memory_system``; it adds no retrieval logic of its own. The harness owns the
leave-one-out boundary and re-checks every arm's output with
``validity.assert_no_leak`` — that stays the runner's job, so this base is a pure
translation layer (mirrors ``OursMemory``). See docs/competitive-arms-integration.md.
"""

import math
from abc import ABC
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from membench.memory_systems.base import (
    MemorySystem,
    RetrievalRequest,
    RetrieveResult,
    validate_top_k,
)
from membench.runtime import StepContext
from membench.schemas.memory_event import MemoryBackend, MemoryEvent, MemoryOperation

DEFAULT_TOP_K = 10


def l2_distance_to_similarity(distance: float) -> float:
    """Map an L2/Euclidean distance (finite, >= 0, lower = closer) to a higher-is-better
    similarity in (0, 1] via ``1 / (1 + d)``. Monotone-decreasing in the distance, so
    the base's best-first ordering matches the backend's nearest-first ordering. Shared
    by the NAT (RedisEditor) and A-MEM (ChromaDB) arms — both expose an L2 distance.

    A real distance is finite and non-negative; a misbehaving backend that returns a
    negative, NaN, or infinite value would otherwise corrupt scores silently — ``d=-1``
    raises ZeroDivisionError, ``d<-1`` yields an out-of-range/negative similarity, and a
    NaN propagates through every downstream score. Validate so the backend fails loud
    rather than poisoning the benchmark (mem-lvp.16)."""
    if not math.isfinite(distance) or distance < 0:
        raise ValueError(
            f"L2 distance must be finite and >= 0, got {distance!r}; a negative/NaN/inf "
            "distance means the backend misbehaved."
        )
    return 1.0 / (1.0 + distance)


@dataclass(frozen=True)
class SemanticHit:
    """One normalized search hit. ``memory_id`` is the backend-assigned id (what
    ``store`` returned), ``content`` is the text to surface, and ``score`` is the
    relevance **normalized higher = better**, or ``None`` when the backend exposes
    no per-hit score (Graphiti) — in which case the base trusts the client's list
    order. The client owns the normalization (cosine, L2-distance→similarity, …),
    so the base builds every arm's result identically."""

    memory_id: str
    content: str
    score: float | None = None


@runtime_checkable
class ClosableClient(Protocol):
    """A ``SemanticMemoryClient`` that owns a process-lifetime resource — an
    ``AsyncClientBridge`` event loop, a connection pool — and must be torn down
    (mem-lvp.15). Kept SEPARATE from ``SemanticMemoryClient`` so the seam stays at
    ``store``/``query``/``clear`` (the §5b no-widening rule): only the clients that
    actually hold a resource (NAT, Graphiti) implement it; the in-memory fakes and
    stateless clients (mem0/A-MEM) don't, and the arm skips closing them."""

    def close(self) -> None:
        """Release the held resource. Idempotent."""


@runtime_checkable
class SemanticMemoryClient(Protocol):
    """The minimal seam a competitive memory backend must expose — three verbs over
    a normalized item shape. Each arm adapts its native SDK to this (mem0
    ``add``/``search``/``delete_all``, NAT ``MemoryEditor`` ``add_items``/``search``/
    ``remove_items``, Graphiti ``add_episode``/``search``, A-MEM
    ``add_note``/``search``); tests inject a deterministic fake.

    ``scope`` is the per-trial isolation key (``ctx.trial_id``); each client maps it
    to its native key (mem0 ``user_id``, NAT ``user_id``, Graphiti ``group_id``,
    A-MEM per-trial collection). The Protocol is **sync**: an async-native backend
    holds a persistent event loop inside its concrete client (mem-lvp.5a
    ``AsyncClientBridge``) rather than forcing the seam — and the fakes — async.
    Backend-specific concerns (infer-mode, metadata round-trip, episode type, score
    normalization) live INSIDE the concrete client, never in the Protocol."""

    def store(self, *, scope: str, content: str, memory_id: str) -> str:
        """Persist one memory under ``scope``; return the **backend-assigned id**
        (mem0/A-MEM/Graphiti mint their own and ignore ``memory_id``, which the
        client round-trips via metadata/a side map). The returned id is what
        retrieval keys its payloads off."""

    def query(self, *, scope: str, query_text: str, top_k: int) -> Sequence[SemanticHit]:
        """Return at most ``top_k`` normalized hits for ``scope``, ranked best-first;
        the arm does no re-ranking, so determinism is the client's responsibility."""

    def clear(self, *, scope: str) -> None:
        """Reset one ``scope`` only; idempotent, never touches other scopes."""


class AbstractSemanticArm(MemorySystem, ABC):
    """Translates the uniform ``MemorySystem`` contract onto an injected
    ``SemanticMemoryClient``, scoping every call by ``ctx.trial_id``. Subclasses set
    ``name`` + ``backend`` only and add no retrieval logic."""

    name: str = "semantic"
    backend: MemoryBackend = MemoryBackend.VECTOR_DB
    # query_text/top_k semantic path — not the Decision-7 dual-track scope.
    uses_scope = False

    def __init__(self, client: SemanticMemoryClient, *, top_k: int = DEFAULT_TOP_K) -> None:
        validate_top_k(top_k)
        self._client = client
        self._top_k = top_k
        # Trial ids this arm has scoped, to assert global uniqueness (mem-lvp.12).
        self._seen_trial_ids: set[str] = set()

    def close(self) -> None:
        # Tear down the injected client when it holds a process-lifetime resource
        # (mem-lvp.15): NAT and Graphiti wrap an AsyncClientBridge loop, so closing
        # the arm closes the loop. mem0/A-MEM and the test fakes hold nothing and are
        # skipped. Delegates to bridge.close(), which is itself idempotent.
        if isinstance(self._client, ClosableClient):
            self._client.close()

    def reset(self, trial_id: str) -> None:
        # ``trial_id`` is the backend isolation scope (``user_id``/``group_id``/
        # collection). Two distinct trials sharing an id would write the same scope and
        # silently cross-contaminate, which no backend filter can undo — so a reused id
        # is a harness bug, caught here rather than corrupting the comparison.
        if trial_id in self._seen_trial_ids:
            raise ValueError(
                f"{self.name!r}: trial_id {trial_id!r} was already used in this run; "
                "trial ids must be globally unique (mem-lvp.12 isolation)."
            )
        self._seen_trial_ids.add(trial_id)
        self._client.clear(scope=trial_id)

    def retrieve(self, request: RetrievalRequest, ctx: StepContext) -> RetrieveResult:
        query = request.query_text
        if query is None:
            raise ValueError(
                f"{self.name!r} is a semantic arm: it needs request.query_text (the "
                "query/failure string). It does not serve the failure-triggered "
                "query_work path that `ours` uses."
            )
        hits = list(self._client.query(scope=ctx.trial_id, query_text=query, top_k=self._top_k))
        # Insertion order = the client's rank order; dict dedupes by id (vector
        # stores key uniquely, so a collision would be a backend bug, not silent loss).
        payloads = {hit.memory_id: hit.content for hit in hits}
        event = MemoryEvent(
            event_id=ctx.clock.event_id(),
            trial_id=ctx.trial_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            timestamp=ctx.clock.timestamp(),
            concrete_tool=f"{self.name}.search(top_k={self._top_k})",
            normalized_operation=MemoryOperation.SEARCH,
            backend=self.backend,
            query=query,
            retrieved_ids=list(payloads),
            latency_ms=ctx.clock.latency_ms(),
            success=True,
        )
        # total_matched is the injected count: a vector top_k arm has no FTS-style
        # uncapped candidate set, so near_duplicate_top / fts_truncated stay default.
        return RetrieveResult(payloads=payloads, event=event, total_matched=len(hits))

    def write(self, memory_id: str, content: str, ctx: StepContext) -> MemoryEvent:
        backend_id = self._client.store(scope=ctx.trial_id, content=content, memory_id=memory_id)
        return MemoryEvent(
            event_id=ctx.clock.event_id(),
            trial_id=ctx.trial_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            timestamp=ctx.clock.timestamp(),
            concrete_tool=f"{self.name}.add",
            normalized_operation=MemoryOperation.WRITE,
            backend=self.backend,
            # requested id vs the id the backend actually assigned (they differ for
            # mem0/A-MEM/Graphiti, which mint their own).
            target_ids=[memory_id],
            written_ids=[backend_id],
            latency_ms=ctx.clock.latency_ms(),
            success=True,
        )
