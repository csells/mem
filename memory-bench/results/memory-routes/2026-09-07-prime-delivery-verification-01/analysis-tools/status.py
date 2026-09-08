"""Read only this cohort's receipts, launch handles and durable progress log."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def inspect(root, recovery, phase):
    manifest = json.loads((root / "manifest.json").read_text())
    selected = [row for row in manifest["slots"] if row["phase"] == phase]
    rows, active = [], []
    for slot in manifest["slots"]:
        folder = root / "cases" / slot["lifecycle"] / f"stage-{slot['stage']}"
        if (folder / "result.json").is_file():
            rows.append(json.loads((folder / "result.json").read_text()))
        elif (folder / "process.json").is_file():
            process = json.loads((folder / "process.json").read_text())
            active.append({"slot": slot["slot"], "pid": process["pid"],
                           "pid_exists": alive(process["pid"]),
                           "elapsed_s": round((time.time_ns() - process["started_ns"]) / 1e9)})
    launch_path = recovery / f"{phase}-launch.json"
    launch = json.loads(launch_path.read_text()) if launch_path.exists() else None
    summary_path = recovery / phase / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else None
    log_path = recovery / f"{phase}-console.log"
    lines = log_path.read_text().splitlines() if log_path.exists() else []
    return {
        "observed_ns": time.time_ns(), "phase": phase,
        "phase_assessed": sum(r["phase"] == phase for r in rows),
        "phase_planned": len(selected), "overall_assessed": len(rows),
        "overall_correct_artifacts": sum(r["artifact_passed"] for r in rows),
        "overall_planned": len(manifest["slots"]),
        "supervisor": ({"pid": launch["pid"], "pid_exists": alive(launch["pid"])} if launch else None),
        "active_process_claims": active, "phase_status": summary["status"] if summary else None,
        "last_progress": next((s for s in reversed(lines) if s.startswith("PROGRESS ")), None),
        "last_events": lines[-5:],
        "limits": "PID existence alone does not establish useful work or explain a wait.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--recovery", type=Path, required=True)
    parser.add_argument("--phase", choices=["phase1", "phase2"], required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.root, args.recovery, args.phase), indent=2))
