"""An autoresearch-style autonomous tuning loop over the local inference rig.

Adapted from karpathy/autoresearch (MIT): give an agent a fixed-budget experiment,
one comparable metric, and a keep-or-discard ledger, and let it iterate overnight.
The mapping:

  autoresearch            →  here
  ----------------------     -----------------------------------------------
  train.py (agent edits)  →  TrialConfig (the rig knobs the agent edits)
  val_bpb (the metric)    →  TrialObjective (max output-tps under a TTFT SLO)
  5-minute fixed budget   →  a fixed sweep (fixed workload + concurrency grid)
  experiment log          →  the JSONL ledger (keep/discard vs best-so-far)
  program.md (the skill)  →  membench/autotune/program.md

This package is the deterministic SUBSTRATE only. The decision of *which config to
try next* belongs to the agent reading the ledger + program.md (ZFC) — there is no
hardcoded search heuristic here.
"""

from __future__ import annotations

from membench.autotune.calibrate import ShapeStats, calibrated_config, measure_sequences
from membench.autotune.config import TrialConfig
from membench.autotune.ledger import TrialRecord, append_record, best_record, keep_decision
from membench.autotune.objective import TrialObjective, score_rows

__all__ = [
    "ShapeStats",
    "TrialConfig",
    "TrialObjective",
    "TrialRecord",
    "append_record",
    "best_record",
    "calibrated_config",
    "keep_decision",
    "measure_sequences",
    "score_rows",
]
