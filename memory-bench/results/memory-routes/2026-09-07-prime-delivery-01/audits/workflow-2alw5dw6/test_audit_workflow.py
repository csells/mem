"""Mechanical no-inference parser checks; all test files live in scratch."""

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "workflow_audit", Path(__file__).with_name("audit_workflow.py")
)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


@pytest.mark.parametrize("command", ["remember", "recall", "memories", "close", "prime"])
def test_help_is_never_credited_as_its_parent_operation(command):
    assert audit.operation([command, "--help"], command) == "help"


def test_json_wrapped_codex_multicommand_output_recovers_exact_full_exposure():
    expected = 'policy scope\nUnicode 雪 and "exact" identifier\n'
    output = [
        {"type": "input_text", "text": "Script completed"},
        {
            "type": "input_text",
            "text": json.dumps(
                {
                    "status": "fulfilled",
                    "value": {
                        "exit_code": 0,
                        "output": json.dumps(expected, ensure_ascii=False)[1:-1],
                    },
                },
                ensure_ascii=False,
            ),
        },
    ]
    assert audit.output_match(output, expected)
    assert not audit.output_match(output, expected + "Missing final clause")
    assert not audit.output_match(output, "")


def test_raw_codex_tool_output_links_to_matching_call_not_adjacent_text(tmp_path):
    folder = tmp_path / "host-evidence"
    folder.mkdir()
    path = folder / "rollout-example.jsonl"
    events = [
        {
            "type": "response_item",
            "payload": {"type": "custom_tool_call", "call_id": "a", "input": "bd prime"},
        },
        {
            "type": "response_item",
            "payload": {"type": "message", "role": "assistant", "content": "not a tool result"},
        },
        {
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": "a",
                "output": "actual stdout",
            },
        },
    ]
    path.write_text("\n".join(json.dumps(e) for e in events))
    outputs, inputs, paths = audit.raw_codex_tools(tmp_path)
    assert len(inputs) == len(outputs) == len(paths) == 1
    assert outputs[0]["call"]["input"] == "bd prime"
    assert outputs[0]["line"] == 3


def test_pseudo_tool_text_is_retained_as_prose_not_real_tool():
    text = "<function=skill>beads</function></tool_call>"
    assert audit.stream_prose([(4, {"type": "text", "part": {"text": text}})]) == [
        {"stream_line": 4, "text": text}
    ]
    assert audit.stream_prose([(4, {"type": "tool_use", "part": {"text": text}})]) == []


def test_isolated_sqlite_export_includes_descendants_and_preserves_database(tmp_path, monkeypatch):
    evidence = tmp_path / "case/stage-1"
    evidence.mkdir(parents=True)
    (evidence.parent / "state.json").write_text(json.dumps({"scratch": str(tmp_path / "scratch")}))
    db = tmp_path / "scratch/stage-1/config/data/opencode/opencode.db"
    db.parent.mkdir(parents=True)
    connection = sqlite3.connect(db)
    connection.executescript(
        "CREATE TABLE session(id TEXT, parent_id TEXT, time_created INTEGER, agent TEXT);"
        "CREATE TABLE message(id TEXT, session_id TEXT, time_created INTEGER, data TEXT);"
        "CREATE TABLE part(id TEXT, session_id TEXT, message_id TEXT, "
        "time_created INTEGER, data TEXT);"
    )
    for i, (identity, parent) in enumerate(
        [("parent", None), ("child", "parent"), ("grandchild", "child"), ("unrelated", None)]
    ):
        connection.execute("INSERT INTO session VALUES(?,?,?,?)", (identity, parent, i, "build"))
        message = {"role": "assistant", "providerID": "local", "modelID": "pinned"}
        connection.execute(
            "INSERT INTO message VALUES(?,?,?,?)",
            ("m-" + identity, identity, i, json.dumps(message)),
        )
        part = {
            "type": "tool",
            "tool": "bash",
            "state": {"status": "completed", "input": {"command": "bd prime"}, "output": "policy"},
        }
        connection.execute(
            "INSERT INTO part VALUES(?,?,?,?,?)",
            ("p-" + identity, identity, "m-" + identity, i, json.dumps(part)),
        )
    connection.commit()
    connection.close()
    original = audit.sha(db)
    out = tmp_path / "audit"
    out.mkdir()
    monkeypatch.setattr(audit, "AUDIT", out)
    summary, tools, paths, _ = audit.opencode_sessions(
        evidence, {"host": "opencode", "session_id": "parent", "stage": 1, "slot": "fixture"}
    )
    assert audit.sha(db) == original
    assert [r["session_id"] for r in summary["sessions"]] == ["parent", "child", "grandchild"]
    assert sum(t["child_session"] for t in tools) == 2
    assert len(paths) == 1
    assert not any(t["session_id"] == "unrelated" for t in tools)
