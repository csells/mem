"""Synthetic-data realism metric (mem-ovi).

Quantifies how realistic a synthetic eval corpus is versus real agent traces, on
three independently-reported axes:

* STRUCTURAL  — mechanical distributional match of task shapes. The signed-off
  form (#mem 2026-06-21) is the per-feature KS vector in ``perfeature_reference``
  (matchable vs disjoint memory-op groups, no aggregate); ``distance`` keeps the
  earlier mean-of-7 aggregate for callers not yet migrated.
* SEMANTIC    — a model judge's per-task realism rating (``semantic``).
* CONSTRUCT   — rank-correlation of memory-arm performance, N-flagged (``construct``).

``report.assess_realism`` assembles the three into a `RealismReport` whose
``defensible`` flag is a transparent AND over the per-axis gates — never an opaque
composite. See ``report.py`` for the gating policy and the publication-freeze note.
"""

from membench.realism.construct import (
    ConstructVerdict,
    FlatSampleError,
    construct_validity,
    construct_validity_from_arms,
    spearman_rho,
)
from membench.realism.distance import (
    StructuralReport,
    ks_statistic,
    structural_realism,
)
from membench.realism.features import (
    FEATURE_NAMES,
    TaskFeatures,
    TraceStep,
    features_from_sequence,
    features_from_trace_steps,
)
from membench.realism.mem_corpus import (
    default_message_filter,
    load_real_corpus,
    load_work_records,
    parse_transcript,
)
from membench.realism.perfeature_reference import (
    MATCHABLE_FEATURES,
    MEMORY_OP_FEATURES,
    PerFeatureReference,
    per_feature_reference,
)
from membench.realism.real_loader import (
    RECOVERABLE_FEATURES,
    features_from_trace,
    load_real_features,
    memory_dependency_depth,
    trace_to_steps,
)
from membench.realism.report import (
    PerTaskRealism,
    RealismReport,
    assess_realism,
)
from membench.realism.run_verdict import (
    SemanticAxis,
    StructuralCell,
    VerdictMatrix,
    construct_axis,
    load_synthetic_corpus,
    run,
    semantic_axis,
    structural_matrix,
)
from membench.realism.semantic import (
    SemanticAggregate,
    SemanticVerdict,
    aggregate_semantic,
    build_semantic_prompt,
    parse_semantic_verdict,
    score_semantic_realism,
    task_text_for_sequence,
)

__all__ = [
    "FEATURE_NAMES",
    "MATCHABLE_FEATURES",
    "MEMORY_OP_FEATURES",
    "RECOVERABLE_FEATURES",
    "ConstructVerdict",
    "FlatSampleError",
    "PerFeatureReference",
    "PerTaskRealism",
    "RealismReport",
    "SemanticAggregate",
    "SemanticAxis",
    "SemanticVerdict",
    "StructuralCell",
    "StructuralReport",
    "TaskFeatures",
    "TraceStep",
    "VerdictMatrix",
    "aggregate_semantic",
    "assess_realism",
    "build_semantic_prompt",
    "construct_axis",
    "construct_validity",
    "construct_validity_from_arms",
    "default_message_filter",
    "features_from_sequence",
    "features_from_trace",
    "features_from_trace_steps",
    "ks_statistic",
    "load_real_corpus",
    "load_real_features",
    "load_synthetic_corpus",
    "load_work_records",
    "memory_dependency_depth",
    "parse_semantic_verdict",
    "parse_transcript",
    "per_feature_reference",
    "run",
    "score_semantic_realism",
    "semantic_axis",
    "spearman_rho",
    "structural_matrix",
    "structural_realism",
    "task_text_for_sequence",
    "trace_to_steps",
]
