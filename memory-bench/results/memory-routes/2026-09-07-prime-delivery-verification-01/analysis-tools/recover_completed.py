"""Assess one already completed Codex turn; never invokes an agent or repairs work."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path

from membench.runner import memory_e2e_receipts as receipts
from membench.runner import memory_model_profiles as profiles
from membench.runner.memory_e2e_audit import classify_operation
from scripts import memory_e2e_experiment as e2e
from scripts import memory_policy_handoff_experiment as policy
from scripts import memory_routes_experiment as base
from scripts import memory_unprompted_experiment as legacy
from scripts import memory_unprompted_smoke as smoke

OUTPUTS = (
    "stream.jsonl",
    "stderr.txt",
    "raw-receipts.json",
    "tool-calls.json",
    "memory-after.json",
    "tasks-after.json",
    "workspace-after",
    "native-after",
    "host-evidence",
    "memory-catalog-after.json",
    "artifact-grade.json",
    "result.json",
    "recovery.json",
)


def preflight(out: Path, slot: str) -> tuple[dict, dict, dict, Path, Path, dict]:
    manifest = json.loads((out / "manifest.json").read_text())
    legacy.assert_frozen(manifest)
    row = next(r for r in manifest["slots"] if r["slot"] == slot)
    if row["host"] != "codex":
        raise ValueError("This recovery only admits a completed Codex turn")
    evidence = legacy.session_path(out, row)
    for name in OUTPUTS:
        if (evidence / name).exists() or (evidence / name).is_symlink():
            raise FileExistsError(evidence / name)
    state = json.loads((evidence.parent / "state.json").read_text())
    local = Path(state["scratch"]) / f"stage-{row['stage']}"
    process = json.loads((evidence / "process.json").read_text())
    try:
        os.kill(process["pid"], 0)
    except ProcessLookupError:
        pass
    else:
        raise ValueError("Recorded process still exists; do not recover a running turn")
    raw = local / "stdout-private.jsonl"
    events = [json.loads(line) for line in raw.read_text().splitlines() if line.strip()]
    if not events or events[-1].get("type") != "turn.completed":
        raise ValueError("No terminal completed-turn receipt; no manufactured completion")
    elapsed = (raw.stat().st_mtime_ns - process["started_ns"]) / 1e9
    if not 0 < elapsed < manifest["timeout_seconds"]:
        raise ValueError("Completion receipt is not demonstrably within the original deadline")
    if (local / "grade.sb").exists():
        raise FileExistsError("Existing grading state must remain untouched")
    return manifest, row, state, evidence, local, process


def recover(out: Path, slot: str) -> dict:
    manifest, row, state, evidence, local, process = preflight(out, slot)
    before = json.loads((evidence / "memory-before.json").read_text())
    task = json.loads((evidence / "task.json").read_text())
    launch = json.loads((evidence / "launch.json").read_text())
    requested = profiles.get_profile(row["profile_id"]).model
    originals = [
        local / n for n in ("stdout-private.jsonl", "stderr-private.txt", "bin/receipts.jsonl")
    ]
    original_hashes = {str(p): base.sha(p) for p in originals}
    elapsed = (originals[0].stat().st_mtime_ns - process["started_ns"]) / 1e9
    secrets = smoke.secret_values(dict(os.environ), local)
    stream, leaked = smoke.sanitize(originals[0].read_text(), secrets)
    stderr, stderr_leaked = smoke.sanitize(originals[1].read_text(), secrets)
    observed = profiles.observe(row["profile_id"], stream, local)
    if not observed.completed or not observed.success or observed.models != [requested]:
        raise ValueError("Existing stream does not establish successful requested-model completion")
    rows_text, receipt_leaked = smoke.sanitize(json.dumps(receipts.read(originals[2])), secrets)
    rows = json.loads(rows_text)
    ops = receipts.assess(
        rows,
        root_pid=process["pid"],
        leg=str(row["stage"]),
        session=launch["harness_session"],
        tool_outputs=[str(c.result or "") for c in observed.calls],
        binary=str(base.BD),
        store=state["store"],
    )
    if leaked or stderr_leaked or receipt_leaked or ops["unknown_execution"]:
        raise ValueError("Recovery requires clean, complete original receipts")
    # Existing-state setup only reconstructs the administrative environment.
    loaded = legacy.setup(out, row, corpus_root=policy.CORPUS)
    workspace, store = Path(state["workspace"]), Path(state["store"])
    after = base.memories(store, loaded["env"])
    actual_tasks = e2e.all_tasks(store, loaded["env"])
    calls = [c.model_dump(mode="json") for c in observed.calls]
    for name, text in (("stream.jsonl", stream), ("stderr.txt", stderr)):
        with (evidence / name).open("x") as dest:
            dest.write(text)
    for name, data in (
        ("raw-receipts.json", rows),
        ("tool-calls.json", calls),
        ("memory-after.json", after),
        ("tasks-after.json", actual_tasks),
    ):
        legacy.write(evidence / name, data)
    e2e.snapshot(workspace, evidence / "workspace-after")
    legacy.native_snapshot(local / "native", evidence / "native-after")
    profiles.export_evidence(row["profile_id"], local, evidence / "host-evidence")
    if (evidence / "memory-catalog-before.json").is_file():
        legacy.write(
            evidence / "memory-catalog-after.json",
            legacy.catalog_evidence(local / "memory-catalog.json"),
        )
    artifact = legacy.grade(workspace, local, row, corpus_root=policy.CORPUS)
    legacy.write(evidence / "artifact-grade.json", artifact)
    actions = [
        classify_operation(
            e["operation_argv"], e["returncode"], e["stdout"], e["stderr"], before, after
        )
        for e in ops["executions"]
    ]
    recovery = {
        "schema": "completed-turn-posthoc-assessment.v1",
        "assessed_ns": time.time_ns(),
        "source_sha256": base.sha(Path(__file__)),
        "manifest_sha256": base.sha(out / "manifest.json"),
        "original_evidence_sha256": original_hashes,
        "model_relaunched": False,
        "cause": "Supervisor progress write raised BrokenPipeError; model independently completed",
        "process_exit_observed": False,
        "terminal_model_event": "turn.completed",
        "duration_source": "Original stream file last-write time minus saved launch time; approximate",
        "posthoc_administrative_memory_reads": 1,
        "limits": "OS exit status unavailable. Original stream and current scratch state retained; no repair.",
    }
    result = {
        **row,
        "task_id": task["id"],
        "delivery": json.loads((evidence / "delivery.json").read_text()),
        "model_requested": requested,
        "models_observed": observed.models,
        "session_id": observed.session_id,
        "exit_code": None,
        "process_exit_observed": False,
        "timed_out": False,
        "host_completed": observed.completed,
        "host_success": observed.success,
        "errors": observed.errors,
        "duration_s": elapsed,
        "duration_source": recovery["duration_source"],
        "cost_usd": observed.cost_usd,
        "usage": observed.usage,
        "artifact_passed": artifact["passed"],
        "artifact_correct": artifact["correct"],
        "artifact_total": artifact["total"],
        "memory_before_count": len(before),
        "memory_after_count": len(after),
        "record_unchanged": before == after,
        "actions": actions,
        "action_counts": dict(Counter(a["action"] for a in actions)),
        "receipt_assessment": ops,
        "credential_redaction_required": False,
        "task_closed": any(
            t.get("id") == task["id"] and t.get("status") == "closed" for t in actual_tasks
        ),
        "package_changed_paths": [
            p
            for p, sha in state["package"]["files"].items()
            if not Path(p).is_file() or base.sha(Path(p)) != sha
        ],
        "administrative_memory_reads": 2,
        "infrastructure_fault": True,
        "infrastructure_fault_kind": "supervisor_logging; recovered completed turn",
        "recovered_assessment": recovery,
        **e2e.instruction_reads(calls, workspace),
    }
    legacy.assert_frozen(manifest)
    if any(base.sha(Path(p)) != sha for p, sha in original_hashes.items()):
        raise ValueError("Original evidence changed during assessment; preserve partial outputs")
    legacy.write(evidence / "recovery.json", recovery)
    legacy.write(evidence / "result.json", result)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "slot",
                    "artifact_passed",
                    "artifact_correct",
                    "artifact_total",
                    "exit_code",
                )
            }
        )
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--slot", required=True)
    parser.add_argument("--assess", action="store_true", required=True)
    args = parser.parse_args()
    recover(args.root.resolve(), args.slot)
