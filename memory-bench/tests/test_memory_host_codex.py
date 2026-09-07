from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from membench.runner import memory_host_codex as host


def encode(*events: dict[str, object]) -> str:
    return "\n".join(json.dumps(event) for event in events)


def model_record(local: Path, session_id: str, model: str = "gpt-6-astra") -> None:
    root = local / "config/sessions"
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{session_id}.jsonl").write_text(
        encode(
            {"type": "session_meta", "payload": {"id": session_id}},
            {"type": "turn_context", "payload": {"model": model, "effort": "high"}},
        )
    )


def test_real_command_surface_preserves_receipt_marker_and_ids(tmp_path: Path) -> None:
    model_record(tmp_path, "thread-1")
    observation = host.observe(
        encode(
            {"type": "thread.started", "thread_id": "thread-1"},
            {
                "type": "item.started",
                "item": {
                    "id": "item_2",
                    "type": "command_execution",
                    "command": "bd recall key",
                    "status": "in_progress",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "item_2",
                    "type": "command_execution",
                    "command": "bd recall key",
                    "aggregated_output": "body\nRECEIPT uuid\n",
                    "exit_code": 0,
                    "status": "completed",
                },
            },
            {"type": "turn.completed", "usage": {"input_tokens": 7, "output_tokens": 2}},
        ),
        tmp_path,
    )
    assert observation.success and observation.models == ["gpt-6-astra"]
    assert observation.session_id == "thread-1"
    assert observation.cost_usd is None
    (call,) = observation.calls
    assert call.tool_use_id == "item_2"
    assert call.tool_use_index == 1 and call.tool_result_index == 2
    assert call.result == "body\nRECEIPT uuid\n"
    assert observation.usage["input_tokens"] == 7


def test_other_session_model_is_never_used(tmp_path: Path) -> None:
    model_record(tmp_path, "unrelated", "wrong-model")
    observation = host.observe(
        encode(
            {"type": "thread.started", "thread_id": "current"},
            {"type": "turn.completed", "usage": {}},
        ),
        tmp_path,
    )
    assert observation.models == [] and observation.model_evidence == "unobserved"


def test_unanswered_command_stays_unanswered(tmp_path: Path) -> None:
    observation = host.observe(
        encode(
            {"type": "thread.started", "thread_id": "current"},
            {
                "type": "item.started",
                "item": {
                    "id": "item_1",
                    "type": "command_execution",
                    "command": "bd remember fact --key key",
                },
            },
        ),
        tmp_path,
    )
    assert not observation.completed and not observation.success
    assert observation.calls[0].result is None
    assert observation.calls[0].tool_result_index is None


@pytest.mark.parametrize("text", ["not json", '{"type":"turn.completed"}', "[]"])
def test_malformed_or_missing_identity_never_passes(text: str, tmp_path: Path) -> None:
    observation = host.observe(text, tmp_path)
    assert not observation.success and observation.errors


def test_nonfatal_item_warning_does_not_become_model_failure(tmp_path: Path) -> None:
    observation = host.observe(
        encode(
            {"type": "thread.started", "thread_id": "current"},
            {
                "type": "item.completed",
                "item": {"id": "item_0", "type": "error", "message": "feature warning"},
            },
            {"type": "turn.completed", "usage": {}},
        ),
        tmp_path,
    )
    assert observation.success
    assert observation.usage["host_warnings"] == ["feature warning"]


def test_failed_turn_and_command_preserve_errors(tmp_path: Path) -> None:
    observation = host.observe(
        encode(
            {"type": "thread.started", "thread_id": "current"},
            {
                "type": "item.started",
                "item": {"id": "item_1", "type": "command_execution", "command": "false"},
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "command_execution",
                    "command": "false",
                    "aggregated_output": "failed",
                    "exit_code": 1,
                    "status": "failed",
                },
            },
            {"type": "turn.failed", "error": {"message": "quota failure"}},
        ),
        tmp_path,
    )
    assert observation.completed and not observation.success
    assert observation.calls[0].is_error
    assert any("quota failure" in error for error in observation.errors)


def test_file_change_without_start_keeps_timing_unknown(tmp_path: Path) -> None:
    observation = host.observe(
        encode(
            {"type": "thread.started", "thread_id": "current"},
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "file_change",
                    "changes": [{"path": "config.json", "kind": "add"}],
                    "status": "completed",
                },
            },
            {"type": "turn.completed", "usage": {}},
        ),
        tmp_path,
    )
    (call,) = observation.calls
    assert call.name == "Write" and call.arguments["file_path"] == "config.json"
    assert call.tool_use_index is None and call.tool_result_index == 1


@pytest.mark.parametrize("mode", ["isolated", "normal"])
def test_prepare_private_auth_and_native_paths(
    mode: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "config.toml").write_text(
        'model="gpt-6-astra"\nmodel_reasoning_effort="high"\nservice_tier="fast"\n'
    )
    payload = {
        "auth_mode": "chatgpt",
        "OPENAI_API_KEY": None,
        "tokens": {"access_token": "private-test-token"},
    }
    (source / "auth.json").write_text(json.dumps(payload))
    monkeypatch.setattr(host, "_source_home", lambda: source)
    local = tmp_path / "session"
    for name in ("work", "config", "tmp", "bin", "native"):
        (local / name).mkdir(parents=True)
    launch = host.prepare(
        local, {"HOME": "/preserved-home", "PATH": "/bin"}, "neutral", "gpt-6-astra", mode, 0.5
    )
    assert launch.env["HOME"] == "/preserved-home"
    assert launch.env["CODEX_HOME"] == str(local / "config")
    assert (local / "config/auth.json").stat().st_mode & 0o777 == 0o600
    assert json.loads((local / "config/auth.json").read_text()) == payload
    assert "private-test-token" not in json.dumps(launch.public_settings)
    assert "--ephemeral" not in launch.argv
    assert (local / "config/memories").resolve() == local / "native/memories"
    assert ("memories.generate_memories=false" in launch.argv) is (mode == "isolated")
    assert launch.public_settings["native_feature_default"] is False
    with pytest.raises(FileExistsError):
        host.prepare(local, {"HOME": "/preserved-home"}, "neutral", "gpt-6-astra", mode, 0.5)


def test_export_keeps_only_exact_rollout_bytes(tmp_path: Path) -> None:
    local = tmp_path / "local"
    model_record(local, "thread-1")
    (local / "config/auth.json").write_text('{"tokens":{"access_token":"fake-private-token"}}')
    (local / "config/config.toml").write_text("private=1")
    out = tmp_path / "archive"
    host.export_evidence(local, out)
    source = local / "config/sessions/thread-1.jsonl"
    copied = out / "config/sessions/thread-1.jsonl"
    assert copied.read_bytes() == source.read_bytes()
    assert not (out / "config/auth.json").exists()
    assert not (out / "config/config.toml").exists()
    observation = host.observe(
        encode(
            {"type": "thread.started", "thread_id": "thread-1"},
            {"type": "turn.completed", "usage": {}},
        ),
        out,
    )
    assert observation.models == ["gpt-6-astra"]
    with pytest.raises(FileExistsError):
        host.export_evidence(local, out)


def test_observe_accepts_relative_offline_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_record(tmp_path / "archive", "thread-1")
    monkeypatch.chdir(tmp_path)
    observation = host.observe(
        encode(
            {"type": "thread.started", "thread_id": "thread-1"},
            {"type": "turn.completed", "usage": {}},
        ),
        Path("archive"),
    )
    assert observation.models == ["gpt-6-astra"] and observation.success


def test_export_rejects_external_links_and_credential_payloads(tmp_path: Path) -> None:
    local = tmp_path / "local"
    model_record(local, "thread-1")
    (local / "config/auth.json").write_text('{"tokens":{"access_token":"fake-private-token"}}')
    source = local / "config/sessions/thread-1.jsonl"
    source.write_text(source.read_text() + '\n{"secret":"fake-private-token"}\n')
    with pytest.raises(ValueError, match="credential"):
        host.export_evidence(local, tmp_path / "archive-secret")
    external = tmp_path / "external"
    external.mkdir()
    (local / "config/sessions/outside").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError):
        host.export_evidence(local, tmp_path / "archive-linked")


def test_native_database_wal_and_shared_memory_follow_target(tmp_path: Path) -> None:
    config = tmp_path / "config"
    native = tmp_path / "native"
    config.mkdir()
    native.mkdir()
    database = config / "memories_1.sqlite"
    database.symlink_to(native / "memories_1.sqlite")
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("pragma journal_mode=wal").fetchone()[0] == "wal"
        connection.execute("create table fixture (value text)")
        connection.execute("insert into fixture values ('scratch only')")
        connection.commit()
        assert (native / "memories_1.sqlite-wal").exists()
        assert (native / "memories_1.sqlite-shm").exists()
        assert not (config / "memories_1.sqlite-wal").exists()
        assert not (config / "memories_1.sqlite-shm").exists()
    finally:
        connection.close()
