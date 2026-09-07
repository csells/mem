"""C1.3 base-rate go/no-go gate — the precondition that protects the .3c headline.

The score-vs-information curve is only a meaningful headline if the held-out
`trace_error` actually recurs at the zero-memory (`none`) rung. If it rarely recurs
even without memory, the deterministic avoid-axis has no dynamic range: every rung
already "resolves" by default, the curve goes flat, and the saturation /
minimum-useful-information readout is destroyed by its own scorer (architect finding
C1 / H1). This gate measures that recurrence base-rate on the `none` rung and emits a
GO / NO_GO / INSUFFICIENT_POWER verdict *before* the curve is trusted.

Three validity defenses make the verdict interpretable:

- **Path-reached denominator (C1).** `deterministic_term` is tri-state: ``None`` when
  the run never reached the held file, ``0.0`` when the failure recurred, ``1.0`` when
  it was avoided. Recurrence is measured over PATH-REACHED tasks only
  (``det is not None``); a run that never engaged the file cannot speak to recurrence
  and must not dilute the denominator. The fraction of tasks the none-rung agent
  actually reached is reported separately as ``path_reach_rate`` — a low value is its
  own kind of weak signal, surfaced rather than hidden.

- **Decide on the lower bound, not the point estimate (H1).** With ≤~23 held-out
  tasks the point estimate is noisy, so the gate compares the **Wilson score-interval
  lower bound** of the recurrence rate against a calibrated threshold. Below a minimum
  applicable-task count the honest answer is INSUFFICIENT_POWER, not a coin-flipped
  GO/NO_GO.

- **One observation per task (M2).** ``k`` repeats of a task collapse to a single
  majority-vote observation before the across-task tally — repeats are within-task,
  not independent tasks, so they must not inflate ``n``.

The gate keys on ``deterministic_term`` ONLY (M3): the OSS judge's ``rubric_score`` is
the semantic-completion axis and is irrelevant to the recurrence dynamic-range
question this gate answers.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from math import sqrt

from membench.grading.trace_score import RewardRecord, deterministic_term

# Two-sided 95% normal quantile — the Wilson interval's z. Named so the confidence
# level is explicit rather than a bare magic number.
Z_95 = 1.959963984540054

# Minimum Wilson-lower-bound recurrence rate for the avoid-axis to have usable
# dynamic range. Rationale (ZFC calibrated-threshold exception, the same class as
# trace_score.relaxed_signature): below ~20% confirmed recurrence the none-rung floor
# is already near-resolved, so memory has almost no headroom to move the reward and
# the curve cannot discriminate rungs. Transparent arithmetic compared against an
# explicit, documented constant — not a hidden semantic judgment.
DEFAULT_MIN_RECURRENCE_LB = 0.20

# Below this many applicable (path-reached) tasks the Wilson interval is too wide to
# support any GO/NO_GO (its half-width at p≈0.5, n=4 already exceeds ±0.4), so the gate
# reports INSUFFICIENT_POWER instead of pretending to decide. mem-lvp §11 synthetic
# fallback is the escalation path when the real held-out set lands here.
DEFAULT_MIN_APPLICABLE = 5


class GateDecision(Enum):
    """The base-rate gate's three outcomes. INSUFFICIENT_POWER is a first-class state,
    not a NO_GO: too little data to decide is categorically different from a confident
    "the floor is already solved"."""

    GO = "go"
    NO_GO = "no_go"
    INSUFFICIENT_POWER = "insufficient_power"


@dataclass(frozen=True)
class GateVerdict:
    """The base-rate gate's full readout. Carries the decision and every number behind
    it so a NO_GO / INSUFFICIENT_POWER can be understood (and a synthetic-fallback
    decision made) without re-running the gate."""

    decision: GateDecision
    recurrence_rate: float  # point estimate over applicable tasks
    recurrence_lower_bound: float  # Wilson lower bound — what the decision keys on
    n_applicable: int  # tasks whose majority of repeats reached the path
    n_recurred: int  # applicable tasks whose failure recurred (majority vote)
    path_reach_rate: float  # n_applicable / n_tasks — reported, never folded in (C1)
    n_tasks: int  # distinct none-rung tasks observed
    threshold: float  # the min recurrence lower bound for GO
    min_applicable: int  # the INSUFFICIENT_POWER cutoff
    reason: str


def _wilson_lower_bound(k: int, n: int, z: float) -> float:
    """Lower bound of the Wilson score interval for ``k`` successes in ``n`` trials.

    Closed-form, dependency-free, and well-behaved at the extremes (exactly 0.0 at
    ``k == 0``), unlike the normal approximation which can go negative. The lower bound
    is clamped to ``≥ 0.0`` for floating-point safety at the boundary; it cannot exceed
    1.0 (``center - half`` is always below 1.0), so no upper clamp is needed."""
    if n == 0:
        return 0.0
    phat = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (phat + z2 / (2 * n)) / denom
    half = (z / denom) * sqrt(phat * (1.0 - phat) / n + z2 / (4 * n * n))
    return max(0.0, center - half)


def _task_observation(dets: list[float | None]) -> tuple[bool, bool]:
    """Collapse one task's per-repeat deterministic terms to (applicable, recurred).

    A task is APPLICABLE if a majority of its repeats reached the held file
    (``det is not None``); ties break toward applicable (lean to include the data
    point). Among the reached repeats, the task RECURRED if a majority have
    ``det == 0.0``; ties break toward recurred (conservative — assume the failure can
    recur). ``recurred`` is meaningless (and returned False) when not applicable.

    ``d == 0.0`` is an exact comparison against a literal: ``deterministic_term``
    returns the literals ``0.0`` / ``1.0`` / ``None``, never a computed float, so the
    equality is safe (it would NOT be if that term were ever arithmetic)."""
    total = len(dets)
    reached = [d for d in dets if d is not None]
    applicable = len(reached) * 2 >= total  # tie -> applicable
    if not applicable:
        return False, False
    recurred_count = sum(1 for d in reached if d == 0.0)
    recurred = recurred_count * 2 >= len(reached)  # tie -> recurred
    return True, recurred


def base_rate_gate(
    records: Sequence[RewardRecord],
    *,
    rung: str = "none",
    threshold: float = DEFAULT_MIN_RECURRENCE_LB,
    min_applicable: int = DEFAULT_MIN_APPLICABLE,
    z: float = Z_95,
) -> GateVerdict:
    """Run the C1.3 base-rate go/no-go gate over one rung's reward records.

    Defaults to the ``none`` rung — the zero-memory floor whose recurrence answers the
    dynamic-range question. Repeats collapse within task (majority vote) before the
    across-task tally; the recurrence rate is over path-reached tasks only and the
    decision keys on its Wilson lower bound. An empty input (or no records for the
    requested rung) is a caller error: the gate cannot speak to a rung it never saw."""
    if not records:
        raise ValueError("base_rate_gate needs at least one reward record")

    by_task: dict[str, list[float | None]] = defaultdict(list)
    for record in records:
        if record.rung != rung:
            continue
        by_task[record.work_id].append(deterministic_term(record.components))

    if not by_task:
        raise ValueError(f"no reward records for rung {rung!r}")

    n_tasks = len(by_task)
    n_applicable = 0
    n_recurred = 0
    for dets in by_task.values():
        applicable, recurred = _task_observation(dets)
        if applicable:
            n_applicable += 1
            if recurred:
                n_recurred += 1

    recurrence_rate = n_recurred / n_applicable if n_applicable else 0.0
    recurrence_lb = _wilson_lower_bound(n_recurred, n_applicable, z)
    path_reach_rate = n_applicable / n_tasks

    if n_applicable < min_applicable:
        decision = GateDecision.INSUFFICIENT_POWER
        reason = (
            f"only {n_applicable} of {n_tasks} {rung}-rung tasks reached the held path "
            f"(need ≥{min_applicable}); the Wilson interval is too wide to decide — "
            f"escalate to the synthetic-fallback set (mem-lvp §11)"
        )
    elif recurrence_lb >= threshold:
        decision = GateDecision.GO
        reason = (
            f"recurrence lower bound {recurrence_lb:.3f} ≥ {threshold:.2f} over "
            f"{n_applicable} applicable tasks — the avoid-axis has usable dynamic range"
        )
    else:
        decision = GateDecision.NO_GO
        reason = (
            f"recurrence lower bound {recurrence_lb:.3f} < {threshold:.2f} "
            f"(point estimate {recurrence_rate:.3f}) over {n_applicable} applicable "
            f"tasks — the none-rung floor is already near-resolved, so the curve "
            f"cannot discriminate rungs"
        )

    return GateVerdict(
        decision=decision,
        recurrence_rate=recurrence_rate,
        recurrence_lower_bound=recurrence_lb,
        n_applicable=n_applicable,
        n_recurred=n_recurred,
        path_reach_rate=path_reach_rate,
        n_tasks=n_tasks,
        threshold=threshold,
        min_applicable=min_applicable,
        reason=reason,
    )
