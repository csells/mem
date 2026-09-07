"""§4.4 trajectory driver — run an arm over a sequence's steps and emit the
`ArmStepTrajectory`s the action-impact harness scores.

This is the seam between the real-run substrate (`HeadlessClaudeAgent`, the producer)
and the deterministic scorer (`metrics.action_impact_run`, the consumer). For each
step it asks the agent to act under the arm's surfaced memory, derives the
`AttemptStep` tool-call trajectory from the agent's raw stream via
`bbon.extract.steps_from_stream`, and wraps it as an `ArmStepTrajectory`.

Per-arm memory is supplied by the caller as ``memory_for_step`` — the harness already
owns the none/ours/builtin retrieval (`runner.conditions` computes ``available_memory``
from each arm's `MemorySystem.retrieve`), so this driver does NOT re-implement it. The
``none`` control is simply the provider that returns ``{}`` for every step.

ZFC: pure mechanism — iteration, delegation to the injected agent, structural
extraction. No semantic judgment; the trajectory IS the agent's behavior.
"""

from __future__ import annotations

from collections.abc import Callable

from membench.bbon.extract import steps_from_stream
from membench.bbon.models import deterministic_id
from membench.metrics.action_impact_run import ArmStepTrajectory
from membench.runner.agent import Agent
from membench.runtime import IdClock, StepContext
from membench.schemas.sequence import BenchmarkSequence, SequenceStep

# Per-step memory provider: (step) -> the memory ids/content the arm surfaces. The
# ``none`` control is `lambda _step: {}` — an empty surface, the real control condition.
MemoryForStep = Callable[[SequenceStep], dict[str, str]]


def _none_memory(_step: SequenceStep) -> dict[str, str]:
    return {}


def run_step_trajectory(
    agent: Agent,
    step: SequenceStep,
    *,
    arm: str,
    sequence_id: str,
    available_memory: dict[str, str] | None = None,
    work_id: str | None = None,
) -> ArmStepTrajectory:
    """Run one step under ``agent`` with the arm's ``available_memory`` and build its
    `ArmStepTrajectory`. The attempt id is content-addressed over (arm, sequence, step)
    so the same run is reproducibly keyed. Terminal status is ``failed`` when the agent
    reported errors, else ``completed`` — the harness uses it for the no-diff pre-filter."""
    memory = available_memory or {}
    ctx = StepContext(
        trial_id=f"{arm}:{sequence_id}:{step.step_id}",
        session_id=arm,
        step_id=step.step_id,
        clock=IdClock(),
    )
    result = agent.run_step(step, memory, ctx)
    attempt_id = deterministic_id({"arm": arm, "sequence_id": sequence_id, "step_id": step.step_id})
    steps = steps_from_stream(result.raw_stream, attempt_id)
    status = "failed" if result.errors else "completed"
    return ArmStepTrajectory(
        arm=arm,
        sequence_id=sequence_id,
        step_id=step.step_id,
        steps=tuple(steps),
        status=status,
        work_id=work_id,
    )


def run_arm_trajectories(
    agent: Agent,
    sequence: BenchmarkSequence,
    *,
    arm: str,
    memory_for_step: MemoryForStep | None = None,
    work_id: str | None = None,
) -> list[ArmStepTrajectory]:
    """Run ``agent`` over every step of ``sequence`` under one arm, returning the
    per-step `ArmStepTrajectory`s in step order. ``memory_for_step`` supplies the arm's
    surfaced memory per step (defaults to the empty ``none`` control). Steps run in
    order because the persistent memory store is the only cross-step channel — but this
    driver does not itself persist writes (the harness owns the store), so a real
    ours/builtin run threads its store through ``memory_for_step``."""
    provider = memory_for_step or _none_memory
    return [
        run_step_trajectory(
            agent,
            step,
            arm=arm,
            sequence_id=sequence.sequence_id,
            available_memory=provider(step),
            work_id=work_id,
        )
        for step in sequence.steps
    ]


def run_sequence_arms(
    agent: Agent,
    sequence: BenchmarkSequence,
    *,
    memory_by_arm: dict[str, MemoryForStep],
    work_id: str | None = None,
) -> dict[str, list[ArmStepTrajectory]]:
    """Run several arms over one sequence and return ``{arm: trajectories}`` ready for
    `metrics.action_impact_run.run_action_impact`. ``memory_by_arm`` maps arm name ->
    its per-step memory provider (e.g. ``{"none": ..., "ours": ..., "builtin": ...}``).
    Each arm is run independently; the caller wraps heavy runs in ``scix-batch``."""
    return {
        arm: run_arm_trajectories(
            agent, sequence, arm=arm, memory_for_step=provider, work_id=work_id
        )
        for arm, provider in memory_by_arm.items()
    }


__all__ = [
    "MemoryForStep",
    "run_arm_trajectories",
    "run_sequence_arms",
    "run_step_trajectory",
]
