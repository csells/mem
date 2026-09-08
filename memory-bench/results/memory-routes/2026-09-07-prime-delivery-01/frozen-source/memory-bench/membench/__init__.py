"""membench — Agentic Memory Evaluation Harness (Spec Phase-1 skeleton).

Governing spec: .gc/memory-eval-harness-spec.md (§3 system model, §4 conditions,
§6.2 normalized memory ops, §8 trace, §12 metrics, §14 Harbor, §16 Phase 1).
Reconciliation: .gc/docs/phase-2.5-plan.md §A (Stephanie's resolutions, 2026-06-05).

This package is the *mechanism* layer (ZFC): Harbor orchestration, schema
validation, deterministic memory-op mapping, and deterministic metric arithmetic.
Semantic judgment (the trace→memory extractor, LLM-as-judge scoring) is a seam
delegated to a model in later phases — not implemented here.
"""

__version__ = "0.1.0"
