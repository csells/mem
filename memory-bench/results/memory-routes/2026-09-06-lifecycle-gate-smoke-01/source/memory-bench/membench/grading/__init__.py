"""Outcome/grading sources + the coverage probe (mem-apg.1).

The verifier oracle is a FAMILY of sources (Stephanie, 2026-06-08): `merged_diff`
(the locked headline, where constructible) and `ablation` (env-independent, always
feasible). `OutcomeSource` is the uniform feasibility contract they share; the
coverage probe surveys which source can grade each held-out task before any Docker
or paid run. Named `grading` (not `oracle`) to avoid colliding with the existing
`OracleMemory` memory-ceiling condition (architect finding H3).
"""

from membench.grading.ablation import DEFAULT_RUNGS, AblationDesign, AblationSource
from membench.grading.base import Feasibility, OutcomeSource
from membench.grading.base_rate import (
    DEFAULT_MIN_APPLICABLE,
    DEFAULT_MIN_RECURRENCE_LB,
    GateDecision,
    GateVerdict,
    base_rate_gate,
)
from membench.grading.coverage import (
    CoverageSummary,
    SourceCount,
    SourceCoverage,
    coverage_table,
    recommend_source,
    summarize,
)
from membench.grading.curve import (
    DEFAULT_SATURATION_TOL,
    InsufficientLadderError,
    RungReward,
    ScoreInformationCurve,
    build_curve,
    min_useful_combo,
    saturation_point,
)
from membench.grading.judge import (
    Calibration,
    CalibrationReport,
    Judge,
    OssLlmJudge,
    Rubric,
    RubricCriterion,
    StubJudge,
    completion_rubric,
    score_completion,
)
from membench.grading.leak_guard import (
    IDENTIFYING_KEYS,
    OutcomeLeakError,
    assert_no_outcome_leak,
    find_outcome_leaks,
    outcome_labels,
)
from membench.grading.merged_diff import MergedDiffSource
from membench.grading.paired_ci import (
    POPULATION_PRIMARY,
    PairedDeltaCI,
    Population,
    paired_delta_ci,
    paired_deltas,
)
from membench.grading.trace_score import (
    RewardComponents,
    RewardRecord,
    RunTrace,
    TraceErrorRef,
    combined_reward,
    deterministic_term,
    exact_recurrence,
    relaxed_signature,
    score_run,
)

__all__ = [
    "DEFAULT_MIN_APPLICABLE",
    "DEFAULT_MIN_RECURRENCE_LB",
    "DEFAULT_RUNGS",
    "DEFAULT_SATURATION_TOL",
    "IDENTIFYING_KEYS",
    "POPULATION_PRIMARY",
    "AblationDesign",
    "AblationSource",
    "Calibration",
    "CalibrationReport",
    "CoverageSummary",
    "Feasibility",
    "GateDecision",
    "GateVerdict",
    "InsufficientLadderError",
    "Judge",
    "MergedDiffSource",
    "OssLlmJudge",
    "OutcomeLeakError",
    "OutcomeSource",
    "PairedDeltaCI",
    "Population",
    "RewardComponents",
    "RewardRecord",
    "Rubric",
    "RubricCriterion",
    "RunTrace",
    "RungReward",
    "ScoreInformationCurve",
    "SourceCount",
    "SourceCoverage",
    "StubJudge",
    "TraceErrorRef",
    "assert_no_outcome_leak",
    "base_rate_gate",
    "build_curve",
    "combined_reward",
    "completion_rubric",
    "coverage_table",
    "deterministic_term",
    "exact_recurrence",
    "find_outcome_leaks",
    "min_useful_combo",
    "outcome_labels",
    "paired_delta_ci",
    "paired_deltas",
    "recommend_source",
    "relaxed_signature",
    "saturation_point",
    "score_completion",
    "score_run",
    "summarize",
]
