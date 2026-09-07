"""Actual host events, failed terminal results, and isolated memory settings."""

import json

import pytest

from membench.runner import memory_host_claude as host


def test_actual_model_identity_and_failure_are_not_replaced_by_requested_model(tmp_path):
    stream = "\n".join(
        json.dumps(row)
        for row in [
            {"type": "system", "subtype": "init", "session_id": "session-1", "model": "other"},
            {"type": "result", "is_error": True, "subtype": "error_max_turns"},
        ]
    )
    result = host.observe(stream, tmp_path)
    assert result.models == ["other"]
    assert result.completed and not result.success
    assert result.cost_usd is None
    assert result.session_id == "session-1"


def test_missing_and_repeated_terminal_events_are_unknown(tmp_path):
    for stream in ["", '{"type":"result"}\n{"type":"result"}']:
        result = host.observe(stream, tmp_path)
        assert not result.success
        assert result.errors


@pytest.mark.parametrize(
    "end",
    [
        {"type": "result"},
        {"type": "result", "subtype": "error_max_turns"},
        {"type": "result", "subtype": "success", "is_error": False, "session_id": "wrong"},
        {"type": "result", "subtype": "unknown", "is_error": False, "session_id": "session-1"},
    ],
)
def test_terminal_cannot_fabricate_success(tmp_path, end):
    start = {"type": "system", "subtype": "init", "session_id": "session-1", "model": "pinned"}
    result = host.observe(json.dumps(start) + "\n" + json.dumps(end), tmp_path)
    assert not result.success
    assert result.errors


@pytest.mark.parametrize("mode,enabled", [("isolated", False), ("normal", True)])
def test_memory_and_auth_are_confined_to_new_scratch(tmp_path, monkeypatch, mode, enabled):
    for name in ("config", "native", "work", "tmp", "bin"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(host, "subscription_token", lambda: "SECRET_TEST_TOKEN")
    inherited = {"HOME": "/unchanged", "PATH": "/bin"}
    launch = host.prepare(tmp_path, inherited, "task", "pinned-model", mode, 0.75)
    assert inherited == {"HOME": "/unchanged", "PATH": "/bin"}
    assert launch.env["HOME"] == "/unchanged"
    assert launch.env["CLAUDE_CODE_OAUTH_TOKEN"] == "SECRET_TEST_TOKEN"
    assert "SECRET_TEST_TOKEN" not in json.dumps(launch.public_settings)
    assert "SECRET_TEST_TOKEN" not in json.dumps(launch.argv)
    settings = json.loads((tmp_path / "config/host-settings.json").read_text())
    assert settings["autoMemoryEnabled"] is enabled
    assert settings["autoMemoryDirectory"] == str(tmp_path / "native")
    assert "hooks" not in settings
    assert launch.argv[launch.argv.index("--model") + 1] == "pinned-model"
