"""Exact CLI receipts with process ancestry, separate from model-visible delivery.

No marker is added to either CLI stream. A fresh host process is the ancestry
anchor; parent administrative calls use the real binary outside this wrapper.
Ancestry is an execution observation, not a security boundary against a malicious
agent forging files. A matching tool result is reported only as session visibility,
never an invented one-to-one tool ID or proof that the model used the information.
This file is copied standalone into the disposable shim directory.
"""

from __future__ import annotations

import base64
import ctypes
import fcntl
import json
import os
import shutil
import struct
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any


def command_name(argv: list[str]) -> str | None:
    flags = {"--json", "--no-color", "--readonly", "--sandbox", "-q", "--quiet", "-v", "--verbose"}
    values = {"--actor", "--format", "--dolt-auto-commit"}
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in {"--help", "-h", "--version"}:
            return "help"
        if arg in flags or any(arg.startswith(f"{value}=") for value in values):
            index += 1
        elif arg in values:
            index += 2
        elif not arg.startswith("-"):
            return arg
        else:
            return None
    return None


def routing_override(argv: list[str]) -> bool:
    for arg in argv:
        if arg == "--":
            break
        if arg in {"-C", "--directory", "--db", "--database", "--global"}:
            return True
        if arg.startswith("-C") or any(
            arg.startswith(f"{flag}=") for flag in ("--directory", "--db", "--database", "--global")
        ):
            return True
    return False


def append(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as out:
        fcntl.flock(out, fcntl.LOCK_EX)
        out.write(json.dumps(row, ensure_ascii=False) + "\n")
        out.flush()


def ancestry() -> tuple[list[int], str | None]:
    chain = [os.getpid()]
    pid = os.getppid()
    while pid > 0 and pid not in chain and len(chain) < 64:
        chain.append(pid)
        try:
            pid = parent_pid(pid)
        except OSError as exc:
            return chain, f"process ancestry unavailable: {type(exc).__name__}"
    return chain, None


def parent_pid(pid: int) -> int:
    if sys.platform == "darwin":
        # Apple's proc_info.h: PROC_PIDT_SHORTBSDINFO=13 and the 64-byte
        # proc_bsdshortinfo begins with uint32 pid, ppid. Avoid executing the
        # setuid /bin/ps binary, which Seatbelt refuses inside this sandbox.
        # https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/proc_info.h
        library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        query = library.proc_pidinfo
        query.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint64,
            ctypes.c_void_p,
            ctypes.c_int,
        ]
        query.restype = ctypes.c_int
        buffer = ctypes.create_string_buffer(64)
        count = query(pid, 13, 0, ctypes.byref(buffer), 64)
        observed, parent = struct.unpack_from("=II", buffer.raw)
        if count != 64 or observed != pid:
            raise OSError(ctypes.get_errno(), "process identity unavailable")
        return int(parent)
    path = Path(f"/proc/{pid}/status")
    for line in path.read_text().splitlines():
        if line.startswith("PPid:"):
            return int(line.split()[1])
    raise OSError("process parent unavailable")


def prepare(
    directory: Path,
    store: Path,
    leg: str,
    session: str,
    *,
    binary: Path,
    python: str | Path,
) -> tuple[Path, Path]:
    if not leg or not session or not binary.is_file() or not store.is_dir():
        raise ValueError("Receipt preparation requires real executable/store and identities")
    interpreter = str(Path(python).resolve())
    if " " in interpreter or "\n" in interpreter:
        raise ValueError("Standalone receipt interpreter requires a shebang-safe path")
    directory.mkdir()
    log = directory / "receipts.jsonl"
    log.touch(exist_ok=False)
    spec = directory / "receipt-policy.json"
    spec.write_text(
        json.dumps(
            {
                "binary": str(binary.resolve()),
                "store": str(store.resolve()),
                "leg": leg,
                "session": session,
                "log": str(log),
            }
        )
    )
    shutil.copyfile(__file__, directory / "e2e_receipts_runtime.py")
    shim = directory / "bd"
    shim.write_text(
        f"#!{interpreter}\nfrom pathlib import Path\n"
        "from e2e_receipts_runtime import shim_main\n"
        f"raise SystemExit(shim_main(Path({str(spec)!r})))\n"
    )
    shim.chmod(0o700)
    return log, shim


def shim_main(path: Path) -> int:
    spec = json.loads(path.read_text())
    if routing_override(sys.argv[1:]):
        sys.stderr.write("Experiment bd wrapper: this session is confined to its assigned store.\n")
        append(
            Path(spec["log"]),
            {
                "event": "routing_rejected",
                "operation_argv": sys.argv[1:],
                "leg": spec["leg"],
                "session": spec["session"],
            },
        )
        return 2
    parents, ancestry_error = ancestry()
    identity = {
        "schema": "memory-e2e-execution.v1",
        "invocation_id": uuid.uuid4().hex,
        "leg": spec["leg"],
        "session": spec["session"],
        "binary": spec["binary"],
        "store": spec["store"],
        "operation_argv": sys.argv[1:],
        "ancestors": parents,
        "ancestry_error": ancestry_error,
    }
    log = Path(spec["log"])
    append(log, {**identity, "event": "start", "wall_ns": time.time_ns()})
    try:
        result = subprocess.run(
            [spec["binary"], "-C", spec["store"], *sys.argv[1:]],
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        append(log, {**identity, "event": "launch_error", "error": type(exc).__name__})
        raise
    append(
        log,
        {
            **identity,
            "event": "finish",
            "wall_ns": time.time_ns(),
            "returncode": result.returncode,
            "stdout": result.stdout.decode("utf-8", errors="replace"),
            "stderr": result.stderr.decode("utf-8", errors="replace"),
            "stdout_base64": base64.b64encode(result.stdout).decode("ascii"),
            "stderr_base64": base64.b64encode(result.stderr).decode("ascii"),
        },
    )
    sys.stdout.buffer.write(result.stdout)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(result.stderr)
    sys.stderr.buffer.flush()
    return result.returncode if result.returncode >= 0 else 128 - result.returncode


def read(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def assess(
    rows: list[dict[str, Any]],
    *,
    root_pid: int,
    leg: str,
    session: str,
    tool_outputs: list[str],
    binary: str,
    store: str,
) -> dict[str, Any]:
    starts: dict[str, dict[str, Any]] = {}
    ends: set[str] = set()
    executions = []
    unknown = 0
    for row in rows:
        invocation = row.get("invocation_id")
        if not isinstance(invocation, str):
            unknown += 1
            continue
        if row.get("event") == "start":
            if invocation in starts:
                unknown += 1
            starts[invocation] = row
            continue
        start = starts.get(invocation)
        if invocation in ends:
            unknown += 1
            continue
        ends.add(invocation)
        valid = (
            start is not None
            and row.get("event") == "finish"
            and row.get("leg") == leg
            and row.get("session") == session
            and root_pid in row.get("ancestors", [])
            and row.get("binary") == binary
            and row.get("store") == store
            and all(
                start.get(k) == row.get(k)
                for k in ("leg", "session", "binary", "store", "operation_argv", "ancestors")
            )
        )
        if not valid:
            unknown += 1
            continue
        stdout = str(row.get("stdout", ""))
        argv = row.get("operation_argv", [])
        executions.append(
            {
                **row,
                "command": command_name(argv),
                "stdout_visible_somewhere_in_session": bool(
                    stdout.strip() and any(stdout.strip() in output for output in tool_outputs)
                ),
            }
        )
    unknown += len(starts.keys() - ends)
    successful = [r for r in executions if r.get("returncode") == 0]
    return {
        "agent_reads": sum(r["command"] in {"recall", "memories"} for r in successful),
        "agent_writes": sum(r["command"] == "remember" for r in successful),
        "agent_searches": sum(r["command"] == "memories" for r in successful),
        "agent_recalls": sum(r["command"] == "recall" for r in successful),
        "prime_calls": sum(r["command"] == "prime" for r in successful),
        "stdout_visible_in_session": sum(
            r["stdout_visible_somewhere_in_session"]
            for r in successful
            if r["command"] in {"recall", "memories"}
        ),
        "failed_commands": sum(r.get("returncode") != 0 for r in executions),
        "unclassified_commands": sum(r["command"] is None for r in executions),
        "unknown_execution": unknown,
        "executions": executions,
        "exact_host_tool_attribution": "not asserted",
    }
