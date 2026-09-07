"""Frozen ordinary coding tasks; standing guidance is the only memory intervention.

--freeze creates 120 immutable slots without inference. --run executes one phase,
never repeats a claimed slot, and carries actual code, issues, and records forward.
Hidden expected answers stay in the parent process, outside the agent sandbox.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import random
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from membench.runner import memory_e2e_receipts as receipts
from membench.runner import memory_unprompted_hosts as hosts
from membench.runner.memory_e2e_audit import classify_operation
from membench.runner.memory_host_shell import shell_environment
from membench.runner.memory_routes_runtime import experiment_env, make_profile
from membench.runner.memory_unprompted_package import FIXTURE, install
from scripts import memory_e2e_experiment as e2e
from scripts import memory_routes_experiment as base
from scripts import memory_unprompted_smoke as smoke

CORPUS = base.REPO / "memory-bench/fixtures/memory-unprompted-corpus"
FAMILIES = ("renewals", "reconciliation")
TIMEOUT = 420
BUDGET = 1.50
PHASES = ("checkpoint", "continuation", "normal")


class FrozenInputsChangedError(RuntimeError):
    """Changed common inputs stop all hosts; host failures stop only that host."""


def write(path: Path, obj: Any) -> None:
    pending = path.with_name(f".{path.name}.{uuid.uuid4().hex}.pending")
    smoke.write_json(pending, obj)
    # Readers see a complete record; link fails instead of replacing any evidence.
    os.link(pending, path)
    pending.unlink()


def schedule() -> list[dict[str, Any]]:
    rows = []
    for host_index, host in enumerate(hosts.MODELS):
        cases = [(family, arm) for family in FAMILIES for arm in ("baseline", "memory")]
        random.Random(907 + host_index).shuffle(cases)
        for phase, stages in (("checkpoint", range(1, 4)), ("continuation", range(4, 7))):
            for family, arm in cases:
                lifecycle = f"{host}-{family}-{arm}-isolated"
                for stage in stages:
                    rows.append(
                        {
                            "slot": f"{lifecycle}-{stage}",
                            "lifecycle": lifecycle,
                            "host": host,
                            "family": family,
                            "arm": arm,
                            "mode": "isolated",
                            "stage": stage,
                            "phase": phase,
                        }
                    )
        lifecycle = f"{host}-renewals-memory-normal"
        for stage in range(1, 7):
            rows.append(
                {
                    "slot": f"{lifecycle}-{stage}",
                    "lifecycle": lifecycle,
                    "host": host,
                    "family": "renewals",
                    "arm": "memory",
                    "mode": "normal",
                    "stage": stage,
                    "phase": "normal",
                }
            )
    return rows


def session_path(out: Path, row: dict[str, Any]) -> Path:
    return out / "cases" / str(row["lifecycle"]) / f"stage-{row['stage']}"


def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def compare_json(text: str, expected: Any) -> bool:
    try:
        actual = json.loads(text, object_pairs_hook=no_duplicates)
    except ValueError:
        return False
    return json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True)


def corpus(family: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = CORPUS / family
    meta: dict[str, Any] = json.loads((root / "manifest.json").read_text())
    raw: dict[str, Any] = json.loads((root / "tasks.json").read_text())
    tasks = []
    for stage, task in enumerate(raw["tasks"], 1):
        if task["stage"] != stage or not task["title"] or not task["prompt"].strip():
            raise ValueError("Expected ordered, nonempty business tasks")
        tasks.append(
            {**task, "body": (raw.get("common_contract", "") + "\n\n" + task["prompt"]).strip()}
        )
    return meta, tasks


def hashes() -> dict[str, str]:
    result = e2e.sources()
    for folder in (CORPUS, FIXTURE):
        for p in folder.rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts:
                result[str(p.relative_to(base.REPO))] = base.sha(p)
    return result


def review_paths() -> set[str]:
    return {
        str(p.relative_to(base.REPO))
        for folder in (CORPUS, FIXTURE)
        for p in folder.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }


def profile_hashes() -> dict[str, str]:
    return {
        str(p): base.sha(p)
        for p in (
            Path.home() / ".codex/config.toml",
            Path.home() / ".config/opencode/opencode.json",
            Path.home() / ".zcode/cli/config.json",
        )
    }


def assert_frozen(manifest: dict[str, Any]) -> None:
    try:
        e2e.assert_frozen(manifest)
        if profile_hashes() != manifest["profile_sha256"]:
            raise ValueError("A selected host's live profile changed after freeze")
    except (OSError, ValueError) as exc:
        raise FrozenInputsChangedError(str(exc)) from exc


def freeze(out: Path, admission: Path) -> None:
    review = json.loads(admission.read_text())
    if review.get("approved") is not True:
        raise ValueError("Independent task/package admission is required")
    if not review_paths().issubset(review["reviewed_sha256"]):
        raise ValueError("Admission must cover every corpus and package input")
    for family in FAMILIES:
        _, tasks = corpus(family)
        if len(tasks) != 6:
            raise ValueError("Each family must contain six reviewed tasks")
    source_hashes = hashes()
    for path, digest in review["reviewed_sha256"].items():
        if base.sha(base.REPO / path) != digest:
            raise ValueError(f"Reviewed input changed: {path}")
    binaries = e2e.binary_hashes()
    for path in (hosts.OPENCODE, hosts.ZCODE, hosts.ZCODE.parent.parent / "vendor/zcode.cjs"):
        binaries[str(path)] = base.sha(path)
    out.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema": "unprompted-memory-adoption.v1",
        "created_ns": time.time_ns(),
        "slots": schedule(),
        "models": hosts.MODELS,
        "source_sha256": source_hashes,
        "binary_sha256": binaries,
        "profile_sha256": profile_hashes(),
        "timeout_seconds": TIMEOUT,
        "claude_cli_budget_usd": BUDGET,
        "no_automatic_retries": True,
        "admission": review,
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "cost_estimate": {
            "claude": (
                "30 sessions; qualification-based $5.26 list-price estimate, likely higher "
                "for coding; $1.50 CLI stopping budget per session"
            ),
            "codex": "30 sessions; existing subscription, dollar charge not emitted",
            "opencode": "30 local sessions; no remote provider charge; compute unpriced",
            "zcode": "30 sessions; existing provider plan, no dollar charge emitted",
            "limit": (
                "420-second process deadline per session; only Claude exposes "
                "the requested USD stopping limit"
            ),
        },
    }
    write(out / "manifest.json", manifest)
    for relative in source_hashes:
        target = out / "frozen-source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base.REPO / relative, target)
    print(f"FROZEN {len(manifest['slots'])} slots; zero model calls", flush=True)


def setup(out: Path, row: dict[str, Any]) -> dict[str, Any]:
    case = out / "cases" / row["lifecycle"]
    saved = case / "state.json"
    if saved.exists():
        state = json.loads(saved.read_text())
    else:
        if row["stage"] != 1:
            raise ValueError("Cannot manufacture an absent predecessor")
        case.mkdir(parents=True, exist_ok=False)
        scratch = Path(tempfile.mkdtemp(prefix="ordinary-work-", dir="/tmp")).resolve()
        workspace = scratch / "work"
        shutil.copytree(CORPUS / row["family"] / "starter", workspace)
        admin = scratch / "admin"
        for name in ("config", "tmp", "bin"):
            (admin / name).mkdir(parents=True)
        env = experiment_env(admin / "config", admin / "tmp", admin / "bin")
        store = scratch / "store"
        base.initialize_store(store, env, case / "initialization.json")
        package = install(workspace, store, row["arm"])
        subprocess.run(["git", "init", "--quiet", str(workspace)], env=env, check=True)
        subprocess.run(["git", "-C", str(workspace), "add", "."], env=env, check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(workspace),
                "-c",
                "user.name=Exercise",
                "-c",
                "user.email=exercise@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--quiet",
                "-m",
                "Initial product scaffold",
            ],
            env=env,
            check=True,
        )
        state = {
            "scratch": str(scratch),
            "workspace": str(workspace),
            "store": str(store),
            "package": package,
            "lifecycle": row["lifecycle"],
        }
        write(saved, state)
        write(
            case / "prime.json",
            {"actor": "harness", "stdout": base.checked_bd(["prime", "--no-memories"], store, env)},
        )
    admin = Path(state["scratch"]) / "admin"
    return {**state, "env": experiment_env(admin / "config", admin / "tmp", admin / "bin")}


def grade(workspace: Path, local: Path, row: dict[str, Any]) -> dict[str, Any]:
    meta, _ = corpus(row["family"])
    cases = json.loads(
        (CORPUS / row["family"] / "graders" / f"stage-{row['stage']}.json").read_text()
    )
    profile = make_profile(local / "grade.sb", [], [workspace, base.PYTHON.parent.parent])
    results = []
    deadline = time.monotonic() + 60
    for case in cases:
        if time.monotonic() >= deadline:
            results.append({"name": case["name"], "passed": False, "reason": "grading_deadline"})
            continue
        args = [
            "/usr/bin/sandbox-exec",
            "-f",
            str(profile),
            str(base.PYTHON),
            str(workspace / meta["entrypoint"]),
            *case.get("argv", []),
        ]
        try:
            proc = subprocess.run(
                args,
                cwd=workspace,
                input=json.dumps(case.get("stdin", case.get("input"))),
                capture_output=True,
                text=True,
                timeout=min(3, max(0.1, deadline - time.monotonic())),
                env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
            )
            results.append(
                {
                    "name": case["name"],
                    "passed": proc.returncode == 0 and compare_json(proc.stdout, case["expected"]),
                    "exit": proc.returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                }
            )
        except subprocess.TimeoutExpired:
            results.append({"name": case["name"], "passed": False, "reason": "case_timeout"})
    return {
        "passed": all(r["passed"] for r in results),
        "correct": sum(r["passed"] for r in results),
        "total": len(cases),
        "cases": results,
    }


def native_snapshot(source: Path, destination: Path) -> None:
    def ignore(directory: str, names: list[str]) -> list[str]:
        # Preserve actual state in scratch. Archive dependency hashes instead of more copies.
        p = Path(directory)
        return [
            n
            for n in names
            if n in {"__pycache__", ".pytest_cache"} or (n == "cache" and p.name == "plugins")
        ]

    shutil.copytree(source, destination, symlinks=True, ignore=ignore)


def run_session(out: Path, row: dict[str, Any], endpoint: str | None) -> dict[str, Any]:
    evidence = session_path(out, row)
    if evidence.exists():
        if (evidence / "result.json").exists():
            print(f"PRESERVED {row['slot']}", flush=True)
            existing: dict[str, Any] = json.loads((evidence / "result.json").read_text())
            return existing
        raise RuntimeError(f"Claimed but unfinished slot cannot be rerun: {row['slot']}")
    state = setup(out, row)
    evidence.mkdir(exist_ok=False)
    scratch, workspace, store = (Path(state[k]) for k in ("scratch", "workspace", "store"))
    stage = row["stage"]
    local = scratch / f"stage-{stage}"
    local.mkdir()
    (local / "work").symlink_to(workspace, target_is_directory=True)
    for name in ("config", "tmp"):
        (local / name).mkdir()
    native = local / "native"
    if stage == 1:
        native.mkdir()
    else:
        previous = session_path(out, {**row, "stage": stage - 1})
        if not (previous / "result.json").exists():
            raise RuntimeError("Missing completed predecessor; no repair or replacement")
        shutil.copytree(scratch / f"stage-{stage-1}" / "native", native, symlinks=True)
    _, tasks = corpus(row["family"])
    spec = tasks[stage - 1]
    public = spec.get("public_tests")
    if public:
        source = CORPUS / row["family"] / public
        target = workspace / public
        if target.exists() or target.is_symlink():
            raise FileExistsError("Stage public examples already exist; preserve and inspect")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    task = e2e.create_task(state, spec["title"], spec["body"])
    write(evidence / "task.json", task)
    write(evidence / "tasks-before.json", e2e.all_tasks(store, state["env"]))
    e2e.snapshot(workspace, evidence / "workspace-before")
    before = base.memories(store, state["env"])
    write(evidence / "memory-before.json", before)
    invocation = uuid.uuid4().hex
    log, _ = receipts.prepare(
        local / "bin", store, str(stage), invocation, binary=base.BD, python=base.PYTHON
    )
    env = shell_environment(local, experiment_env(local / "config", local / "tmp", local / "bin"))
    if endpoint:
        env["MEMBENCH_OLLAMA_BASE_URL"] = endpoint
    prompt = f"Work on {task['id']}."
    (evidence / "prompt.txt").write_text(prompt)
    launch = hosts.prepare(
        row["host"], local, env, prompt, hosts.MODELS[row["host"]], row["mode"], BUDGET
    )
    profile = make_profile(
        local / "sandbox.sb",
        [local, workspace, store],
        [local, workspace, store, *launch.readable_roots],
    )
    argv = ["/usr/bin/sandbox-exec", "-f", str(profile), *launch.argv]
    write(
        evidence / "launch.json",
        {"argv": argv, "settings": launch.public_settings, "harness_session": invocation},
    )
    start = time.monotonic()
    print(f"START {row['slot']} deadline={TIMEOUT}s", flush=True)
    timed_out = False
    with (
        (local / "stdout-private.jsonl").open("x") as stdout,
        (local / "stderr-private.txt").open("x") as stderr,
    ):
        proc = subprocess.Popen(
            argv,
            cwd=workspace,
            env=launch.env,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        write(evidence / "process.json", {"pid": proc.pid, "started_ns": time.time_ns()})
        try:
            code = proc.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            code = proc.wait()
    secrets = smoke.secret_values(launch.env, local)
    stream, leaked = smoke.sanitize((local / "stdout-private.jsonl").read_text(), secrets)
    stderr_text, stderr_leaked = smoke.sanitize((local / "stderr-private.txt").read_text(), secrets)
    (evidence / "stream.jsonl").write_text(stream)
    (evidence / "stderr.txt").write_text(stderr_text)
    observed = hosts.observe(row["host"], stream, local)
    rows_text, receipt_leaked = smoke.sanitize(json.dumps(receipts.read(log)), secrets)
    rows = json.loads(rows_text)
    write(evidence / "raw-receipts.json", rows)
    write(evidence / "tool-calls.json", [c.model_dump(mode="json") for c in observed.calls])
    ops = receipts.assess(
        rows,
        root_pid=proc.pid,
        leg=str(stage),
        session=invocation,
        tool_outputs=[str(c.result or "") for c in observed.calls],
        binary=str(base.BD),
        store=str(store),
    )
    after = base.memories(store, state["env"])
    write(evidence / "memory-after.json", after)
    actual_tasks = e2e.all_tasks(store, state["env"])
    write(evidence / "tasks-after.json", actual_tasks)
    e2e.snapshot(workspace, evidence / "workspace-after")
    native_snapshot(native, evidence / "native-after")
    hosts.export_evidence(row["host"], local, evidence / "host-evidence")
    artifact = grade(workspace, local, row)
    write(evidence / "artifact-grade.json", artifact)
    actions = [
        classify_operation(
            e["operation_argv"], e["returncode"], e["stdout"], e["stderr"], before, after
        )
        for e in ops["executions"]
    ]
    package_changes = [
        p
        for p, digest in state["package"]["files"].items()
        if not Path(p).is_file() or base.sha(Path(p)) != digest
    ]
    result = {
        **row,
        "task_id": task["id"],
        "model_requested": hosts.MODELS[row["host"]],
        "models_observed": observed.models,
        "session_id": observed.session_id,
        "exit_code": code,
        "timed_out": timed_out,
        "host_completed": observed.completed,
        "host_success": observed.success,
        "errors": observed.errors,
        "duration_s": time.monotonic() - start,
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
        "credential_redaction_required": leaked or stderr_leaked or receipt_leaked,
        "task_closed": any(
            t.get("id") == task["id"] and t.get("status") == "closed" for t in actual_tasks
        ),
        "package_changed_paths": package_changes,
        "administrative_memory_reads": 2,
        **e2e.instruction_reads([c.model_dump(mode="json") for c in observed.calls], workspace),
    }
    if endpoint:
        with urllib.request.urlopen(
            endpoint.removesuffix("/v1") + "/api/ps", timeout=5
        ) as response:
            context = json.load(response)
        write(evidence / "ollama-context.json", context)
        result["runtime_context_qualified"] = bool(
            context.get("models")
            and all(m.get("context_length", 0) >= 32768 for m in context["models"])
        )
    result["infrastructure_fault"] = bool(
        leaked
        or stderr_leaked
        or receipt_leaked
        or ops["unknown_execution"]
        or observed.models != [hosts.MODELS[row["host"]]]
        or not observed.session_id
        or result.get("runtime_context_qualified") is False
    )
    write(evidence / "result.json", result)
    print(
        f"DONE {row['slot']} artifact={artifact['correct']}/{artifact['total']} "
        f"actions={result['action_counts']} exit={code}",
        flush=True,
    )
    return result


def progress(out: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    results = [json.loads(p.read_text()) for p in (out / "cases").glob("*/stage-*/result.json")]
    return {
        "scheduled": len(manifest["slots"]),
        "assessed": len(results),
        "correct_artifacts": sum(r["artifact_passed"] for r in results),
        "hosts": {
            host: {
                "assessed": sum(r["host"] == host for r in results),
                "correct": sum(r["host"] == host and r["artifact_passed"] for r in results),
            }
            for host in hosts.MODELS
        },
    }


def run_phase(out: Path, phase: str) -> None:
    manifest = json.loads((out / "manifest.json").read_text())
    assert_frozen(manifest)
    phase_root = out / "phases" / phase
    if phase != "checkpoint":
        preceding = PHASES[PHASES.index(phase) - 1]
        prior = out / "phases" / preceding
        if not any((prior / name).exists() for name in ("completed.json", "failed.json")):
            raise ValueError("Prior phase must complete and be reviewed before continuation")
    phase_root.mkdir(parents=True, exist_ok=False)
    stop = threading.Event()

    def worker(host: str) -> None:
        server = log = endpoint = None
        blocked = out / "blocked" / f"{host}.json"
        if blocked.exists():
            print(f"BLOCKED {host}: preserving earlier failure; no replacement runs", flush=True)
            return
        try:
            rows = [r for r in manifest["slots"] if r["phase"] == phase and r["host"] == host]
            if host == "opencode":
                folder = phase_root / "ollama"
                folder.mkdir()
                scratch = Path(tempfile.mkdtemp(prefix="ordinary-server-", dir="/tmp")).resolve()
                server, endpoint, log = smoke.ollama_start(scratch, folder)
            for row in rows:
                if stop.is_set():
                    break
                assert_frozen(manifest)
                result = run_session(out, row, endpoint)
                assert_frozen(manifest)
                print("PROGRESS " + json.dumps(progress(out, manifest)), flush=True)
                if result["infrastructure_fault"]:
                    raise RuntimeError(
                        f"Infrastructure fault in {row['slot']}; inspect preserved evidence"
                    )
        except BaseException as exc:
            failure = {"type": type(exc).__name__, "message": str(exc), "phase": phase}
            if isinstance(exc, FrozenInputsChangedError):
                stop.set()
            else:
                blocked.parent.mkdir(exist_ok=True)
                write(blocked, failure)
            write(
                phase_root / f"{host}-failure.json",
                failure,
            )
            raise
        finally:
            if server is not None:
                smoke.stop_owned_server(server)
            if log is not None:
                log.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(worker, host): host for host in hosts.MODELS}
        failures = []
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                failures.append({"host": futures[future], "error": str(exc)})
    try:
        assert_frozen(manifest)
    except FrozenInputsChangedError as exc:
        failures.append({"host": "shared-inputs", "error": str(exc)})
    if failures:
        write(
            phase_root / "failed.json", {"failures": failures, "progress": progress(out, manifest)}
        )
        raise RuntimeError("Phase stopped with preserved failures; no automatic reruns")
    write(phase_root / "completed.json", progress(out, manifest))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--admission", type=Path)
    parser.add_argument("--run", choices=PHASES)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if sum([args.freeze, bool(args.run), args.status]) != 1:
        parser.error("Choose exactly one of --freeze, --run, or --status")
    if args.freeze:
        if args.admission is None:
            parser.error("--freeze requires --admission")
        freeze(args.out, args.admission)
    elif args.run:
        run_phase(args.out, args.run)
    else:
        print(
            json.dumps(
                progress(args.out, json.loads((args.out / "manifest.json").read_text())), indent=2
            )
        )


if __name__ == "__main__":
    main()
