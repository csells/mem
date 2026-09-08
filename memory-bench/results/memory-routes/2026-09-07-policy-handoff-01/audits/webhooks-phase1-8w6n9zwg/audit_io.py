"""Evidence packaging only: all semantic findings are supplied by the reviewer."""
from pathlib import Path
import hashlib
import json

AUDIT = Path(__file__).resolve().parent
COHORT = AUDIT.parents[1]


def write_slot(slot, findings):
    lifecycle, stage = slot.rsplit("-", 1)
    folder = COHORT / "cases" / lifecycle / ("stage-" + stage)
    result = json.loads((folder / "result.json").read_text())
    assert result["slot"] == slot and result["family"] == "webhooks"
    files = ["result.json", "task.json", "tasks-before.json", "tasks-after.json",
             "memory-before.json", "memory-after.json", "tool-calls.json", "stream.jsonl",
             "raw-receipts.json", "workspace-before/main.py", "workspace-after/main.py",
             "workspace-before/vendor/protocol-1.md", "workspace-after/vendor/protocol-1.md"]
    report = {
        "slot": slot,
        "review": "Manual semantic audit of actual bodies, source, tools, and issue history",
        "metadata": {key: result.get(key) for key in ["profile_id", "host", "arm", "stage",
                     "corpus_family", "catalog_mode", "model_requested", "models_observed",
                     "session_id", "host_success", "infrastructure_fault", "errors",
                     "artifact_passed", "artifact_correct", "artifact_total", "task_closed"]},
        "record_bodies_before": json.loads((folder / "memory-before.json").read_text()),
        "record_bodies_after": json.loads((folder / "memory-after.json").read_text()),
        "findings": findings,
        "evidence_sha256": {str((folder / name).relative_to(COHORT)):
                            hashlib.sha256((folder / name).read_bytes()).hexdigest()
                            for name in files if (folder / name).is_file()},
    }
    with (AUDIT / (slot + ".json")).open("x") as output:
        json.dump(report, output, indent=2, ensure_ascii=False)
    return report
