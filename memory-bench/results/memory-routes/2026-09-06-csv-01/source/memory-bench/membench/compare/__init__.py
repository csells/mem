"""`ours` vs semantic-arm head-to-head, retrieval-quality only (mem-compare).

The replay runner (`replay.py`) drives `ours` over the work-audit graph via the
`query_work` path; the semantic arms (`mem0`, a-mem, …) consume the `query_text`
path and retrieve over whatever was *written* into their per-trial scope. The two
arm families therefore never met on one task surface. This package is the bridge:

1. compute the harness LOO-bounded ingest set for a query work `B`
   (`validity.loo_bounded`) — the single door to the corpus, identical for both
   arms;
2. **seed** the semantic arm with exactly that set (each prior bead's text), so it
   is not compared against an empty store (the `mem-bxhh.3` substrate trap);
3. run `ours` (failure-triggered) and the semantic arm (`query_text`) and score
   BOTH `retrieved` work_ids against ONE authored relevant set
   (`grading.retrieval_leg.score_retrieval_leg` — precision/recall/MRR/nDCG);
4. re-check BOTH arms' output against the LOO boundary (`validity.assert_no_leak`).

Retrieval-quality only — NO agent re-run, NO outcome lift, so it is free/local. The
outcome-lift comparison is the paid Harbor path and is deliberately out of scope.
"""

from membench.compare.circularity_baseline import (
    DEFAULT_CIRCULARITY_DELTA,
    CircularityMetric,
    CircularityVerdict,
    circularity_check,
)
from membench.compare.judged_relevance import (
    JudgedPair,
    JudgedRelevance,
    PairCache,
    harvest_and_judge,
    judge_relevance,
)
from membench.compare.relevance_calibration import (
    PREREGISTERED_FPR_GAP_MAX,
    BinaryLabelPair,
    CalibrationGateVerdict,
    CalibrationReport,
    ClassMetrics,
    FrozenCalibration,
    GradedLabelPair,
    RelevanceCalibration,
    load_frozen_calibration,
    relevance_calibration_authority,
)
from membench.compare.relevance_judge import (
    SIGNATURE_FIELD_NAMES,
    RelevanceInputs,
    RelevanceJudgeError,
    RelevanceResult,
    RelevanceVerdict,
    build_relevance_prompt,
    parse_relevance_verdict,
    relevance_cache_key,
    score_relevance,
)
from membench.compare.retrieval_compare import (
    ArmComparison,
    ArmHarvest,
    ComparisonResult,
    compare_arms,
    harvest_ours,
    harvest_semantic,
    ours_replay,
    pool_candidates,
    score_harvest,
    seed_semantic_arm,
    semantic_replay,
)

__all__ = [
    "DEFAULT_CIRCULARITY_DELTA",
    "PREREGISTERED_FPR_GAP_MAX",
    "SIGNATURE_FIELD_NAMES",
    "ArmComparison",
    "ArmHarvest",
    "BinaryLabelPair",
    "CalibrationGateVerdict",
    "CalibrationReport",
    "CircularityMetric",
    "CircularityVerdict",
    "ClassMetrics",
    "ComparisonResult",
    "FrozenCalibration",
    "GradedLabelPair",
    "JudgedPair",
    "JudgedRelevance",
    "PairCache",
    "RelevanceCalibration",
    "RelevanceInputs",
    "RelevanceJudgeError",
    "RelevanceResult",
    "RelevanceVerdict",
    "build_relevance_prompt",
    "circularity_check",
    "compare_arms",
    "harvest_and_judge",
    "harvest_ours",
    "harvest_semantic",
    "judge_relevance",
    "load_frozen_calibration",
    "ours_replay",
    "parse_relevance_verdict",
    "pool_candidates",
    "relevance_cache_key",
    "relevance_calibration_authority",
    "score_harvest",
    "score_relevance",
    "seed_semantic_arm",
    "semantic_replay",
]
