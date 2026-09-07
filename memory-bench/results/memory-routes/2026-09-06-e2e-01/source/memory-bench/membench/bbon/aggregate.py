"""Aggregate per-pair judge outcomes into the mem-0ut qualitative readout.

Each A/B pair yields one `Comparison` (which arm the judge picked, with what
confidence, over which narrative diff). This module rolls a list of them into the
experiment-level view that sits beside `armcompare.summarize_arms`: how often each
arm won, the mean confidence, and the per-pair rationales as the evidence trail.

ZFC: pure mechanism — counting and arithmetic over already-decided verdicts. The
semantic call (who won) was the judge's; this only tallies it.
"""

from __future__ import annotations

from collections.abc import Sequence
from statistics import fmean
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from membench.bbon.models import Attempt, Judgment, NarrativeDiff


class Comparison(BaseModel):
    """One A/B pair's resolved outcome: the two arms, the winning arm, and the
    judge's confidence/rationale, with the diff summary as the qualitative evidence."""

    model_config = ConfigDict(frozen=True)

    left_work_id: str
    right_work_id: str
    left_arm: str
    right_arm: str
    winner_arm: str
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    rationale: str


def build_comparison(
    left: Attempt, right: Attempt, narrative_diff: NarrativeDiff, judgment: Judgment
) -> Comparison:
    """Assemble the `Comparison` from a resolved pair. The winning arm is read off
    the judgment's winner id; a winner id matching neither attempt is an upstream
    bug and raises (the judgment must be over this exact pair)."""
    if judgment.winner_attempt_id == left.id:
        winner_arm = left.arm
    elif judgment.winner_attempt_id == right.id:
        winner_arm = right.arm
    else:
        raise ValueError(
            f"judgment winner {judgment.winner_attempt_id!r} matches neither "
            f"attempt ({left.id!r}, {right.id!r})"
        )
    return Comparison(
        left_work_id=left.work_id,
        right_work_id=right.work_id,
        left_arm=left.arm,
        right_arm=right.arm,
        winner_arm=winner_arm,
        confidence=judgment.confidence,
        summary=narrative_diff.summary,
        rationale=judgment.rationale,
    )


def summarize_comparisons(comparisons: Sequence[Comparison]) -> dict[str, Any]:
    """Win counts per arm + mean judge confidence across all pairs. Raises on an
    empty input — there is nothing to summarize, and a zeroed readout would read as
    a real (tied) result."""
    if not comparisons:
        raise ValueError("no comparisons to summarize")
    wins: dict[str, int] = {}
    for comparison in comparisons:
        wins[comparison.winner_arm] = wins.get(comparison.winner_arm, 0) + 1
    return {
        "n_pairs": len(comparisons),
        "wins_by_arm": wins,
        "mean_confidence": fmean(c.confidence for c in comparisons),
    }
