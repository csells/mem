"""Shared paired-delta inference for the grading stack (mem-lp24).

The grid designs are fully paired — every rung replays the same held-out tasks —
so deltas are formed per task and summarized with the paired percentile bootstrap
that already backs the handoff-efficiency metrics
(``membench.handoff_efficiency.bootstrap_median_ci``, reused here rather than
duplicated).

Two populations, always explicitly labeled (never a silent choice):

- ``itt`` (intention-to-treat, the pre-registered PRIMARY): every task admitted to
  either rung contributes a delta; a task missing one rung's observation — e.g. the
  ``ours`` rung fired no retrieval, so the arm degenerates to its counterpart —
  contributes delta 0 rather than silently dropping out. Stable as the corpus grows.
- ``matched`` (per-protocol, the labeled SECONDARY): only tasks observed on BOTH
  rungs. Mechanism-conditional — its selection function (e.g. lesson coverage)
  moves as the corpus grows, so successive reads are different populations.

ZFC: pure mechanism — arithmetic plus seeded resampling, no semantic judgment.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from membench.handoff_efficiency import bootstrap_median_ci

Population = Literal["itt", "matched"]

POPULATION_PRIMARY: Population = "itt"


@dataclass(frozen=True)
class PairedDeltaCI:
    """A paired delta (treatment - baseline) with its bootstrap CI and the
    population it was read on. ``n_pairs`` counts every delta entering the
    bootstrap; ``n_imputed_zero`` says how many were ITT zero-imputations
    (always 0 for ``matched``)."""

    delta: float
    ci_low: float
    ci_high: float
    n_pairs: int
    n_imputed_zero: int
    population: Population


def paired_deltas(
    baseline: Mapping[str, float],
    treatment: Mapping[str, float],
    *,
    population: Population,
) -> tuple[list[float], int]:
    """Per-task deltas (treatment - baseline) in sorted task order (a deterministic
    bootstrap input). Returns the deltas and the count of ITT zero-imputations —
    tasks observed on only one rung, whose delta is pinned to 0 under ``itt`` and
    dropped under ``matched``."""
    if population == "matched":
        keys = sorted(baseline.keys() & treatment.keys())
        return [treatment[k] - baseline[k] for k in keys], 0
    deltas: list[float] = []
    imputed = 0
    for key in sorted(baseline.keys() | treatment.keys()):
        if key in baseline and key in treatment:
            deltas.append(treatment[key] - baseline[key])
        else:
            deltas.append(0.0)
            imputed += 1
    return deltas, imputed


def paired_delta_ci(
    baseline: Mapping[str, float],
    treatment: Mapping[str, float],
    *,
    population: Population = POPULATION_PRIMARY,
    n_resamples: int = 5000,
    conf: float = 0.95,
    seed: int = 0,
) -> PairedDeltaCI:
    """The paired median delta + percentile-bootstrap CI on the labeled population.

    An empty population is a caller error — there is nothing to infer from — so it
    raises rather than fabricating a degenerate interval."""
    deltas, imputed = paired_deltas(baseline, treatment, population=population)
    if not deltas:
        raise ValueError(f"paired_delta_ci: no tasks in the {population!r} population")
    point, lo, hi = bootstrap_median_ci(deltas, n_resamples=n_resamples, conf=conf, seed=seed)
    return PairedDeltaCI(
        delta=point,
        ci_low=lo,
        ci_high=hi,
        n_pairs=len(deltas),
        n_imputed_zero=imputed,
        population=population,
    )
