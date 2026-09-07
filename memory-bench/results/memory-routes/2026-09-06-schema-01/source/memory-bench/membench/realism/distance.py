"""Structural realism (axis 1): distributional distance between two task corpora.

Given the feature vectors of a synthetic corpus and a real reference corpus, the
structural axis reports — PER FEATURE — how far apart the two distributions are,
plus an aggregate distance. Each feature's distance is the two-sample
Kolmogorov-Smirnov statistic: the maximum gap between the two empirical CDFs, a
parameter-free number in ``[0, 1]`` (0 = identical distributions, 1 = disjoint
supports). Lower is more realistic.

ZFC: this is mechanical distributional comparison (an explicit, transparent
statistic over numeric samples), not a semantic "does this look real" judgment —
that is axis 2 (``semantic.py``). The KS statistic is implemented here directly
rather than pulled from scipy because scipy is not a declared dependency of this
package; the two-sample KS is small and exact, so there is no reason to hide it
behind an undeclared import.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from membench.realism.features import FEATURE_NAMES, TaskFeatures

# Default ceiling on the aggregate structural distance for the corpus to count as
# structurally realistic. PLACEHOLDER pending Stephanie's #mem sign-off on the
# realism criterion — the framework is robust to retuning this; it is a threshold,
# not an architectural choice.
DEFAULT_MAX_STRUCTURAL_DISTANCE = 0.30


def ks_statistic(a: Sequence[float], b: Sequence[float]) -> float:
    """Two-sample Kolmogorov-Smirnov statistic: the max gap between the empirical
    CDFs of ``a`` and ``b``. Both samples must be non-empty — a distance over an
    empty sample is undefined and raises rather than silently returning 0 (which
    would read as 'identical' and hide a missing corpus)."""
    if not a or not b:
        raise ValueError("ks_statistic needs two non-empty samples")
    grid = sorted(set(a) | set(b))
    na, nb = len(a), len(b)
    sorted_a, sorted_b = sorted(a), sorted(b)

    def _cdf(sorted_vals: list[float], x: float, n: int) -> float:
        # Fraction of values <= x. Linear scan over the merged grid is ample for
        # the corpus sizes here (tens to low thousands of tasks).
        count = 0
        for v in sorted_vals:
            if v <= x:
                count += 1
            else:
                break
        return count / n

    return max(abs(_cdf(sorted_a, x, na) - _cdf(sorted_b, x, nb)) for x in grid)


@dataclass(frozen=True)
class StructuralReport:
    """The structural axis verdict: per-feature distances + an aggregate.

    ``per_feature`` maps each feature name to its KS distance; ``aggregate`` is
    the mean across features (reported alongside, never instead of, the raw
    vector). ``passes`` is the aggregate against ``max_distance`` — a tunable
    gate, not a hidden composite."""

    per_feature: dict[str, float]
    aggregate: float
    max_distance: float

    @property
    def passes(self) -> bool:
        return self.aggregate <= self.max_distance

    @property
    def worst_feature(self) -> str:
        """The single feature whose distribution is furthest from real — the
        first thing to inspect when the aggregate is high."""
        return max(self.per_feature, key=lambda name: self.per_feature[name])


def structural_realism(
    synthetic: Sequence[TaskFeatures],
    real: Sequence[TaskFeatures],
    *,
    max_distance: float = DEFAULT_MAX_STRUCTURAL_DISTANCE,
) -> StructuralReport:
    """Compare the structural feature distributions of a synthetic corpus against
    a real reference corpus, one feature at a time.

    Both corpora must be non-empty. The result reports the KS distance for every
    feature in ``FEATURE_NAMES`` plus their mean, so a corpus that matches on most
    shapes but diverges on one (e.g. far fewer tool calls) is visibly diagnosed
    rather than averaged into a passing aggregate."""
    if not synthetic or not real:
        raise ValueError("structural_realism needs non-empty synthetic and real corpora")
    per_feature = {
        name: ks_statistic(
            [f.value(name) for f in synthetic],
            [f.value(name) for f in real],
        )
        for name in FEATURE_NAMES
    }
    aggregate = sum(per_feature.values()) / len(per_feature)
    return StructuralReport(per_feature=per_feature, aggregate=aggregate, max_distance=max_distance)
