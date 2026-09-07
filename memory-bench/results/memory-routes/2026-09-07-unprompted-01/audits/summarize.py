"""Read-only mechanical cohort summary; no semantic memory grading or model calls."""

import collections
import json
from pathlib import Path


root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "manifest.json").read_text())
results = {
    r["slot"]: r
    for p in sorted((root / "cases").glob("*/stage-*/result.json"))
    for r in [json.loads(p.read_text())]
}
groups = collections.defaultdict(list)
for slot in manifest["slots"]:
    groups[(slot["mode"], slot["host"], slot["arm"])].append(slot)
output = {"scheduled": len(manifest["slots"]), "assessed": len(results), "groups": []}
for group, slots in sorted(groups.items()):
    rows = [results[s["slot"]] for s in slots if s["slot"] in results]
    started = sum(
        (root / "cases" / s["lifecycle"] / f"stage-{s['stage']}" / "process.json").exists()
        for s in slots
    )
    action_sessions = collections.Counter()
    for row in rows:
        action_sessions.update(set(row["action_counts"]))
    output["groups"].append({
        "mode": group[0], "host": group[1], "arm": group[2],
        "planned": len(slots), "started": started, "assessed": len(rows),
        "correct_artifacts": sum(r["artifact_passed"] for r in rows),
        "host_success": sum(r["host_success"] for r in rows),
        "timed_out": sum(r["timed_out"] for r in rows),
        "infrastructure_faults": sum(r["infrastructure_fault"] for r in rows),
        "sessions_with_actions": dict(action_sessions),
        "records_changed_sessions": sum(not r["record_unchanged"] for r in rows),
        "native_skill_sessions": sum(bool(r["native_skill_calls"]) for r in rows),
        "memory_reference_read_sessions": sum(bool(r["memory_workflow_read_calls"]) for r in rows),
        "package_changed_sessions": sum(bool(r["package_changed_paths"]) for r in rows),
        "administrative_reads": sum(r["administrative_memory_reads"] for r in rows),
        "reported_usd": sum(r["cost_usd"] for r in rows if r["cost_usd"] is not None),
        "reported_usd_sessions": sum(r["cost_usd"] is not None for r in rows),
        "stage_results": [{"slot":r["slot"], "correct":r["artifact_correct"],
                           "total":r["artifact_total"], "actions":r["action_counts"]}
                          for r in rows],
    })
output["blocked"] = {p.stem: json.loads(p.read_text()) for p in (root / "blocked").glob("*.json")}
print(json.dumps(output, indent=2))
