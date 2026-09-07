"""Deterministic metric scorers (§12).

Pure mechanism (ZFC / patterns.md §ZFC): set arithmetic, ranking math, and counting
over what a trial actually produced. Fields that need a judge (rubric_score,
completion_quality, derailment_signal magnitude) are left at their None/default
seams by the callers.

The §12.6 action-impact scorer is the one orchestrated judge seam: its own code is
still pure mechanism (mechanical trajectory diff, prompt assembly, reply parsing),
but it calls an INJECTED comparative judge for the counterfactual booleans. No judge
=> the semantic axes stay None; the mechanical pre-filter still fills the axes the
trajectories prove unchanged.
"""

from membench.metrics.action_impact import (
    ActionImpactInputs,
    ActionImpactJudgeError,
    ActionImpactVerdict,
    TrajectoryDiff,
    build_action_impact_prompt,
    diff_trajectories,
    parse_action_impact_verdict,
    score_action_impact,
)
from membench.metrics.action_impact_run import (
    ArmActionImpact,
    ArmStepTrajectory,
    AxisTally,
    aggregate_metrics,
    pair_trajectories,
    run_action_impact,
    score_arm_run,
)
from membench.metrics.scorers import (
    InterruptionInputs,
    PrivacyInputs,
    RetentionInputs,
    RetrievalInputs,
    SynthesisInputs,
    score_efficiency,
    score_interruption,
    score_privacy,
    score_retention,
    score_retrieval,
    score_synthesis,
)

__all__ = [
    "ActionImpactInputs",
    "ActionImpactJudgeError",
    "ActionImpactVerdict",
    "ArmActionImpact",
    "ArmStepTrajectory",
    "AxisTally",
    "InterruptionInputs",
    "PrivacyInputs",
    "RetentionInputs",
    "RetrievalInputs",
    "SynthesisInputs",
    "TrajectoryDiff",
    "aggregate_metrics",
    "build_action_impact_prompt",
    "diff_trajectories",
    "pair_trajectories",
    "parse_action_impact_verdict",
    "run_action_impact",
    "score_action_impact",
    "score_arm_run",
    "score_efficiency",
    "score_interruption",
    "score_privacy",
    "score_retention",
    "score_retrieval",
    "score_synthesis",
]
