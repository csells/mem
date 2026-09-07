"""``RetentionScheduledMemory`` — the scheduled-disposition arm (S3).

The disposition-oracle sibling of the S1 consolidation arm. The hot path is cheap:
``write`` appends a version and a record carries a *class* assigned at write; all
disposition work is deferred to an offline ``consolidate()`` sweep that applies a
deterministic class→disposition policy. The sweep IS the ``ConsolidationCapable``
pass, so the arm is reachable from the sequence runner exactly like the
consolidation arm.

Lifecycle (a record advances ``active`` → ``tombstoned`` → ``archived``):

* ``permanent`` / ``review`` — stay live.
* ``destroy`` — soft-tombstone: removed from the live working set but content
  retained and re-derivable, so ``restore`` brings it back. Reversible.
* ``archive`` — move to cold storage and cross the IRREVERSIBILITY boundary:
  ``restore`` raises. The content is still reachable for audit, but the disposition
  is one-way.

Two overrides ride above the class policy:

* **legal-hold / PIN** — a held record is pinned live; the sweep never destroys or
  archives it regardless of class (``place_hold`` / the ``legal_hold`` class which
  auto-holds).
* **unknown class** — a class the policy does not recognise is RETAINED (kept live),
  never destroyed: the schedule never silently disposes of what it cannot classify.

There is no hard-delete primitive — ``tombstone`` (soft) is the only subtractive op,
and even an archive keeps the content row (a source-scan test enforces it). That is
the M7 reversibility invariant the wrongful_destruction gate scores against: a
must-keep record absent from BOTH the live set AND the recoverable set is a
wrongful destruction, and that is exactly what an archive of a misclassified
must-keep record produces.
"""

from __future__ import annotations

from membench.memory_systems.base import MemorySystem, RetrievalRequest, RetrieveResult
from membench.memory_systems.consolidation import ConsolidationResult
from membench.runtime import StepContext
from membench.schemas.memory_event import MemoryBackend, MemoryEvent, MemoryOperation

# The retention schedule: class → the disposition it prescribes. The single source of
# truth for both the arm's sweep and the generator's ground-truth oracle (which
# re-exports this), so the two can never silently drift apart.
RETENTION_POLICY: dict[str, str] = {
    "permanent": "permanent",  # keep live indefinitely
    "needs_review": "review",  # keep live, flagged for human review
    "cold": "archive",  # move to cold storage (irreversible)
    "expired": "destroy",  # soft-tombstone (reversible until archived)
    "legal_hold": "permanent",  # pinned live regardless of age (auto-holds)
}

# A class the policy does not recognise is retained, never destroyed (conservative
# default — the schedule never disposes of what it cannot classify).
UNKNOWN_DISPOSITION = "permanent"

# The dispositions that keep a record in the LIVE working set. The scorer reuses this
# to derive the must-stay-live (void-eligible) oracle set, so the arm and the gate
# agree on what "must remain live" means.
LIVE_DISPOSITIONS = frozenset({"permanent", "review"})
_HOLD_CLASS = "legal_hold"


class RetentionScheduledMemory(MemorySystem):
    """Scheduled-retention arm. Satisfies ``ConsolidationCapable`` structurally
    (``consolidate`` is the sweep, ``tombstone`` the soft-delete) without widening
    the ``MemorySystem`` ABC."""

    name = "retention_scheduled"
    backend = MemoryBackend.FILESYSTEM
    supports_write = True

    def __init__(self, *, policy: dict[str, str] | None = None) -> None:
        self._policy = dict(policy) if policy is not None else dict(RETENTION_POLICY)
        self._reset_state()

    def _reset_state(self) -> None:
        # Per-trial reset (the sanctioned clear(scope), M7) — reassigns, never a
        # per-item hard delete. _store holds the latest content; _versions is the
        # append-only version table; _state is the lifecycle marker.
        self._store: dict[str, str] = {}
        self._order: list[str] = []
        self._versions: dict[str, list[str]] = {}
        self._class: dict[str, str | None] = {}
        self._state: dict[str, str] = {}
        self._held: set[str] = set()
        self._applied: dict[str, str] = {}

    def reset(self, trial_id: str) -> None:
        self._reset_state()

    # -- classification + hot-path write ---------------------------------- #
    def assign_class(self, memory_id: str, record_class: str | None) -> None:
        """Assign a record's retention class (the sweep's input). A ``legal_hold``
        class auto-holds, so the override travels with the class."""
        self._class[memory_id] = record_class
        if record_class == _HOLD_CLASS:
            self.place_hold(memory_id)

    def place_hold(self, memory_id: str) -> None:
        """Legal-hold / PIN: pin a record live through the sweep."""
        self._held.add(memory_id)

    def release_hold(self, memory_id: str) -> None:
        self._held.discard(memory_id)

    def write(self, memory_id: str, content: str, ctx: StepContext) -> MemoryEvent:
        if memory_id not in self._store:
            self._order.append(memory_id)
            self._versions[memory_id] = []
            self._class.setdefault(memory_id, None)
            self._state[memory_id] = "active"
        self._versions[memory_id].append(content)
        self._store[memory_id] = content
        return MemoryEvent(
            event_id=ctx.clock.event_id(),
            trial_id=ctx.trial_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            timestamp=ctx.clock.timestamp(),
            concrete_tool=f"{self.name}.classify_write",
            normalized_operation=MemoryOperation.WRITE,
            backend=self.backend,
            written_ids=[memory_id],
            latency_ms=ctx.clock.latency_ms(),
            success=True,
        )

    # -- offline sweep (the consolidate() pass) --------------------------- #
    def _disposition_for(self, memory_id: str) -> str:
        """The sweep's decision: a held record is pinned ``permanent``; otherwise the
        class policy decides, with an unrecognised class retained (never destroyed)."""
        if memory_id in self._held:
            return "permanent"
        record_class = self._class.get(memory_id)
        if record_class is None:
            return UNKNOWN_DISPOSITION
        return self._policy.get(record_class, UNKNOWN_DISPOSITION)

    def consolidate(self, ctx: StepContext) -> ConsolidationResult:
        tombstoned: list[str] = []
        archived: list[str] = []
        for mid in self._order:
            if self._state.get(mid) != "active":
                continue
            disp = self._disposition_for(mid)
            self._applied[mid] = disp
            if disp in LIVE_DISPOSITIONS:
                continue
            if disp == "destroy":
                self.tombstone(mid)
                tombstoned.append(mid)
            elif disp == "archive":
                self._state[mid] = "archived"
                archived.append(mid)
        return ConsolidationResult(
            items=(),  # retention disposes; it does not synthesise schema rows
            tombstoned_ids=tuple(tombstoned),
            background_tokens=0,
            notes={
                "mode": "retention-sweep",
                "tombstoned": str(len(tombstoned)),
                "archived": str(len(archived)),
            },
        )

    def tombstone(self, memory_id: str) -> None:
        # Soft delete: out of the live working set, content retained and recoverable.
        self._state[memory_id] = "tombstoned"

    def restore(self, memory_id: str) -> None:
        """Reverse a tombstone (reversible-until-archived). Raises past the archive
        boundary — that one-way move is the point the gate treats as destruction."""
        state = self._state.get(memory_id)
        if state == "archived":
            raise ValueError(
                f"cannot restore {memory_id!r}: archived (past the reversibility boundary)"
            )
        if state == "tombstoned":
            self._state[memory_id] = "active"

    # -- state readouts (for the scorer + the gate) ----------------------- #
    def state_of(self, memory_id: str) -> str:
        return self._state[memory_id]

    def versions(self, memory_id: str) -> tuple[str, ...]:
        return tuple(self._versions.get(memory_id, ()))

    def applied_disposition(self, memory_id: str) -> str | None:
        return self._applied.get(memory_id)

    def live_ids(self) -> tuple[str, ...]:
        return tuple(mid for mid in self._order if self._state.get(mid) == "active")

    def recoverable_ids(self) -> tuple[str, ...]:
        # Every tombstone is reversible until archived, so the tombstoned set IS the
        # recoverable (provenance-bearing) set the gate counts as "not destroyed".
        return tuple(mid for mid in self._order if self._state.get(mid) == "tombstoned")

    def archived_ids(self) -> tuple[str, ...]:
        return tuple(mid for mid in self._order if self._state.get(mid) == "archived")

    def is_live(self, trace_id: str) -> bool:
        """Reachability oracle (M7): a trace is live iff its content is still present.
        Tombstoned and archived rows keep their content for audit, so both count;
        a never-written id does not."""
        return trace_id in self._store

    # -- retrieval -------------------------------------------------------- #
    def retrieve(self, request: RetrievalRequest, ctx: StepContext) -> RetrieveResult:
        payloads: dict[str, str] = {}
        provenance: dict[str, tuple[str, ...]] = {}
        for rid in request.requested_ids:
            if self._state.get(rid) == "active":
                payloads[rid] = self._store[rid]
                provenance[rid] = (rid,)
        event = MemoryEvent(
            event_id=ctx.clock.event_id(),
            trial_id=ctx.trial_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            timestamp=ctx.clock.timestamp(),
            concrete_tool=f"{self.name}.retrieve",
            normalized_operation=MemoryOperation.SEARCH,
            backend=self.backend,
            query=request.query_text,
            retrieved_ids=list(payloads),
            latency_ms=ctx.clock.latency_ms(),
            success=True,
        )
        return RetrieveResult(payloads=payloads, event=event, source_trace_ids=provenance)
