"""Mechanical receipts for executions of the isolated bd shim.

The PreToolUse hook injects call IDs into Bash's environment; shells and background
children inherit them. Timing is never used to infer attribution. The hook builder
raises on malformed Bash events: its caller must log the instrumentation fault and
allow the original tool call, marking that observation unmeasured. It neither grants
permissions nor supplies model-facing prose. updatedInput replaces the entire input:
https://code.claude.com/docs/en/hooks#pretooluse-decision-control

Start records survive unfinished commands. Only finish records establish outcomes.
UTF-8 fields are convenient views; base64 fields preserve exact CLI output bytes.
The wrapper forwards those bytes without decoding. Receipts contain no environment
dumps. The reserved context variables are attribution metadata, not a security boundary.
"""

from __future__ import annotations

import base64
import fcntl
import json
import os
import shlex
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CONTEXT_KEYS = {
    "tool_use_id": "MEMBENCH_BD_TOOL_USE_ID",
    "session_id": "MEMBENCH_BD_SESSION_ID",
    "leg_id": "MEMBENCH_BD_LEG_ID",
}


class InstrumentationError(ValueError):
    """An observation cannot be attributed; this is never a bd operation result."""


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise InstrumentationError(f"missing or invalid {field}")
    return value


def hook_response(event: Mapping[str, object], *, leg_id: str) -> dict[str, Any]:
    """Inject shell-quoted identifiers, preserving all other Bash input fields."""
    if event.get("tool_name") != "Bash":
        return {}
    if event.get("hook_event_name") != "PreToolUse":
        raise InstrumentationError("expected PreToolUse event")
    arguments = event.get("tool_input")
    if not isinstance(arguments, dict) or not isinstance(arguments.get("command"), str):
        raise InstrumentationError("missing or invalid tool_input.command")
    identifiers = {
        "tool_use_id": _identifier(event.get("tool_use_id"), "tool_use_id"),
        "session_id": _identifier(event.get("session_id"), "session_id"),
        "leg_id": _identifier(leg_id, "leg_id"),
    }
    prefix = "export " + " ".join(
        f"{CONTEXT_KEYS[key]}={shlex.quote(value)}" for key, value in identifiers.items()
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": {**arguments, "command": prefix + "\n" + arguments["command"]},
        }
    }


def append_record(path: Path, record: Mapping[str, object]) -> None:
    """Serialize each append under flock, including short-write retries.

    O_APPEND alone cannot prevent interleaving if a large regular-file write is
    partial. Each writer holds the same file's advisory lock until its line is done.
    IO errors propagate; callers must surface instrumentation failure.
    """
    payload = (json.dumps(record, ensure_ascii=True) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        remaining = memoryview(payload)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("receipt append made no progress")
            remaining = remaining[written:]
    finally:
        os.close(descriptor)


def _observe(path: Path, record: Mapping[str, object]) -> None:
    try:
        append_record(path, record)
    except OSError as exc:
        # Do not convert an instrumentation IO fault into a bd command failure.
        print(
            f"bd receipt instrumentation: log write failed ({type(exc).__name__})", file=sys.stderr
        )


def _context(environ: Mapping[str, str]) -> dict[str, str]:
    return {field: _identifier(environ.get(key), field) for field, key in CONTEXT_KEYS.items()}


def _execution_identity(binary: Path, store: Path, argv: Sequence[str]) -> dict[str, object]:
    if not binary.is_absolute() or not store.is_absolute():
        raise InstrumentationError("pinned binary and store must be absolute paths")
    return {
        "invocation_id": uuid.uuid4().hex,
        "argv": [str(binary), "-C", str(store), *argv],
        "operation_argv": list(argv),
        "start_monotonic_ns": time.monotonic_ns(),
    }


def run_bd(
    argv: Sequence[str],
    *,
    binary: Path,
    store: Path,
    receipt_path: Path,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Execute pinned bd without a shell, forward raw bytes, and record its outcome.

    Missing attribution executes unmeasured and logs a separate diagnostic; it never
    manufactures a finish receipt. A launch failure propagates after recording an
    instrumentation fault. A killed child returns its negative subprocess returncode.
    """
    environment = dict(os.environ if environ is None else environ)
    identity = _execution_identity(binary, store, argv)
    try:
        attribution = _context(environment)
    except InstrumentationError as exc:
        _observe(receipt_path, {**identity, "instrumentation_error": str(exc)})
        print(f"bd receipt instrumentation: {exc}", file=sys.stderr)
        attribution = {}
    if attribution:
        _observe(receipt_path, {**identity, **attribution, "event": "start"})
    try:
        result = subprocess.run(
            [str(binary), "-C", str(store), *argv],
            env=environment,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        _observe(
            receipt_path,
            {
                **identity,
                **attribution,
                "instrumentation_error": f"launch failed: {type(exc).__name__}",
            },
        )
        raise
    ended = time.monotonic_ns()
    if attribution:
        _observe(
            receipt_path,
            {
                **identity,
                **attribution,
                "event": "finish",
                "returncode": result.returncode,
                "stdout": result.stdout.decode("utf-8", errors="replace"),
                "stderr": result.stderr.decode("utf-8", errors="replace"),
                "stdout_base64": base64.b64encode(result.stdout).decode("ascii"),
                "stderr_base64": base64.b64encode(result.stderr).decode("ascii"),
                "end_monotonic_ns": ended,
            },
        )
    sys.stdout.buffer.write(result.stdout)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(result.stderr)
    sys.stderr.buffer.flush()
    return result.returncode


def wrapper_main(*, binary: str, store: str, receipt_path: str) -> int:
    """Entrypoint for the generated shim; propagate child signals to the shell."""
    code = run_bd(
        sys.argv[1:], binary=Path(binary), store=Path(store), receipt_path=Path(receipt_path)
    )
    if code < 0:
        signum = -code
        if signum not in (signal.SIGKILL, signal.SIGSTOP):
            signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)
        return 128 + signum
    return code
