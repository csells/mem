"""ATIF — a derived trajectory export (NOT the source of truth).

ATIF (Agentic Trajectory Interchange Format) is NVIDIA NAT's eval-trace schema. We
emit it as a *derived* view of the same trace that produces the primary OTel spans,
so NAT-side tooling can consume our trials without us taking a hard NAT dependency
(plan §1c / §A; ARCHITECTURE.md Decisions 12 & 15). The exact upstream ATIF schema
is not pinned here; this is the stable subset the skeleton commits to.
"""

from typing import Any

from membench.schemas.trace import Trace


def trace_to_atif(trace: Trace) -> dict[str, Any]:
    """Derive an ATIF-style trajectory record from a `Trace`."""
    actions: list[dict[str, Any]] = []
    for tc in trace.tool_calls:
        actions.append({"action_type": "tool_call", "name": tc.name, "arguments": tc.arguments})
    for ev in trace.memory_events:
        actions.append(
            {
                "action_type": "memory_operation",
                "operation": ev.normalized_operation.value,
                "backend": ev.backend.value,
                "retrieved_ids": list(ev.retrieved_ids),
                "written_ids": list(ev.written_ids),
                "success": ev.success,
            }
        )
    return {
        "format": "atif-derived",
        "derived_from": "otel",
        "trajectory_id": trace.trial_id,
        "experiment_id": trace.experiment_id,
        "task_id": trace.task_id,
        "step_id": trace.step_id,
        "agent_config_id": trace.agent_config_id,
        "memory_config_id": trace.memory_config_id,
        "actions": actions,
        "final_answer": trace.final_answer,
        "reward": float(trace.verifier_result.get("reward", 0.0)) if trace.verifier_result else 0.0,
    }
