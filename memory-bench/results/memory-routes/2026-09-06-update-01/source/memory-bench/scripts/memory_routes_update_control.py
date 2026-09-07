"""Explicit permanent memory revision followed by a fresh exact-key goal.

Run ``python -m scripts.memory_routes_update_control --out PATH`` to freeze the
two-session plan; add --fire after review. A failed semantic update is transferred
unchanged to the goal. Infrastructure failures halt without repurchasing either leg.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import math
import tempfile
from pathlib import Path
from typing import Any

from membench.runner.memory_routes_grade import grade_capture
from membench.runner.memory_routes_runtime import experiment_env
from scripts import memory_routes_csv_challenge as csv_control
from scripts import memory_routes_experiment as driver


def make_plan(source: Path, budget: float) -> tuple[dict[str, Any], dict[str, str], bytes]:
    if not math.isfinite(budget) or budget <= 0:
        raise ValueError("Session budget must be finite and positive")
    task, captured, source_hashes = csv_control.load_capture(source)
    if task.expected_config["csv_export"]["delimiter"] == ";":
        raise ValueError("Source agreement already uses the intended revised delimiter")
    revised = copy.deepcopy(task.expected_config)
    revised["csv_export"]["delimiter"] = ";"
    memory = source / "cases" / f"{task.id}-protocol" / "establish/memory.json"
    snapshot = memory.read_bytes()
    prompts = {
        "update": (
            "Approved PERMANENT revision for all future Acme finance invoice exports. "
            "This changes the standing agreement, not just one export.\n"
            f"Decision reference: `{task.key}`.\n"
            "Source label: approved permanent revision in current task.\n\n"
            "Change only csv_export.delimiter to a semicolon (;). All other agreed settings "
            "remain unchanged. Recover the existing agreement, then create config.json with "
            "the complete revised project configuration, preserving all field names, JSON "
            "types and unchanged values. Validate the actual file. Persist the complete "
            "revised agreement at the SAME existing Decision reference key, including its "
            "approved JSON and the source label above. Confirm the successful write "
            "acknowledgment and read back that exact key to verify the revision before "
            "closing the assigned task. A fresh future session must receive this permanent "
            "revision from memory alone."
        ),
        "goal": (
            "Create config.json for the Acme finance invoice export using the current "
            "permanent agreement recorded in the preceding work session. This fresh "
            "checkout contains none of that session's files, task notes or configuration. "
            "Use the current saved agreement rather than conventional defaults; preserve "
            "the complete project's field names, JSON types and values. Validate the "
            "actual JSON file.\n\n"
            f"The exact Decision reference key is `{task.key}`."
        ),
    }
    sources = [
        Path(__file__).resolve(),
        Path(driver.__file__).resolve(),
        Path(csv_control.__file__).resolve(),
        *sorted((driver.REPO / "memory-bench/membench").rglob("*.py")),
    ]
    return (
        {
            "schema": "memory-routes-update-control.v1",
            "source_run": str(source.resolve()),
            "source_evidence_sha256": source_hashes,
            "source_memory_sha256": hashlib.sha256(snapshot).hexdigest(),
            "source_sha256": {str(p.relative_to(driver.REPO)): driver.sha(p) for p in sources},
            "binary_sha256": {
                str(p): driver.sha(p) for p in (driver.BD, driver.CLAUDE, driver.PYTHON)
            },
            "model": driver.MODEL,
            "policy": "protocol",
            "policy_prompt": driver.BASE + driver.EXAMPLES + driver.PROCEDURE,
            "canonical_key": task.key,
            "original_config": task.expected_config,
            "expected_config": revised,
            "prompts": prompts,
            "schedule": ["update", "goal"],
            "planned_sessions": 2,
            "session_budget_usd": budget,
            "interpretation": (
                "Targeted compliance with an explicit permanent revision, followed by fresh "
                "use of actual saved memory. Only actual KV state after update crosses the "
                "session boundary; a missing or wrong update is never repaired. Canonical "
                "literal capture and both final JSON artifacts are scored separately. "
                "This does not estimate spontaneous update behavior or test immutable "
                "historical versions. Literal JSON checks do not certify surrounding prose."
            ),
        },
        captured,
        snapshot,
    )


def transfer(
    store: Path,
    env: dict[str, str],
    captured: dict[str, str],
    evidence: Path,
) -> None:
    driver.initialize_store(store, env, evidence)
    for key, body in captured.items():
        driver.checked_bd(["remember", body, "--key", key], store, env)
    if driver.memories(store, env) != captured:
        raise RuntimeError("Transferred memory differs from the actual captured state")


def run_control(out: Path, plan: dict[str, Any], captured: dict[str, str]) -> None:
    evidence = out / "run"
    evidence.mkdir()
    scratch = Path(tempfile.mkdtemp(prefix="mem-update-", dir="/tmp")).resolve()
    driver.new_json(evidence / "started.json", {"scratch": str(scratch)})
    try:
        setup = scratch / "setup"
        setup.mkdir()
        for name in ("config", "tmp", "bin"):
            (setup / name).mkdir()
        env = experiment_env(setup / "config", setup / "tmp", setup / "bin")
        update_store = scratch / "store-update"
        transfer(update_store, env, captured, evidence / "initialization-update.json")
        driver.new_json(evidence / "transferred-update.json", captured)
        update, _ = driver.run_leg(
            case=scratch,
            evidence=evidence / "update",
            leg="update",
            policy="protocol",
            prompt=plan["prompts"]["update"],
            store=update_store,
            native_from=None,
            expected=plan["expected_config"],
            budget=plan["session_budget_usd"],
        )
        saved = driver.memories(update_store, env)
        if saved != csv_control._read_json(evidence / "update/memory.json"):
            raise RuntimeError("Update store differs from the recorded post-session memory")
        capture = grade_capture(saved, plan["canonical_key"], plan["expected_config"])
        driver.new_json(evidence / "captured-after-update.json", saved)
        driver.new_json(evidence / "canonical-update-grade.json", capture)
        # Deliberately unconditional on semantic capture/artifact success. A bad
        # update must remain bad in the fresh goal; only infrastructure halts.
        goal_store = scratch / "store-goal"
        transfer(goal_store, env, saved, evidence / "initialization-goal.json")
        driver.new_json(evidence / "transferred-goal.json", saved)
        goal, _ = driver.run_leg(
            case=scratch,
            evidence=evidence / "goal",
            leg="goal",
            policy="protocol",
            prompt=plan["prompts"]["goal"],
            store=goal_store,
            native_from=None,
            expected=plan["expected_config"],
            budget=plan["session_budget_usd"],
        )
        driver.new_json(
            evidence / "result.json",
            {
                "canonical_update": capture,
                "update_artifact": update["artifact"],
                "goal_artifact": goal["artifact"],
                "saved_memory_sha256": driver.sha(evidence / "captured-after-update.json"),
                "session_result_sha256": {
                    leg: driver.sha(evidence / leg / "result.json") for leg in ("update", "goal")
                },
                "legs": {"update": update, "goal": goal},
            },
        )
        print(
            f"UPDATE CONTROL: canonical={capture['passed']} "
            f"update={update['artifact']['passed']} goal={goal['artifact']['passed']}",
            flush=True,
        )
    except Exception as exc:
        driver.new_json(evidence / "halt.json", {"type": type(exc).__name__, "message": str(exc)})
        raise


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-run", type=Path, default=csv_control.DEFAULT_SOURCE)
    parser.add_argument("--session-budget", type=float, default=0.75)
    parser.add_argument("--fire", action="store_true")
    args = parser.parse_args(argv)
    plan, captured, original_bytes = make_plan(args.source_run, args.session_budget)
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = args.out / "manifest.json"
    snapshot = args.out / "source-memory.json"
    if manifest.exists():
        if csv_control._read_json(manifest) != plan or snapshot.read_bytes() != original_bytes:
            raise ValueError("Frozen update plan or source snapshot differs; use a new output")
    else:
        if any(args.out.iterdir()):
            raise ValueError("Nonempty update-control output has no manifest")
        driver.new_json(manifest, plan)
        with snapshot.open("xb") as target:
            target.write(original_bytes)
    print(f"PLAN 2 update-control sessions at {args.out}", flush=True)
    if not args.fire:
        return
    evidence = args.out / "run"
    if evidence.exists():
        if not (evidence / "result.json").exists():
            raise ValueError(f"Interrupted update control cannot be repurchased: {evidence}")
        result = csv_control._read_json(evidence / "result.json")
        for leg in ("update", "goal"):
            if result.get("session_result_sha256", {}).get(leg) != driver.sha(
                evidence / leg / "result.json"
            ) or result.get("legs", {}).get(leg) != csv_control._read_json(
                evidence / leg / "result.json"
            ):
                raise ValueError("Completed update-control session evidence differs")
        if result.get("saved_memory_sha256") != driver.sha(evidence / "captured-after-update.json"):
            raise ValueError("Completed update-control memory evidence differs")
        return
    run_control(args.out, plan, captured)


if __name__ == "__main__":
    main()
