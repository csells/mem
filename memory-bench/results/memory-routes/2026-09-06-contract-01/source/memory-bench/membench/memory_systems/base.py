"""The uniform memory-system (arm) interface.

The harness drives every system identically: it owns the record set, the scope,
the LOO boundary, and telemetry; the system only implements `retrieve` and
`write` and reports each as a normalized `MemoryEvent` (§6.2). This is the same
uniform-arm contract promoted as ARCHITECTURE.md Decision 11, and the seam the
competitive arms (a-mem / mem0 / graphiti / nat, mem-lvp) plug into later without
re-touching it.

`retrieve` takes a single `RetrievalRequest` so one signature serves both arm
families:

- **id-based reference arms** (`oracle`, `filesystem`) use `query_text` +
  `requested_ids` — exact-by-id recovery over what earlier steps wrote.
- **failure-triggered arms** (`ours`, and the competitive arms) use `query_work`
  + `scope` — retrieval over the work-audit graph under the harness-owned LOO
  boundary (Decision 6/8). The harness, not the arm, fixes the boundary; the
  arm's output is re-checked against it (`validity.assert_no_leak`).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from membench.runtime import StepContext
from membench.schemas.memory_event import MemoryBackend, MemoryEvent
from membench.validity import QueryWork

# The Decision-7 retrieval track, named identically to the retrieval-v1 surface.
RetrievalScope = str  # "cross_rig" | "same_rig_temporal"


def validate_top_k(top_k: int) -> None:
    """Enforce the retrieval-width floor every top-k-bounded arm shares
    (``LexicalTopKMemory``, ``AbstractSemanticArm``) — the single home for a check
    that was previously byte-duplicated across three call sites (mem-03acq)."""
    if top_k < 1:
        raise ValueError(f"top_k must be >= 1, got {top_k}")


@dataclass(frozen=True)
class RetrievalRequest:
    """What the harness hands an arm to retrieve (one shape for both families).

    `requested_ids` is also the *relevant set* the harness scores against, so an
    id-based arm returning a superset (distractors) or subset (misses) is what
    makes precision/recall meaningful.
    """

    query_text: str | None = None
    requested_ids: list[str] = field(default_factory=list)
    # Failure-triggered / replay context (Decision 6/8). None on the id path.
    query_work: QueryWork | None = None
    scope: RetrievalScope | None = None


@dataclass
class RetrieveResult:
    """What a retrieve call returns: the recovered payloads + the normalized event.

    `total_matched` / `near_duplicate_top` / `fts_truncated` carry the
    retrieval-v1 precision-guard signal (Decision 10) through to the report; they
    stay at their defaults for arms that don't rank (oracle/filesystem return
    exactly what was asked). `fts_truncated` means the substrate's FTS candidate
    scan hit its cap, so the message-tier ranking may be incomplete — silent
    truncation is exactly what the guard exists to surface."""

    payloads: dict[str, str]  # memory_id → content (id arms) / work_id → lesson (ours)
    event: MemoryEvent
    # Reserved arm self-report seam: an arm MAY declare which returned ids it believes are
    # distractors. The harness does NOT score this — Confusion/Staleness are scored against
    # the AUTHORED ground truth on the step (``distractor_memories`` / ``superseded_memory_ids``,
    # mem-zt1c), never an arm's self-assessment — so it stays default-empty and unconsumed.
    distractor_ids: list[str] = field(default_factory=list)
    total_matched: int = 0
    near_duplicate_top: bool = False
    fts_truncated: bool = False
    # Reversibility/provenance contract (M7): for a CONSOLIDATING arm, each returned
    # item maps to the source trace ids it was derived from, so the provenance gate
    # can dereference the citation chain. Default-empty: id-based / semantic arms
    # return raw rows with no derivation, so they cite nothing (an honest absence,
    # never a fabricated provenance).
    source_trace_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)


class MemorySystem(ABC):
    """Uniform interface implemented by every reference / competitive arm."""

    name: str
    backend: MemoryBackend
    supports_write: bool = True
    # Whether retrieval depends on the Decision-7 track (cross_rig vs
    # same_rig_temporal). Failure-triggered arms set this; the replay runner then
    # evaluates them under both tracks (D7 dual-track). Id-based arms leave it
    # False and run once.
    uses_scope: bool = False

    @abstractmethod
    def reset(self, trial_id: str) -> None:
        """Clear all state for a fresh trial (per condition run)."""

    @abstractmethod
    def retrieve(self, request: RetrievalRequest, ctx: StepContext) -> RetrieveResult:
        """Return the payloads this arm can recover for `request`."""

    @abstractmethod
    def write(self, memory_id: str, content: str, ctx: StepContext) -> MemoryEvent:
        """Persist a memory; returns the normalized write event."""

    def seed(self, memories: dict[str, str], ctx: StepContext) -> None:
        """Inject pre-existing WORLD memories (distractor / interference noise) into the
        store WITHOUT emitting telemetry — these model environment state the harness owns,
        not agent-persisted writes, so they must never count toward efficiency or retention
        (mem-zt1c). The default writes each via ``write`` and DISCARDS the returned events;
        callers pass a dedicated clock so seeding does not perturb the step's own event ids.
        An arm that cannot hold extra state (``oracle`` is ``load``-injected, ``none`` is
        stateless) short-circuits via ``supports_write`` and stays a no-op. An arm that sets
        ``supports_write = True`` but overrides ``write`` to raise MUST also override this to
        avoid raising during harness seeding."""
        if not self.supports_write:
            return
        for memory_id, content in memories.items():
            self.write(memory_id, content, ctx)

    def close(self) -> None:  # noqa: B027 (intentional no-op hook, NOT abstract)
        """Release any process-lifetime resources the arm holds — event loops,
        executor threads, connection pools. No-op by default; an arm that holds a
        live resource (e.g. NAT/Graphiti's ``AsyncClientBridge`` loop, mem-lvp.15)
        overrides this. The harness calls it once per arm at end of run, so it must
        be idempotent: a double close (harness + a test fixture) is safe."""
