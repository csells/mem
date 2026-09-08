"""Bounded read-only observer for recovery02 phase1; no agents or bd commands."""

import json
import time
from pathlib import Path

import audit_workflow as audit

started = time.monotonic()
last = None
while time.monotonic() - started < 10800:
    count = len(list((audit.COHORT / "cases").glob("*/stage-*/result.json")))
    if count != last:
        audit.capture()
        print(
            json.dumps({"assessed": count, "target": 68, "observed_ns": time.time_ns()}), flush=True
        )
        last = count
    if count == 68:
        result = audit.snapshot("phase1", 68)
        audit.write(
            Path(__file__).with_name("phase1-watcher-completed.json"),
            {
                "status": "completed",
                "assessed": result["assessed"],
                "completed_ns": time.time_ns(),
            },
        )
        break
    if count > 68:
        raise RuntimeError(
            "Phase2 began before phase1 workflow checkpoint; do not mislabel snapshot"
        )
    summary = audit.COHORT / "recovery-02/phase1/summary.json"
    if summary.exists():
        raise RuntimeError("Phase stopped below68 assessed; no completion inferred")
    time.sleep(15)
else:
    raise TimeoutError("Audit watcher reached its3hour bound without phase1 completion")
