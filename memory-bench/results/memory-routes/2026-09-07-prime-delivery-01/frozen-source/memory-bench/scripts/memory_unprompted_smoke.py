"""Two fresh real CLI sessions qualify wiring, never unprompted adoption.

Each output directory is single-use. Only --run launches inference. Actual Beads
records and project files survive, while sessions/config/credentials are isolated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from membench.runner import memory_e2e_receipts as receipts
from membench.runner import memory_model_profiles
from membench.runner import memory_unprompted_hosts as hosts
from membench.runner.memory_e2e_package import install_package
from membench.runner.memory_host_shell import shell_environment
from membench.runner.memory_routes_runtime import experiment_env, make_profile
from membench.runner.memory_unprompted_grade import grade_record
from scripts import memory_e2e_experiment as e2e
from scripts import memory_routes_experiment as base

POLICY = {
    "project": "qualification",
    "identifiers": {"kind": "opaque-string", "trim": True},
    "examples": ["000417", "AC-019"],
}
TIMEOUT = 420


def write_json(path: Path, value: Any) -> None:
    with path.open("x") as target:
        json.dump(value, target, indent=2, ensure_ascii=False)
        target.write("\n")


def secret_values(launch_env: dict[str, str], local: Path) -> list[str]:
    values = [
        value
        for key, value in launch_env.items()
        if any(word in key for word in ("TOKEN", "API_KEY", "SECRET")) and len(value) > 10
    ]
    auth = local / "config/auth.json"
    if auth.is_file():
        data = json.loads(auth.read_text())
        values.extend(
            v for v in data.get("tokens", {}).values() if isinstance(v, str) and len(v) > 10
        )
    return values


def sanitize(text: str, secrets: list[str]) -> tuple[str, bool]:
    changed = False
    for value in secrets:
        if value in text:
            text = text.replace(value, "<redacted-credential>")
            changed = True
    return text, changed


def setup(out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=False)
    scratch = Path(tempfile.mkdtemp(prefix="memory-four-cli-", dir="/tmp")).resolve()
    work = scratch / "work"
    work.mkdir()
    admin = scratch / "admin"
    for name in ("config", "tmp", "bin"):
        (admin / name).mkdir(parents=True)
    env = experiment_env(admin / "config", admin / "tmp", admin / "bin")
    store = scratch / "store"
    base.initialize_store(store, env, out / "initialization.json")
    subprocess.run(["/usr/bin/git", "init", "--quiet", str(work)], check=True, env=env)
    install_package(work, store, "installed")
    marks = {k: uuid.uuid4().hex for k in ("rule", "skill", "reference")}
    with (work / "AGENTS.md").open("a") as target:
        target.write(
            "\n## Integration qualification only\n"
            "For each qualification task, also write `markers-<issue-id>.json` with keys "
            "rule, skill, reference. Read the Beads skill and its memory reference for their "
            f"marker values. The rule marker is `{marks['rule']}`. "
            "These diagnostics are excluded from the adoption experiment.\n"
        )
    skill = work / ".agents/skills/beads"
    for path, key in [(skill / "SKILL.md", "skill"), (skill / "references/memory.md", "reference")]:
        with path.open("a") as target:
            target.write(f"\nFor integration qualification, the {key} marker is `{marks[key]}`.\n")
    state = {"scratch": str(scratch), "workspace": str(work), "store": str(store), "marks": marks}
    write_json(out / "state.json", state)
    prime = base.checked_bd(["prime", "--no-memories"], store, env)
    write_json(out / "prime.json", {"actor": "harness", "output": prime})
    return {**state, "env": env}


def grade_files(workspace: Path, task_id: str, markers: dict[str, str], leg: str) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, expected in [(f"markers-{task_id}.json", markers), (f"{leg}.json", POLICY)]:
        try:
            value = json.loads((workspace / name).read_text())
            # JSON booleans and numeric scalars are distinct application types.
            results[name] = json.dumps(value, sort_keys=True) == json.dumps(
                expected, sort_keys=True
            )
        except (OSError, ValueError):
            results[name] = False
    results["passed"] = all(results.values())
    return results


def run_leg(
    out: Path,
    state: dict[str, Any],
    host: str,
    leg: str,
    native_from: Path | None,
    endpoint: str | None,
    profile_id: str | None = None,
) -> tuple[dict[str, Any], Path]:
    out.mkdir(exist_ok=False)
    scratch, workspace, store = (Path(state[k]) for k in ("scratch", "workspace", "store"))
    local = scratch / leg
    local.mkdir()
    (local / "work").symlink_to(workspace, target_is_directory=True)
    for name in ("config", "tmp"):
        (local / name).mkdir()
    native = local / "native"
    if native_from is None:
        native.mkdir()
    else:
        shutil.copytree(native_from, native, symlinks=True)
    key = "qualification-identifiers"
    body = (
        "This is an explicit integration qualification, excluded from adoption scores. "
        "Implement id_format.py: when run with one command-line argument, print that "
        "argument with surrounding whitespace removed, preserving leading zeros and case. "
        "Verify it with ' 000417 ' and ' AC-019 '. "
        f"Write {leg}.json with the full settings recovered or supplied below. "
    )
    if leg == "capture":
        body += f"Settings: {json.dumps(POLICY)}. Save these exact settings with bd remember "
        body += f"under key {key}, then search qualification-identifiers and recall the full key."
    else:
        body += f"Search bd memories for qualification-identifiers, then use bd recall {key} "
        body += "to inspect the full record. Reproduce the saved settings without another "
        body += "memory write. "
        body += "Also run bd recall qualification-missing-record and observe its expected nonzero "
        body += "exit; this missing-key diagnostic should not prevent completing the task."
    task = e2e.create_task(state, f"Qualify {leg} CLI integration", body)
    write_json(out / "task.json", task)
    e2e.snapshot(workspace, out / "workspace-before")
    before = base.memories(store, state["env"])
    write_json(out / "memory-before.json", before)
    invocation = uuid.uuid4().hex
    log, _ = receipts.prepare(
        local / "bin", store, leg, invocation, binary=base.BD, python=base.PYTHON
    )
    env = shell_environment(local, experiment_env(local / "config", local / "tmp", local / "bin"))
    if endpoint:
        env["MEMBENCH_OLLAMA_BASE_URL"] = endpoint
    prompt = f"Work on {task['id']}."
    (out / "prompt.txt").write_text(prompt)
    model = (
        memory_model_profiles.get_profile(profile_id).model
        if profile_id is not None
        else hosts.MODELS[host]
    )
    if profile_id is None:
        launch = hosts.prepare(host, local, env, prompt, model, "isolated", 1.50)
    else:
        if memory_model_profiles.get_profile(profile_id).host != host:
            raise ValueError("Qualification profile and host differ")
        launch = memory_model_profiles.prepare(profile_id, local, env, prompt, "isolated", 1.50)
    profile = make_profile(
        local / "sandbox.sb",
        [local, workspace, store],
        [local, workspace, store, *launch.readable_roots],
    )
    argv = ["/usr/bin/sandbox-exec", "-f", str(profile), *launch.argv]
    write_json(
        out / "launch.json",
        {
            "argv": argv,
            "settings": launch.public_settings,
            "harness_session": invocation,
            "inference": True,
        },
    )
    start = time.monotonic()
    label = profile_id or host
    print(f"START {label}/{leg}: timeout={TIMEOUT}s", flush=True)
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
        write_json(out / "process.json", {"pid": proc.pid, "started_ns": time.time_ns()})
        while True:
            remaining = TIMEOUT - (time.monotonic() - start)
            if remaining <= 0:
                timed_out = True
                os.killpg(proc.pid, signal.SIGKILL)
                code = proc.wait()
                break
            try:
                code = proc.wait(timeout=min(30, remaining))
                break
            except subprocess.TimeoutExpired:
                print(
                    f"RUNNING {label}/{leg}: elapsed={time.monotonic() - start:.1f}s "
                    f"stdout_bytes={(local / 'stdout-private.jsonl').stat().st_size}",
                    flush=True,
                )
    secrets = secret_values(launch.env, local)
    stream, leaked = sanitize((local / "stdout-private.jsonl").read_text(), secrets)
    stderr_text, stderr_leaked = sanitize((local / "stderr-private.txt").read_text(), secrets)
    (out / "stream.jsonl").write_text(stream)
    (out / "stderr.txt").write_text(stderr_text)
    observed = (
        hosts.observe(host, stream, local)
        if profile_id is None
        else memory_model_profiles.observe(profile_id, stream, local)
    )
    rows = receipts.read(log)
    safe_rows, receipt_leaked = sanitize(json.dumps(rows), secrets)
    rows = json.loads(safe_rows)
    write_json(out / "raw-receipts.json", rows)
    write_json(out / "tool-calls.json", [c.model_dump(mode="json") for c in observed.calls])
    ops = receipts.assess(
        rows,
        root_pid=proc.pid,
        leg=leg,
        session=invocation,
        tool_outputs=[str(c.result or "") for c in observed.calls],
        binary=str(base.BD),
        store=str(store),
    )
    after = base.memories(store, state["env"])
    write_json(out / "memory-after.json", after)
    tasks = e2e.all_tasks(store, state["env"])
    write_json(out / "tasks-after.json", tasks)
    e2e.snapshot(workspace, out / "workspace-after")
    e2e.snapshot(native, out / "native-after")
    try:
        hosts.export_evidence(host, local, out / "host-evidence")
        export_error = None
    except (OSError, ValueError) as exc:
        export_error = type(exc).__name__
    file_grade = grade_files(workspace, task["id"], state["marks"], leg)
    behavior: list[bool] = []
    grade_profile = make_profile(local / "grade.sb", [], [workspace, base.PYTHON.parent.parent])
    for value, expected in [(" 000417 ", "000417"), (" AC-019 ", "AC-019")]:
        r = subprocess.run(
            [
                "/usr/bin/sandbox-exec",
                "-f",
                str(grade_profile),
                str(base.PYTHON),
                str(workspace / "id_format.py"),
                value,
            ],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=15,
        )
        behavior.append(r.returncode == 0 and r.stdout.strip() == expected)
    retained = grade_record(after.get(key, ""), POLICY)["passed"] is True
    failures = [r for r in ops["executions"] if r.get("returncode") != 0]
    missing_seen = any("qualification-missing-record" in str(r) for r in failures)
    report = {
        "host": host,
        "leg": leg,
        "profile_id": profile_id,
        "model_requested": model,
        "models_observed": observed.models,
        "model_evidence": observed.model_evidence,
        "session_id": observed.session_id,
        "model_matches": observed.models == [model],
        "exit_code": code,
        "timed_out": timed_out,
        "completed": observed.completed,
        "host_success": observed.success,
        "errors": observed.errors,
        "duration_s": time.monotonic() - start,
        "cost_usd": observed.cost_usd,
        "usage": observed.usage,
        "files": file_grade,
        "behavior": behavior,
        "retained_exact": retained,
        "memory_operations": ops,
        "record_unchanged": before == after,
        "missing_key_error_observed": missing_seen,
        "task_closed": any(
            t.get("id") == task["id"] and t.get("status") == "closed" for t in tasks
        ),
        "credential_redaction_required": leaked or stderr_leaked or receipt_leaked,
        "evidence_export_error": export_error,
        "administrative_reads": {"memory": 2, "tasks": 1},
        **e2e.instruction_reads([c.model_dump(mode="json") for c in observed.calls], workspace),
    }
    report["passed"] = bool(
        code == 0
        and not timed_out
        and observed.success
        and report["model_matches"]
        and file_grade["passed"]
        and all(behavior)
        and retained
        and report["task_closed"]
        and ops["agent_searches"]
        and ops["agent_recalls"]
        and ops["prime_calls"]
        and not ops["unknown_execution"]
        and not report["credential_redaction_required"]
        and export_error is None
        and (ops["agent_writes"] > 0 if leg == "capture" else before == after and missing_seen)
    )
    write_json(out / "result.json", report)
    print(
        f"DONE {label}/{leg}: passed={report['passed']} exit={code} model={observed.models}",
        flush=True,
    )
    return report, native


def stop_owned_server(proc: subprocess.Popen[str]) -> None:
    """Stop only the process group created for this qualification run."""
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()


def ollama_start(scratch: Path, out: Path) -> tuple[subprocess.Popen[str], str, Any]:
    root = scratch / "ollama"
    root.mkdir()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    model_root = Path.home() / ".ollama/models"
    read_roots = [model_root]
    for name in ("id_ed25519", "id_ed25519.pub"):
        path = Path.home() / ".ollama" / name
        if path.is_file():
            read_roots.append(path)
    profile = make_profile(root / "sandbox.sb", [root], read_roots)
    env = dict(os.environ)
    env.update(
        OLLAMA_HOST=f"127.0.0.1:{port}",
        OLLAMA_CONTEXT_LENGTH="32768",
        OLLAMA_MODELS=str(model_root),
        OLLAMA_NOPRUNE="true",
        OLLAMA_NO_CLOUD="1",
        OLLAMA_NUM_PARALLEL="1",
        TMPDIR=str(root),
        TMP=str(root),
        TEMP=str(root),
    )
    log = (out / "ollama-server.log").open("x")
    proc = None
    try:
        proc = subprocess.Popen(
            ["/usr/bin/sandbox-exec", "-f", str(profile), "/opt/homebrew/bin/ollama", "serve"],
            env=env,
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            text=True,
            start_new_session=True,
        )
        endpoint = f"http://127.0.0.1:{port}"
        write_json(
            out / "ollama-server.json",
            {
                "pid": proc.pid,
                "endpoint": endpoint,
                "context_requested": 32768,
                "existing_server_changed": False,
            },
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and proc.poll() is None:
            try:
                with urllib.request.urlopen(endpoint + "/api/version", timeout=1) as response:
                    json.load(response)
                return proc, endpoint + "/v1", log
            except OSError:
                time.sleep(0.2)
        raise RuntimeError("Task-owned Ollama server did not start; inspect its preserved log")
    except BaseException:
        if proc is not None:
            stop_owned_server(proc)
        log.close()
        raise


def run(out: Path, host: str, profile_id: str | None = None) -> dict[str, Any]:
    if profile_id is not None and memory_model_profiles.get_profile(profile_id).host != host:
        raise ValueError("Qualification profile and host differ")
    state = setup(out)
    write_json(out / "source-sha256.json", e2e.sources())
    binaries = [
        base.BD,
        base.PYTHON,
        Path(shutil.which(host if host != "claude" else "claude") or "").resolve(),
    ]
    if host == "zcode":
        binaries.append(hosts.ZCODE.parent.parent / "vendor/zcode.cjs")
    write_json(
        out / "binary-sha256.json",
        {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in binaries},
    )
    server, endpoint, log = None, None, None
    legs: list[dict[str, Any]] = []
    try:
        if host == "opencode":
            server, endpoint, log = ollama_start(Path(state["scratch"]), out)
        native = None
        for leg in ("capture", "reuse"):
            result, native = run_leg(out / leg, state, host, leg, native, endpoint, profile_id)
            legs.append(result)
            if not result["host_success"]:
                break
        context = None
        if endpoint:
            with urllib.request.urlopen(
                endpoint.removesuffix("/v1") + "/api/ps", timeout=5
            ) as response:
                context = json.load(response)
            write_json(out / "ollama-context.json", context)
        identities = [r["session_id"] for r in legs]
        result = {
            "host": host,
            "profile_id": profile_id,
            "scope": "explicit integration only; no adoption result",
            "legs": legs,
            "fresh_sessions": len(set(identities)) == 2,
            "passed": len(legs) == 2
            and len(set(identities)) == 2
            and all(r["passed"] for r in legs),
        }
        if host == "opencode":
            sized = bool(
                context
                and context.get("models")
                and all(m.get("context_length", 0) >= 32768 for m in context["models"])
            )
            result["runtime_context_qualified"] = sized
            result["passed"] = result["passed"] and sized
        write_json(out / "result.json", result)
        return result
    finally:
        if server is not None:
            stop_owned_server(server)
        if log is not None:
            log.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=hosts.MODELS, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--run", action="store_true", help="Launch the two integration sessions")
    args = parser.parse_args()
    if not args.run:
        print("No inference launched. Pass --run for a fresh isolated integration check.")
        return 0
    if args.out.exists():
        raise FileExistsError("Existing evidence is never overwritten or repurchased")
    try:
        result = run(args.out, args.host)
    except Exception as exc:
        if args.out.is_dir():
            write_json(args.out / "failure.json", {"type": type(exc).__name__, "message": str(exc)})
        raise
    print(json.dumps({"host": args.host, "passed": result["passed"]}), flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
