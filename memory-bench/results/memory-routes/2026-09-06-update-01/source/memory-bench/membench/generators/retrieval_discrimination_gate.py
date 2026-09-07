"""§11 retrieval-discrimination gate (mem-31vl).

The necessity gate proves a task NEEDS memory (oracle beats no-memory). This gate
proves the stronger property a tool-requiring shape is built for: the shape
separates a QUALITY retriever from a NAIVE one. An id-exact arm (``filesystem``,
surfaces exactly the requested current ids) applies the current value and PASSES
the goal; a token-overlap arm (``lexical``) surfaces the superseded versions too, so
a stale value rides into the tool argument and it FAILS.

This is a deterministic, model-free PROXY for ours-vs-builtin. Real ``ours`` is
replay-only (needs a work_id + store) and real ``builtin`` is off-store native
memory, so the LITERAL ours-vs-builtin verdict is the paid Harbor path and is out of
scope here — what this gate proves is that the shape CAN discriminate retrieval
quality, the precondition for ever spending on that comparison. Reuses
``pilot_filter``'s delta>epsilon decision (and its ``EPSILON``) so admission and
reporting agree on what "beats" means.

Reads the GOAL-step reward, not the whole-sequence mean: establishing steps carry no
checks and would dilute a clean 1.0-vs-0.0 goal signal toward epsilon.
"""

from __future__ import annotations

from dataclasses import dataclass

from membench.generators.pilot_filter import pilot_filter
from membench.memory_systems.base import validate_top_k
from membench.report.comparison import EPSILON
from membench.runner.conditions import run_sequence
from membench.schemas.conditions import Condition
from membench.schemas.config import AgentConfig, ExperimentConfig, MemoryConfig
from membench.schemas.sequence import BenchmarkSequence

# The id-exact "quality" arm surfaces exactly the requested (current) ids; the
# token-overlap "naive" arm surfaces the superseded versions too and is fooled.
QUALITY_ARM = "filesystem"
NAIVE_ARM = "lexical"


@dataclass(frozen=True)
class DiscriminationResult:
    """Whether the shape separates the quality arm from the naive one at the goal.

    ``delta`` is ``quality_reward - naive_reward``; ``accepted`` is true only when it
    exceeds ``epsilon`` — the shape's retrieval-quality discrimination is real."""

    sequence_id: str
    quality_arm: str
    naive_arm: str
    quality_reward: float
    naive_reward: float
    delta: float
    accepted: bool
    epsilon: float
    reason: str


def _experiment(arm: str, *, top_k: int | None = None) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=f"discrimination-{arm}",
        agent=AgentConfig(agent_config_id="scripted-ref"),
        memory=MemoryConfig(memory_config_id=arm, system=arm, top_k=top_k),
        dataset_id="synthetic",
    )


def _goal_reward(seq: BenchmarkSequence, arm: str, *, top_k: int | None = None) -> float:
    """MEMORY_ENABLED reward of the GOAL step (the last step) for ``arm``."""
    run = run_sequence(seq, _experiment(arm, top_k=top_k), conditions=[Condition.MEMORY_ENABLED])
    goal_id = seq.steps[-1].step_id
    for trial in run.trials:
        if trial.condition is Condition.MEMORY_ENABLED and trial.step_id == goal_id:
            return trial.reward
    raise RuntimeError(f"no MEMORY_ENABLED goal trial for {seq.sequence_id} arm={arm}")


def retrieval_discrimination_gate(
    seq: BenchmarkSequence,
    *,
    quality_arm: str = QUALITY_ARM,
    naive_arm: str = NAIVE_ARM,
    epsilon: float = EPSILON,
    top_k: int | None = None,
) -> DiscriminationResult:
    """Admit ``seq`` as retrieval-quality-discriminating iff the quality arm beats the
    naive arm at the goal by more than ``epsilon`` — the deterministic proxy for
    ours-vs-builtin (see module docstring). Reuses ``pilot_filter`` for the decision.
    ``top_k``, when set, overrides the naive arm's retrieval width (only ``lexical``
    consumes it; the id-exact quality arm ignores it). Checked up front against
    ``LexicalTopKMemory``'s own floor so an invalid value fails before either arm runs,
    not after a full quality-arm simulation is thrown away."""
    if top_k is not None:
        validate_top_k(top_k)
    quality_reward = _goal_reward(seq, quality_arm)
    naive_reward = _goal_reward(seq, naive_arm, top_k=top_k)
    verdict = pilot_filter(
        oracle_reward=quality_reward, no_memory_reward=naive_reward, epsilon=epsilon
    )
    reason = (
        f"quality arm {quality_arm!r} beats naive {naive_arm!r} at the goal by "
        f"{verdict.delta:.3f} > epsilon {epsilon:.3f}"
        if verdict.accepted
        else (
            f"quality {quality_arm!r} does not beat naive {naive_arm!r} at the goal "
            f"(delta {verdict.delta:.3f} <= epsilon {epsilon:.3f}): shape does not "
            "discriminate retrieval quality"
        )
    )
    return DiscriminationResult(
        sequence_id=seq.sequence_id,
        quality_arm=quality_arm,
        naive_arm=naive_arm,
        quality_reward=quality_reward,
        naive_reward=naive_reward,
        delta=verdict.delta,
        accepted=verdict.accepted,
        epsilon=epsilon,
        reason=reason,
    )
