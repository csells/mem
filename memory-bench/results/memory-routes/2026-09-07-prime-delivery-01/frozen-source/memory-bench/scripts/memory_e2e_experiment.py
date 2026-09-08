"""Installed Beads guidance: isolated smokes and a frozen 32-slot feature screen.

Only --smoke and --fire launch models. A started session is never purchased twice.
Actual source, tasks, records and native state survive; hidden oracles do not enter
the model sandbox. Legacy text references are not production Memory Bead links.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from membench.runner import memory_e2e_hosts as hosts
from membench.runner import memory_e2e_receipts as receipts
from membench.runner import memory_host_claude, memory_host_codex
from membench.runner.memory_e2e_corpus import (
    E2ECase,
    E2EStage,
    build_e2e_case,
    find_successor_task,
    grade_component,
    initial_scaffold,
    stage_task,
)
from membench.runner.memory_e2e_grade import grade_retained
from membench.runner.memory_e2e_package import candidate_policy, install_package
from membench.runner.memory_host_shell import shell_environment
from membench.runner.memory_routes_grade import grade_artifact, grade_capture
from membench.runner.memory_routes_runtime import experiment_env, make_profile
from scripts import memory_routes_experiment as base

MODELS = {"claude": "claude-sonnet-4-6", "codex": "gpt-6-astra"}
ARMS = ("explicit", "installed")
TIMEOUT = 420
BUDGET = 1.50
SMOKE_POLICY = {"project": "integration-smoke", "retention_days": 17, "enabled": True}


def write_json(path: Path, value: Any) -> None:
    with path.open("x") as out:
        json.dump(value, out, indent=2, ensure_ascii=False)
        out.write("\n")


def sources() -> dict[str, str]:
    root = base.REPO / "memory-bench"
    paths = [*root.glob("membench/**/*.py"), *root.glob("scripts/memory_*.py")]
    paths.extend(p for p in (root / "fixtures/memory-e2e-package").rglob("*") if p.is_file())
    return {str(p.relative_to(base.REPO)): base.sha(p) for p in sorted(paths)}


def binary_hashes() -> dict[str, str]:
    binaries = [base.BD, base.PYTHON, memory_host_claude.EXECUTABLE, memory_host_codex.BINARY]
    return {str(p): base.sha(p) for p in binaries}


def body_delivered(output: str, expected: str) -> bool:
    """Recognize full ordered lines, including normal Read tool line prefixes."""
    cursor = 0
    for line in expected.splitlines():
        if not line.strip():
            continue
        offset = output.find(line.rstrip(), cursor)
        if offset < 0:
            return False
        cursor = offset + len(line.rstrip())
    return bool(expected.strip())


def instruction_reads(calls: list[dict[str, Any]], workspace: Path) -> dict[str, int]:
    completed = [
        c
        for c in calls
        if c.get("tool_result_index") is not None
        and not c.get("is_error")
        and isinstance(c.get("result"), str)
    ]

    def delivered(suffix: str) -> int:
        path = workspace / ".agents/skills/beads" / suffix
        if not path.is_file():
            return 0
        body = path.read_text()
        return sum(
            suffix in json.dumps(c.get("arguments", {})) and body_delivered(c["result"], body)
            for c in completed
        )

    return {
        "native_skill_calls": sum(
            c.get("name", "").lower() in {"skill", "activate_skill"}
            and "beads" in str(c.get("arguments"))
            for c in completed
        ),
        "skill_file_read_calls": delivered("SKILL.md"),
        "memory_workflow_read_calls": delivered("references/memory.md"),
        "skill_read_attempts": sum("SKILL.md" in json.dumps(c.get("arguments", {})) for c in calls),
    }


def assert_frozen(manifest: dict[str, Any]) -> None:
    for path, digest in manifest["source_sha256"].items():
        if base.sha(base.REPO / path) != digest:
            raise ValueError(f"Frozen source changed: {path}")
    for path, digest in manifest["binary_sha256"].items():
        if base.sha(Path(path)) != digest:
            raise ValueError(f"Frozen executable changed: {path}")


def snapshot(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        symlinks=True,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"),
    )


def administrative(argv: list[str], store: Path, env: dict[str, str]) -> Any:
    return json.loads(base.checked_bd([*argv, "--json"], store, env))


def all_tasks(store: Path, env: dict[str, str]) -> list[dict[str, Any]]:
    value = administrative(["list", "--all", "--limit", "0"], store, env)
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise ValueError("Task listing did not return complete structured records")
    return value


def setup_case(out: Path, arm: str, case: E2ECase) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=False)
    scratch = Path(tempfile.mkdtemp(prefix="mem-e2e-", dir="/tmp")).resolve()
    workspace = scratch / "work"
    workspace.mkdir()
    setup = scratch / "setup"
    for name in ("config", "tmp", "bin"):
        (setup / name).mkdir(parents=True)
    env = experiment_env(setup / "config", setup / "tmp", setup / "bin")
    store = scratch / "store"
    base.initialize_store(store, env, out / "initialization.json")
    subprocess.run(["/usr/bin/git", "init", "--quiet", str(workspace)], env=env, check=True)
    for name, body in initial_scaffold(case).items():
        path = workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as target:
            target.write(body)
    package = install_package(workspace, store, arm)
    for key, body in case.decoys.items():
        base.checked_bd(["remember", body, "--key", key], store, env)
    prime = base.checked_bd(["prime", "--no-memories"], store, env)
    if any(body in prime for body in case.decoys.values()):
        raise ValueError("Prime injected distractor memory bodies")
    write_json(
        out / "prime-check.json",
        {
            "command": "bd prime --no-memories",
            "stdout": prime,
            "memory_bodies_absent": True,
            "actor": "harness",
            "model_call": False,
        },
    )
    state = {
        "scratch": str(scratch),
        "workspace": str(workspace),
        "store": str(store),
        "arm": arm,
        "package": package,
    }
    write_json(out / "case.json", state)
    return {**state, "env": env}


def create_task(state: dict[str, Any], title: str, body: str) -> dict[str, Any]:
    value = administrative(
        ["create", title, "--description", body], Path(state["store"]), state["env"]
    )
    if not isinstance(value, dict) or not isinstance(value.get("id"), str):
        raise ValueError("Task creation did not return an actual ID")
    return value


def run_session(
    evidence: Path,
    state: dict[str, Any],
    host: str,
    task: dict[str, Any],
    leg: str,
    native_from: Path | None,
    *,
    smoke: bool = False,
) -> tuple[dict[str, Any], Path]:
    evidence.mkdir(exist_ok=False)
    local = Path(state["scratch"]) / leg
    local.mkdir()
    workspace, store = Path(state["workspace"]), Path(state["store"])
    (local / "work").symlink_to(workspace, target_is_directory=True)
    for name in ("config", "tmp"):
        (local / name).mkdir()
    native = local / "native"
    if native_from:
        shutil.copytree(native_from, native, symlinks=True)
    else:
        native.mkdir()
    snapshot(workspace, evidence / "workspace-before")
    before = base.memories(store, state["env"])
    write_json(evidence / "memory-before.json", before)
    write_json(evidence / "task-before.json", task)
    invocation = uuid.uuid4().hex
    log, _ = receipts.prepare(
        local / "bin", store, leg, invocation, binary=base.BD, python=base.PYTHON
    )
    env = shell_environment(local, experiment_env(local / "config", local / "tmp", local / "bin"))
    prompt = f"Work on {task['id']}."
    if state["arm"] == "explicit":
        prompt = candidate_policy() + "\n\n" + prompt
    (evidence / "prompt.txt").write_text(prompt)
    launch = hosts.prepare_host(host, local, env, prompt, MODELS[host], "normal", BUDGET)
    profile = make_profile(
        local / "sandbox.sb",
        [local, workspace, store],
        [local, workspace, store, *launch.readable_roots],
    )
    argv = ["/usr/bin/sandbox-exec", "-f", str(profile), *launch.argv]
    write_json(
        evidence / "launch.json",
        {
            "argv": argv,
            "settings": launch.public_settings,
            "harness_session": invocation,
            "task": task["id"],
            "smoke": smoke,
        },
    )
    started = time.monotonic()
    print(f"START {host}/{state['arm']}/{leg}", flush=True)
    timed_out = False
    with (
        (evidence / "stream.jsonl").open("x") as stdout,
        (evidence / "stderr.txt").open("x") as stderr,
    ):
        proc = subprocess.Popen(
            argv,
            cwd=workspace,
            env=launch.env,
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        write_json(evidence / "process.json", {"pid": proc.pid, "wall_ns": time.time_ns()})
        try:
            code = proc.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            code = proc.wait()
    stream = (evidence / "stream.jsonl").read_text()
    observed = hosts.observe_host(host, stream, local)
    if host == "codex":
        memory_host_codex.export_evidence(local, evidence / "host-evidence")
    rows = receipts.read(log)
    calls = [c.model_dump(mode="json") for c in observed.calls]
    score = receipts.assess(
        rows,
        root_pid=proc.pid,
        leg=leg,
        session=invocation,
        tool_outputs=[str(c.result or "") for c in observed.calls],
        binary=str(base.BD),
        store=str(store),
    )
    after = base.memories(store, state["env"])
    tasks = all_tasks(store, state["env"])
    write_json(evidence / "raw-receipts.json", rows)
    write_json(evidence / "tool-calls.json", calls)
    write_json(evidence / "memory-after.json", after)
    write_json(evidence / "tasks-after.json", tasks)
    snapshot(workspace, evidence / "workspace-after")
    snapshot(native, evidence / "native-after")
    result = {
        "host": host,
        "arm": state["arm"],
        "leg": leg,
        "task_id": task["id"],
        "model_requested": MODELS[host],
        "models_observed": observed.models,
        "model_matches": observed.models == [MODELS[host]],
        "session_id": observed.session_id,
        "process_exit_code": code,
        "completed": observed.completed,
        "success": observed.success and code == 0 and not timed_out,
        "timed_out": timed_out,
        "errors": observed.errors,
        "cost_usd": observed.cost_usd,
        "usage": observed.usage,
        "duration_s": time.monotonic() - started,
        "memory_operations": score,
        **instruction_reads(calls, workspace),
        "rule_delivery": (
            "installed files and observed behavior; automatic loading not directly certified"
        ),
        "administrative_reads": {"memory_snapshots": 2, "task_snapshots": 1},
        "scratch": str(local),
        "workspace": str(workspace),
        "task_closed": any(
            t.get("id") == task["id"] and t.get("status") == "closed" for t in tasks
        ),
    }
    write_json(evidence / "execution.json", result)
    print(
        f"DONE {host}/{state['arm']}/{leg}: success={result['success']} "
        f"reads={score['agent_reads']} writes={score['agent_writes']} "
        f"cost={observed.cost_usd}",
        flush=True,
    )
    return result, native


def run_smoke(out: Path, host: str) -> dict[str, Any]:
    state = setup_case(out, "installed", build_e2e_case())
    write_json(out / "source-sha256.json", sources())
    write_json(out / "binary-sha256.json", binary_hashes())
    task = create_task(
        state,
        "Implement approved integration smoke settings",
        "Create smoke_result.json with this complete approved project agreement: "
        + json.dumps(SMOKE_POLICY)
        + ". Validate the file. "
        "Approval source: Integration compatibility decision v1. "
        "Future components in this project must follow this durable agreement.",
    )
    result, _ = run_session(
        out / "session", state, host, task, "integration-smoke", None, smoke=True
    )
    artifact = grade_artifact(Path(state["workspace"]) / "smoke_result.json", SMOKE_POLICY)
    ops = result["memory_operations"]
    retained = json.loads((out / "session/memory-after.json").read_text())
    exact_capture = any(
        grade_capture(retained, key, SMOKE_POLICY)["passed"] is True for key in retained
    )
    admitted = bool(
        result["success"]
        and result["model_matches"]
        and artifact["passed"]
        and result["task_closed"]
        and exact_capture
        and ops["agent_writes"]
        and ops["agent_recalls"]
        and ops["agent_searches"]
        and ops["prime_calls"]
        and not ops["unknown_execution"]
        and (result["native_skill_calls"] or result["skill_file_read_calls"])
        and result["memory_workflow_read_calls"]
    )
    proof = {
        "host": host,
        "admitted": admitted,
        "artifact": artifact,
        "execution": result,
        "exact_capture": exact_capture,
    }
    write_json(out / "result.json", proof)
    return proof


def freeze(out: Path, smokes: dict[str, Path]) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=False)
    coverage: dict[str, Any] = {}
    for host in MODELS:
        path = smokes[host]
        proof = (
            json.loads((path / "result.json").read_text())
            if (path / "result.json").exists()
            else {}
        )
        admitted = proof.get("admitted") is True
        if admitted:
            if json.loads((path / "source-sha256.json").read_text()) != sources():
                raise ValueError(f"{host} smoke source/package differs from current inputs")
            if json.loads((path / "binary-sha256.json").read_text()) != binary_hashes():
                raise ValueError(f"{host} smoke executable differs from current inputs")
        failure_path = path / "failure.json"
        failure = json.loads(failure_path.read_text()) if failure_path.exists() else None
        coverage[host] = {
            "admitted": admitted,
            "smoke": str(path),
            "model": MODELS[host],
            "blocker": (
                None
                if admitted
                else (
                    failure["reason"]
                    if failure
                    else "integration smoke did not meet admission checks"
                )
            ),
            "smoke_completed": bool(proof),
            "failure": failure,
        }
    for host, reason in {
        "gemini": "previous preserved preflight: depleted credits; no qualified adapter",
        "copilot": "previous preserved preflight: launcher without CLI; no qualified adapter",
        "opencode": "previous preserved preflight: context truncation; no qualified adapter",
    }.items():
        coverage[host] = {"admitted": False, "blocker": reason, "rechecked_by_model": False}
    manifest: dict[str, Any] = {
        "schema": "memory-e2e-screen.v1",
        "coverage": coverage,
        "planned_sessions": 32,
        "stages": [s.name for s in build_e2e_case().stages],
        "source_sha256": sources(),
        "binary_sha256": binary_hashes(),
        "case": dataclasses.asdict(build_e2e_case()),
        "native_mode": "normal in fresh isolated state",
        "timeout_s": TIMEOUT,
        "requested_budget_usd_per_session": BUDGET,
        "budget_limit": "Claude CLI USD cap; Codex wall time only, USD cost unreported",
        "cases": [
            {"host": host, "arm": arm, "id": f"{host}-{arm}"}
            for host, arms in (("claude", ARMS), ("codex", tuple(reversed(ARMS))))
            for arm in arms
        ],
        "interruption_policy": (
            "never rerun a started session; skip dependent missing tasks; retain failures"
        ),
    }
    write_json(out / "manifest.json", manifest)
    for name in manifest["source_sha256"]:
        target = out / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base.REPO / name, target)
    return manifest


def package_unchanged(state: dict[str, Any]) -> bool:
    roots = {"workspace": Path(state["workspace"]), "store": Path(state["store"])}
    for row in state["package"]["files"]:
        path = roots[row["root"]] / row["path"]
        if not path.is_file() or path.is_symlink() or base.sha(path) != row["sha256"]:
            return False
    return all(
        (roots[row["root"]] / row["path"]).is_symlink()
        and os.readlink(roots[row["root"]] / row["path"]) == row["target"]
        for row in state["package"]["symlinks"]
    )


def assess_feature(
    workspace: Path, stage: E2EStage, case: E2ECase, scratch: Path
) -> dict[str, Any]:
    # Generated code runs without write access to either the real user filesystem
    # or the retained project. Oracles stay in the parent process.
    import sys

    profile = make_profile(scratch / "grade.sb", [], [workspace, Path(sys.base_prefix).resolve()])
    return grade_component(
        workspace, stage, case, process_prefix=["/usr/bin/sandbox-exec", "-f", str(profile)]
    )


def run_lifecycle(out: Path, row: dict[str, str], manifest: dict[str, Any]) -> None:
    case = build_e2e_case()
    directory = out / "cases" / row["id"]
    if directory.exists():
        raise FileExistsError(
            f"Lifecycle already exists; inspect it, do not repurchase: {directory}"
        )
    if not manifest["coverage"][row["host"]]["admitted"]:
        directory.mkdir(parents=True)
        write_json(
            directory / "result.json",
            {
                **row,
                "status": "blocked",
                "reason": manifest["coverage"][row["host"]]["blocker"],
                "stages": [{"leg": s.name, "status": "unrun"} for s in case.stages],
            },
        )
        return
    state = setup_case(directory, row["arm"], case)
    native = None
    stages: list[dict[str, Any]] = []
    standing_keys: list[str] | None = None
    history_keys: list[str] | None = None
    initial_memory: dict[str, str] | None = None
    halt: str | None = None
    for stage in case.stages:
        if halt:
            stages.append({"leg": stage.name, "status": "unrun", "reason": halt})
            continue
        assert_frozen(manifest)
        if not package_unchanged(state):
            halt = "agent changed installed instruction package; retained without repair"
            stages.append({"leg": stage.name, "status": "unrun", "reason": halt})
            continue
        description = stage_task(case, stage)
        if stage.authored_task:
            selected = find_successor_task(
                all_tasks(Path(state["store"]), state["env"]), description["title"]
            )
            if selected["status"] != "selected":
                stages.append(
                    {
                        "leg": stage.name,
                        "status": "unrun",
                        "reason": "author handoff " + selected["status"],
                        "selection": selected,
                    }
                )
                continue
            task = selected["task"]
        else:
            task = create_task(state, description["title"], description["body"])
        try:
            result, native = run_session(
                directory / stage.name, state, row["host"], task, stage.name, native
            )
            evidence = directory / stage.name
            before = json.loads((evidence / "memory-before.json").read_text())
            after = json.loads((evidence / "memory-after.json").read_text())
            retained = grade_retained(
                before, after, case, stage, standing_keys=standing_keys, history_keys=history_keys
            )
            if stage.name == "establish":
                initial_memory = after
            if stage.name == "revise":
                # These are retrospective content roles, not inferred from key names
                # or a claimed production reference. Keep the distinction in evidence.
                standing_keys = retained["v2_exact_keys"] or None
                history_keys = retained["v1_exact_keys"] or None
                retained["v1_survivor_body_preservation"] = (
                    {key: initial_memory.get(key) == after.get(key) for key in history_keys}
                    if initial_memory is not None and history_keys is not None
                    else None
                )
                retained["role_evidence"] = (
                    "post-revision content matches, not canonical references"
                )
            grade = assess_feature(Path(state["workspace"]), stage, case, Path(result["scratch"]))
            component = Path(state["workspace"]) / stage.component
            modification = component.stat().st_mtime_ns if component.is_file() else None
            recalled_before = [
                r
                for r in result["memory_operations"]["executions"]
                if r["command"] == "recall"
                and r["returncode"] == 0
                and modification is not None
                and r["wall_ns"] < modification
            ]
            assessment = {
                "leg": stage.name,
                "status": "completed",
                "execution": result,
                "artifact": grade,
                "retained": retained,
                "recalls_before_final_artifact_mtime": len(recalled_before),
                "mtime_limit": "ordering diagnostic; not proof of model use or first write",
                "memory_necessary": False,
                "alternative_sources": "earlier tasks and components retained",
                "instruction_package_unchanged": package_unchanged(state),
            }
            write_json(evidence / "assessment.json", assessment)
            stages.append(assessment)
            if not result["success"] or not result["model_matches"]:
                halt = "unsuccessful/interrupted host session retained; later stages unrun"
        except Exception as exc:
            # Preserve the attempted stage, even if only partial launch evidence exists.
            stages.append(
                {
                    "leg": stage.name,
                    "status": "interrupted",
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )
            halt = "interrupted attempt; never repurchased"
    write_json(
        directory / "result.json",
        {**row, "stages": stages, "status": "finished" if halt is None else "halted", "halt": halt},
    )


def report(out: Path) -> dict[str, Any]:
    manifest = json.loads((out / "manifest.json").read_text())
    rows: list[dict[str, Any]] = []
    case_results = []
    for case in manifest["cases"]:
        path = out / "cases" / case["id"] / "result.json"
        if path.exists():
            result = json.loads(path.read_text())
            case_results.append(result)
            rows.extend({"host": case["host"], "arm": case["arm"], **s} for s in result["stages"])
        else:
            rows.extend({**case, "leg": name, "status": "unrun"} for name in manifest["stages"])
    completed = [r for r in rows if r["status"] == "completed"]
    known_cost = sum(
        r["execution"]["cost_usd"] for r in completed if r["execution"]["cost_usd"] is not None
    )
    groups = []
    for case in manifest["cases"]:
        group = [r for r in completed if r["host"] == case["host"] and r["arm"] == case["arm"]]
        groups.append(
            {
                **case,
                "completed": len(group),
                "planned": 8,
                "artifacts_correct": sum(r["artifact"]["passed"] for r in group),
                "current_memory_complete": sum(
                    r["retained"]["current_content_available"] for r in group
                ),
                "agent_reads": sum(
                    r["execution"]["memory_operations"]["agent_reads"] for r in group
                ),
                "agent_writes": sum(
                    r["execution"]["memory_operations"]["agent_writes"] for r in group
                ),
                "reproduction_writes": sum(
                    r["execution"]["memory_operations"]["agent_writes"]
                    for r in group
                    if r["leg"] not in {"establish", "revise"}
                ),
            }
        )
    analysis = {
        "schema": "memory-e2e-analysis.v1",
        "planned": 32,
        "completed": len(completed),
        "artifacts_correct": sum(r["artifact"]["passed"] for r in completed),
        "known_cost_usd": known_cost,
        "completed_sessions_cost_unknown": sum(
            r["execution"]["cost_usd"] is None for r in completed
        ),
        "groups": groups,
        "coverage": manifest["coverage"],
        "cases": case_results,
        "limits": [
            "four correlated lifecycles, not a reliability estimate",
            "legacy keyed memory, no production Memory type",
            "source/rationale text checks do not certify all prose",
            "legitimate alternative source access remains available",
            "full tool stdout visible in a session does not prove model use",
        ],
    }
    # Report revisions have distinct filenames; no existing assessment is overwritten.
    index = 1
    while (out / f"analysis-{index:02}.json").exists():
        index += 1
    write_json(out / f"analysis-{index:02}.json", analysis)
    lines = [
        "# Installed memory workflow screen",
        "",
        f"Completed {len(completed)}/32 planned sessions; "
        f"{analysis['artifacts_correct']} correct feature artifacts.",
        "",
        "| CLI | Delivery | Completed | Correct artifacts | Complete current memories "
        "| Reproduction writes |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(
        f"| {r['host']} | {r['arm']} | {r['completed']}/8 | {r['artifacts_correct']} | "
        f"{r['current_memory_complete']} | {r['reproduction_writes']} |"
        for r in groups
    )
    lines.extend(
        [
            "",
            f"Known completed-session estimate: ${known_cost:.6f}; "
            f"{analysis['completed_sessions_cost_unknown']} completed sessions "
            "have unknown dollar cost.",
            "Smokes and interrupted/failed-attempt usage are separate evidence and may add cost.",
            "",
        ]
    )
    lines.extend(
        f"- {host}: {'admitted' if row['admitted'] else row['blocker']}"
        for host, row in manifest["coverage"].items()
    )
    lines.extend(["", *[f"- Limit: {limit}." for limit in analysis["limits"]], ""])
    with (out / f"report-{index:02}.md").open("x") as target:
        target.write("\n".join(lines))
    return analysis


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--smoke", choices=tuple(MODELS))
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--fire", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--claude-smoke", type=Path)
    parser.add_argument("--codex-smoke", type=Path)
    args = parser.parse_args()
    if sum((bool(args.smoke), args.freeze, args.fire, args.report)) != 1:
        parser.error("Choose exactly one action")
    out = args.out.resolve()
    if args.smoke:
        if out.exists():
            raise FileExistsError("Smoke already has evidence; no repeat purchase")
        try:
            run_smoke(out, args.smoke)
        except Exception as exc:
            out.mkdir(parents=True, exist_ok=True)
            write_json(
                out / "failure.json",
                {
                    "host": args.smoke,
                    "reason": f"{type(exc).__name__}: {exc}",
                    "model_process_started": (out / "session/process.json").exists(),
                },
            )
            raise
    elif args.freeze:
        if args.claude_smoke is None or args.codex_smoke is None:
            parser.error("Freeze requires both smoke evidence paths, including failed smokes")
        freeze(out, {"claude": args.claude_smoke.resolve(), "codex": args.codex_smoke.resolve()})
    elif args.fire:
        manifest = json.loads((out / "manifest.json").read_text())
        assert_frozen(manifest)
        for row in manifest["cases"]:
            run_lifecycle(out, row, manifest)
        report(out)
    else:
        report(out)


if __name__ == "__main__":
    main()
