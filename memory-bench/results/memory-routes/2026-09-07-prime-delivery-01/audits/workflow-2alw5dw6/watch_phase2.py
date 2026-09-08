"""Bounded read-only observer for recovery02 phase2; no agents or bd commands."""

import json
import time
from pathlib import Path

import audit_workflow as audit

started = time.monotonic()
last = None
while time.monotonic() - started < 21600:
    count = len(list((audit.COHORT / "cases").glob("*/stage-*/result.json")))
    if count != last:
        audit.capture()
        print(
            json.dumps({"assessed": count, "target": 204, "observed_ns": time.time_ns()}),
            flush=True,
        )
        last = count
    if count == 204:
        result = audit.snapshot("final", 204)
        audit.write(
            Path(__file__).with_name("phase2-watcher-completed.json"),
            {
                "status": "completed",
                "assessed": result["assessed"],
                "completed_ns": time.time_ns(),
            },
        )
        break
    if count > 204:
        raise RuntimeError("Cohort exceeded204 assessed; do not mislabel frozen completion")
    summary = audit.COHORT / "recovery-02/phase2/summary.json"
    if summary.exists():
        raise RuntimeError("Phase stopped below204 assessed; no completion inferred")
    time.sleep(15)
else:
    raise TimeoutError("Audit watcher reached its6hour bound without phase2 completion")
