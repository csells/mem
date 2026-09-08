"""§11 pilot filter — the synthetic-task validity gate.

A synthetic task is only a valid eval task if it actually discriminates memory
benefit: the oracle arm (memory available) must beat the no-memory arm. A task
where the two tie measures nothing about memory and is rejected.

This is the same oracle-vs-no_memory relationship the §4 interpretation calls the
task-validity gate (DIV-3, see ``report.comparison``); the gate's ``EPSILON`` is
reused here so generation and reporting agree on what "beats" means. The decision
is pure arithmetic over rewards a pilot run produced — running the pilot is the
caller's job (runner + ``build_comparison``); this module only judges the result.
"""

from __future__ import annotations

from dataclasses import dataclass

from membench.report.comparison import EPSILON


@dataclass(frozen=True)
class PilotVerdict:
    """The admission decision for one synthetic task. ``delta`` is
    ``oracle_reward - no_memory_reward``; ``accepted`` is true only when it exceeds
    ``epsilon`` (the task discriminates memory benefit)."""

    accepted: bool
    oracle_reward: float
    no_memory_reward: float
    delta: float
    epsilon: float
    reason: str


def pilot_filter(
    *, oracle_reward: float, no_memory_reward: float, epsilon: float = EPSILON
) -> PilotVerdict:
    """Decide whether a synthetic task is admitted, given the mean reward its oracle
    and no-memory arms scored in a pilot run.

    Admit only when ``oracle_reward`` beats ``no_memory_reward`` by more than
    ``epsilon``. A non-positive or within-``epsilon`` delta means the task does not
    discriminate memory benefit (DIV-3) and is rejected — never silently kept."""
    delta = oracle_reward - no_memory_reward
    accepted = delta > epsilon
    if accepted:
        reason = f"oracle beats no_memory by {delta:.3f} > epsilon {epsilon:.3f}"
    else:
        reason = (
            f"oracle does not beat no_memory (delta {delta:.3f} <= epsilon "
            f"{epsilon:.3f}): task does not discriminate memory benefit (DIV-3)"
        )
    return PilotVerdict(
        accepted=accepted,
        oracle_reward=oracle_reward,
        no_memory_reward=no_memory_reward,
        delta=delta,
        epsilon=epsilon,
        reason=reason,
    )
