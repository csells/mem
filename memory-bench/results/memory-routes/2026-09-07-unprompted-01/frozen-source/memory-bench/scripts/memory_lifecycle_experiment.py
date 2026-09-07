"""Three-arm cumulative memory lifecycles; real CLI sessions in fresh scratch.

Freeze with --out PATH, then add --fire. Prior results and interrupted purchases
are never overwritten. Carryover is exactly the preceding session's entire memory
snapshot, including its mistakes. The historical key is an explicit public task
requirement, not a history feature fabricated by the harness.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import random
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from pathlib import Path
from typing import Any

from membench.runner import (
    bd_receipts,
    memory_lifecycle_gate,
    memory_lifecycle_hooks,
    memory_routes_grade,
)
from membench.runner.memory_lifecycle_corpus import (
    SELECTIVE_CAPTURE_GUIDANCE,
    WORKFLOW_CHECK_GUIDANCE,
    LifecycleStage,
    LifecycleTask,
    build_lifecycles,
)
from membench.runner.memory_routes_grade import grade_capture
from membench.runner.memory_routes_runtime import experiment_env
from scripts import memory_routes_experiment as base

POLICIES = ("existing", "selective", "checked")


def policy_guidance(policy: str) -> str:
    if policy not in POLICIES:
        raise ValueError("Unknown lifecycle policy")
    return (
        base.EXAMPLES
        + base.PROCEDURE
        + (SELECTIVE_CAPTURE_GUIDANCE if policy != "existing" else "")
        + (
            WORKFLOW_CHECK_GUIDANCE + "\nTask closure and session completion are checked "
            "against these public requirements and actual write/readback receipts. "
            "Resolve reported omissions before completing the task.\n"
            if policy == "checked"
            else ""
        )
    )


def install_checks(
    local: Path, store: Path, task_id: str, *, stage: LifecycleStage
) -> dict[str, Any]:
    """Copy only the enforcement implementation and public policy into the sandbox."""
    package = local / "bin" / "membench" / "runner"
    package.mkdir(parents=True)
    (package.parent / "__init__.py").touch()
    (package / "__init__.py").touch()
    for module in (bd_receipts, memory_routes_grade, memory_lifecycle_gate, memory_lifecycle_hooks):
        assert module.__file__
        shutil.copyfile(module.__file__, package / Path(module.__file__).name)
    spec = {
        "binary": str(base.BD),
        "store": str(store),
        "artifact": str(local / "work/config.json"),
        "receipts": str(local / "receipts.jsonl"),
        "events": str(local / "gate-events.jsonl"),
        "task_id": task_id,
        "required_write_keys": list(stage.required_write_keys),
        "require_read": stage.retrieval_required,
        "read_matches_artifact": stage.name != "revise",
    }
    spec_path = local / "bin/gate-policy.json"
    base.new_json(spec_path, spec)
    # The initial shim was produced in this new scratch session only; retain its
    # bytes before replacing it with the completion-aware entry point.
    shim = local / "bin/bd"
    shim.rename(local / "bin/bd-without-completion-check")
    shim.write_text(
        f"#!{base.PYTHON}\nimport sys\n"
        "from membench.runner.memory_lifecycle_hooks import cli_main\n"
        f"sys.exit(cli_main({str(spec_path)!r}))\n"
    )
    shim.chmod(0o700)
    stop = local / "bin/stop.py"
    stop.write_text(
        "from membench.runner.memory_lifecycle_hooks import stop_main\n"
        f"stop_main({str(spec_path)!r})\n"
    )
    return {"Stop": [{"hooks": [{"type": "command", "command": f"{base.PYTHON} {stop}"}]}]}


def memory_delta(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    return {
        "added": sorted(after.keys() - before.keys()),
        "removed": sorted(before.keys() - after.keys()),
        "changed": sorted(key for key in before.keys() & after.keys() if before[key] != after[key]),
    }


def stage_summary(
    stage: LifecycleStage,
    task: LifecycleTask,
    result: dict[str, Any],
    before: dict[str, str],
    after: dict[str, str],
    task_closed: bool,
    receipts: list[dict[str, Any]],
    events: list[dict[str, Any]],
    workspace: Path,
) -> dict[str, Any]:
    current = (
        task.initial_config
        if stage.expected_version == "v1" and stage.name != "historical"
        else task.revised_config
    )
    # Historical reproduction must leave the standing revised agreement intact.
    current_grade = grade_capture(after, task.key, current)
    history_grade = grade_capture(after, task.historical_key, task.initial_config)
    delta = memory_delta(before, after)
    no_curation = not any(delta.values()) and result["memory_evidence"]["accepted_writes"] == 0
    check = memory_lifecycle_gate.evaluate_gate(
        workspace / "config.json",
        after,
        receipts,
        list(stage.required_write_keys),
        stage.retrieval_required,
        stage.name != "revise",
    )
    extra = sorted(after.keys() - (task.task.decoys.keys() | {task.key, task.historical_key}))
    delivery = (
        result["bd_correct_payload_observed"]
        if (stage.retrieval_required and stage.name != "revise")
        else True
    )
    complete = bool(
        result["artifact"]["passed"]
        and task_closed
        and current_grade["passed"] is True
        and history_grade["passed"] is True
        and not extra
        and (stage.capture_required or no_curation)
        and delivery is True
        and not result.get("behavioral_limit", False)
    )
    return {
        "name": stage.name,
        "artifact": result["artifact"],
        "task_closed": task_closed,
        "current_capture": current_grade,
        "historical_capture": history_grade,
        "delta": delta,
        "extra_keys": extra,
        "no_unnecessary_curation": no_curation,
        "public_completion_check": check,
        "complete_handoff": complete,
        "gate_events": events,
        "enforced_completion": (
            bool(events and events[-1].get("event") == "stop" and events[-1].get("passed"))
            if result.get("policy") == "checked"
            else None
        ),
        "result": result,
    }


def run_lifecycle(out: Path, task: LifecycleTask, policy: str, budget: float) -> None:
    directory = out / "cases" / f"{task.id}-{policy}"
    directory.mkdir(parents=True)
    case = Path(tempfile.mkdtemp(prefix="mem-lifecycle-", dir="/tmp")).resolve()
    base.new_json(
        directory / "started.json", {"scratch": str(case), "task": task.id, "policy": policy}
    )
    try:
        setup = case / "setup"
        for child in ("config", "tmp", "bin"):
            (setup / child).mkdir(parents=True)
        env = experiment_env(setup / "config", setup / "tmp", setup / "bin")
        carried = dict(task.task.decoys)
        stages = []
        for stage in task.stages:
            store = case / f"store-{stage.name}"
            base.initialize_store(store, env, directory / f"initialization-{stage.name}.json")
            for key, body in carried.items():
                base.checked_bd(["remember", body, "--key", key], store, env)
            before = base.memories(store, env)
            if before != carried:
                raise RuntimeError("Lifecycle transfer differs from actual preceding memory")
            base.new_json(directory / f"transferred-{stage.name}.json", before)

            configure = partial(install_checks, stage=stage)

            evidence = directory / stage.name
            result, _ = base.run_leg(
                case=case,
                evidence=evidence,
                leg=stage.name,
                policy=policy,
                prompt=stage.prompt,
                store=store,
                native_from=None,
                expected=stage.expected_config,
                budget=budget,
                guidance_override=policy_guidance(policy),
                configure_session=configure if policy == "checked" else None,
                retain_behavioral_limits=True,
            )
            after = base.memories(store, env)
            assigned = json.loads(
                base.checked_bd(["show", result["task_id"], "--json"], store, env)
            )
            base.new_json(evidence / "task.json", assigned)
            closed = (
                isinstance(assigned, list)
                and len(assigned) == 1
                and assigned[0].get("status") == "closed"
            )
            local = Path(result["scratch"])
            events_path = local / "gate-events.jsonl"
            events = (
                [json.loads(line) for line in events_path.read_text().splitlines()]
                if events_path.exists()
                else []
            )
            if events_path.exists():
                shutil.copyfile(events_path, evidence / "gate-events.jsonl")
                shutil.copyfile(local / "bin/gate-policy.json", evidence / "gate-policy.json")
            if policy == "checked" and (
                (
                    not any(event.get("event") == "stop" for event in events)
                    and not result.get("behavioral_limit")
                )
                or any(event.get("infrastructure_error") for event in events)
            ):
                raise RuntimeError("Completion hook did not produce valid measured Stop evidence")
            receipts = json.loads((evidence / "receipts.json").read_text())
            summary = stage_summary(
                stage, task, result, before, after, closed, receipts, events, evidence / "workspace"
            )
            base.new_json(evidence / "assessment.json", summary)
            stages.append(summary)
            carried = after
        base.new_json(
            directory / "result.json",
            {
                "task": task.id,
                "policy": policy,
                "stages": stages,
                "complete_lifecycle": all(stage["complete_handoff"] for stage in stages),
            },
        )
    except Exception as exc:
        base.new_json(directory / "halt.json", {"type": type(exc).__name__, "message": str(exc)})
        raise


def make_manifest(seed: int, domains: list[str], budget: float) -> dict[str, Any]:
    if not math.isfinite(budget) or budget <= 0:
        raise ValueError("Budget must be finite and positive")
    tasks = [task for task in build_lifecycles(seed) if task.domain in domains]
    if not tasks or len(tasks) != len(set(domains)) or len(domains) != len(set(domains)):
        raise ValueError("Choose distinct supported lifecycle domains")
    schedule = [{"task": task.id, "policy": policy} for task in tasks for policy in POLICIES]
    random.Random(seed).shuffle(schedule)
    sources = sorted(
        {
            Path(__file__).resolve(),
            Path(base.__file__).resolve(),
            *sorted((base.REPO / "memory-bench/membench").rglob("*.py")),
        }
    )
    return {
        "schema": "memory-lifecycle.v1",
        "seed": seed,
        "model": base.MODEL,
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=base.REPO, text=True
        ).strip(),
        "claude_version": subprocess.check_output(
            [str(base.CLAUDE), "--version"], text=True
        ).strip(),
        "bd_version": subprocess.check_output([str(base.BD), "--version"], text=True).strip(),
        "binary_sha256": {
            str(path): base.sha(path) for path in (base.CLAUDE, base.BD, base.PYTHON)
        },
        "source_sha256": {str(path.relative_to(base.REPO)): base.sha(path) for path in sources},
        "tasks": json.loads(json.dumps([dataclasses.asdict(task) for task in tasks])),
        "schedule": schedule,
        "planned_sessions": sum(len(task.stages) for task in tasks) * len(POLICIES),
        "session_budget_usd": budget,
        "policies": {policy: base.BASE + policy_guidance(policy) for policy in POLICIES},
        "interpretation": "Synthetic public durable-decision labels; cumulative actual legacy KV. "
        "No hidden expected values in completion checks. No new Memory-type validation. "
        "Native memory disabled. Historical key is an equally instructed manual snapshot. "
        "Primary outcome is complete lifecycle; stages share captures and are correlated.",
    }


def freeze(out: Path, manifest: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    path = out / "manifest.json"
    if path.exists():
        if json.loads(path.read_text()) != manifest:
            raise ValueError("Frozen plan differs; choose a new output directory")
        for name, digest in manifest["source_sha256"].items():
            if base.sha(out / "source" / name) != digest:
                raise ValueError("Frozen source copy differs")
        return
    if any(out.iterdir()):
        raise ValueError("Nonempty output has no frozen plan")
    for name, digest in manifest["source_sha256"].items():
        source = base.REPO / name
        if base.sha(source) != digest:
            raise ValueError("Source changed while freezing")
        target = out / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    base.new_json(path, manifest)


def pending_cases(out: Path, manifest: dict[str, Any]) -> list[dict[str, str]]:
    pending = []
    for row in manifest["schedule"]:
        directory = out / "cases" / f"{row['task']}-{row['policy']}"
        if not directory.exists():
            pending.append(row)
            continue
        path = directory / "result.json"
        if not path.exists():
            raise ValueError(f"Interrupted lifecycle cannot be repurchased: {directory}")
        result = json.loads(path.read_text())
        if (
            result.get("task") != row["task"]
            or result.get("policy") != row["policy"]
            or len(result.get("stages", [])) != 8
        ):
            raise ValueError("Invalid completed lifecycle")
        for stage in result["stages"]:
            if json.loads((directory / stage["name"] / "assessment.json").read_text()) != stage:
                raise ValueError("Lifecycle assessment differs from recorded stage")
            if (
                json.loads((directory / stage["name"] / "result.json").read_text())
                != stage["result"]
            ):
                raise ValueError("Lifecycle stage differs from actual session")
    return pending


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260907)
    parser.add_argument("--domains", default="cache,csv_export,image_export,logging")
    parser.add_argument("--session-budget", type=float, default=0.75)
    parser.add_argument("--fire", action="store_true")
    parser.add_argument("--max-cases", type=int, default=1)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if args.max_cases < 1 or not 1 <= args.workers <= 2:
        raise ValueError("Positive max-cases and workers 1..2 required")
    manifest = make_manifest(args.seed, args.domains.split(","), args.session_budget)
    freeze(args.out, manifest)
    pending = pending_cases(args.out, manifest)
    print(
        f"PLAN {len(manifest['schedule'])} lifecycles / "
        f"{manifest['planned_sessions']} sessions; {len(pending)} pending",
        flush=True,
    )
    if not args.fire:
        return
    tasks = {task.id: task for task in build_lifecycles(args.seed)}
    purchased = pending[: args.max_cases]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        completed = 0
        for offset in range(0, len(purchased), args.workers):
            futures = [
                pool.submit(
                    run_lifecycle, args.out, tasks[row["task"]], row["policy"], args.session_budget
                )
                for row in purchased[offset : offset + args.workers]
            ]
            for future in as_completed(futures):
                future.result()
                completed += 1
                print(f"LIFECYCLE {completed}/{len(purchased)} completed", flush=True)


if __name__ == "__main__":
    main()
