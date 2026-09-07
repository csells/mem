"""The realism metric (mem-ovi): three axes, reported SEPARATELY.

A synthetic eval corpus is judged on three independent axes, each surfaced on its
own — there is no opaque composite scalar (per ZFC + the §4.2 raw-vector style):

1. STRUCTURAL  (``distance.py``)  — mechanical distributional match of task shapes.
2. SEMANTIC    (``semantic.py``)  — a model judge rating per task + aggregate.
3. CONSTRUCT   (``construct.py``) — rank-correlation of arm performance, N-flagged.

The corpus is "DEFENSIBLE" when structural AND semantic both hold and construct
does not CONTRADICT (construct is allowed to be N-flagged or absent — it is the
N-limited bxhh.5 bridge and is never relied on alone). The boolean is a
transparent AND over the per-axis gates, each of which is reported next to it; it
never collapses the three numbers into one score.

Per mem-ovi policy: building this framework is the deliverable. Any realism
NUMBERS computed over the actual corpora are HELD/gated (publication freeze);
``assess_realism`` is the gated entry point and is exercised in tests only with
synthetic tasks + a stub judge.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from membench.bbon.comparative_judge import ComparativeJudge
from membench.realism.construct import (
    DEFAULT_CONSTRUCT_MIN_N,
    DEFAULT_CONTRADICTION_RHO,
    ConstructVerdict,
    construct_validity_from_arms,
)
from membench.realism.distance import StructuralReport, structural_realism
from membench.realism.features import TaskFeatures, features_from_sequence
from membench.realism.semantic import (
    SemanticAggregate,
    SemanticVerdict,
    aggregate_semantic,
    score_semantic_realism,
)
from membench.schemas.sequence import BenchmarkSequence


@dataclass(frozen=True)
class PerTaskRealism:
    """The per-task slice of the report: the task's structural features and its
    own semantic verdict. (Structural distance and construct validity are
    corpus-level by nature — a single task has no distribution to compare.)"""

    task_id: str
    features: TaskFeatures
    semantic: SemanticVerdict


@dataclass(frozen=True)
class RealismReport:
    """The full realism verdict: per-task slices + the three corpus-level axes.

    ``construct`` is None when no real arm-performance was supplied (the bridge is
    optional and N-limited). ``defensible`` ANDs the structural and semantic gates
    and requires construct not to contradict."""

    per_task: tuple[PerTaskRealism, ...]
    structural: StructuralReport
    semantic: SemanticAggregate
    construct: ConstructVerdict | None

    @property
    def defensible(self) -> bool:
        construct_ok = self.construct is None or not self.construct.contradicts
        return self.structural.passes and self.semantic.passes and construct_ok

    @property
    def verdict_reason(self) -> str:
        parts = [
            f"structural {'PASS' if self.structural.passes else 'FAIL'} "
            f"(aggregate={self.structural.aggregate:.3f} <= {self.structural.max_distance:.3f}; "
            f"worst={self.structural.worst_feature})",
            f"semantic {'PASS' if self.semantic.passes else 'FAIL'} "
            f"(mean_realism={self.semantic.mean_realism:.3f}, "
            f"real_fraction={self.semantic.real_fraction:.3f}, n={self.semantic.n})",
        ]
        if self.construct is None:
            parts.append("construct N/A (no real arm performance supplied)")
        else:
            rho = "undefined" if self.construct.rho is None else f"{self.construct.rho:.3f}"
            parts.append(
                f"construct {'CONTRADICTS' if self.construct.contradicts else 'ok'} "
                f"(rho={rho}, n={self.construct.n}, flagged={self.construct.n_flagged})"
            )
        return "; ".join(parts)


def assess_realism(
    synthetic: Sequence[BenchmarkSequence],
    real_features: Sequence[TaskFeatures],
    judge: ComparativeJudge,
    *,
    synthetic_arm_perf: Mapping[str, float] | None = None,
    real_arm_perf: Mapping[str, float] | None = None,
    construct_min_n: int = DEFAULT_CONSTRUCT_MIN_N,
    construct_contradiction_rho: float = DEFAULT_CONTRADICTION_RHO,
) -> RealismReport:
    """Assess a synthetic corpus against a real reference, on all three axes.

    GATED: running this over the actual corpora produces held realism numbers.
    Tests drive it with synthetic sequences + a ``StubComparativeJudge``.

    Structural compares ``synthetic``'s extracted features to ``real_features``.
    Semantic scores every synthetic task with ``judge``. Construct is computed only
    when BOTH ``synthetic_arm_perf`` and ``real_arm_perf`` are supplied (else the
    bridge is reported as N/A); ``construct_min_n`` / ``construct_contradiction_rho``
    tune when that bridge is thin enough to flag and negative enough to veto — note
    the canonical none/oracle/lexical setup is only 3 arms, so at the default
    ``min_n`` construct is always N-flagged and can corroborate but never veto. The
    three axes are assembled into a `RealismReport` — orchestration only; each
    axis's own module owns its math."""
    if not synthetic:
        raise ValueError("assess_realism needs at least one synthetic task")

    syn_features = [features_from_sequence(seq) for seq in synthetic]
    structural = structural_realism(syn_features, real_features)

    verdicts = [score_semantic_realism(seq, judge) for seq in synthetic]
    semantic = aggregate_semantic(verdicts)

    per_task = tuple(
        PerTaskRealism(task_id=seq.sequence_id, features=feat, semantic=verdict)
        for seq, feat, verdict in zip(synthetic, syn_features, verdicts, strict=True)
    )

    construct: ConstructVerdict | None = None
    if synthetic_arm_perf is not None and real_arm_perf is not None:
        construct = construct_validity_from_arms(
            synthetic_arm_perf,
            real_arm_perf,
            min_n=construct_min_n,
            contradiction_rho=construct_contradiction_rho,
        )

    return RealismReport(
        per_task=per_task,
        structural=structural,
        semantic=semantic,
        construct=construct,
    )
