"""Append manually adjudicated stage findings; no semantic automation or model calls."""
import hashlib
import json
import time
from pathlib import Path

AUDIT = Path(__file__).resolve().parent
COHORT = AUDIT.parents[1]


def save(lifecycle, stage, **manual):
    folder = COHORT / "cases" / lifecycle / f"stage-{stage}"
    result = json.loads((folder / "result.json").read_text())
    before = json.loads((folder / "memory-before.json").read_text())
    after = json.loads((folder / "memory-after.json").read_text())
    required = {"capture", "exposure", "analysis", "saved_claim_findings", "unsupported_standing_or_history_mutation"}
    if stage in (2, 4, 5):
        required.add("eligible_use")
    if not required.issubset(manual):
        raise ValueError(f"Missing manual decisions: {required - manual.keys()}")
    value = {
        "schema": "prime-courier-stage-audit.v1",
        "created_ns": time.time_ns(),
        **{k: result[k] for k in ("slot", "lifecycle", "stage", "profile_id", "family", "arm", "catalog_mode", "corpus_family")},
        "status": "assessed",
        "artifact": {"passed": result["artifact_passed"], "correct": result["artifact_correct"], "total": result["artifact_total"]},
        "record_count_before": len(before),
        "record_count_after": len(after),
        "record_unchanged": before == after,
        "evidence_root": str(folder.relative_to(COHORT)),
        "evidence_sha256": {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in ("result.json", "task.json", "memory-before.json", "memory-after.json", "tool-calls.json", "artifact-grade.json", "stream.jsonl", "launch-prompt.txt")},
        **manual,
    }
    out = AUDIT / f"{result['slot']}.json"
    with out.open("x") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return out
