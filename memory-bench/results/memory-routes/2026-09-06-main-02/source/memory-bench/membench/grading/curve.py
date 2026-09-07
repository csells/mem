"""Score-vs-information curve — the .3c headline artifact.

Aggregates per-rung ``combined_reward`` across the held-out set into the curve the
mem-apg headline is read off (ARCHITECTURE.md D17). Pure deterministic aggregation
(ZFC): grouping, arithmetic means, a Student-t confidence interval, and a seeded
paired bootstrap for the delta readouts — no semantic judgment.

The design is fully paired (every rung replays the same tasks), so the delta
readouts (``floor_lift_ci`` / ``ceiling_gap_ci``) are inferred per task via the
shared ``paired_ci`` helper on an explicitly labeled population: ``itt`` (all
admitted tasks, an empty-retrieval task contributing delta 0) is the pre-registered
primary; the retrieval-fired ``matched`` set is the mechanism-conditional secondary
(mem-lp24).

**What the reward readouts support today (architect H2).** With the combinatorial
rungs (`builtin`, `ours+builtin`) deferred to mem-whi, the name-based delta readouts
report what the ``none``/``ours``/``oracle`` points genuinely support:

- ``floor_lift`` — how far ``ours`` lifts reward above the zero-memory ``none`` floor.
- ``ceiling_gap`` — how far ``ours`` still trails the ``oracle`` ceiling.

``saturation_point`` and ``min_useful_combo`` are the D17 readouts that need the full
ladder; they REFUSE (raise ``InsufficientLadderError``) below four rungs rather than
fabricate a vacuous "saturation at the only interior rung". They were designed for the
mem-whi *combination* axis and become meaningful once the builtin rungs land.

**Recall ladder (mem-do8r / mem-do8r.2, RESOLVED).** The ``vector-rag`` rung is
runnable (``harbor.memory_inject.RUNNABLE_RUNGS``) and sits between ``none`` and ``ours``
in ``DEFAULT_RUNGS`` (canonical order ``none < vector-rag < ours ≤ oracle``), so
``_ladder_order`` places it correctly. A 4-rung RECALL ladder varies the recall policy, a
different axis from the ``saturation_point`` / ``min_useful_combo`` COMBINATION readouts,
and reading a combination number over a recall sweep is a category error. So
``_require_full_ladder`` gates on the COMBINATION AXIS, not on rung count: it requires both
a combination rung (``builtin`` / ``ours+builtin``) AND the ``ours`` base rung
(``ablation.COMBINATION_BASE_RUNG``) that combination layers onto -- ``builtin`` with no
``ours`` baseline has no reference point for "does layering add reward?". A
``(none, vector-rag, builtin, oracle)`` ladder therefore REFUSES despite reaching four
rungs and carrying a combination rung (mem-do8r.2 / Codex F1). We GUARD the recall axis
(option b) rather than define new recall-saturation semantics (option a), per KISS/YAGNI.

``floor_lift`` / ``ceiling_gap`` stay name-based: ``floor_lift`` keeps the ``none``
(zero-memory) floor as its baseline -- re-baselining to ``vector-rag`` would silently
redefine the pre-registered D17 headline (``ours`` minus ``none``). ``ceiling_gap`` stays
``oracle`` minus ``ours`` (None until both rungs are present). The ``vector-rag`` -> ``ours``
interior recall delta stays reachable through the generic ``paired_delta`` escape hatch
instead of a named property.

Repeats collapse within task (architect M2) before the across-task mean + CI: ``k``
repeats of a task are correlated, not independent observations, so each task
contributes one mean-reward value to its rung's sample.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import atan, cos, fsum, pi, sin, sqrt

from membench.grading.ablation import COMBINATION_BASE_RUNG, COMBINATION_RUNGS, DEFAULT_RUNGS
from membench.grading.paired_ci import (
    POPULATION_PRIMARY,
    PairedDeltaCI,
    Population,
    paired_delta_ci,
)
from membench.grading.trace_score import RewardRecord

# Below four rungs the curve has no interior resolution, so the saturation /
# minimum-useful-combination readouts cannot be computed (architect H2).
MIN_LADDER_FOR_SATURATION = 4

# Reward-scale tolerance for "stopped improving" / "reached the ceiling". A
# calibrated-threshold ZFC exception (transparent arithmetic against a documented
# constant): two rungs within 5% of the [0, 1] reward scale are treated as
# indistinguishable for the saturation/min-useful readouts.
DEFAULT_SATURATION_TOL = 0.05

# Absolute slack on the tolerance comparison so a reward difference that is exactly
# DEFAULT_SATURATION_TOL is not excluded by IEEE-754 rounding (e.g. 0.55 - 0.5
# evaluates to 0.0500000000000000444). Tiny relative to the 0.05 tolerance.
_TOL_EPS = 1e-9


@dataclass(frozen=True)
class RungReward:
    """One rung's aggregate reward over the held-out set. ``lower_bound`` /
    ``upper_bound`` are the Student-t CI clamped to ``[0, 1]``; for a single task
    they collapse to the mean (no across-task spread to estimate)."""

    rung: str
    mean_reward: float
    lower_bound: float
    upper_bound: float
    n_tasks: int


@dataclass(frozen=True)
class ScoreInformationCurve:
    """The per-rung reward curve in ladder order. ``floor_lift`` and ``ceiling_gap``
    are the two readouts the 3-rung ladder supports; both are ``None`` when the
    rung they need is absent (a partial run), surfaced rather than guessed.

    ``task_rewards`` carries the per-task means the aggregates were formed from
    (rung → work_id → task mean reward, repeats collapsed) so the paired-delta
    readouts (``floor_lift_ci`` / ``ceiling_gap_ci``) can be inferred on the paired
    design instead of shipped as bare point estimates (mem-lp24)."""

    rungs: tuple[RungReward, ...]
    task_rewards: Mapping[str, Mapping[str, float]] = field(default_factory=dict)

    def rung(self, name: str) -> RungReward | None:
        """The aggregate for ``name``, or None if that rung is not in the curve."""
        for r in self.rungs:
            if r.rung == name:
                return r
        return None

    @property
    def floor_lift(self) -> float | None:
        """``ours`` mean minus ``none`` mean — the lift our memory buys over zero
        memory. None unless both rungs are present."""
        none, ours = self.rung("none"), self.rung("ours")
        if none is None or ours is None:
            return None
        return ours.mean_reward - none.mean_reward

    @property
    def ceiling_gap(self) -> float | None:
        """``oracle`` mean minus ``ours`` mean — how far our memory still trails the
        oracle ceiling. None unless both rungs are present."""
        ours, oracle = self.rung("ours"), self.rung("oracle")
        if ours is None or oracle is None:
            return None
        return oracle.mean_reward - ours.mean_reward

    def paired_delta(
        self,
        baseline: str,
        treatment: str,
        *,
        population: Population = POPULATION_PRIMARY,
        n_resamples: int = 5000,
        conf: float = 0.95,
        seed: int = 0,
    ) -> PairedDeltaCI | None:
        """The per-task paired delta (``treatment`` - ``baseline``) with its
        seeded bootstrap CI, on the explicitly labeled population (``itt`` is the
        pre-registered primary; ``matched`` the mechanism-conditional secondary).
        None when either rung is absent from the per-task data — surfaced rather
        than guessed, mirroring ``floor_lift`` / ``ceiling_gap``."""
        base = self.task_rewards.get(baseline)
        treat = self.task_rewards.get(treatment)
        if not base or not treat:
            return None
        return paired_delta_ci(
            base, treat, population=population, n_resamples=n_resamples, conf=conf, seed=seed
        )

    def floor_lift_ci(
        self,
        *,
        population: Population = POPULATION_PRIMARY,
        n_resamples: int = 5000,
        conf: float = 0.95,
        seed: int = 0,
    ) -> PairedDeltaCI | None:
        """``floor_lift`` as a paired per-task delta (``ours`` - ``none``) + CI."""
        return self.paired_delta(
            "none", "ours", population=population, n_resamples=n_resamples, conf=conf, seed=seed
        )

    def ceiling_gap_ci(
        self,
        *,
        population: Population = POPULATION_PRIMARY,
        n_resamples: int = 5000,
        conf: float = 0.95,
        seed: int = 0,
    ) -> PairedDeltaCI | None:
        """``ceiling_gap`` as a paired per-task delta (``oracle`` - ``ours``) + CI."""
        return self.paired_delta(
            "ours", "oracle", population=population, n_resamples=n_resamples, conf=conf, seed=seed
        )


class InsufficientLadderError(Exception):
    """Raised when a readout needs more rungs than the curve has (architect H2):
    saturation / minimum-useful-combination require the full ladder, not the live
    3-rung subset."""


def _t_cdf(t: float, df: int) -> float:
    """Student-t CDF for integer ``df``, via the exact closed-form finite sums
    (Abramowitz & Stegun 26.7.3 / 26.7.4) — pure ``math``, no scipy. Exact for the
    integer degrees of freedom a task sample always has."""
    theta = atan(t / sqrt(df))
    c, s = cos(theta), sin(theta)
    if df % 2 == 1:
        acc = term = c if df > 1 else 0.0
        for j in range(2, df - 1, 2):
            term *= j / (j + 1) * c * c
            acc += term
        return 0.5 + (theta + s * acc) / pi
    acc = term = 1.0
    for j in range(1, df - 1, 2):
        term *= j / (j + 1) * c * c
        acc += term
    return 0.5 + s * acc / 2.0


def _t_quantile(p: float, df: int) -> float:
    """The upper Student-t quantile: the ``t ≥ 0`` with ``CDF(t) = p`` for
    ``p ∈ [0.5, 1)``, by bisection on the exact CDF. Deterministic arithmetic."""
    lo, hi = 0.0, 2.0
    while _t_cdf(hi, df) < p:
        hi *= 2.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if _t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _mean_ci(values: list[float], conf: float) -> tuple[float, float, float]:
    """Mean and Student-t CI of ``values``, clamped to ``[0, 1]``.

    A single value has no across-task variance to interval, so its bounds collapse
    to the mean. The interval is mean ± t_{n-1}·sem — the normal-z approximation the
    module used to emit was anti-conservative at held-out-set sizes (z = 1.96 where
    n = 9 wants t₈ = 2.306; mem-lp24). Still scipy-free: the t quantile comes from
    the exact integer-df CDF above."""
    n = len(values)
    if n == 0:
        # build_curve never calls this with an empty rung, but make the invariant
        # explicit so a future refactor can't reach a ZeroDivisionError here.
        raise ValueError("_mean_ci requires at least one value")
    mean = fsum(values) / n
    if n < 2:
        return mean, mean, mean
    variance = fsum((x - mean) ** 2 for x in values) / (n - 1)
    sem = sqrt(variance / n)
    half = _t_quantile(0.5 + conf / 2.0, n - 1) * sem
    return mean, max(0.0, mean - half), min(1.0, mean + half)


def _validate_explicit_rungs(rungs: Sequence[str]) -> None:
    """Reject an explicit ``rungs=`` that is not a duplicate-free subsequence of
    ``DEFAULT_RUNGS`` in canonical order.

    ``saturation_point`` and ``min_useful_combo`` read rung order verbatim off
    ``_ladder_order``, and ``_require_full_ladder`` gates on the raw slot count, so a
    duplicated ladder fakes extra rungs and a reordered one flips both readouts to
    whichever rung is listed first — pure artifacts. The production caller auto-detects
    (no ``rungs=``); an explicit non-canonical ladder is a caller error surfaced loudly
    rather than silently canonicalized (mem-rvu6)."""
    given = set(rungs)
    canonical = [r for r in DEFAULT_RUNGS if r in given]
    if list(rungs) != canonical:
        unknown = sorted(given - set(DEFAULT_RUNGS))
        detail = f"; unknown rung(s) {unknown!r}" if unknown else ""
        raise ValueError(
            f"rungs={tuple(rungs)!r} must be a duplicate-free subsequence of the canonical "
            f"ladder {DEFAULT_RUNGS!r}, in that order (the saturation / min-useful-combo "
            f"readouts are order-sensitive){detail}; canonical form is {tuple(canonical)!r}"
        )


def _ladder_order(present: set[str], rungs: Sequence[str] | None) -> list[str]:
    """The rungs to report, in order. Explicit ``rungs`` are honored (restricted to
    those with data); auto-detect falls back to canonical ladder order with any
    non-canonical rungs appended deterministically (sorted), so the order is never
    LLM- or dict-iteration-dependent."""
    if rungs is not None:
        return [r for r in rungs if r in present]
    canonical = [r for r in DEFAULT_RUNGS if r in present]
    extra = sorted(present - set(DEFAULT_RUNGS))
    return canonical + extra


def build_curve(
    records: Sequence[RewardRecord],
    *,
    rungs: Sequence[str] | None = None,
    conf: float = 0.95,
) -> ScoreInformationCurve:
    """Build the score-vs-information curve from reward records across rungs.

    Per-rung value = mean over tasks of each task's mean ``combined_reward`` (repeats
    collapsed within task first, M2). Rung order follows the canonical ladder unless
    ``rungs`` is given. An empty input is a caller error — there is no curve to build
    from no observations; likewise a ``rungs`` filter that selects nothing present."""
    if not records:
        raise ValueError("build_curve needs at least one reward record")
    if not 0.0 < conf < 1.0:
        raise ValueError(f"conf must be in (0, 1), got {conf}")
    if rungs is not None:
        _validate_explicit_rungs(rungs)

    # (rung, work_id) -> the task's per-repeat rewards.
    by_task: dict[tuple[str, str], list[float]] = defaultdict(list)
    present: set[str] = set()
    for record in records:
        by_task[(record.rung, record.work_id)].append(record.reward)
        present.add(record.rung)

    # rung -> work_id -> the task's mean reward (repeats collapsed). Kept per task
    # (not flattened) so the paired-delta readouts can pair across rungs.
    task_means: dict[str, dict[str, float]] = defaultdict(dict)
    for (rung, work_id), rewards in by_task.items():
        task_means[rung][work_id] = fsum(rewards) / len(rewards)

    order = _ladder_order(present, rungs)
    if not order:
        # An explicit rungs= filter that matches nothing present would otherwise
        # return an empty curve silently (silent_fallbacks) — fail loudly instead.
        raise ValueError(f"rungs filter {rungs!r} selected no rungs present in records")

    built: list[RungReward] = []
    for rung in order:
        values = list(task_means[rung].values())
        mean, lower, upper = _mean_ci(values, conf)
        built.append(
            RungReward(
                rung=rung,
                mean_reward=mean,
                lower_bound=lower,
                upper_bound=upper,
                n_tasks=len(values),
            )
        )
    return ScoreInformationCurve(
        rungs=tuple(built), task_rewards={rung: task_means[rung] for rung in order}
    )


def _require_full_ladder(curve: ScoreInformationCurve) -> None:
    # Axis gate, not a raw count: require >=4 rungs, a combination rung, AND the
    # `ours` base rung it layers onto. A recall-only or ours-absent ladder refuses
    # (rationale: the "Recall ladder" note in the module docstring; the raised
    # message below spells out the missing prerequisite to the caller).
    present = {r.rung for r in curve.rungs}
    if (
        len(curve.rungs) < MIN_LADDER_FOR_SATURATION
        or present.isdisjoint(COMBINATION_RUNGS)
        or COMBINATION_BASE_RUNG not in present
    ):
        raise InsufficientLadderError(
            f"need ≥{MIN_LADDER_FOR_SATURATION} rungs including the `{COMBINATION_BASE_RUNG}` "
            f"base rung and a combination rung ({' / '.join(sorted(COMBINATION_RUNGS))}, mem-whi) "
            f"to read this off; have {[r.rung for r in curve.rungs]}. A recall-only ladder has no "
            f"combination axis, and a combination rung with no `{COMBINATION_BASE_RUNG}` baseline "
            f"has nothing to measure lift against (mem-do8r.2)."
        )


def saturation_point(
    curve: ScoreInformationCurve, *, tol: float = DEFAULT_SATURATION_TOL
) -> RungReward:
    """The earliest rung past which more information stops adding reward (within
    ``tol``) — i.e. no later rung's mean exceeds this rung's mean by more than ``tol``.
    The last rung trivially qualifies, so a value is always returned. Refuses below the
    full ladder (architect H2)."""
    _require_full_ladder(curve)
    rungs = curve.rungs
    for i, rung in enumerate(rungs):
        if all(later.mean_reward - rung.mean_reward <= tol + _TOL_EPS for later in rungs[i + 1 :]):
            return rung
    return rungs[-1]  # unreachable: rungs[-1] satisfies the predicate vacuously (all([]))


def min_useful_combo(
    curve: ScoreInformationCurve, *, tol: float = DEFAULT_SATURATION_TOL
) -> RungReward:
    """The cheapest (earliest-on-the-ladder) rung whose mean reward reaches the curve's
    ceiling within ``tol`` — the minimum information that buys essentially the best
    score. Refuses below the full ladder (architect H2)."""
    _require_full_ladder(curve)
    ceiling = max(r.mean_reward for r in curve.rungs)
    for rung in curve.rungs:
        if ceiling - rung.mean_reward <= tol + _TOL_EPS:
            return rung
    return curve.rungs[-1]  # unreachable: the ceiling rung itself always qualifies
