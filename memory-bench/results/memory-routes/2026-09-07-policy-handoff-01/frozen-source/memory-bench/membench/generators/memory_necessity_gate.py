"""§11 memory-necessity gate — run the pilot, then judge it.

``pilot_filter`` decides admission from two rewards but, by design, leaves
"running the pilot is the caller's job". This module is that caller: it runs a
generated ``BenchmarkSequence`` under the two conditions the task-validity gate
compares — NO_MEMORY and ORACLE_MEMORY — aggregates each arm's mean reward with
the same ``build_comparison`` summary reporting uses, and feeds the pair to
``pilot_filter``. The result is one reusable admission call any generator (the
authored blueprints today, NeMo-materialised worlds later) can gate on.

MEMORY_ENABLED is deliberately not run: necessity is a property of the task
(does ground-truth memory beat no memory?), independent of any arm under test.
The decision reuses ``EPSILON`` so generation and reporting agree on "beats".
No model is called — the reference ``ScriptedAgent`` (run_sequence's default)
makes the pilot deterministic and CI-safe.
"""

from __future__ import annotations

from dataclasses import dataclass

from membench.generators.pilot_filter import PilotVerdict, pilot_filter
from membench.report.comparison import EPSILON, build_comparison
from membench.runner.agent import Agent
from membench.runner.conditions import run_sequence
from membench.schemas.conditions import Condition
from membench.schemas.config import AgentConfig, ExperimentConfig, MemoryConfig
from membench.schemas.sequence import BenchmarkSequence

# The two conditions the necessity decision compares (DIV-3). MEMORY_ENABLED is
# the arm under test, not part of whether the task *requires* memory.
_NECESSITY_CONDITIONS = (Condition.NO_MEMORY, Condition.ORACLE_MEMORY)


@dataclass(frozen=True)
class NecessityResult:
    """One sequence's admission decision. ``verdict`` carries the rewards, delta,
    epsilon and reason from ``pilot_filter``; ``sequence_id`` names the task so a
    batch run is traceable."""

    sequence_id: str
    verdict: PilotVerdict


def _necessity_experiment(seq: BenchmarkSequence) -> ExperimentConfig:
    """A minimal two-condition experiment for the pilot. The memory system is left
    at the ``none`` default — ORACLE injects ground truth and NO_MEMORY withholds
    it, so neither arm needs the system under test."""
    return ExperimentConfig(
        experiment_id=f"necessity-{seq.sequence_id}",
        agent=AgentConfig(agent_config_id="scripted-ref"),
        memory=MemoryConfig(memory_config_id="necessity-none"),
        dataset_id="synthetic",
        conditions=list(_NECESSITY_CONDITIONS),
    )


def memory_necessity_gate(
    seq: BenchmarkSequence,
    *,
    agent: Agent | None = None,
    epsilon: float = EPSILON,
) -> NecessityResult:
    """Run ``seq`` under NO_MEMORY and ORACLE_MEMORY and decide whether it
    discriminates memory benefit.

    Admitted only when the oracle arm's mean reward beats the no-memory arm's by
    more than ``epsilon`` (DIV-3). A task that ties measures nothing about memory
    and is rejected — the construct-validity precondition for the whole benchmark.
    """
    run = run_sequence(seq, _necessity_experiment(seq), agent)
    summaries = build_comparison(run).summaries
    oracle = summaries[Condition.ORACLE_MEMORY.value].mean_reward
    no_memory = summaries[Condition.NO_MEMORY.value].mean_reward
    verdict = pilot_filter(oracle_reward=oracle, no_memory_reward=no_memory, epsilon=epsilon)
    return NecessityResult(sequence_id=seq.sequence_id, verdict=verdict)
