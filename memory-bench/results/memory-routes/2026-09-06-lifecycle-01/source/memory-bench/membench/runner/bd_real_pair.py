"""Two fresh real-task sessions with bd-only carryover and withheld repository checks."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from membench.runner.bd_real_runtime import wrap_agent_runner
from membench.runner.bd_receipt_surface import prepare_receipt_leg, read_receipts
from membench.runner.headless_agent import (
    HeadlessClaudeAgent,
    RecordingRunner,
    seed_config_dir,
    stream_cli_version,
    tool_calls_from_stream,
)
from membench.runner.native_memory_hook import hook_reaches, install_native_memory_hook
from membench.runner.sandbox import assert_neutral_ancestry
from membench.runner.tool_surface import (
    BD_CONTEXT_ADDENDUM,
    HOST_DENIED_TOOLS,
    MemoryToolSurface,
    provision_memory_tool,
)
from membench.runtime import StepContext
from membench.schemas.sequence import SequenceStep
from membench.spawn import Runner, run_in_session

COMMON_R4 = (
    "You have a persistent memory tool available in this session. "
    "Consult it when the task may depend on facts established in earlier sessions. "
    "If something you need is not stated in this task, recall it before you answer. "
    "After you act, record any durable fact you established so a later session can recall it."
)
FOCUSED_PROTOCOL = (
    "When you establish useful new knowledge, preserve the fact with its source and scope in bd. "
    "Keep the saved claim faithful to what you actually observed; do not invent missing details. "
    "Use the write acknowledgement to check that saving succeeded; a separate read-back is not "
    "required. If you learned nothing useful and new, do not create a memory just to satisfy this "
    "protocol. In a fresh task, retrieve prior knowledge when it could help, check its "
    "applicability against the current evidence, and use it before the related work."
)
ENV_UNSET = (
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY",
    "CLAUDE_CODE_SIMPLE",
    "CLAUDE_CODE_REMOTE",
    "CLAUDE_CODE_REMOTE_MEMORY_DIR",
    "CLAUDE_COWORK_MEMORY_PATH_OVERRIDE",
    "CLAUDE_CODE_SAFE_MODE",
)
IMPORT_GUARDED_PYTEST = """import importlib, json, pathlib, runpy, sys
root = pathlib.Path(sys.argv[1]).resolve()
try:
    package = importlib.import_module("codeprobe")
    origin = pathlib.Path(package.__file__).resolve()
    if not origin.is_relative_to(root):
        raise RuntimeError("codeprobe import outside candidate: " + str(origin))
except Exception as exc:
    print(str(exc), file=sys.stderr)
    sys.exit(2)
print(json.dumps({"candidate_import_origin": str(origin)}), flush=True)
sys.argv = ["pytest", *sys.argv[2:]]
try:
    runpy.run_module("pytest", run_name="__main__")
finally:
    origins = {}
    for name, module in tuple(sys.modules.items()):
        if name == "codeprobe" or name.startswith("codeprobe."):
            source = getattr(module, "__file__", None)
            if source is not None:
                resolved = pathlib.Path(source).resolve()
                if not resolved.is_relative_to(root):
                    print("codeprobe module import outside candidate: " +
                          str(resolved), file=sys.stderr)
                    sys.exit(2)
                origins[name] = str(resolved)
    print(json.dumps({"candidate_module_origins": origins}), flush=True)
"""
AGENT_RUNNER: Runner = run_in_session
CHECK_RUNNER: Runner = run_in_session


def _json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def assert_managed_settings_absent() -> None:
    """Managed policy survives --setting-sources; refuse unmeasured policy on this Linux pilot."""
    root = Path("/etc/claude-code")
    paths = [root / "managed-settings.json"]
    dropins = root / "managed-settings.d"
    if dropins.exists():
        paths.extend(dropins.iterdir())
    if any(path.exists() or path.is_symlink() for path in paths):
        raise RuntimeError("managed Claude settings must be absent for this isolated pilot")


def _archive_base(task: Mapping[str, Any], cwd: Path) -> None:
    archive = subprocess.run(
        [
            "git",
            "-C",
            str(task["repo_absolute"]),
            "archive",
            "--format=tar",
            str(task["base_commit"]),
        ],
        capture_output=True,
        check=True,
        timeout=60,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(cwd, filter="data")
    if (cwd / ".git").exists():
        raise RuntimeError("goal archive unexpectedly contains .git")


def _snapshot(cwd: Path, path: Path) -> dict[str, str]:
    hashes = {}
    with tarfile.open(path, "w") as archive:
        for entry in sorted(cwd.rglob("*")):
            relative = entry.relative_to(cwd).as_posix()
            archive.add(entry, arcname=relative, recursive=False)
            if entry.is_file() and not entry.is_symlink():
                hashes[relative] = hashlib.sha256(entry.read_bytes()).hexdigest()
    return hashes


def _plant_context(cwd: Path, surface: MemoryToolSurface, condition: str) -> None:
    if not surface.bd_context:
        raise RuntimeError("bd deployment context was not captured")
    for name, text in sorted(surface.bd_context.items()):
        if Path(name).name != name:
            raise RuntimeError("bd context name must be a direct child")
        target = cwd / name
        if target.is_symlink():
            raise RuntimeError("cannot append agent context to a symlink")
        original = target.read_text() if target.exists() else ""
        target.write_text(original + "\n\n" + text + "\n" + BD_CONTEXT_ADDENDUM)
    target = cwd / "CLAUDE.md"
    if target.is_symlink():
        raise RuntimeError("cannot append guidance to a symlink")
    original = target.read_text() if target.exists() else ""
    focused = "\n\n" + FOCUSED_PROTOCOL if condition == "focused" else ""
    target.write_text(original + "\n\n" + COMMON_R4 + focused + "\n")


def deliver_user_instructions(cwd: Path, config_dir: Path, out: Path) -> dict[str, str]:
    """Deliver this corpus's import-free guide through the enabled user settings source."""
    source = cwd / "CLAUDE.md"
    if source.is_symlink() or not source.is_file():
        raise RuntimeError("instruction source must be a regular CLAUDE.md file")
    content = source.read_bytes()
    text = content.decode("utf-8")
    if not text.strip() or re.search(r"(?<!\w)@\S+", text):
        raise RuntimeError("instructions must be nonempty and contain no relative-context imports")
    target = config_dir / "CLAUDE.md"
    if target.is_symlink():
        raise RuntimeError("instruction destination must not be a symlink")
    with target.open("xb") as handle:
        handle.write(content)
    with (out / "instructions.md").open("xb") as handle:
        handle.write(content)
    record = {
        "source": str(source),
        "destination": str(target),
        "setting_sources": "user",
        "sha256": hashlib.sha256(content).hexdigest(),
        "import_policy": "reject",
    }
    _json(out / "instruction-delivery.json", record)
    return record


def _text(value: str | bytes | None) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""


def _preserving_runner(out: Path) -> Runner:
    def run(argv: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        _json(out / "argv.json", list(argv))
        try:
            completed = AGENT_RUNNER(argv, **kwargs)
        except subprocess.TimeoutExpired as exc:
            (out / "raw.stream.jsonl").write_text(_text(exc.stdout))
            (out / "stderr.txt").write_text(_text(exc.stderr))
            _json(out / "process.json", {"status": "timeout", "returncode": None})
            raise
        except OSError as exc:
            _json(out / "process.json", {"status": "error", "error_type": type(exc).__name__})
            raise
        (out / "raw.stream.jsonl").write_text(completed.stdout or "")
        (out / "stderr.txt").write_text(completed.stderr or "")
        _json(
            out / "process.json",
            {
                "status": "ok" if completed.returncode == 0 else "error",
                "returncode": completed.returncode,
            },
        )
        return completed

    return run


def _unexpected_hooks(stream: str) -> bool:
    for line in stream.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if str(event.get("subtype", "")).startswith("hook_"):
            hook_event = event.get("hook_event")
            if hook_event != "PreToolUse":
                return True
    return False


def _stream_evidence(
    stream: str, receipts: Sequence[Mapping[str, Any]], model: str, cli_version: str
) -> tuple[dict[str, Any], Any, list[str]]:
    events = []
    for line in stream.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    terminal = [event for event in events if event.get("type") == "result"]
    init = [
        event
        for event in events
        if event.get("type") == "system" and event.get("subtype") == "init"
    ]
    result_event = terminal[-1] if terminal else {}
    session_id = init[0].get("session_id") if init else None
    integrity_errors = []
    if len(init) != 1 or not isinstance(session_id, str) or not session_id.strip():
        integrity_errors.append("missing_or_ambiguous_session_identity")
    if not init or init[0].get("model") != model:
        integrity_errors.append("init_model_mismatch")
    for event in events:
        if event.get("type") == "assistant":
            message = event.get("message", {})
            if isinstance(message, dict) and message.get("model") not in (None, model):
                integrity_errors.append("assistant_model_mismatch")
    if stream_cli_version(stream) != cli_version:
        integrity_errors.append("cli_version_mismatch")
    if len(terminal) != 1 or result_event.get("is_error") is not False:
        integrity_errors.append("missing_or_failed_terminal_result")
    if _unexpected_hooks(stream):
        integrity_errors.append("unexpected_hook_event")
    if any("instrumentation_error" in row for row in receipts):
        integrity_errors.append("receipt_instrumentation_error")
    return result_event, session_id, integrity_errors


def _record_leg(
    *,
    cwd: Path,
    surface: MemoryToolSurface,
    leg: int,
    out: Path,
    model: str,
    cli_version: str,
    receipts_path: Path,
    native_log: Path,
    started: float,
    failure: Exception | None,
) -> dict[str, Any]:
    from membench.runner.bd_real_metrics import score_real_leg

    raw_path = out / "raw.stream.jsonl"
    stream = raw_path.read_text() if raw_path.exists() else ""
    receipts = read_receipts(receipts_path)
    if receipts_path.exists():
        shutil.copyfile(receipts_path, out / "receipts.jsonl")
    _json(out / "receipts.json", receipts)
    _json(out / "native-hook.json", hook_reaches(native_log))
    status = "error" if failure else "ok"
    process_path = out / "process.json"
    if process_path.exists():
        status = json.loads(process_path.read_text())["status"]
    result_event, session_id, integrity_errors = _stream_evidence(
        stream, receipts, model, cli_version
    )
    if integrity_errors and not failure:
        status = "error"
    calls = tool_calls_from_stream(stream)
    evidence = score_real_leg(
        calls,
        receipts,
        leg_id=receipts_path.stem,
        status=status,
        expected_binary=surface.bd_binary,
        expected_store=str(surface.store_dir),
        expected_session=session_id,
    )
    record = {
        "leg": leg,
        "status": status,
        "cwd": str(cwd),
        "config_dir": str(surface.config_dir),
        "bd_store": str(surface.store_dir),
        "receipt_leg_id": receipts_path.stem,
        "instruction_delivery": json.loads((out / "instruction-delivery.json").read_text()),
        "runtime_proof_sha256": (
            hashlib.sha256((out / "runtime.json").read_bytes()).hexdigest()
            if (out / "runtime.json").is_file()
            else None
        ),
        "memory": evidence.model_dump(mode="json"),
        "session_id": session_id,
        "duration_s": time.monotonic() - started,
        "total_cost_usd": result_event.get("total_cost_usd"),
        "usage": result_event.get("usage"),
        "terminal_result": result_event,
        "integrity_errors": integrity_errors,
    }
    _json(out / "result.json", record)
    if failure:
        raise RuntimeError(f"leg {leg} {status}; evidence retained at {out}") from failure
    if integrity_errors:
        raise RuntimeError(f"leg {leg} failed integrity: {integrity_errors}")
    return record


def _run_snapshotted_leg(
    *,
    cwd: Path,
    surface: MemoryToolSurface,
    condition: str,
    out: Path,
    leg: int,
    root: Path,
    corpus_dir: Path,
    artifacts: Mapping[str, Any],
    prompt_key: str,
    model: str,
    cli_version: str,
    timeout_s: float,
    agent_python: Path,
    python_paths: tuple[str, ...] = ("src",),
) -> dict[str, Any]:
    _plant_context(cwd, surface, condition)
    _json(out / f"leg-{leg}-input-files.json", _snapshot(cwd, out / f"leg-{leg}-input.tar"))
    leg_surface = replace(surface, config_dir=root / "memory" / f"config-{leg}")
    prompt = (corpus_dir / artifacts[prompt_key]["path"]).read_text()
    try:
        result = _leg(
            cwd=cwd,
            pair_root=root,
            agent_python=agent_python,
            surface=leg_surface,
            prompt=prompt,
            leg=leg,
            out=out / f"leg-{leg}",
            model=model,
            cli_version=cli_version,
            timeout_s=timeout_s,
            python_paths=python_paths,
        )
    finally:
        _json(
            out / f"leg-{leg}-output-files.json",
            _snapshot(cwd, out / ("goal-candidate.tar" if leg else "establish-output.tar")),
        )
        _snapshot(surface.store_dir, out / f"leg-{leg}-bd-store.tar")
        _json(out / f"leg-{leg}-snapshots.json", {"completed": True})
    if leg_surface.config_dir is not None:
        shutil.rmtree(leg_surface.config_dir)
    return result


def _leg(
    *,
    cwd: Path,
    pair_root: Path,
    agent_python: Path,
    surface: MemoryToolSurface,
    prompt: str,
    leg: int,
    out: Path,
    model: str,
    cli_version: str,
    timeout_s: float,
    python_paths: tuple[str, ...] = ("src",),
) -> dict[str, Any]:
    out.mkdir()
    if surface.config_dir is None:
        raise RuntimeError("isolated config required")
    seed_config_dir(surface.config_dir, {"autoMemoryEnabled": True})
    deliver_user_instructions(cwd, surface.config_dir, out)
    native_log = install_native_memory_hook(surface.config_dir, mode="redirect")
    receipts_path = prepare_receipt_leg(surface, leg=leg)
    settings = json.loads((surface.config_dir / "settings.json").read_text())
    if set(settings.get("hooks", {})) != {"PreToolUse"}:
        raise RuntimeError("only expected PreToolUse hooks may be configured")
    _json(out / "settings.json", settings)
    recorder = RecordingRunner(inner=_preserving_runner(out))
    runtime_runner = wrap_agent_runner(
        recorder,
        pair_root=pair_root,
        cwd=cwd,
        agent_python=agent_python,
        bd_binary=Path(surface.bd_binary),
        config_dir=surface.config_dir,
        record_path=out / "runtime.json",
        python_paths=python_paths,
    )
    agent = HeadlessClaudeAgent(
        model=model,
        timeout_s=timeout_s,
        runner=runtime_runner,
        cwd=str(cwd),
        env={**surface.env(), "PWD": str(cwd)},
        env_unset=ENV_UNSET,
        setting_sources="user",
        include_hook_events=True,
        disallowed_tools=HOST_DENIED_TOOLS,
    )
    step = SequenceStep(
        step_id=str(leg),
        user_request=prompt,
        available_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep"],
    )
    _json(out / "agent-argv.json", agent.argv_for(step, {}))
    started = time.monotonic()
    failure: Exception | None = None
    try:
        agent.run_step(
            step, {}, StepContext(trial_id=out.parent.name, session_id=str(leg), step_id=str(leg))
        )
    except Exception as exc:
        failure = exc
    return _record_leg(
        cwd=cwd,
        surface=surface,
        leg=leg,
        out=out,
        model=model,
        cli_version=cli_version,
        receipts_path=receipts_path,
        native_log=native_log,
        started=started,
        failure=failure,
    )


def _grade(
    task: Mapping[str, Any], corpus_dir: Path, cwd: Path, out: Path, timeout_s: float
) -> dict[str, Any]:
    for module in task["grader"]["modules"]:
        source = corpus_dir / module["path"]
        relative = Path(module["target_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("grader destination must be relative to snapshot")
        target = cwd / relative
        if not target.resolve().is_relative_to(cwd.resolve()):
            raise RuntimeError("grader destination escapes snapshot")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    manifest_argv = list(task["grader"]["check_command"])
    if manifest_argv[1:3] != ["-m", "pytest"]:
        raise RuntimeError("this curated grader requires python -m pytest")
    argv = [manifest_argv[0], "-c", IMPORT_GUARDED_PYTEST, str(cwd / "src"), *manifest_argv[3:]]
    _json(out / "task-check-manifest-argv.json", manifest_argv)
    env = {**os.environ, "PYTHONPATH": str(cwd / "src")}
    _json(out / "task-check-argv.json", argv)
    try:
        completed = CHECK_RUNNER(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
            cwd=str(cwd),
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        (out / "task-check.stdout").write_text(_text(exc.stdout))
        (out / "task-check.stderr").write_text(_text(exc.stderr))
        _json(out / "task_check.json", {"passed": None, "status": "timeout", "returncode": None})
        raise RuntimeError("repository checks timed out; partial evidence retained") from exc
    (out / "task-check.stdout").write_text(completed.stdout or "")
    (out / "task-check.stderr").write_text(completed.stderr or "")
    result = {
        "passed": completed.returncode == 0 if completed.returncode in (0, 1) else None,
        "returncode": completed.returncode,
        "status": "ok" if completed.returncode in (0, 1) else "error",
        "argv": argv,
        "pythonpath": env["PYTHONPATH"],
    }
    _json(out / "task_check.json", result)
    if completed.returncode not in (0, 1):
        raise RuntimeError("repository check infrastructure failed; evidence retained")
    return result


def _retain_only_store(root: Path, store: Path) -> None:
    """Remove other writable pair paths before restoring the fresh goal workspace."""
    if store.is_symlink() or not store.is_dir() or not store.is_relative_to(root):
        raise RuntimeError("cannot preserve an invalid bd store across the leg boundary")
    for path in root.iterdir():
        if path == store:
            continue
        if path.is_dir() and not path.is_symlink():
            if store.is_relative_to(path):
                _retain_only_store(path, store)
            else:
                shutil.rmtree(path)
        else:
            path.unlink()


def run_real_pair(
    task: Mapping[str, Any],
    *,
    corpus_dir: Path,
    out: Path,
    condition: str,
    variant: str,
    model: str,
    cli_version: str,
    bd_binary: str,
    timeout_s: float,
) -> dict[str, Any]:
    """Execute once; caller journals started state before entry and must never retry implicitly."""
    if condition not in {"current", "focused"} or variant not in {"unbriefed", "briefed"}:
        raise ValueError("unsupported condition or variant")
    if out.exists():
        raise RuntimeError("pair output already exists; use retained evidence, never repurchase")
    assert_managed_settings_absent()
    out.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="bd-real-pair-", dir="/tmp") as temporary:
        root = Path(temporary)
        cwd = root / "workspace"
        cwd.mkdir()
        assert_neutral_ancestry(cwd)
        surface = provision_memory_tool(root / "memory", sandbox=cwd, bd_binary=bd_binary)
        artifacts = task["artifacts"]
        (cwd / "source_packet.md").write_bytes(
            (corpus_dir / artifacts["source_packet"]["path"]).read_bytes()
        )
        legs = []
        for leg, prompt_key in enumerate(("establish_prompt", f"goal_{variant}")):
            if leg:
                _retain_only_store(root, surface.store_dir)
                cwd.mkdir()
                surface.bin_dir.mkdir(parents=True)
                _archive_base(task, cwd)
            legs.append(
                _run_snapshotted_leg(
                    cwd=cwd,
                    surface=surface,
                    condition=condition,
                    out=out,
                    leg=leg,
                    root=root,
                    corpus_dir=corpus_dir,
                    artifacts=artifacts,
                    prompt_key=prompt_key,
                    model=model,
                    cli_version=cli_version,
                    timeout_s=timeout_s,
                    agent_python=Path(task["grader"]["check_command"][0]),
                )
            )
        task_check = _grade(task, corpus_dir, cwd, out, timeout_s)
        result = {
            "task_id": task["task_id"],
            "condition": condition,
            "variant": variant,
            "legs": legs,
            "task_check": task_check,
        }
        _json(out / "result.json", result)
        return result
