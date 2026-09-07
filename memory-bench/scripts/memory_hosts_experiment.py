"""Frozen matched memory handoffs across installed coding-agent CLIs.

Old experiment sources and results are imports, never mutation targets. A distinct
shim receipt schema maps real executions to actual host tool-result identities.
Only retained Beads/native records cross fresh sessions; private expected values
remain in the parent process and evidence directory outside the model sandbox.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
import math
import os
import random
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from membench.runner.memory_host_shell import shell_environment
from membench.runner.memory_host_types import HostLaunch, HostObservation
from membench.runner.memory_lifecycle_corpus import LifecycleTask, build_lifecycles
from membench.runner.memory_routes_grade import grade_artifact
from membench.runner.memory_routes_runtime import experiment_env, make_profile
from scripts import memory_lifecycle_experiment as lifecycle
from scripts import memory_routes_experiment as base

HOSTS = ("claude", "codex", "gemini", "opencode", "copilot")
MODES = ("isolated", "normal")
DOMAINS = ("cache", "image_export")
SOURCE_FIDELITY = """Retain the approved source faithfully. Omit unsupported explanations
from the approved record; any interpretation must be explicitly labeled as such.
After initial capture, leave the historical note's entire body unchanged. A permanent
revision updates the current reference only; do not regenerate the historical note.
"""


def guidance(mode: str) -> str:
    if mode not in MODES:
        raise ValueError("Unknown native-memory condition")
    text = lifecycle.policy_guidance("selective")
    native = (
        "Native memory is disabled or unavailable in this isolated condition."
        if mode == "isolated"
        else "The host's ordinary native-memory feature retains its installed default "
        "in isolated state. Any native records actually saved there also survive; "
        "previous task files and conversation transcripts do not."
    )
    return text.replace("Native automatic memory is disabled.", native) + SOURCE_FIDELITY


def adapter(host: str) -> Any:
    if host not in HOSTS:
        raise ValueError("Unknown CLI host")
    name = host if host in {"claude", "codex"} else "other"
    return importlib.import_module(f"membench.runner.memory_host_{name}")


def prepare_host(
    host: str, local: Path, env: dict[str, str], prompt: str, model: str, mode: str, budget: float
) -> HostLaunch:
    module = adapter(host)
    if host in {"claude", "codex"}:
        return module.prepare(local, env, prompt, model, mode, budget)  # type: ignore[no-any-return]
    return module.prepare(host, local, env, prompt, model, mode, budget)  # type: ignore[no-any-return]


def observe_host(host: str, stream: str, local: Path) -> HostObservation:
    module = adapter(host)
    if host in {"claude", "codex"}:
        return module.observe(stream, local)  # type: ignore[no-any-return]
    return module.observe(host, stream, local)  # type: ignore[no-any-return]


def assert_frozen(manifest: dict[str, Any]) -> None:
    for name, digest in manifest["source_sha256"].items():
        if base.sha(base.REPO / name) != digest:
            raise ValueError(f"Frozen source changed before next session: {name}")
    for name, digest in manifest["binary_sha256"].items():
        if base.sha(Path(name)) != digest:
            raise ValueError(f"Frozen binary changed before next session: {name}")


def run_leg(
    *,
    case: Path,
    evidence: Path,
    leg: str,
    host: str,
    model: str,
    mode: str,
    prompt: str,
    store: Path,
    native_from: Path | None,
    expected: dict[str, Any],
    budget: float,
    timeout_s: float,
    workflow: str | None = None,
    settings_expected: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], Path]:
    from membench.runner import memory_host_receipts

    evidence.mkdir()
    local = case / leg
    local.mkdir()
    for name in ("work", "config", "tmp"):
        (local / name).mkdir()
    native = local / "native"
    if native_from is None:
        native.mkdir()
    else:
        shutil.copytree(native_from, native, symlinks=True)
    shutil.copytree(native, evidence / "native-before", symlinks=True)
    harness_session = uuid.uuid4().hex
    receipt_path, _ = memory_host_receipts.prepare(
        local / "bin", store, leg, harness_session, binary=base.BD, python=base.PYTHON
    )
    env = experiment_env(local / "config", local / "tmp", local / "bin")
    env = shell_environment(local, env)
    initialized = subprocess.run(
        ["/usr/bin/git", "init", "--initial-branch=main", str(local / "work")],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    base.new_json(
        evidence / "git-init.json",
        {
            "exit_code": initialized.returncode,
            "stdout": initialized.stdout,
            "stderr": initialized.stderr,
        },
    )
    if initialized.returncode:
        raise RuntimeError("Fresh workspace Git initialization failed")
    task = json.loads(
        base.checked_bd(["create", f"{leg}: produce project configuration", "--json"], store, env)
    )
    full_prompt = (
        base.BASE
        + "\n"
        + (guidance(mode) if workflow is None else workflow)
        + f"\nAssigned task: {task['id']}\n\n{prompt}"
    )
    (evidence / "prompt.txt").write_text(full_prompt)
    launch = prepare_host(host, local, env, full_prompt, model, mode, budget)
    for key, value in (settings_expected or {}).items():
        if launch.public_settings.get(key) != value:
            raise ValueError(f"Frozen host setting changed before launch: {key}")
    profile = make_profile(
        local / "sandbox.sb",
        writable_roots=[local, store],
        readable_roots=[local, store, *launch.readable_roots],
    )
    args = ["/usr/bin/sandbox-exec", "-f", str(profile), *launch.argv]
    base.new_json(
        evidence / "started.json",
        {
            "host": host,
            "model_requested": model,
            "mode": mode,
            "leg": leg,
            "scratch": str(local),
            "store": str(store),
            "harness_session_id": harness_session,
            "argv": args,
            "public_settings": launch.public_settings,
            "timeout_s": timeout_s,
        },
    )
    print(f"START {evidence.parent.name}/{leg}", flush=True)
    started = time.monotonic()
    timed_out = False
    with (evidence / "stream.jsonl").open("x") as out, (evidence / "stderr.txt").open("x") as err:
        proc = subprocess.Popen(
            args,
            cwd=local / "work",
            env=launch.env,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            start_new_session=True,
            text=True,
        )
        try:
            exit_code = proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            exit_code = proc.wait()
    stream = (evidence / "stream.jsonl").read_text()
    observed = observe_host(host, stream, local)
    host_evidence = evidence / "host-evidence"
    module = adapter(host)
    if hasattr(module, "export_evidence"):
        module.export_evidence(local, host_evidence)
    else:
        host_evidence.mkdir()
    raw = (
        [json.loads(line) for line in receipt_path.read_text().splitlines()]
        if receipt_path.exists()
        else []
    )
    scored, mapping = memory_host_receipts.score_correlated(
        raw,
        observed.calls,
        observed.session_id or "",
        leg_id=leg,
        status="ok" if observed.completed else "error",
        expected_binary=str(base.BD),
        expected_store=str(store),
    )
    evidence_score = scored.model_dump(mode="json")
    derived = mapping["derived_receipts"]
    after = base.memories(store, env)
    artifact = grade_artifact(local / "work/config.json", expected)
    shutil.copytree(local / "work", evidence / "workspace", symlinks=True)
    shutil.copytree(native, evidence / "native", symlinks=True)
    base.new_json(evidence / "memory.json", after)
    base.new_json(evidence / "raw-receipts.json", raw)
    base.new_json(evidence / "receipts.json", derived)
    base.new_json(evidence / "receipt-mapping.json", mapping)
    base.new_json(evidence / "tool-calls.json", [c.model_dump(mode="json") for c in observed.calls])
    result = {
        "leg": leg,
        "host": host,
        "policy": "selective-source-fidelity",
        "mode": mode,
        "model_requested": model,
        "models_observed": observed.models,
        "model_evidence": observed.model_evidence,
        "model_matches": observed.models == [model],
        "session_id": observed.session_id,
        "harness_session_id": harness_session,
        "exit_code": exit_code,
        "completed": observed.completed,
        "is_error": not observed.success,
        "errors": observed.errors,
        "behavioral_limit": timed_out
        or any(e in {"error_max_turns", "error_max_budget_usd"} for e in observed.errors),
        "timed_out": timed_out,
        "cost_usd": observed.cost_usd,
        "model_usage": observed.usage,
        "duration_s": time.monotonic() - started,
        "artifact": artifact,
        "memory_evidence": evidence_score,
        "task_id": task["id"],
        "scratch": str(local),
        "native_file_count": sum(p.is_file() and not p.is_symlink() for p in native.rglob("*")),
        **base.route_summary(evidence_score, observed.calls, local / "work/config.json", expected),
    }
    base.new_json(evidence / "result.json", result)
    print(
        f"DONE {evidence.parent.name}/{leg}: artifact={artifact['passed']} "
        f"reads={evidence_score['observed_reads']} writes={evidence_score['accepted_writes']} "
        f"unknown={evidence_score['evidence_unknown']} cost={observed.cost_usd}",
        flush=True,
    )
    return result, native


def run_lifecycle(
    out: Path, task: LifecycleTask, row: dict[str, Any], manifest: dict[str, Any]
) -> None:
    host, mode = row["host"], row["mode"]
    directory = out / "cases" / row["id"]
    directory.mkdir(parents=True, exist_ok=False)
    case = Path(tempfile.mkdtemp(prefix="mem-hosts-", dir="/tmp")).resolve()
    base.new_json(directory / "started.json", {"scratch": str(case), **row})
    try:
        setup = case / "setup"
        for child in ("config", "tmp", "bin"):
            (setup / child).mkdir(parents=True)
        env = experiment_env(setup / "config", setup / "tmp", setup / "bin")
        carried = dict(task.task.decoys)
        native: Path | None = None
        stages = []
        for stage in task.stages:
            assert_frozen(manifest)
            store = case / f"store-{stage.name}"
            base.initialize_store(store, env, directory / f"initialization-{stage.name}.json")
            for key, body in carried.items():
                base.checked_bd(["remember", body, "--key", key], store, env)
            before = base.memories(store, env)
            if before != carried:
                raise RuntimeError("Actual retained memory transfer differs")
            base.new_json(directory / f"transferred-{stage.name}.json", before)
            result, native = run_leg(
                case=case,
                evidence=directory / stage.name,
                leg=stage.name,
                host=host,
                model=manifest["coverage"][host]["model"],
                mode=mode,
                prompt=stage.prompt,
                store=store,
                native_from=native if mode == "normal" else None,
                expected=stage.expected_config,
                budget=manifest["session_budget_usd"],
                timeout_s=manifest["timeout_s"],
                settings_expected=manifest["coverage"][host].get("frozen_settings", {}),
            )
            after = base.memories(store, env)
            assigned = json.loads(
                base.checked_bd(["show", result["task_id"], "--json"], store, env)
            )
            base.new_json(directory / stage.name / "task.json", assigned)
            closed = (
                isinstance(assigned, list)
                and len(assigned) == 1
                and assigned[0].get("status") == "closed"
            )
            receipts = json.loads((directory / stage.name / "receipts.json").read_text())
            summary = lifecycle.stage_summary(
                stage,
                task,
                result,
                before,
                after,
                closed,
                receipts,
                [],
                Path(result["scratch"]) / "work",
            )
            summary["historical_body_preserved"] = (
                before.get(task.historical_key) == after.get(task.historical_key)
                if task.historical_key in before
                else None
            )
            summary["complete_handoff"] = bool(
                summary["complete_handoff"]
                and not result["is_error"]
                and result["exit_code"] == 0
                and result["model_matches"]
                and not result["memory_evidence"]["evidence_unknown"]
            )
            stages.append(summary)
            base.new_json(directory / stage.name / "assessment.json", summary)
            carried = after
            if (
                result["timed_out"]
                or result["exit_code"] != 0
                or not result["completed"]
                or not result["model_matches"]
                or result["memory_evidence"]["evidence_unknown"]
            ):
                raise RuntimeError("Interrupted or unmeasurable stage; retained without repurchase")
        base.new_json(
            directory / "result.json",
            {
                **row,
                "stages": stages,
                "complete_lifecycle": all(s["complete_handoff"] for s in stages),
                "history_immutable": all(
                    s["historical_body_preserved"] is not False for s in stages
                ),
                "literal_handoff_and_immutable_history": all(
                    s["complete_handoff"] and s["historical_body_preserved"] is not False
                    for s in stages
                ),
            },
        )
    except Exception as exc:
        base.new_json(directory / "halt.json", {"type": type(exc).__name__, "message": str(exc)})
        raise


def make_manifest(
    coverage: dict[str, Any], seed: int, budget: float, timeout_s: float
) -> dict[str, Any]:
    if not math.isfinite(budget) or budget <= 0 or not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("Finite positive budget and timeout required")
    if set(coverage) != set(HOSTS):
        raise ValueError("Coverage must retain all five installed CLI candidates")
    for host, info in coverage.items():
        if info.get("runnable") and not all(info.get(k) for k in ("model", "version", "smoke")):
            raise ValueError(f"Unverified runnable host: {host}")
        if not info.get("runnable") and not info.get("blocker"):
            raise ValueError(f"Blocked host needs a concrete reason: {host}")
    tasks = [t for t in build_lifecycles(seed) if t.domain in DOMAINS]
    schedule = [
        {"id": f"{host}-{mode}-{task.domain}", "host": host, "mode": mode, "task": task.id}
        for host in HOSTS
        if coverage[host].get("runnable")
        for mode in MODES
        for task in tasks
        if mode == "isolated" or task.domain == "cache"
    ]
    random.Random(seed).shuffle(schedule)
    sources = [
        Path(__file__),
        Path(lifecycle.__file__),
        base.REPO / "memory-bench/scripts/memory_hosts_report.py",
        base.REPO / "memory-bench/scripts/memory_hosts_smoke.py",
        base.REPO / "memory-bench/scripts/memory_lifecycle_report.py",
        Path(base.__file__),
        *sorted((base.REPO / "memory-bench/membench").rglob("*.py")),
    ]
    binaries = {str(base.BD): base.sha(base.BD), str(base.PYTHON): base.sha(base.PYTHON)}
    for info in coverage.values():
        for path in info.get("binary_paths", []):
            binary = Path(path).resolve(strict=True)
            binaries[str(binary)] = base.sha(binary)
    manifest: dict[str, Any] = json.loads(
        json.dumps(
            {
                "schema": "memory-hosts.v1",
                "coverage": coverage,
                "seed": seed,
                "session_budget_usd": budget,
                "timeout_s": timeout_s,
                "tasks": [dataclasses.asdict(t) for t in tasks],
                "schedule": schedule,
                "intended_max_sessions": 120,
                "planned_sessions": len(schedule) * 8,
                "blocked_host_slots": 120 - len(schedule) * 8,
                "concurrency": "at most two lifecycles; at most one per host",
                "guidance": {mode: base.BASE + guidance(mode) for mode in MODES},
                "binary_sha256": binaries,
                "source_sha256": {str(p.relative_to(base.REPO)): base.sha(p) for p in sources},
            }
        )
    )
    return manifest


def pending_cases(out: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    pending = []
    for row in manifest["schedule"]:
        path = out / "cases" / row["id"]
        if path.exists():
            if not (path / "result.json").exists():
                raise ValueError(f"Interrupted lifecycle cannot be repurchased: {path}")
        else:
            pending.append(row)
    return pending


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--seed", default=20260908, type=int)
    parser.add_argument("--session-budget", default=0.75, type=float)
    parser.add_argument("--timeout", default=240.0, type=float)
    parser.add_argument("--fire", action="store_true")
    parser.add_argument("--max-cases", default=1, type=int)
    parser.add_argument("--workers", default=2, type=int)
    args = parser.parse_args()
    if not 1 <= args.workers <= 2 or args.max_cases < 1 or args.timeout <= 0:
        raise ValueError("Invalid bounded execution limits")
    coverage = json.loads(args.coverage.read_text())
    manifest = make_manifest(coverage, args.seed, args.session_budget, args.timeout)
    out = args.out.resolve()
    if not out.exists():
        out.mkdir(parents=True)
        base.new_json(out / "manifest.json", manifest)
        for name in manifest["source_sha256"]:
            destination = out / "source" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(base.REPO / name, destination)
    elif json.loads((out / "manifest.json").read_text()) != manifest:
        raise ValueError("Frozen conditions differ; prior experiment preserved")
    pending = pending_cases(out, manifest)
    print(
        f"FROZEN {len(manifest['schedule'])} lifecycles / {manifest['planned_sessions']} sessions; "
        f"{manifest['blocked_host_slots']} candidate slots blocked",
        flush=True,
    )
    if not args.fire:
        return
    tasks = {t.id: t for t in build_lifecycles(args.seed)}
    selected = pending[: args.max_cases]
    host_locks = {host: threading.Lock() for host in HOSTS}

    def execute(row: dict[str, Any]) -> None:
        with host_locks[row["host"]]:
            run_lifecycle(out, tasks[row["task"]], row, manifest)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(execute, row) for row in selected]
        errors = []
        for index, future in enumerate(as_completed(futures), 1):
            try:
                future.result()
                print(f"LIFECYCLE DONE [{index}/{len(selected)}]", flush=True)
            except Exception as exc:
                errors.append(str(exc))
                print(f"LIFECYCLE HALTED [{index}/{len(selected)}]: {exc}", flush=True)
        if errors:
            raise RuntimeError("; ".join(errors))


if __name__ == "__main__":
    main()
