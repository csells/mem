"""Replay-bead eval path (Decision 5) — failure-triggered arms over the
work-audit graph, under the harness-owned LOO guard.

This is distinct from the convention-sequence runner (`runner/conditions.py`).
There the eval object is a multi-session sequence with id-based memory; here it is
a closed historical bead `B`:

- the retrievable corpus is bounded to records closed strictly before `B.started`
  (`validity.loo_bounded`) — the V1 leakage guard, owned by the harness, applied
  before any arm runs and re-checked on every arm's output (`assert_no_leak`);
- arms are failure-triggered (`ours` = retrieval-v1); the `none` arm is the
  baseline;
- both Decision-7 tracks are evaluated for scope-using arms (cross_rig +
  same_rig_temporal), reported separately;
- the merged-PR/CI outcome is the oracle for `B` — never a label the arm sees, so
  it is not part of this retrieval-side path (it scores the agent re-run on the
  paid Harbor path).

The deterministic skeleton measures the retrieval-side instruments (what the arm
returned, the Decision-10 injected-context volume + near-duplicate guard, latency)
and the LOO validity invariant. The agent-dependent task outcome is the Harbor
path and is left to that path, consistent with the rest of the skeleton.
"""

from dataclasses import dataclass, field

from membench.memory_systems.base import MemorySystem, RetrievalRequest
from membench.runtime import IdClock, StepContext
from membench.schemas.memory_event import MemoryEvent
from membench.validity import QueryWork, WorkRef, assert_no_leak, loo_bounded

# The Decision-7 tracks, evaluated for any scope-using arm.
TRACKS: tuple[str, ...] = ("cross_rig", "same_rig_temporal")


@dataclass(frozen=True)
class ArmReplayResult:
    """One arm's retrieval over one query work under one track."""

    arm: str
    work_id: str
    scope: str | None
    retrieved_ids: list[str]
    total_matched: int
    near_duplicate_top: bool
    # The substrate's FTS candidate scan hit its cap — the message-tier ranking
    # may be incomplete. Surfaced per Decision 10: truncation is never silent.
    fts_truncated: bool
    # Decision-10 precision guard: the volume of injected memory text. Outcome
    # lift alone is gameable by over-injection, so this is reported, not optional.
    injected_context_chars: int
    latency_ms: float
    event: MemoryEvent
    # How many LOO-eligible records existed — the denominator behind any later
    # precision/recall, surfaced so an empty result is distinguishable from an
    # empty corpus.
    eligible_count: int


@dataclass(frozen=True)
class ReplayRun:
    work_id: str
    rig: str
    eligible_count: int
    results: list[ArmReplayResult] = field(default_factory=list)


def _scopes_for(arm: MemorySystem) -> tuple[str | None, ...]:
    return TRACKS if arm.uses_scope else (None,)


def replay_arm(
    arm: MemorySystem,
    query: QueryWork,
    corpus: list[WorkRef],
    *,
    scope: str | None,
    clock: IdClock | None = None,
) -> ArmReplayResult:
    """Run one arm for `query` under `scope`, then audit its output against the
    harness LOO set. A leak raises (`LeakageError`) — never silently filtered."""
    clock = clock or IdClock()
    ctx = StepContext(
        trial_id=f"{query.work_id}-{arm.name}-{scope or 'noscope'}",
        session_id=query.work_id,
        step_id="replay",
        clock=clock,
    )
    arm.reset(ctx.trial_id)
    request = RetrievalRequest(query_work=query, scope=scope)
    result = arm.retrieve(request, ctx)

    # Harness-owned validity re-check: the substrate's D6 must agree with ours.
    assert_no_leak(result.payloads.keys(), corpus, query)

    eligible = loo_bounded(corpus, query)
    return ArmReplayResult(
        arm=arm.name,
        work_id=query.work_id,
        scope=scope,
        retrieved_ids=list(result.payloads),
        total_matched=result.total_matched,
        near_duplicate_top=result.near_duplicate_top,
        fts_truncated=result.fts_truncated,
        injected_context_chars=sum(len(v) for v in result.payloads.values()),
        latency_ms=result.event.latency_ms,
        event=result.event,
        eligible_count=len(eligible),
    )


def run_replay(
    query: QueryWork,
    corpus: list[WorkRef],
    arms: list[MemorySystem],
) -> ReplayRun:
    """Replay `query` across every arm (and, for scope-using arms, both D7 tracks)
    under the LOO guard. Computing the eligible set once also fails fast if the
    boundary itself is malformed, before any arm runs."""
    eligible = loo_bounded(corpus, query)
    results = [
        replay_arm(arm, query, corpus, scope=scope) for arm in arms for scope in _scopes_for(arm)
    ]
    return ReplayRun(
        work_id=query.work_id,
        rig=query.rig,
        eligible_count=len(eligible),
        results=results,
    )
