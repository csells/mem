"""OpenCode identity evidence, completed results, and isolated state boundaries."""

import json
import sqlite3
from pathlib import Path

import pytest

from membench.runner import memory_host_other as host


def database(local, *, model="actual-model", secret="PRIVATE_UNUSED"):
    path = local / "config/data/opencode/opencode.db"
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE message (id TEXT,session_id TEXT,data TEXT,time_created INT)"
        )
        connection.execute("CREATE TABLE credential (token TEXT)")
        connection.execute("INSERT INTO credential VALUES (?)", (secret,))
        for identity, role in [("message-1", "assistant"), ("user-1", "user")]:
            connection.execute(
                "INSERT INTO message VALUES (?,?,?,?)",
                (
                    identity,
                    "session-1",
                    json.dumps(
                        {"role": role, "providerID": "provider", "modelID": model, "text": secret}
                    ),
                    1,
                ),
            )


def event(kind, **fields):
    part = {"id": "part-1", "messageID": "message-1", "sessionID": "session-1", **fields}
    return {"type": kind, "sessionID": "session-1", "part": part}


def terminal(**fields):
    return event("step_finish", reason="stop", tokens={"input": 4, "output": 2}, cost=0, **fields)


def stream(*events):
    return "\n".join(json.dumps(row) for row in events)


def test_actual_model_comes_from_assistant_database_rows(tmp_path):
    database(tmp_path)
    result = host.observe("opencode", stream(terminal()), tmp_path)
    assert result.success and result.completed
    assert result.models == ["provider/actual-model"]
    assert result.session_id == "session-1"
    assert result.cost_usd == 0


def test_archive_excludes_credentials_and_text_and_can_regrade(tmp_path):
    local, archive = tmp_path / "local", tmp_path / "archive"
    database(local)
    host.export_evidence(local, archive)
    text = (archive / "opencode-models.json").read_text()
    assert "PRIVATE_UNUSED" not in text
    assert "user-1" not in text
    assert host.observe("opencode", stream(terminal()), archive).success
    with pytest.raises(FileExistsError):
        host.export_evidence(local, archive)


@pytest.mark.parametrize("mutation", ["session", "message", "model", "schema"])
def test_wrong_but_consistent_requested_identity_cannot_replace_actual_rows(tmp_path, mutation):
    database(tmp_path)
    archive = tmp_path / "archive"
    host.export_evidence(tmp_path, archive)
    path = archive / "opencode-models.json"
    data = json.loads(path.read_text())
    if mutation == "schema":
        data["schema"] = "other"
    else:
        field = {"session": "session_id", "message": "id", "model": "model_id"}[mutation]
        data["rows"][0][field] = None
    path.write_text(json.dumps(data))
    assert not host.observe("opencode", stream(terminal()), archive).success


def test_shell_error_result_is_retained_with_actual_id_and_output(tmp_path):
    database(tmp_path)
    tool = event(
        "tool_use",
        tool="bash",
        callID="call-1",
        state={
            "status": "error",
            "input": {"command": "bd recall x"},
            "error": "failure bytes",
            "time": {"start": 2, "end": 5},
        },
    )
    result = host.observe("opencode", stream(tool, terminal()), tmp_path)
    assert result.success  # Host completed; the artifact oracle remains independent.
    call = result.calls[0]
    assert call.name == "Bash" and call.tool_use_id == "call-1"
    assert call.result == "failure bytes" and call.is_error
    assert call.tool_use_index is None and call.tool_result_index == 0
    assert call.latency_ms == 3


def test_write_paths_are_normalized_without_inventing_success(tmp_path):
    database(tmp_path)
    tool = event(
        "tool_use",
        tool="write",
        callID="call-1",
        state={
            "status": "completed",
            "input": {"filePath": "/work/config.json", "content": "{}"},
            "output": "written",
        },
    )
    result = host.observe("opencode", stream(tool), tmp_path)
    assert result.calls[0].name == "Write"
    assert result.calls[0].arguments["file_path"] == "/work/config.json"
    assert not result.completed and not result.success


@pytest.mark.parametrize(
    "broken", ["not-json", "[]", '{"type":"tool_use","sessionID":"session-1","part":{}}']
)
def test_malformed_stream_is_unknown_not_success(tmp_path, broken):
    database(tmp_path)
    result = host.observe("opencode", broken + "\n" + stream(terminal()), tmp_path)
    assert not result.success and result.errors


def test_tool_calls_step_is_not_a_session_stop_and_costs_are_retained(tmp_path):
    database(tmp_path)
    first = event("step_finish", reason="tool-calls", cost=0.2, tokens={"input": 9})
    result = host.observe("opencode", stream(first), tmp_path)
    assert not result.completed
    assert result.cost_usd == 0.2
    assert result.usage["steps"][0]["tokens"] == {"input": 9}
    second = terminal(id="part-2")
    result = host.observe("opencode", stream(first, second), tmp_path)
    assert result.success and result.cost_usd == 0.2
    assert not result.usage["auxiliary_usage_known"]


def test_duplicate_terminal_cannot_double_count_as_success(tmp_path):
    database(tmp_path)
    result = host.observe("opencode", stream(terminal(), terminal()), tmp_path)
    assert not result.success
    assert any("repeated" in error for error in result.errors)


@pytest.mark.parametrize("mode", ["isolated", "normal"])
def test_prepare_uses_existing_local_model_and_only_scratch_native_state(
    tmp_path, monkeypatch, mode
):
    for name in ("config", "native", "work", "tmp", "bin"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(
        host, "_provider", lambda: {"options": {"baseURL": "http://localhost:11434/v1"}}
    )
    original = {"HOME": "/unchanged", "PATH": "/bin"}
    launch = host.prepare("opencode", tmp_path, original, "task", host.MODEL, mode, 0.75)
    assert original == {"HOME": "/unchanged", "PATH": "/bin"}
    assert launch.env["HOME"] == "/unchanged"
    assert launch.argv[launch.argv.index("--model") + 1] == host.MODEL
    assert launch.env["npm_config_offline"] == "true"
    assert launch.env["OPENCODE_DISABLE_CLAUDE_CODE"] == "true"
    assert launch.env["OPENCODE_DISABLE_PROJECT_CONFIG"] == (
        "true" if mode == "isolated" else "false"
    )
    assert launch.public_settings["context_override"] is None
    assert not launch.public_settings["budget_enforced_by_cli"]
    if mode == "normal":
        project = tmp_path / "work/AGENTS.md"
        assert project.is_symlink()
        assert project.resolve().is_relative_to(tmp_path / "native")
        global_note = Path(launch.env["OPENCODE_CONFIG_DIR"]) / "AGENTS.md"
        assert global_note.resolve() == tmp_path / "native/global/AGENTS.md"
        project.write_text("saved local fact")
        assert (tmp_path / "native/project/AGENTS.md").read_text() == "saved local fact"
    else:
        assert list((tmp_path / "native").iterdir()) == []


@pytest.mark.parametrize("blocked", ["gemini", "copilot"])
def test_blocked_hosts_cannot_fall_back_to_another_model(tmp_path, blocked):
    with pytest.raises(RuntimeError, match=host.BLOCKERS[blocked]):
        host.prepare(blocked, tmp_path, {}, "task", "model", "normal", 1)
    with pytest.raises(RuntimeError, match=host.BLOCKERS[blocked]):
        host.observe(blocked, "", tmp_path)
