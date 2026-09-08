"""Diagnostic issue/memory activity counts; these are not success scores."""
import argparse
import collections
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
manifest = json.loads((args.root / "manifest.json").read_text())
rows = []
for slot in manifest["slots"]:
    folder = args.root / "cases" / slot["lifecycle"] / f"stage-{slot['stage']}"
    if not (folder / "result.json").is_file():
        continue
    result = json.loads((folder / "result.json").read_text())
    executions = result["receipt_assessment"]["executions"]
    commands = collections.Counter(e["command"] for e in executions if e.get("returncode") == 0)
    rows.append({**slot, "host_success": result["host_success"],
                 "task_closed": result["task_closed"],
                 "successful_command_counts": dict(commands),
                 "any_memory_write": bool(result["receipt_assessment"]["agent_writes"]),
                 "any_memory_read": bool(result["receipt_assessment"]["agent_reads"]),
                 "administrative_memory_reads": result["administrative_memory_reads"]})

def counts(selected):
    return {"assessed": len(selected),
            "host_success": sum(r["host_success"] for r in selected),
            "task_closed": sum(r["task_closed"] for r in selected),
            "any_memory_write": sum(r["any_memory_write"] for r in selected),
            "any_memory_read": sum(r["any_memory_read"] for r in selected),
            "administrative_memory_reads": sum(r["administrative_memory_reads"] for r in selected),
            "sessions_with_successful_command": {command: sum(r["successful_command_counts"].get(command, 0) > 0 for r in selected)
                                                 for command in ("show", "update", "close", "prime", "memories", "recall", "remember")}}

report = {"schema": "policy-handoff-workflow-counts.v1", "rows": rows,
          "overall": counts(rows),
          "phase": {phase: counts([r for r in rows if r["phase"] == phase]) for phase in manifest["phases"]},
          "limits": ["Task assignment names an issue ID; comparison with voluntary memory decisions is descriptive, not randomized issue-versus-memory causality.",
                     "Executed memory reads include searches and same-session readback; use the semantic audits for relevant full prior-record use.",
                     "Administrative snapshots are separate from agent reads; full raw receipts do not guarantee complete delivery after output piping."]}
with args.out.open("x") as output:
    json.dump(report, output, indent=2)
    output.write("\n")
print(json.dumps(report["overall"], indent=2))
