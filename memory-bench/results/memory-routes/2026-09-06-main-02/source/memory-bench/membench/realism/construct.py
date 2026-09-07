"""Construct validity (axis 3): does a memory arm rank the same on synthetic and
real tasks?

The strongest realism evidence is behavioral: if the memory arms (none / oracle /
a real system) order the same way by performance on the synthetic corpus as on the
real corpus, the synthetic world exercises memory the way real work does. This axis
rank-correlates the two per-arm performance vectors (Spearman rho).

It is the bxhh.5 bridge, and it is N-LIMITED by construction: real measurable arms
are scarce (bxhh.5 was NO-GO at N~8). So this axis is ALWAYS reported with its N and
is NEVER relied on alone — the report (``report.py``) treats it as a veto only when
it *contradicts* (rho strongly negative) on a non-flat, non-N-flagged sample, and
otherwise as corroboration at most.

ZFC: Spearman rho is a transparent, deterministic statistic over numeric samples
(mechanical comparison, ZFC-allowed). Implemented here directly to avoid an
undeclared scipy dependency.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# Below this many shared arms the rank-correlation is reported but flagged as
# too thin to lean on. PLACEHOLDER pending sign-off.
DEFAULT_CONSTRUCT_MIN_N = 5
# A correlation this negative on a non-flat, non-flagged sample is treated as the
# synthetic world ranking arms OPPOSITELY to real — a contradiction. PLACEHOLDER.
DEFAULT_CONTRADICTION_RHO = -0.5


class FlatSampleError(ValueError):
    """A correlation was requested over a sample with zero variance — it is
    genuinely undefined, not 0. A distinct type so callers can catch ONLY this
    (the flat-anchor NO-GO case) without swallowing unrelated ValueErrors."""


def _average_ranks(values: Sequence[float]) -> list[float]:
    """1-based ranks with ties resolved to the average rank of the tied block."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[order[j + 1]] == values[order[i]]:
            j += 1
        average = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = average
        i = j + 1
    return ranks


def _pearson(a: Sequence[float], b: Sequence[float]) -> float:
    n = len(a)
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b, strict=True))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((y - mean_b) ** 2 for y in b)
    if var_a == 0.0 or var_b == 0.0:
        raise FlatSampleError("correlation undefined: a sample has zero variance (flat)")
    return float(cov / (var_a**0.5 * var_b**0.5))


def spearman_rho(a: Sequence[float], b: Sequence[float]) -> float:
    """Spearman rank-correlation of two equal-length samples. Raises on length
    mismatch, fewer than two points, or a flat sample (zero rank variance — the
    correlation is genuinely undefined, not 0)."""
    if len(a) != len(b):
        raise ValueError(f"length mismatch: {len(a)} vs {len(b)}")
    if len(a) < 2:
        raise ValueError("spearman_rho needs at least two points")
    return _pearson(_average_ranks(a), _average_ranks(b))


@dataclass(frozen=True)
class ConstructVerdict:
    """The construct-validity verdict over the shared arms.

    ``rho`` is None when the correlation is undefined (a flat performance vector —
    the bxhh.5 flat-anchor NO-GO case). ``n`` is the number of shared arms;
    ``n_flagged`` marks a sample too thin to lean on. ``contradicts`` is True only
    on a defined, non-flagged, strongly-negative correlation."""

    rho: float | None
    n: int
    n_flagged: bool
    flat: bool
    min_n: int
    contradiction_rho: float
    reason: str

    @property
    def contradicts(self) -> bool:
        # ``<=`` is inclusive: rho exactly at the threshold counts as "at least as
        # negative as the contradiction bar", so it vetoes.
        return (
            self.rho is not None
            and not self.flat
            and not self.n_flagged
            and self.rho <= self.contradiction_rho
        )


def construct_validity(
    synthetic_perf: Sequence[float],
    real_perf: Sequence[float],
    *,
    min_n: int = DEFAULT_CONSTRUCT_MIN_N,
    contradiction_rho: float = DEFAULT_CONTRADICTION_RHO,
) -> ConstructVerdict:
    """Rank-correlate per-arm performance on synthetic vs real, aligned by index.

    The two vectors must be the same length (one entry per shared arm) and have at
    least two arms. A flat vector yields ``rho=None`` + ``flat=True`` (undefined,
    not contradicting); a sample below ``min_n`` is reported but ``n_flagged``."""
    if len(synthetic_perf) != len(real_perf):
        raise ValueError(f"arm-count mismatch: {len(synthetic_perf)} vs {len(real_perf)}")
    n = len(synthetic_perf)
    if n < 2:
        raise ValueError("construct_validity needs at least two shared arms")
    n_flagged = n < min_n
    try:
        rho: float | None = spearman_rho(synthetic_perf, real_perf)
        flat = False
        reason = "rank-correlation computed"
    except FlatSampleError:
        rho = None
        flat = True
        reason = "performance vector is flat — rank-correlation undefined (bxhh.5 NO-GO shape)"
    if n_flagged:
        reason = f"N={n} below min_n={min_n}; reported but not relied on. {reason}"
    return ConstructVerdict(
        rho=rho,
        n=n,
        n_flagged=n_flagged,
        flat=flat,
        min_n=min_n,
        contradiction_rho=contradiction_rho,
        reason=reason,
    )


def construct_validity_from_arms(
    synthetic_perf: Mapping[str, float],
    real_perf: Mapping[str, float],
    *,
    min_n: int = DEFAULT_CONSTRUCT_MIN_N,
    contradiction_rho: float = DEFAULT_CONTRADICTION_RHO,
) -> ConstructVerdict:
    """Convenience: align two arm→performance maps on their SHARED arms (sorted for
    determinism) and rank-correlate. ``performance`` is whatever scalar the caller
    measured per arm (e.g. ``ArmResult.lift``)."""
    shared = sorted(set(synthetic_perf) & set(real_perf))
    if len(shared) < 2:
        raise ValueError(f"need at least two shared arms, got {len(shared)}: {shared}")
    return construct_validity(
        [synthetic_perf[arm] for arm in shared],
        [real_perf[arm] for arm in shared],
        min_n=min_n,
        contradiction_rho=contradiction_rho,
    )
