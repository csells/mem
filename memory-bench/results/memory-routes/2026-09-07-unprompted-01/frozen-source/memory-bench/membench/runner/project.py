"""Run a PROJECT — a list of sequences sharing one memory store (§Continuity).

``run_sequence`` resets the store per sequence, so memory never crosses task
boundaries. ``run_project`` instead runs every sequence under ONE per-condition
scope without resetting between them, so a later task can read what an earlier task
wrote — the cross-task continuity the benchmark targets. It reuses ``run_sequence``'s
extracted ``_execute_step`` (identical step semantics); the only difference is the
shared scope and a unioned oracle pool.

Additive by design: ``run_sequence`` is untouched. A project whose later tasks
depend on an earlier task's memory passes under ``run_project`` but fails under
isolated ``run_sequence`` — that gap IS the continuity signal.
"""

from dataclasses import dataclass, field
from pathlib import Path

from membench.memory_systems.base import MemorySystem
from membench.memory_systems.consolidation import ConsolidationCapable, ConsolidationResult
from membench.memory_systems.oracle_system import OracleMemory
from membench.runner.agent import Agent, ScriptedAgent
from membench.runner.conditions import (
    StepTrial,
    _assert_superseded_written,
    _execute_step,
    _oracle_pool,
    _system_for,
    _TokenAccumulator,
)
from membench.runtime import IdClock, StepContext
from membench.schemas.conditions import Condition
from membench.schemas.config import ExperimentConfig
from membench.schemas.sequence import BenchmarkSequence


@dataclass
class ProjectRun:
    """All trials from running a project's sequences under a shared store."""

    project_id: str
    experiment_id: str
    trials: list[StepTrial] = field(default_factory=list)
    consolidations: dict[str, ConsolidationResult] = field(default_factory=dict)

    def by_condition(self) -> dict[Condition, list[StepTrial]]:
        out: dict[Condition, list[StepTrial]] = {}
        for t in self.trials:
            out.setdefault(t.condition, []).append(t)
        return out

    def by_sequence(self) -> dict[str, list[StepTrial]]:
        out: dict[str, list[StepTrial]] = {}
        for t in self.trials:
            out.setdefault(t.sequence_id, []).append(t)
        return out


def _project_oracle_pool(sequences: list[BenchmarkSequence]) -> dict[str, str]:
    """Union of every sequence's oracle pool. Ids are sequence- or project-namespaced,
    so a cross-sequence collision with different content is a design error and raises
    (mirrors ``_oracle_pool``); identical re-writes (e.g. a shared charter) are fine."""
    pool: dict[str, str] = {}
    for seq in sequences:
        for memory_id, content in _oracle_pool(seq).items():
            existing = pool.get(memory_id)
            if existing is not None and existing != content:
                raise ValueError(
                    f"project oracle conflict: memory_id {memory_id!r} written with "
                    f"different content across sequences"
                )
            pool[memory_id] = content
    return pool


def run_project(
    sequences: list[BenchmarkSequence],
    experiment: ExperimentConfig,
    agent: Agent | None = None,
    *,
    project_id: str = "project",
    conditions: list[Condition] | None = None,
    fs_base_dir: str | Path | None = None,
    memory_system: MemorySystem | None = None,
) -> ProjectRun:
    """Run ``sequences`` in order under a shared per-condition store. The store is
    reset once per condition (not per sequence), so writes persist across tasks."""
    if not sequences:
        raise ValueError("run_project requires at least one sequence")
    for seq in sequences:
        _assert_superseded_written(seq)
    agent = agent or ScriptedAgent()
    conditions = conditions or experiment.conditions
    base = Path(fs_base_dir) if fs_base_dir is not None else None
    run = ProjectRun(project_id=project_id, experiment_id=experiment.experiment_id)

    for condition in conditions:
        system, memory_config_id = _system_for(condition, experiment, base, memory_system)
        project_root = f"{project_id}-{condition.value}"
        system.reset(project_root)
        if isinstance(system, OracleMemory):
            system.load(_project_oracle_pool(sequences))

        # Accumulated across EVERY sequence in the project — the shared scope means
        # context pressure carries across task boundaries here just like memory does.
        tokens = _TokenAccumulator()
        for seq in sequences:
            for step in seq.steps:
                trial = _execute_step(
                    seq_id=seq.sequence_id,
                    step=step,
                    system=system,
                    condition=condition,
                    scope=project_root,
                    memory_config_id=memory_config_id,
                    experiment=experiment,
                    agent=agent,
                    accumulated_tokens_before=tokens.tokens,
                )
                run.trials.append(trial)
                tokens.record(trial)

        if condition is Condition.MEMORY_ENABLED and isinstance(system, ConsolidationCapable):
            consolidate_ctx = StepContext(
                trial_id=f"{project_root}-consolidate",
                session_id=project_root,
                step_id="consolidate",
                clock=IdClock(),
            )
            run.consolidations[condition.value] = system.consolidate(consolidate_ctx)
    return run
