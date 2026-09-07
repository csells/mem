"""The experiment ledger: an append-only JSONL log of trials, plus the keep-or-discard
decision against the best score so far.

autoresearch's loop is "train, check if it improved, keep or discard, repeat". The
ledger is the memory of that loop — the agent reads it to see what's been tried and
what won, and a fresh agent (or you, in the morning) reconstructs the whole run from
it. Append-only so a crashed trial never corrupts prior history.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from membench.autotune._coerce import as_bool, as_float, as_int, as_mapping, opt_float, opt_int
from membench.autotune.config import TrialConfig
from membench.autotune.objective import TrialObjective


@dataclass(frozen=True)
class TrialRecord:
    """One row of the ledger: the trial's id, the config it ran, and its score."""

    trial_id: int
    config: TrialConfig
    objective: TrialObjective
    note: str = ""

    def to_dict(self) -> dict[str, object]:
        obj = self.objective
        return {
            "trial_id": self.trial_id,
            "note": self.note,
            "score": obj.score,
            "slo_met": obj.slo_met,
            "best_concurrency": obj.best_concurrency,
            "best_output_tps": obj.best_output_tps,
            "best_ttft_p50_s": obj.best_ttft_p50_s,
            "ttft_p50_slo_s": obj.ttft_p50_slo_s,
            "cells_evaluated": obj.cells_evaluated,
            "config": self.config.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> TrialRecord:
        config = TrialConfig.from_dict(dict(as_mapping(raw["config"], "config")))
        objective = TrialObjective(
            score=as_float(raw["score"], "score"),
            slo_met=as_bool(raw["slo_met"], "slo_met"),
            best_concurrency=opt_int(raw.get("best_concurrency"), "best_concurrency"),
            best_output_tps=opt_float(raw.get("best_output_tps"), "best_output_tps"),
            best_ttft_p50_s=opt_float(raw.get("best_ttft_p50_s"), "best_ttft_p50_s"),
            ttft_p50_slo_s=as_float(raw["ttft_p50_slo_s"], "ttft_p50_slo_s"),
            cells_evaluated=as_int(raw["cells_evaluated"], "cells_evaluated"),
        )
        note = raw.get("note", "")
        return cls(
            trial_id=as_int(raw["trial_id"], "trial_id"),
            config=config,
            objective=objective,
            note=note if isinstance(note, str) else "",
        )


def read_ledger(path: Path) -> list[TrialRecord]:
    """Read all trials. A missing ledger is an empty run (the first trial), not an
    error; a malformed line IS an error — silently skipping it would lose history."""
    if not path.exists():
        return []
    records: list[TrialRecord] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            records.append(TrialRecord.from_dict(json.loads(line)))
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            raise ValueError(f"{path}:{lineno}: malformed ledger row: {exc}") from exc
    return records


def append_record(path: Path, record: TrialRecord) -> None:
    """Append one trial. Creates the parent dir and file if absent (a new run)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record.to_dict()) + "\n")


def next_trial_id(records: Sequence[TrialRecord]) -> int:
    """The id for the next trial: one past the max seen (0 for an empty ledger). Not
    ``len`` — robust to a ledger whose ids are non-contiguous."""
    return max((r.trial_id for r in records), default=-1) + 1


def best_record(records: Sequence[TrialRecord]) -> TrialRecord | None:
    """The highest-scoring trial so far, or None for an empty ledger. Ties break toward
    the EARLIER trial (don't churn the incumbent on an equal score)."""
    best: TrialRecord | None = None
    for r in records:
        if best is None or r.objective.score > best.objective.score:
            best = r
    return best


def keep_decision(candidate: TrialRecord, prior_best: TrialRecord | None) -> bool:
    """Keep iff the candidate strictly improves on the prior best (or there is none).
    Strict improvement avoids accepting equal-score configs that only add KV pressure."""
    if prior_best is None:
        return True
    return candidate.objective.score > prior_best.objective.score
