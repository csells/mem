"""Bounded macOS memory capture/search/lookup experiment with real CLI receipts.

Run from memory-bench. A plan freezes before any model call. Every case owns fresh
scratch state; goal branches copy only the captured store/native memory. Never
re-purchase an interrupted case. This driver intentionally uses the existing
bd_receipts implementation and score_real_leg instead of inventing operation counts.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import random
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from membench.runner import bd_receipts
from membench.runner.bd_real_metrics import score_real_leg
from membench.runner.headless_agent import tool_calls_from_stream
from membench.runner.memory_routes_corpus import Task, build_tasks
from membench.runner.memory_routes_grade import grade_artifact, grade_capture
from membench.runner.memory_routes_runtime import experiment_env, make_profile, subscription_token
from membench.schemas.trace import ToolCall

MODEL = "claude-sonnet-4-6"
CLAUDE = Path("/Users/csells/.local/bin/claude").resolve()
BD = Path("/opt/homebrew/bin/bd").resolve()
PYTHON = Path("/opt/homebrew/bin/python3").resolve()
REPO = Path(__file__).resolve().parents[2]
BASE = """This project uses bd for task tracking. Inspect the assigned task, mark it
in_progress while working, and close it when the requested artifact is complete.
Task commands: bd show <id>; bd update <id> --status in_progress; bd close <id>.
Work only in this disposable project. Produce config.json, then finish.
A later session starts from a fresh checkout. Files created here and task
descriptions/notes are not carried over; only this project's persistent memory
survives. Preserve agreements that later work will need through that memory.
"""
EXAMPLES = """Persistent project memory is available through bd and survives sessions.
Use it to retain useful project knowledge. Native automatic memory is disabled.
Commands (use these exact forms):
bd remember '<content>' --key <key>   # create/update a memory
bd recall <key>                      # exact lookup
bd memories '<query>'                # search key/body by literal substring
bd memories                         # list all memories
Add --json for structured output. A successful write returns an acknowledgment.
"""
PROCEDURE = """Before finishing work that establishes an approved project contract,
save what a fresh session would need and could not recover from its own files.
Use the supplied Decision reference as the memory key. Preserve project and scope,
field names, types, values, units, and the source; include the approved JSON verbatim
in a fenced json block. Distinguish supplied facts from your interpretations.
Check the write acknowledgment, then read back that exact key and confirm the saved
contract. Do not invent history or claim checks you did not run.
Before implementing work governed by an earlier agreement absent from this session:
- If given its exact key, run bd recall <key>.
- Otherwise search for a distinctive project/topic word with bd memories '<word>'.
  Search is literal substring, not semantic search. If empty, try a shorter distinct
  word; inspect matching scope and recall the matching key before implementing.
- Use the retrieved contract's actual types and values. Do not reinterpret a value
  as an issue reference. Prefer a complete current specification in the user request
  over older memory; when the full current contract is supplied, no lookup is needed.
If memory lacks the required agreement, explain what is missing instead of guessing.
"""
NATIVE = """Use your normal persistent native memory to retain project knowledge that
will help future sessions. It survives this session; ordinary workspace files do not.
The bd tool handles task tracking. Native memory is enabled in its isolated directory.
"""


def new_json(path: Path, value: Any) -> None:
    with path.open("x") as target:
        json.dump(value, target, indent=2)
        target.write("\n")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cli(args: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=90)


def checked_bd(args: list[str], store: Path, env: dict[str, str]) -> str:
    profile = Path(env["CLAUDE_CONFIG_DIR"]) / (
        "bd-" + hashlib.sha256(str(store).encode()).hexdigest()[:16] + ".sb"
    )
    if not profile.exists():
        make_profile(profile, [Path(env["CLAUDE_CONFIG_DIR"]), Path(env["TMPDIR"]), store], [store])
    result = cli(
        ["/usr/bin/sandbox-exec", "-f", str(profile), str(BD), "--sandbox", *args],
        cwd=store,
        env=env,
    )
    if result.returncode:
        raise RuntimeError(f"bd {args[0]} failed: {result.stderr[-2000:]}")
    return result.stdout


def initialize_store(store: Path, env: dict[str, str], evidence: Path) -> None:
    store.mkdir()
    profile = make_profile(
        store / "initialization.sb",
        [Path(env["CLAUDE_CONFIG_DIR"]), Path(env["TMPDIR"]), store],
        [store],
    )
    result = cli(
        [
            "/usr/bin/sandbox-exec",
            "-f",
            str(profile),
            str(BD),
            "--sandbox",
            "init",
            "--non-interactive",
            "--skip-agents",
            "--skip-hooks",
            "--prefix",
            "trial",
        ],
        cwd=store,
        env=env,
    )
    new_json(
        evidence,
        {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr},
    )
    if result.returncode:
        raise RuntimeError(f"bd initialization failed: {result.stderr}")


def memories(store: Path, env: dict[str, str]) -> dict[str, str]:
    value = json.loads(checked_bd(["memories", "--json"], store, env))
    if (
        not isinstance(value, dict)
        or type(value.get("schema_version")) is not int
        or value["schema_version"] != 1
    ):
        raise ValueError("bd memories returned an unexpected schema")
    entries = {k: v for k, v in value.items() if k != "schema_version"}
    if any(not isinstance(v, str) for v in entries.values()):
        raise ValueError("bd memories returned non-string memory content")
    return entries


def prepare_instrumentation(directory: Path, store: Path, leg_id: str) -> tuple[Path, Path]:
    directory.mkdir()
    shutil.copyfile(Path(bd_receipts.__file__), directory / "receipt_impl.py")
    receipt = directory.parent / "receipts.jsonl"
    shim = directory / "bd"
    shim.write_text(
        f"#!{PYTHON}\nimport sys\nfrom receipt_impl import wrapper_main\n"
        f"sys.exit(wrapper_main(binary={str(BD)!r}, store={str(store)!r}, "
        f"receipt_path={str(receipt)!r}))\n"
    )
    shim.chmod(0o700)
    hook = directory / "hook.py"
    hook.write_text(
        "import json,sys\nfrom receipt_impl import hook_response\n"
        f"print(json.dumps(hook_response(json.load(sys.stdin), leg_id={leg_id!r})))\n"
    )
    return hook, receipt


def _result_event(stream: str) -> dict[str, Any]:
    values = [json.loads(line) for line in stream.splitlines() if line.strip()]
    results = [value for value in values if value.get("type") == "result"]
    if len(results) != 1:
        raise RuntimeError("Expected exactly one terminal Claude result")
    return dict(results[0])


def session_event(stream: str) -> dict[str, Any]:
    values = [json.loads(line) for line in stream.splitlines() if line.strip()]
    starts = [v for v in values if v.get("type") == "system" and v.get("subtype") == "init"]
    if len(starts) != 1:
        raise RuntimeError("Expected exactly one Claude session initialization")
    event = dict(starts[0])
    if (
        event.get("model") != MODEL
        or not isinstance(event.get("session_id"), str)
        or not event["session_id"].strip()
    ):
        raise RuntimeError("Claude session model/identity differs from planned run")
    return event


def observed_expected_payload(
    operations: list[dict[str, Any]], expected: dict[str, Any]
) -> bool | None:
    verdicts = [
        grade_capture({"observed": content}, "observed", expected)["passed"]
        for op in operations
        if op["is_read"] and op["output_observed"] and op["returncode"] == 0
        for content in op["content"]
    ]
    if any(v is True for v in verdicts):
        return True
    return None if any(v is None for v in verdicts) else False


def is_behavioral_limit(terminal: dict[str, Any], *, allow: bool) -> bool:
    """Recognized terminal budget caps remain failed trials, not broken infrastructure."""
    return (
        allow
        and terminal.get("is_error") is True
        and terminal.get("subtype") in {"error_max_turns", "error_max_budget_usd"}
    )


def route_summary(
    observation: dict[str, Any],
    calls: list[ToolCall],
    artifact_path: Path,
    expected: dict[str, Any],
) -> dict[str, Any]:
    reads = [
        op
        for op in observation["operations"]
        if op["is_read"] and op["output_observed"] and op["returncode"] == 0
    ]
    writes = []
    for call in calls:
        value = call.arguments.get("file_path")
        if call.name == "Write" and isinstance(value, str) and value:
            path = Path(value)
            if not path.is_absolute():
                path = artifact_path.parent / path
            if path.resolve() == artifact_path.resolve():
                writes.append(call)
    first_write = min(
        (c.tool_use_index for c in writes if c.tool_use_index is not None), default=None
    )
    before = [
        op
        for op in reads
        if first_write is not None
        and op["tool_result_index"] is not None
        and op["tool_result_index"] < first_write
    ]
    direct = [op for op in reads if "recall" in op["argv"]]
    searches = [
        op
        for op in reads
        if "memories" in op["argv"]
        and any(not x.startswith("-") for x in op["argv"][op["argv"].index("memories") + 1 :])
    ]
    return {
        "bd_read_before_first_config_write": bool(before) if first_write is not None else None,
        "bd_direct_lookup": bool(direct),
        "bd_search": bool(searches),
        "bd_correct_payload_observed": observed_expected_payload(reads, expected),
        "bd_correct_payload_via_direct": observed_expected_payload(direct, expected),
        "bd_correct_payload_via_search": observed_expected_payload(searches, expected),
        "bd_correct_payload_before_first_config_write": (
            observed_expected_payload(before, expected) if first_write is not None else None
        ),
    }


def run_leg(
    *,
    case: Path,
    evidence: Path,
    leg: str,
    policy: str,
    prompt: str,
    store: Path,
    native_from: Path | None,
    expected: dict[str, Any],
    budget: float,
    guidance_override: str | None = None,
    configure_session: Callable[[Path, Path, str], dict[str, Any]] | None = None,
    retain_behavioral_limits: bool = False,
) -> tuple[dict[str, Any], Path]:
    evidence.mkdir()
    local = case / leg
    local.mkdir()
    for name in ("work", "config", "tmp"):
        (local / name).mkdir()
    native = local / "native"
    if native_from is None:
        native.mkdir()
    else:
        shutil.copytree(native_from, native)
    hook, receipts = prepare_instrumentation(local / "bin", store, leg)
    env = experiment_env(local / "config", local / "tmp", local / "bin")
    # The subscription credential is transient and never included in artifacts.
    env["CLAUDE_CODE_OAUTH_TOKEN"] = subscription_token()
    task = json.loads(
        checked_bd(["create", f"{leg}: produce project configuration", "--json"], store, env)
    )
    task_id = task["id"]
    settings: dict[str, Any] = {
        "autoMemoryEnabled": policy == "native",
        "autoMemoryDirectory": str(native),
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": f"{PYTHON} {hook}"}],
                }
            ]
        },
    }
    if configure_session is not None:
        extra_hooks = configure_session(local, store, task_id)
        for event, handlers in extra_hooks.items():
            settings["hooks"].setdefault(event, []).extend(handlers)
    settings_path = local / "settings.json"
    new_json(settings_path, settings)
    profile = make_profile(
        local / "sandbox.sb",
        writable_roots=[local / "work", local / "config", local / "tmp", native, store, local],
        readable_roots=[local, store, CLAUDE.parent],
    )
    guidance = (
        NATIVE if policy == "native" else EXAMPLES + (PROCEDURE if policy == "protocol" else "")
    )
    if guidance_override is not None:
        guidance = guidance_override
    full_prompt = f"{BASE}\n{guidance}\nAssigned task: {task_id}\n\n{prompt}"
    (evidence / "prompt.txt").write_text(full_prompt)
    args = [
        "/usr/bin/sandbox-exec",
        "-f",
        str(profile),
        str(CLAUDE),
        "-p",
        full_prompt,
        "--model",
        MODEL,
        "--output-format",
        "stream-json",
        "--verbose",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--setting-sources",
        "",
        "--settings",
        str(settings_path),
        "--tools",
        "Bash,Read,Write,Edit",
        "--allowedTools",
        "Bash,Read,Write,Edit",
        "--permission-mode",
        "dontAsk",
        "--permission-prompts",
        "none",
        "--disable-slash-commands",
        "--no-chrome",
        "--max-turns",
        "18",
        "--max-budget-usd",
        str(budget),
    ]
    new_json(
        evidence / "started.json",
        {"leg": leg, "policy": policy, "scratch": str(local), "argv": args},
    )
    started = time.monotonic()
    print(f"START {evidence.parent.name}/{leg}", flush=True)
    with (evidence / "stream.jsonl").open("x") as out, (evidence / "stderr.txt").open("x") as err:
        try:
            proc = subprocess.Popen(
                args,
                cwd=local / "work",
                env=env,
                stdout=out,
                stderr=err,
                text=True,
                start_new_session=True,
            )
            exit_code = proc.wait(timeout=180)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            new_json(
                evidence / "halt.json",
                {"reason": "timeout", "elapsed_s": time.monotonic() - started},
            )
            raise
    stream = (evidence / "stream.jsonl").read_text()
    terminal = _result_event(stream)
    behavioral_limit = is_behavioral_limit(terminal, allow=retain_behavioral_limits)
    session = session_event(stream)
    calls = tool_calls_from_stream(stream)
    raw_receipts = (
        [json.loads(line) for line in receipts.read_text().splitlines()]
        if receipts.exists()
        else []
    )
    observation = score_real_leg(
        calls,
        raw_receipts,
        leg_id=leg,
        status="ok" if exit_code == 0 or behavioral_limit else "error",
        expected_binary=str(BD),
        expected_store=str(store),
        expected_session=session["session_id"],
    ).model_dump(mode="json")
    store_state = memories(store, env)
    artifact = grade_artifact(local / "work" / "config.json", expected)
    shutil.copytree(local / "work", evidence / "workspace")
    shutil.copytree(native, evidence / "native")
    new_json(evidence / "memory.json", store_state)
    new_json(evidence / "receipts.json", raw_receipts)
    result = {
        "leg": leg,
        "policy": policy,
        "exit_code": exit_code,
        "terminal_subtype": terminal.get("subtype"),
        "is_error": terminal.get("is_error"),
        "behavioral_limit": behavioral_limit,
        "cost_usd": terminal.get("total_cost_usd"),
        "duration_s": time.monotonic() - started,
        "turns": terminal.get("num_turns"),
        "model_usage": terminal.get("modelUsage"),
        "artifact": artifact,
        "memory_evidence": observation,
        "session_id": session["session_id"],
        "task_id": task_id,
        **route_summary(observation, calls, local / "work" / "config.json", expected),
        "native_file_count": sum(p.is_file() for p in native.rglob("*")),
        "scratch": str(local),
    }
    new_json(evidence / "result.json", result)
    print(
        f"DONE {evidence.parent.name}/{leg}: artifact={artifact['passed']} "
        f"reads={observation['observed_reads']} writes={observation['accepted_writes']} "
        f"cost={result['cost_usd']}",
        flush=True,
    )
    if ((exit_code != 0 or terminal.get("is_error")) and not behavioral_limit) or observation[
        "evidence_unknown"
    ]:
        raise RuntimeError(
            f"Session infrastructure/measurement failure: {evidence}; inspect preserved evidence"
        )
    return result, native


def run_case(out: Path, task: Task, policy: str, budget: float) -> None:
    directory = out / "cases" / f"{task.id}-{policy}"
    directory.mkdir(parents=True)
    case = Path(tempfile.mkdtemp(prefix="mem-route-", dir="/tmp")).resolve()
    new_json(directory / "started.json", {"task": task.id, "policy": policy, "scratch": str(case)})
    try:
        setup = case / "setup"
        setup.mkdir()
        for child in ("config", "tmp", "bin"):
            (setup / child).mkdir()
        env = experiment_env(setup / "config", setup / "tmp", setup / "bin")
        store = case / "store"
        initialize_store(store, env, directory / "initialization.json")
        for key, body in task.decoys.items():
            checked_bd(["remember", body, "--key", key], store, env)
        new_json(directory / "initial-memory.json", memories(store, env))
        establish, native = run_leg(
            case=case,
            evidence=directory / "establish",
            leg="establish",
            policy=policy,
            prompt=task.establish_prompt,
            store=store,
            native_from=None,
            expected=task.expected_config,
            budget=budget,
        )
        captured = memories(store, env)
        capture = (
            grade_capture(captured, task.key, task.expected_config)
            if policy != "native"
            else {"passed": None, "reason": "native_capture_graded_by_downstream_artifact"}
        )
        results = {"establish": establish}
        for route in ("direct", "search", "unnecessary"):
            branch = case / f"store-{route}"
            initialize_store(branch, env, directory / f"initialization-{route}.json")
            # Transfer only actual captured KV; task notes/history cannot carry answers.
            for key, body in captured.items():
                checked_bd(["remember", body, "--key", key], branch, env)
            transferred = memories(branch, env)
            if transferred != captured:
                raise RuntimeError("Goal memory transfer differs from actual capture")
            new_json(directory / f"transferred-{route}.json", transferred)
            result, _ = run_leg(
                case=case,
                evidence=directory / route,
                leg=route,
                policy=policy,
                prompt=getattr(task, f"goal_prompt_{route}"),
                store=branch,
                native_from=native if policy == "native" else None,
                expected=task.expected_config,
                budget=budget,
            )
            results[route] = result
        new_json(
            directory / "result.json",
            {"task": task.id, "policy": policy, "capture": capture, "legs": results},
        )
    except Exception as exc:
        new_json(directory / "halt.json", {"type": type(exc).__name__, "message": str(exc)})
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260906)
    parser.add_argument("--tasks", type=int, default=8)
    parser.add_argument("--policies", default="examples,protocol")
    parser.add_argument("--fire", action="store_true")
    parser.add_argument("--max-cases", type=int, default=1)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--session-budget", type=float, default=0.75)
    args = parser.parse_args()
    policies = args.policies.split(",")
    if not set(policies) <= {"examples", "protocol", "native"} or len(policies) != len(
        set(policies)
    ):
        raise ValueError("Invalid policies")
    if not 1 <= args.tasks <= 8 or not 1 <= args.workers <= 2 or args.max_cases < 1:
        raise ValueError("Tasks 1..8, workers 1..2, and positive max-cases required")
    tasks = build_tasks(args.seed)[: args.tasks]
    schedule = [{"task": task.id, "policy": policy} for task in tasks for policy in policies]
    random.Random(args.seed).shuffle(schedule)
    files = [
        Path(__file__),
        *sorted((REPO / "memory-bench/membench").rglob("*.py")),
    ]
    manifest = {
        "schema": "memory-routes-macos.v1",
        "model": MODEL,
        "seed": args.seed,
        "claude_version": subprocess.check_output([str(CLAUDE), "--version"], text=True).strip(),
        "bd_version": subprocess.check_output([str(BD), "--version"], text=True).strip(),
        "binary_sha256": {str(p): sha(p) for p in (CLAUDE, BD, PYTHON)},
        "source_sha256": {str(p.relative_to(REPO)): sha(p) for p in files},
        "tasks": [dataclasses.asdict(task) for task in tasks],
        "schedule": schedule,
        "planned_sessions": len(schedule) * 4,
        "session_budget_usd": args.session_budget,
        "policies": {
            "examples": BASE + EXAMPLES,
            "protocol": BASE + EXAMPLES + PROCEDURE,
            "native": BASE + NATIVE,
        },
        "interpretation": (
            "Configured bd-only policies; native is separate. Paired routes branch actual "
            "captured stores; no goal repair or reseeding. Literal JSON grading may leave "
            "prose capture unknown."
        ),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "manifest.json"
    if path.exists():
        if json.loads(path.read_text()) != manifest:
            raise ValueError("Frozen manifest differs; use a new output directory")
    else:
        if any(args.out.iterdir()):
            raise ValueError("Nonempty output has no manifest")
        new_json(path, manifest)
    print(f"PLAN {len(schedule)} cases / {len(schedule) * 4} sessions at {args.out}", flush=True)
    if not args.fire:
        return
    pending = []
    for row in schedule:
        directory = args.out / "cases" / f"{row['task']}-{row['policy']}"
        if directory.exists():
            if not (directory / "result.json").exists():
                raise ValueError(f"Interrupted case cannot be repurchased: {directory}")
            completed_case = json.loads((directory / "result.json").read_text())
            if (
                completed_case.get("task") != row["task"]
                or completed_case.get("policy") != row["policy"]
                or set(completed_case.get("legs", {}))
                != {"establish", "direct", "search", "unnecessary"}
            ):
                raise ValueError(f"Invalid completed case: {directory}")
            for leg, summary in completed_case["legs"].items():
                if json.loads((directory / leg / "result.json").read_text()) != summary:
                    raise ValueError(f"Completed leg differs from case result: {directory / leg}")
        else:
            pending.append(row)
    indexed = {task.id: task for task in tasks}
    purchased = pending[: args.max_cases]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        completed = 0
        for offset in range(0, len(purchased), args.workers):
            futures = [
                pool.submit(
                    run_case, args.out, indexed[row["task"]], row["policy"], args.session_budget
                )
                for row in purchased[offset : offset + args.workers]
            ]
            for future in as_completed(futures):
                future.result()
                completed += 1
                print(f"CASES {completed}/{len(purchased)} completed this invocation", flush=True)


if __name__ == "__main__":
    main()
