"""Read-only evidence access and exclusive offline audit publication. No inference."""
from pathlib import Path
import hashlib
import json
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent


def save(review):
    p = ROOT / "cases" / review["lifecycle"] / f"stage-{review['stage']}"
    result = json.loads((p / "result.json").read_text())
    review.update({"audit_schema": "ordinary-memory-offline-review.v1", "audited_ns": time.time_ns(),
        "slot": result["slot"], "host": result["host"], "arm": result["arm"], "family": result["family"],
        "session_id": result["session_id"],
        "completion": {key: result[key] for key in ("host_success", "host_completed", "exit_code", "timed_out", "infrastructure_fault")},
        "artifact": {"passed": result["artifact_passed"], "correct": result["artifact_correct"], "total": result["artifact_total"]},
        "source_sha256": {str((p / name).relative_to(ROOT)): hashlib.sha256((p / name).read_bytes()).hexdigest()
            for name in ("result.json", "task.json", "tasks-before.json", "tasks-after.json", "memory-before.json", "memory-after.json", "tool-calls.json", "raw-receipts.json", "stream.jsonl")}})
    path = OUT / f"{result['slot']}.audit.json"
    with path.open("x") as stream:
        json.dump(review, stream, indent=2)
    return path


def inventory():
    entries = []
    for p in sorted((ROOT / "cases").glob("*/stage-*/result.json")):
        if not p.parent.parent.name.startswith(("claude-", "codex-")):
            continue
        r = json.loads(p.read_text())
        entries.append({**{key: r.get(key) for key in ("slot", "host", "family", "arm", "stage", "artifact_correct", "artifact_total", "action_counts", "memory_after_count", "host_success", "infrastructure_fault")},
            "audited": (OUT / f"{r['slot']}.audit.json").exists()})
    return entries
