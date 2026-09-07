"""The uniform outcome-source interface.

An `OutcomeSource` answers one question per WorkRecord: *can this source grade this
task, and what (if anything) does it still need before it can?* This is the
feasibility contract the coverage probe (mem-apg.1) runs across every source — the
construction half (`build`) is added by the sources that own it in mem-apg.2/.3.

Modelled on `memory_systems/base.py` (`MemorySystem`): the harness drives every
source through one signature, so the coverage table is a byproduct of the protocol
rather than a hand-rolled per-source classifier (architect finding M5).
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Feasibility:
    """Whether a source can grade a record. `unresolved` names the conditions that
    cannot be confirmed offline (e.g. a base-commit walk that needs a clone) — they
    are reported, never silently assumed satisfied."""

    source: str
    feasible: bool
    reason: str
    unresolved: tuple[str, ...] = ()


class OutcomeSource(ABC):
    """Uniform interface implemented by every outcome/grading source.

    Subclasses MUST set `name` as a class attribute (mirrors `MemorySystem.name`);
    it is not enforced abstractly, so an omission surfaces as an `AttributeError`
    the first time `.name` is read.
    """

    name: str

    @abstractmethod
    def can_build(self, record: Mapping[str, Any]) -> Feasibility:
        """Whether this source can grade `record` (the WorkRecord JSON shape).

        Precondition: `record` carries the required `work_id` and `rig` keys (the
        same contract as `validity.work_ref_from_record`); their absence is a caller
        error, not a graceful-degradation case."""
