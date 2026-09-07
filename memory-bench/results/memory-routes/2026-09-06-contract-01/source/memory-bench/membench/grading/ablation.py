"""Ablation outcome source — the env-independent, always-feasible grading family.

Ablation needs no ground-truth label: it varies *which information the agent can
access* across an information ladder and reads the score-vs-information curve (the
saturation point and the minimum-useful combination). Because the agent is its own
control, it sidesteps the flaky per-rig env reconstruction the merged-diff source
needs (Stephanie, 2026-06-08).

This bead (mem-apg.1) ships the feasibility + the label-free ladder *design*; the
grid *execution* is mem-apg.3.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from membench.grading.base import Feasibility, OutcomeSource

# The information ladder swept to read the score-vs-information curve. Each rung
# names WHICH memory the agent may access — never an outcome value, so the ladder
# is label-free by construction.
DEFAULT_RUNGS: tuple[str, ...] = (
    "none",
    "vector-rag",
    "ours",
    "builtin",
    "ours+builtin",
    "oracle",
)

# The rungs that constitute the COMBINATION axis the saturation / min-useful-combo
# readouts measure (the agent's opaque memory, layered with `ours`; mem-whi). Lives
# here beside the rung vocabulary; `harbor.memory_inject.DEFERRED_RUNGS` names the
# same rungs for the separate runnability concept (they coincide until mem-whi).
COMBINATION_RUNGS: frozenset[str] = frozenset({"builtin", "ours+builtin"})

# The base rung a combination rung (`builtin` / `ours+builtin`) layers onto — the
# baseline `curve._require_full_ladder` requires present before the saturation /
# min-useful-combo readouts may compute. Full rationale: the "Recall ladder" note in
# curve.py's module docstring (mem-do8r.2 / Codex F1).
COMBINATION_BASE_RUNG: str = "ours"


@dataclass(frozen=True)
class AblationDesign:
    """The label-free information ladder to sweep for one task."""

    work_id: str
    rungs: tuple[str, ...]


class AblationSource(OutcomeSource):
    name = "ablation"

    def __init__(self, rungs: tuple[str, ...] = DEFAULT_RUNGS) -> None:
        self.rungs = rungs

    def can_build(self, record: Mapping[str, Any]) -> Feasibility:
        return Feasibility(
            source=self.name,
            feasible=True,
            reason="ablation needs no ground-truth label; the agent is its own control",
        )

    def design(self, record: Mapping[str, Any]) -> AblationDesign:
        """The label-free ladder for `record` — consumed by the task manifest, never
        the verifier manifest."""
        return AblationDesign(work_id=record["work_id"], rungs=self.rungs)
