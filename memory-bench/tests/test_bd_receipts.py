from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from membench.runner.bd_receipts import InstrumentationError, hook_response, run_bd


def event(command: str) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_use_id": "tool'$(never)",
        "session_id": "session one",
        "tool_input": {"command": command, "timeout": 1000},
    }


@pytest.fixture
def fake_bd(tmp_path: Path) -> Path:
    binary = tmp_path / "fake bd"
    binary.write_text(
        f"#!{sys.executable}\nimport json, os, sys\n"
        "os.write(1, json.dumps(sys.argv[1:]).encode() + b'\\n\\xff')\n"
        "os.write(2, b'err\\x00\\xfe')\n"
        "sys.exit(7 if 'fail' in sys.argv else 0)\n"
    )
    binary.chmod(0o700)
    return binary


def context() -> dict[str, str]:
    return {
        **os.environ,
        "MEMBENCH_BD_TOOL_USE_ID": "tool-1",
        "MEMBENCH_BD_SESSION_ID": "session-1",
        "MEMBENCH_BD_LEG_ID": "leg-1",
    }


@pytest.mark.parametrize("args,code", [(["remember", "a b;$x"], 0), (["recall", "fail"], 7)])
def test_execution(tmp_path: Path, fake_bd: Path, capfdbinary, args, code) -> None:
    log = tmp_path / "receipts.jsonl"
    store = tmp_path / "store with spaces"
    assert run_bd(args, binary=fake_bd, store=store, receipt_path=log, environ=context()) == code
    out, err = capfdbinary.readouterr()
    assert out == json.dumps(["-C", str(store), *args]).encode() + b"\n\xff"
    assert err == b"err\x00\xfe"
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert rows[0]["event"] == "start"
    receipt = rows[1]
    assert receipt["event"] == "finish"
    assert receipt["argv"] == [str(fake_bd), "-C", str(store), *args]
    assert receipt["operation_argv"] == args
    assert receipt["returncode"] == code
    assert receipt["tool_use_id"] == "tool-1"
    assert receipt["session_id"] == "session-1"
    assert receipt["leg_id"] == "leg-1"
    assert rows[0]["invocation_id"] == receipt["invocation_id"]
    assert base64.b64decode(receipt["stdout_base64"]) == out
    assert base64.b64decode(receipt["stderr_base64"]) == err
    assert receipt["end_monotonic_ns"] >= receipt["start_monotonic_ns"]


def test_hook_preserves_input() -> None:
    original = event("echo hello")
    specific = hook_response(original, leg_id="leg one")["hookSpecificOutput"]
    assert set(specific) == {"hookEventName", "updatedInput"}
    assert specific["updatedInput"]["timeout"] == 1000
    assert original["tool_input"]["command"] == "echo hello"
    assert hook_response({"tool_name": "Read"}, leg_id="leg") == {}


@pytest.mark.parametrize("missing", ["tool_use_id", "session_id", "tool_input"])
def test_malformed_hook(missing: str) -> None:
    payload = {key: value for key, value in event("bd recall x").items() if key != missing}
    with pytest.raises(InstrumentationError):
        hook_response(payload, leg_id="leg")


def test_missing_context(tmp_path: Path, fake_bd: Path, capfdbinary) -> None:
    log = tmp_path / "receipts.jsonl"
    assert run_bd([], binary=fake_bd, store=tmp_path, receipt_path=log, environ={}) == 0
    receipt = json.loads(log.read_text())
    assert "instrumentation_error" in receipt
    assert "returncode" not in receipt
    assert b"instrumentation" in capfdbinary.readouterr().err


@pytest.mark.parametrize(
    "commands",
    [
        "bd remember 'value; with quotes' && bd recall value",
        "(bd remember 'subshell')\nbd recall 'second line'",
        "bd remember one &\nbd recall two &\nwait",
    ],
)
def test_compound_commands(tmp_path: Path, fake_bd: Path, commands: str) -> None:
    log = tmp_path / "receipts.jsonl"
    wrapper = tmp_path / "bd"
    wrapper.write_text(
        f"#!{sys.executable}\n"
        "from membench.runner.bd_receipts import wrapper_main\n"
        f"raise SystemExit(wrapper_main(binary={str(fake_bd)!r}, "
        f"store={str(tmp_path)!r}, receipt_path={str(log)!r}))\n"
    )
    wrapper.chmod(0o700)
    response = hook_response(event(commands), leg_id="leg' ; $(false)")
    command = response["hookSpecificOutput"]["updatedInput"]["command"]
    completed = subprocess.run(
        ["bash", "-c", command],
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(rows) == 4
    assert {row["tool_use_id"] for row in rows} == {"tool'$(never)"}
    assert {row["session_id"] for row in rows} == {"session one"}
    assert {row["leg_id"] for row in rows} == {"leg' ; $(false)"}


def test_concurrent_large_appends(tmp_path: Path, fake_bd: Path) -> None:
    log = tmp_path / "receipts.jsonl"
    snippet = (
        "from pathlib import Path; from membench.runner.bd_receipts import run_bd; "
        f"run_bd(['x'*60000], binary=Path({str(fake_bd)!r}), "
        f"store=Path({str(tmp_path)!r}), receipt_path=Path({str(log)!r}))"
    )
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", snippet],
            env=context(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(8)
    ]
    assert [process.wait(timeout=20) for process in processes] == [0] * 8
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(rows) == 16
    assert all(len(row["operation_argv"][0]) == 60000 for row in rows)


@pytest.mark.parametrize("signum", [15, 9])
def test_signal_exit_preserved(tmp_path: Path, signum: int) -> None:
    binary = tmp_path / "signal-bd"
    binary.write_text(f"#!{sys.executable}\nimport os\nos.kill(os.getpid(), {signum})\n")
    binary.chmod(0o700)
    log = tmp_path / "receipts.jsonl"
    snippet = (
        "from membench.runner.bd_receipts import wrapper_main; "
        f"raise SystemExit(wrapper_main(binary={str(binary)!r}, "
        f"store={str(tmp_path)!r}, receipt_path={str(log)!r}))"
    )
    result = subprocess.run([sys.executable, "-c", snippet], env=context(), capture_output=True)
    assert result.returncode == -signum
    assert json.loads(log.read_text().splitlines()[-1])["returncode"] == -signum


def test_unwritable_receipt_does_not_change_bd_result(
    tmp_path: Path, fake_bd: Path, capfdbinary
) -> None:
    assert (
        run_bd(
            ["fail"],
            binary=fake_bd,
            store=tmp_path,
            receipt_path=tmp_path / "missing" / "log",
            environ=context(),
        )
        == 7
    )
    assert b"log write failed" in capfdbinary.readouterr().err


def test_launch_failure_never_has_finish(tmp_path: Path) -> None:
    log = tmp_path / "receipts.jsonl"
    with pytest.raises(FileNotFoundError):
        run_bd([], binary=tmp_path / "missing", store=tmp_path, receipt_path=log, environ=context())
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert rows[0]["event"] == "start"
    assert "instrumentation_error" in rows[1]
    assert all("returncode" not in row for row in rows)


def test_relative_pin_rejected(tmp_path: Path) -> None:
    with pytest.raises(InstrumentationError):
        run_bd([], binary=Path("bd"), store=tmp_path, receipt_path=tmp_path / "log")


def test_invalid_hook_event_and_identifier() -> None:
    with pytest.raises(InstrumentationError):
        hook_response({**event("true"), "hook_event_name": "PostToolUse"}, leg_id="leg")
    with pytest.raises(InstrumentationError):
        hook_response(event("true"), leg_id="\x00")
