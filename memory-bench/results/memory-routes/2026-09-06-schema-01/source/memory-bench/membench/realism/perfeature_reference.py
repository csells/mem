"""R-C interim per-feature realism reference (mem-ovi, Stephanie #mem 2026-06-21).

mem-4so2's structural verdict collapsed a STRUCTURAL=FAIL out of a mean-of-7 KS
aggregate (0.939) computed over an UNMATCHED 980-session general corpus. The
aggregate hid which axes actually diverged and was dominated by the disjoint
memory-op features. This module is the "stay-on-a-vector" replacement: it reports
the per-feature distance and DROPS the mean-of-7 aggregate entirely
(``distance.structural_realism`` remains for callers still on the aggregate form,
but the signed-off structural criterion is this per-feature vector).

Two feature groups, reported SEPARATELY and never mixed:

* ``MATCHABLE_FEATURES`` — the axes that are genuinely comparable between a
  synthetic task and a real coding session (step count, tool-call count, tool
  breadth, request-text length). These are the only axes a realism comparison
  should read.
* ``MEMORY_OP_FEATURES`` — memory writes/reads. Real coding sessions emit ZERO
  memory operations until forward-capture (mem-31kz) lands, so these are
  disjoint-by-construction: their KS distance is ~1.0 as a property of the
  corpus, not a realism defect. Reporting them mixed into the matchable group
  would have re-created exactly mem-4so2's aggregate confound, so they are kept
  in a separate dict.

``dependency_depth`` is excluded entirely — it is N/A on the flat real side (a
real session's trace carries no per-message write→read ordering to recover a
dependency chain from) and never enters either group.

There is intentionally NO mean, NO pass/fail aggregate, and NO threshold gate:
thresholds stay PLACEHOLDER and Stephanie owns hardening them. ``worst_matchable``
is exposed only as a diagnosis convenience (the single furthest matchable axis)
and is explicitly non-load-bearing — it composes nothing.

ZFC: this is mechanical distributional comparison (the two-sample KS statistic
reused verbatim from ``distance.ks_statistic``), not a semantic judgment.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from membench.realism.distance import ks_statistic
from membench.realism.features import TaskFeatures

# The axes comparable between a synthetic task and a real coding session.
MATCHABLE_FEATURES: tuple[str, ...] = (
    "n_steps",
    "n_tool_calls",
    "tool_diversity",
    "task_text_length",
)

# Memory writes/reads: disjoint-by-construction (real coding sessions emit 0
# memory ops until forward-capture mem-31kz lands), so they are reported SEPARATELY
# and never folded into the matchable comparison.
MEMORY_OP_FEATURES: tuple[str, ...] = (
    "n_memory_writes",
    "n_memory_reads",
)


def _per_feature_ks(
    synthetic: Sequence[TaskFeatures],
    real: Sequence[TaskFeatures],
    names: tuple[str, ...],
) -> dict[str, float]:
    """Per-feature two-sample KS distance over a fixed set of feature names."""
    return {
        name: ks_statistic(
            [f.value(name) for f in synthetic],
            [f.value(name) for f in real],
        )
        for name in names
    }


@dataclass(frozen=True)
class PerFeatureReference:
    """The R-C interim verdict: per-feature distances, no aggregate, no gate.

    ``matchable`` maps each ``MATCHABLE_FEATURES`` name to its KS distance;
    ``memory_op`` maps each ``MEMORY_OP_FEATURES`` name to its KS distance,
    reported separately (disjoint-by-construction). ``n_synthetic`` / ``n_real``
    are the corpus sizes so a reader can weigh the distances. There is
    deliberately no mean, no ``passes``, and no threshold."""

    matchable: dict[str, float]
    memory_op: dict[str, float]
    n_synthetic: int
    n_real: int

    @property
    def worst_matchable(self) -> tuple[str, float]:
        """Diagnosis convenience (NON-LOAD-BEARING): the single matchable feature
        furthest from real, as ``(name, distance)``. This composes nothing and is
        not a gate — it only points at the first axis to inspect."""
        name = max(self.matchable, key=lambda key: self.matchable[key])
        return name, self.matchable[name]


def per_feature_reference(
    synthetic: Sequence[TaskFeatures],
    real: Sequence[TaskFeatures],
) -> PerFeatureReference:
    """Compute the R-C interim per-feature reference between two corpora.

    Reports the KS distance for every matchable feature and (separately) every
    memory-op feature. Both corpora must be non-empty — mirroring
    ``distance.structural_realism``, an empty corpus raises rather than silently
    reading as identical."""
    if not synthetic or not real:
        raise ValueError("per_feature_reference needs non-empty synthetic and real corpora")
    return PerFeatureReference(
        matchable=_per_feature_ks(synthetic, real, MATCHABLE_FEATURES),
        memory_op=_per_feature_ks(synthetic, real, MEMORY_OP_FEATURES),
        n_synthetic=len(synthetic),
        n_real=len(real),
    )
