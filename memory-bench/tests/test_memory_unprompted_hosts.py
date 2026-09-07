"""Qualification checks: false completion, instruction delivery, and isolation."""

from __future__ import annotations

import json
import signal
from pathlib import Path
from unittest.mock import Mock

import pytest

from membench.runner import memory_host_other
from membench.runner import memory_unprompted_hosts as hosts
from scripts import memory_unprompted_smoke as smoke


def _stream() -> list[dict[str, object]]:
    return [
        {"type": "turn.started", "sessionId": "session-a", "payload": {}},
        {
            "type": "session.updated",
            "sessionId": "session-a",
            "payload": {"modelRef": {"providerId": "zai", "modelId": "glm-5.3"}},
        },
        {
            "type": "tool.updated",
            "sessionId": "session-a",
            "payload": {
                "kind": "scheduled",
                "toolCallId": "tool-a",
                "toolName": "Bash",
                "input": {"command": "bd recall x"},
            },
        },
        {
            "type": "tool.updated",
            "sessionId": "session-a",
            "payload": {"kind": "started", "toolCallId": "tool-a", "toolName": "Bash"},
        },
        {
            "type": "tool.updated",
            "sessionId": "session-a",
            "payload": {
                "kind": "result",
                "toolCallId": "tool-a",
                "result": {"success": True, "content": "actual body"},
            },
        },
        {"type": "turn.completed", "sessionId": "session-a", "payload": {}},
        {"type": "result", "sessionId": "session-a", "usage": {"totalTokens": 17}},
    ]


def _jsonl(events: list[dict[str, object]]) -> str:
    return "\n".join(json.dumps(e) for e in events)


def test_zcode_requires_observed_identity_and_actual_tool_result() -> None:
    result = hosts.observe_zcode(_jsonl(_stream()))
    assert result.success
    assert result.models == ["zai/glm-5.3"]
    assert result.calls[0].result == "actual body"
    assert result.calls[0].arguments == {"command": "bd recall x"}
    assert result.cost_usd is None


@pytest.mark.parametrize("remove", [1, 2, 4, 5, 6])
def test_zcode_does_not_invent_missing_events(remove: int) -> None:
    events = _stream()
    events.pop(remove)
    result = hosts.observe_zcode(_jsonl(events))
    if remove == 2:  # A started event still establishes execution, but no input was observed.
        assert result.calls[0].arguments == {}
    else:
        assert not result.success


def test_zcode_mixed_session_fails() -> None:
    events = _stream()
    events[4]["sessionId"] = "foreign"
    assert not hosts.observe_zcode(_jsonl(events)).success


def test_zcode_non_json_and_duplicate_completion_fail() -> None:
    assert not hosts.observe_zcode("banner\n" + _jsonl(_stream())).success
    assert not hosts.observe_zcode(_jsonl([*_stream(), _stream()[-1]])).success


def test_expected_tool_failure_is_not_fabricated_turn_failure() -> None:
    events = _stream()
    events[4]["payload"] = {"kind": "error", "toolCallId": "tool-a", "error": "missing key"}
    observed = hosts.observe_zcode(_jsonl(events))
    assert observed.success and observed.calls[0].is_error


def test_real_file_grading_rejects_boolean_as_integer(tmp_path: Path) -> None:
    marks = {"rule": "one", "skill": "two", "reference": "three"}
    (tmp_path / "markers-issue.json").write_text(json.dumps(marks))
    policy = json.loads(json.dumps(smoke.POLICY))
    policy["identifiers"]["trim"] = 1
    (tmp_path / "capture.json").write_text(json.dumps(policy))
    assert not smoke.grade_files(tmp_path, "issue", marks, "capture")["passed"]
    (tmp_path / "capture.json").write_text(json.dumps(smoke.POLICY))
    assert smoke.grade_files(tmp_path, "issue", marks, "capture")["passed"]


def test_secret_redaction_detected_without_changing_benign_text() -> None:
    assert smoke.sanitize("body abc-secret-value", ["abc-secret-value"]) == (
        "body <redacted-credential>",
        True,
    )
    assert smoke.sanitize("body", ["abc-secret-value"]) == ("body", False)


def test_invalid_mode_or_budget_rejected_before_auth(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        hosts.prepare("zcode", tmp_path, {}, "task", hosts.MODELS["zcode"], "guess")
    with pytest.raises(ValueError):
        hosts.prepare("zcode", tmp_path, {}, "task", hosts.MODELS["zcode"], budget=float("nan"))


def test_opencode_keeps_project_instructions_and_declares_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("work", "config", "bin", "native", "tmp"):
        (tmp_path / name).mkdir()
    model = hosts.MODELS["opencode"]
    monkeypatch.setattr(
        memory_host_other,
        "_provider",
        lambda: {
            "options": {"baseURL": "http://localhost:11434/v1"},
            "models": {model.split("/", 1)[1]: {}},
        },
    )
    launch = hosts.prepare("opencode", tmp_path, {}, "literal `prompt`\n$HOME", model)
    assert launch.env["OPENCODE_DISABLE_PROJECT_CONFIG"] == "false"
    assert launch.env["OPENCODE_DISABLE_EXTERNAL_SKILLS"] == "true"
    assert (tmp_path / "config/prompt.txt").read_text() == "literal `prompt`\n$HOME"
    settings = json.loads((tmp_path / "config/host-settings.json").read_text())
    assert settings["skills"]["paths"] == [str(tmp_path / "work/.agents/skills")]
    assert "must be observed" in launch.public_settings["runtime_context"]


def test_nonlocal_opencode_route_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("work", "config", "bin", "native", "tmp"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(
        memory_host_other,
        "_provider",
        lambda: {
            "options": {"baseURL": "http://localhost:11434/v1"},
            "models": {},
        },
    )
    with pytest.raises(ValueError, match="local"):
        hosts.prepare(
            "opencode",
            tmp_path,
            {"MEMBENCH_OLLAMA_BASE_URL": "https://remote.example/v1"},
            "task",
            hosts.MODELS["opencode"],
        )


def test_unready_owned_server_is_stopped_and_log_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "evidence"
    out.mkdir()
    proc = Mock(pid=123456, poll=Mock(return_value=None))
    launch = Mock(return_value=proc)
    kill = Mock()
    ticks = iter([0.0, 31.0])
    monkeypatch.setattr("subprocess.Popen", launch)
    monkeypatch.setattr("os.killpg", kill)
    monkeypatch.setattr("time.monotonic", lambda: next(ticks))
    monkeypatch.setattr(smoke, "make_profile", lambda path, *args: path)
    with pytest.raises(RuntimeError, match="did not start"):
        smoke.ollama_start(tmp_path, out)
    kill.assert_called_once_with(proc.pid, signal.SIGTERM)
    proc.wait.assert_called_once_with(timeout=10)
    assert launch.call_args.kwargs["stdout"].closed
    assert (out / "ollama-server.log").exists()
    assert json.loads((out / "ollama-server.json").read_text())["pid"] == proc.pid
