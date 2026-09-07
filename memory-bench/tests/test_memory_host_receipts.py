"""Execution evidence must not become observed memory through a marker alone."""

from __future__ import annotations

import base64
import copy
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from membench.runner.memory_host_receipts import correlate, marker, prepare, score_correlated
from membench.schemas.trace import ToolCall

INVOCATION = "a" * 32


def raw_pair(out: str = "fact", code: int = 0) -> list[dict]:
    start = {
        "schema": "memory-host-receipt.v1",
        "invocation_id": INVOCATION,
        "harness_session_id": "harness-session",
        "leg_id": "direct",
        "event": "start",
        "argv": ["/bin/bd", "-C", "/store", "recall", "k"],
        "operation_argv": ["recall", "k"],
        "start_monotonic_ns": 1,
    }
    return [
        start,
        {
            **start,
            "event": "finish",
            "returncode": code,
            "stdout": out,
            "stderr": "",
            "stdout_base64": base64.b64encode(out.encode()).decode(),
            "stderr_base64": "",
            "end_monotonic_ns": 2,
        },
    ]


def shell(output: str | None = None, **changes: object) -> ToolCall:
    values = {
        "name": "Bash",
        "tool_use_id": "actual-host-tool",
        "tool_use_index": 1,
        "tool_result_index": 2,
        "arguments": {"command": "bd recall k"},
        "result": output if output is not None else "fact\n" + marker(INVOCATION),
    }
    values.update(changes)
    return ToolCall(**values)


def scored(rows: list[dict], calls: list[ToolCall]):
    return score_correlated(
        rows,
        calls,
        "actual-host-session",
        leg_id="direct",
        status="ok",
        expected_binary="/bin/bd",
        expected_store="/store",
    )


def test_unique_actual_result_derives_host_ids_without_mutating_raw() -> None:
    rows = raw_pair()
    original = copy.deepcopy(rows)
    derived, diagnostics = correlate(rows, [shell()], "actual-host-session")
    assert rows == original
    assert not diagnostics["evidence_unknown"]
    assert len(derived) == 2
    assert all(row["session_id"] == "actual-host-session" for row in derived)
    assert all(row["tool_use_id"] == "actual-host-tool" for row in derived)
    assert all("session_id" not in row and "tool_use_id" not in row for row in rows)
    evidence, _ = scored(rows, [shell()])
    assert evidence.executed_reads == evidence.observed_content_reads == 1
    assert not evidence.evidence_unknown


@pytest.mark.parametrize(
    "calls",
    [
        [],
        [shell("fact")],
        [shell("fact " + marker(INVOCATION) * 2)],
        [shell(), shell(tool_use_id="second")],
        [shell(tool_use_id=None)],
        [shell(tool_use_id=" ")],
        [shell(tool_result_index=None)],
        [shell(name="Read")],
        [shell(), shell("other output")],  # duplicate host tool identity
    ],
)
def test_missing_duplicate_or_unattributable_marker_stays_unknown(calls: list[ToolCall]) -> None:
    derived, diagnostic = correlate(raw_pair(), calls, "actual-host-session")
    assert derived == []
    assert diagnostic["evidence_unknown"]
    evidence, _ = scored(raw_pair(), calls)
    assert evidence.evidence_unknown
    assert evidence.executed_reads == 0


def test_marker_is_not_delivery_of_truncated_or_redirected_stdout() -> None:
    evidence, diagnostics = scored(raw_pair(), [shell(marker(INVOCATION))])
    assert len(diagnostics["associations"]) == 1
    assert evidence.executed_reads == 1
    assert evidence.observed_reads == evidence.observed_content_reads == 0
    assert evidence.evidence_unknown


def test_fabricated_marker_without_execution_is_unknown_even_without_memory_command() -> None:
    call = shell(marker(INVOCATION), arguments={"command": "echo unrelated"})
    evidence, diagnostics = scored([], [call])
    assert diagnostics["evidence_unknown"]
    assert evidence.evidence_unknown
    assert evidence.executed_reads == 0


@pytest.mark.parametrize(
    "mutation",
    [
        lambda rows: rows.pop(),
        lambda rows: rows.append(copy.deepcopy(rows[-1])),
        lambda rows: rows[-1].update(stdout="changed"),
        lambda rows: rows[-1].update(stdout_base64="!!!"),
        lambda rows: rows[-1].update(end_monotonic_ns=0),
        lambda rows: rows[-1].update(harness_session_id="other"),
        lambda rows: rows[-1].update(tool_use_id="fabricated-host-id"),
        lambda rows: rows[-1].update(argv=["/bin/bd", "-C", "/other", "recall", "k"]),
    ],
)
def test_malformed_or_incomplete_raw_pair_cannot_be_repaired(mutation) -> None:
    rows = raw_pair()
    mutation(rows)
    derived, diagnostic = correlate(rows, [shell()], "actual-host-session")
    assert derived == []
    assert diagnostic["evidence_unknown"]


def test_failed_command_is_executed_but_never_accepted_or_successfully_observed() -> None:
    evidence, diagnostics = scored(
        raw_pair("not found", 1), [shell("not found\n" + marker(INVOCATION))]
    )
    assert not diagnostics["evidence_unknown"]
    assert evidence.executed_reads == 1
    assert evidence.observed_reads == evidence.accepted_writes == 0
    assert not evidence.evidence_unknown


def test_two_executions_in_one_compound_tool_result_are_distinct() -> None:
    rows = raw_pair()
    second = copy.deepcopy(rows)
    for row in second:
        row["invocation_id"] = "b" * 32
    call = shell("fact\n" + marker(INVOCATION) + "\nfact\n" + marker("b" * 32))
    evidence, diagnostics = scored(rows + second, [call])
    assert not diagnostics["evidence_unknown"]
    assert evidence.executed_reads == evidence.observed_reads == 2


def test_invalid_host_session_id_is_not_invented() -> None:
    derived, diagnostic = correlate(raw_pair(), [shell()], "")
    assert not derived
    assert diagnostic["evidence_unknown"]


@pytest.mark.parametrize("command", ["/bin/zsh -lc 'bd recall k'", "false && bd recall k"])
def test_wrapped_or_conditional_memory_without_receipt_remains_unknown(command: str) -> None:
    evidence, diagnostic = scored([], [shell("unattributed fact", arguments={"command": command})])
    assert evidence.executed_reads == 0
    assert evidence.evidence_unknown and diagnostic["evidence_unknown"]
    assert any(
        reason.startswith("uncovered_memory_invocation:") for reason in evidence.unknown_reasons
    )


def test_one_matching_receipt_does_not_hide_another_missing_compound_operation() -> None:
    evidence, diagnostic = scored(
        raw_pair(), [shell(arguments={"command": "bd recall k; bd recall different"})]
    )
    assert evidence.executed_reads == evidence.observed_reads == 1
    assert evidence.evidence_unknown and diagnostic["evidence_unknown"]


def test_valid_receipt_can_cover_a_shell_expanded_key() -> None:
    evidence, diagnostic = scored(raw_pair(), [shell(arguments={"command": 'bd recall "$KEY"'})])
    assert evidence.observed_content_reads == 1
    assert not evidence.evidence_unknown and not diagnostic["evidence_unknown"]


def test_isolated_shim_forwards_bytes_and_preserves_raw_execution_identity(tmp_path: Path) -> None:
    binary = tmp_path / "fake-bd"
    binary.write_text("#!/bin/sh\nprintf 'valid JSON stdout'\nprintf 'real stderr' >&2\nexit 7\n")
    binary.chmod(0o700)
    store = tmp_path / "store"
    store.mkdir()
    receipts, shim = prepare(
        tmp_path / "bin",
        store,
        "direct",
        "harness-session",
        binary=binary,
        python=Path(sys.executable).resolve(),
    )
    result = subprocess.run(
        [str(shim), "recall", "k"],
        env={"PATH": os.defpath},
        cwd=store,
        capture_output=True,
        timeout=30,
    )
    rows = [json.loads(line) for line in receipts.read_text().splitlines()]
    assert result.returncode == 7
    assert result.stdout == b"valid JSON stdout"
    assert result.stderr == marker(rows[0]["invocation_id"]).encode() + b"\nreal stderr"
    assert [row["event"] for row in rows] == ["start", "finish"]
    assert rows[-1]["stderr"] == "real stderr"
    assert rows[-1]["harness_session_id"] == "harness-session"
    assert not any("session_id" in row or "tool_use_id" in row for row in rows)
    assert rows[-1]["argv"] == [str(binary), "-C", str(store), "recall", "k"]
    assert rows[-1]["returncode"] == 7
    assert not any(
        str(Path(__file__).resolve().parents[2]) in p.read_text() for p in shim.parent.rglob("*.py")
    )
    with pytest.raises(FileExistsError):
        prepare(
            tmp_path / "bin",
            store,
            "direct",
            "harness-session",
            binary=binary,
            python=Path(sys.executable),
        )


@pytest.mark.parametrize("args,is_read", [(["remember", "--help"], False), (["recall", "k"], True)])
def test_head_preserves_attribution_without_crediting_truncated_memory(
    tmp_path: Path, args: list[str], is_read: bool
) -> None:
    binary = tmp_path / "fake-bd"
    binary.write_text("#!/bin/sh\n" + "printf 'one\\ntwo\\nthree\\nfour\\nfive\\n'\n")
    binary.chmod(0o700)
    store = tmp_path / "store"
    store.mkdir()
    receipts, shim = prepare(
        tmp_path / "bin",
        store,
        "direct",
        "harness-session",
        binary=binary,
        python=Path(sys.executable).resolve(),
    )
    command = shlex.join([str(shim), *args]) + " 2>&1 | head -n 3"
    result = subprocess.run(
        ["/bin/sh", "-c", command],
        cwd=store,
        env={"PATH": os.defpath},
        capture_output=True,
        text=True,
        timeout=30,
    )
    rows = [json.loads(line) for line in receipts.read_text().splitlines()]
    assert result.stdout == marker(rows[0]["invocation_id"]) + "\none\ntwo\n"
    call = shell(
        result.stdout, arguments={"command": shlex.join(["bd", *args]) + " 2>&1 | head -n 3"}
    )
    evidence, diagnostics = score_correlated(
        rows,
        [call],
        "actual-host-session",
        leg_id="direct",
        status="ok",
        expected_binary=str(binary),
        expected_store=str(store),
    )
    assert not diagnostics["evidence_unknown"]
    assert len(diagnostics["associations"]) == 1
    assert evidence.executed_reads == int(is_read)
    assert evidence.observed_content_reads == 0
    assert evidence.evidence_unknown is is_read
