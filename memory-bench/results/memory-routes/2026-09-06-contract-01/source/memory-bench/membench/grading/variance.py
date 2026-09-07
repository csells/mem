"""Within-task repeat variance + the paired MDE sampling-noise floor (mem-eacq).

Every grid delta reported so far came from single runs — no task has ever run
twice under the same condition, so the within-task run-to-run spread of the
graded signals (``diff_sim`` / ``judge_score`` / ``repro_passed``) has never
been measured. This module is the aggregation layer for the variance pilot and
for the headline runner's ``--repeats`` wiring: sample statistics over a task's
repeats, degrees-of-freedom-weighted pooling across tasks, delta-of-means
between arms, and the paired minimum-detectable-effect floor.

The MDE here is a *sampling-noise lower bound*, deliberately labeled as such:
it models only the within-condition run-to-run variance the pilot can measure.
The task-x-arm interaction (memory helping some tasks and hurting others) is
unmeasurable from same-condition repeats and inflates the true MDE above this
floor — reporting the floor as "the MDE" would overstate the design's power.

ZFC: pure deterministic arithmetic — no semantic judgment, no thresholds.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import fsum, sqrt
from statistics import fmean, stdev

# Same-package reuse of the exact integer-df Student-t quantile (mem-lp24): the
# z-approximation is anti-conservative at grid pool sizes (N = 2-5).
from membench.grading.curve import _t_quantile

DEFAULT_ALPHA = 0.05
DEFAULT_POWER = 0.8


@dataclass(frozen=True)
class MetricStats:
    """One metric's sample statistics over a task's repeats. ``sd`` is the
    sample standard deviation (n-1); None when a single observation carries no
    spread to estimate. ``values`` keeps the raw repeats so nothing is
    silently truncated in the persisted artifact."""

    mean: float
    sd: float | None
    n: int
    values: tuple[float, ...]

    def as_dict(self) -> dict[str, object]:
        return {"mean": self.mean, "sd": self.sd, "n": self.n, "values": list(self.values)}


def within_task_stats(values: Sequence[float]) -> MetricStats:
    """Sample mean / SD over one task's repeats under one condition."""
    n = len(values)
    if n == 0:
        raise ValueError("within_task_stats requires at least one value")
    mean = fmean(values)
    if n < 2:
        return MetricStats(mean=mean, sd=None, n=n, values=tuple(values))
    return MetricStats(mean=mean, sd=stdev(values), n=n, values=tuple(values))


def metric_stats_by_key(
    metric_maps: Sequence[Mapping[str, float | None]],
) -> dict[str, MetricStats]:
    """Per-metric repeat statistics from one task's per-repeat metric vectors
    (`GridConditionResult.metrics()` dicts). A None observation is dropped for
    that key (the signal did not compute on that run — e.g. no repro under a
    fallback toolchain); a key that is None on every repeat is omitted rather
    than fabricated. ``n`` per key records how many repeats actually carried
    the signal, so partial coverage is visible, never silent."""
    if not metric_maps:
        raise ValueError("metric_stats_by_key requires at least one metric map")
    keys = {key for metrics in metric_maps for key in metrics}
    stats: dict[str, MetricStats] = {}
    for key in sorted(keys):
        observed = [value for metrics in metric_maps if (value := metrics.get(key)) is not None]
        if observed:
            stats[key] = within_task_stats(observed)
    return stats


def pooled_within_sd(stats: Sequence[MetricStats]) -> float | None:
    """The degrees-of-freedom-weighted pooled within-task SD across tasks:
    ``sqrt(sum((n_i - 1) * sd_i^2) / sum(n_i - 1))``. Tasks with a single
    observation carry no df and drop out; None when no task has spread to
    pool — surfaced rather than reported as zero noise."""
    contributing = [(s.n - 1, s.sd) for s in stats if s.sd is not None and s.n >= 2]
    if not contributing:
        return None
    df_total = sum(df for df, _ in contributing)
    weighted = fsum(df * sd**2 for df, sd in contributing)
    return sqrt(weighted / df_total)


def delta_of_means(base: MetricStats, treat: MetricStats) -> tuple[float, float | None]:
    """The repeats-collapsed paired delta (treatment mean - baseline mean) and
    its standard error ``sqrt(sd_b^2/n_b + sd_t^2/n_t)``. Arms are independent
    samples — repeats are NOT paired across arms (rep indices are arbitrary),
    so the delta is of means, never of per-rep pairs. SE is None when either
    arm has no measured spread (single repeat)."""
    delta = treat.mean - base.mean
    if base.sd is None or treat.sd is None:
        return delta, None
    return delta, sqrt(base.sd**2 / base.n + treat.sd**2 / treat.n)


def mde_paired_floor(
    sd_within: float,
    *,
    n_tasks: int,
    k_repeats: int,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
) -> float:
    """The sampling-noise LOWER BOUND on the minimum detectable paired delta at
    pool size ``n_tasks`` with ``k_repeats`` runs per arm:

        (t_{1-alpha/2, N-1} + t_{power, N-1}) * sqrt(2/k) * sd_within / sqrt(N)

    Model: each task's delta is a difference of two independent k-repeat arm
    means with common within-condition SD, so Var(delta_task) = 2*sd^2/k; the
    across-task mean divides by N. The task-x-arm interaction term is set to
    zero because same-condition repeats cannot estimate it — the true MDE is
    at least this value. t-quantiles, not z: N-1 df at N = 2-5 is where the
    normal approximation is most anti-conservative (mem-lp24)."""
    if sd_within < 0:
        raise ValueError(f"sd_within must be >= 0, got {sd_within}")
    if n_tasks < 2:
        raise ValueError(f"n_tasks must be >= 2 to test a paired delta, got {n_tasks}")
    if k_repeats < 1:
        raise ValueError(f"k_repeats must be >= 1, got {k_repeats}")
    if not 0.0 < alpha < 1.0 or not 0.0 < power < 1.0:
        raise ValueError(f"alpha and power must be in (0, 1), got {alpha}, {power}")
    df = n_tasks - 1
    multiplier = _t_quantile(1.0 - alpha / 2.0, df) + _t_quantile(power, df)
    return multiplier * sqrt(2.0 / k_repeats) * sd_within / sqrt(n_tasks)
