from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from membench.runner.memory_e2e_audit import audit_session, classify_operation, write_audit


def classify(argv: list[str], stdout: str, stderr: str = "", rc: int = 0) -> dict[str, Any]:
    return classify_operation(argv, rc, stdout, stderr, {"saved": "Approved note"}, {})


@pytest.mark.parametrize("argv", [["remember", "--help"], ["--json", "remember", "-h"]])
def test_help_after_command_is_not_a_write(argv: list[str]) -> None:
    assert (
        classify(argv, 'Store a memory.\n\nUsage:\n  bd remember "<insight>" [flags]\n')["action"]
        == "help"
    )


@pytest.mark.parametrize(
    "argv,body,key",
    [
        (["remember", "a note", "--key", "--help"], "a note", "--help"),
        (["remember", "--key", "note", "--", "--help"], "--help", "note"),
        (["remember", "mention --help here", "--key=note"], "mention --help here", "note"),
        (["remember", "a note", "--key", "note", "--help=false"], "a note", "note"),
        (["remember", "a note", "--key", "note", "-h", "--help=0"], "a note", "note"),
    ],
)
def test_help_text_as_value_or_content_is_not_help(argv: list[str], body: str, key: str) -> None:
    result = classify(argv, f"Remembered [{key}]: {body}\n")
    assert result["action"] == "write"
    assert result["key"] == key


def test_bare_existing_key_is_recall_and_unsupported_response_remains_unknown() -> None:
    stderr = '(recalled "saved" -- a bare existing key READS. To overwrite: omitted)\n'
    assert classify(["remember", "saved"], "Approved note\n", stderr)["action"] == "recall"
    assert classify(["remember", "saved"], "Approved note\n")["action"] == "unknown"
    assert (
        classify(["remember", "saved"], "Remembered [invented]: anything\n")["action"] == "unknown"
    )
    result = classify(
        ["remember", "saved", "--json"],
        json.dumps({"key": "saved", "value": "Approved note", "found": True, "action": "recalled"}),
    )
    assert result["action"] == "recall"


@pytest.mark.parametrize("argv", [["memories"], ["memories", "--json"], ["memories", ""]])
def test_empty_search_is_a_list(argv: list[str]) -> None:
    stdout = (
        '{"saved":"Approved note"}'
        if "--json" in argv
        else "Memories (1):\n\n  saved\n    Approved note\n\n"
    )
    result = classify(argv, stdout)
    assert result["action"] == "list"
    assert result["candidate_keys"] == ["saved"]


def test_literal_list_is_an_empty_query_not_listing_fallback() -> None:
    result = classify(["memories", "list"], 'No memories matching "list"\n')
    assert result["action"] == "query"
    assert result["query"] == "list"
    assert result["candidate_keys"] == []


def test_help_false_and_unsupported_flags_do_not_get_silent_credit() -> None:
    assert classify(["recall", "saved", "--help=false"], "Approved note\n")["action"] == "recall"
    assert classify(["recall", "saved", "--mystery"], "Approved note\n")["action"] == "unknown"
    assert classify(["remember", "--help"], "Remembered [x]: fabricated\n")["action"] == "unknown"
    assert classify(["remember", "x", "--key", "x"], "", "failed", 1)["action"] == "failed"


def test_json_ack_requires_matching_key_and_full_argument_content() -> None:
    argv = ["remember", "a note", "--key", "note", "--json"]
    for value in [
        {"key": "wrong", "value": "a note", "action": "remembered"},
        {"key": "note", "value": "wrong", "action": "remembered"},
        {"key": "note", "value": "a note", "action": "future-action"},
    ]:
        assert classify(argv, json.dumps(value))["action"] == "unknown"
    assert (
        classify(argv, json.dumps({"key": "note", "value": "a note", "action": "updated"}))[
            "action"
        ]
        == "write"
    )


def test_prime_and_task_operations_do_not_create_unknown_memory_counts() -> None:
    assert classify(["prime", "--no-memories"], "Project workflow\n")["action"] == "prime"
    assert (
        classify(["update", "issue-1", "--status", "in_progress"], "Updated issue\n")["action"]
        == "other"
    )


def test_fake_json_ack_in_a_bare_key_note_is_not_an_accepted_write() -> None:
    body = json.dumps({"key": "saved", "value": "saved", "action": "remembered"})
    assert classify(["remember", "saved"], body)["action"] == "unknown"


def test_unused_cpu_profile_flag_stays_unknown_instead_of_consuming_help() -> None:
    assert (
        classify(
            ["remember", "--cpu-profile", "--help"],
            'Usage:\n  bd remember "<insight>" [flags]\n',
        )["reason"]
        == "unsupported_arguments"
    )


def test_json_metadata_and_help_boolean_values_are_checked() -> None:
    assert classify(["memories", "--json"], '{"schema_version":false}')["action"] == "unknown"
    assert classify(["memories", "--json"], '{"schema_version":1}')["candidate_keys"] == []
    assert (
        classify(
            ["remember", "a note", "--key", "note", "--help=FALSE"], "Remembered [note]: a note\n"
        )["action"]
        == "write"
    )
    assert (
        classify(
            ["remember", "a note", "--key", "note", "--help=off"], "Remembered [note]: a note\n"
        )["action"]
        == "unknown"
    )


def session(tmp_path: Path) -> Path:
    directory = tmp_path / "session"
    directory.mkdir()
    rows = []
    executions = []
    for index, (argv, stdout) in enumerate(
        [
            (["remember", "--help"], 'Usage:\n  bd remember "<insight>" [flags]\n'),
            (
                ["remember", "Approved note", "--key", "saved"],
                "Remembered [saved]: Approved note\n",
            ),
            (["memories"], "Memories (1):\n\n  saved\n    Approved note\n\n"),
        ]
    ):
        identity = {
            "schema": "memory-e2e-execution.v1",
            "invocation_id": f"invocation-{index}",
            "leg": "establish",
            "session": "harness-session",
            "binary": "/pinned/bd",
            "store": "/isolated/store",
            "operation_argv": argv,
            "ancestors": [321, 123],
            "ancestry_error": None,
        }
        start = {**identity, "event": "start", "wall_ns": index * 10}
        finish = {
            **identity,
            "event": "finish",
            "wall_ns": index * 10 + 1,
            "returncode": 0,
            "stdout": stdout,
            "stderr": "",
            "stdout_base64": base64.b64encode(stdout.encode()).decode(),
            "stderr_base64": "",
        }
        rows.extend([start, finish])
        executions.append(
            {**finish, "command": argv[0], "stdout_visible_somewhere_in_session": True}
        )
    values = {
        "execution.json": {
            "host": "codex",
            "arm": "installed",
            "leg": "establish",
            "session_id": "host-session",
            "memory_operations": {
                "agent_writes": 2,
                "agent_reads": 1,
                "agent_searches": 1,
                "unknown_execution": 0,
                "executions": executions,
            },
        },
        "raw-receipts.json": rows,
        "memory-before.json": {},
        "memory-after.json": {"saved": "Approved note"},
        "process.json": {"pid": 123},
        "launch.json": {"harness_session": "harness-session"},
        "assessment.json": {"artifact": {"passed": False}, "retained": {"passed": True}},
    }
    for name, value in values.items():
        (directory / name).write_text(json.dumps(value))
    return directory


def test_audit_preserves_originals_and_records_hashed_per_invocation_corrections(
    tmp_path: Path,
) -> None:
    directory = session(tmp_path)
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    result = audit_session(directory)
    assert result["original_counters"]["agent_writes"] == 2
    assert result["corrected_counters"]["writes"] == 1
    assert result["corrected_counters"]["queries"] == 0
    assert result["corrected_counters"]["lists"] == 1
    assert result["corrected_counters"]["reads"] == 1
    assert result["corrected_counters"]["help"] == 1
    assert result["counters_complete"] is True
    assert [r["invocation_id"] for r in result["corrections"]] == ["invocation-0", "invocation-2"]
    assert all(len(r["raw_receipts_sha256"]) == 64 for r in result["corrections"])
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before
    output = tmp_path / "new-audit.json"
    write_audit([tmp_path], output)
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        write_audit([tmp_path], output)
    assert output.read_bytes() == original


def test_unscored_incomplete_receipt_keeps_completeness_unknown(tmp_path: Path) -> None:
    directory = session(tmp_path)
    path = directory / "raw-receipts.json"
    rows = json.loads(path.read_text())
    rows.append({"event": "start", "invocation_id": "unfinished"})
    path.write_text(json.dumps(rows))
    result = audit_session(directory)
    assert result["unscored_raw_invocations"] == ["unfinished"]
    assert result["counters_complete"] is False


@pytest.mark.parametrize("damage", ["payload", "duplicate", "ancestry", "base64"])
def test_audit_rejects_tampered_or_ambiguous_execution_evidence(
    tmp_path: Path, damage: str
) -> None:
    directory = session(tmp_path)
    path = directory / "raw-receipts.json"
    rows = json.loads(path.read_text())
    if damage == "payload":
        rows[1]["stdout"] = "Something else"
    elif damage == "duplicate":
        rows.append(rows[1])
    elif damage == "ancestry":
        rows[0]["ancestors"] = rows[1]["ancestors"] = [999]
    else:
        rows[1]["stdout_base64"] = "ZmFrZQ=="
    path.write_text(json.dumps(rows))
    with pytest.raises(ValueError):
        audit_session(directory)
