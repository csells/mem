"""Entrypoint integrity checks do not purchase provider sessions."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from membench.runner import bd_component_run as launch


def test_archive_identity_uses_exact_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls = []

    def output(argv, **kwargs):
        calls.append(argv)
        return b"archive"

    monkeypatch.setattr(launch.subprocess, "check_output", output)
    assert launch.archive_identity(tmp_path, "pinned") == launch.sha256(b"archive")
    assert calls == [["git", "-C", str(tmp_path), "archive", "--format=tar", "pinned"]]


def test_dataset_inventory_rejects_tampered_content(tmp_path: Path):
    (tmp_path / "evidence.txt").write_text("original")
    inventory = {"evidence.txt": launch.sha256(b"original")}
    (tmp_path / "SHA256.json").write_text(json.dumps(inventory))
    launch.verify_inventory(tmp_path)
    (tmp_path / "evidence.txt").write_text("changed")
    with pytest.raises(ValueError, match="inventory"):
        launch.verify_inventory(tmp_path)


@pytest.mark.parametrize("name", ["../outside", "/etc/passwd"])
def test_inventory_rejects_outside_paths(tmp_path: Path, name: str):
    (tmp_path / "SHA256.json").write_text(json.dumps({name: "hash"}))
    with pytest.raises(ValueError, match="inventory"):
        launch.verify_inventory(tmp_path)


def test_no_fire_only_freezes_and_checks_identity(tmp_path: Path, monkeypatch):
    manifest = {"configuration": {}}
    path = tmp_path / "input.json"
    path.write_text(json.dumps(manifest))
    calls = []
    monkeypatch.setattr(launch, "verify_live_identity", lambda value: calls.append("check"))
    monkeypatch.setattr(launch, "freeze", lambda out, value: calls.append("freeze"))
    monkeypatch.setattr(launch, "execute", lambda *a, **k: pytest.fail("no provider run"))
    assert launch.main(["--manifest", str(path), "--out", str(tmp_path / "run")]) == 0
    assert calls == ["check", "freeze"]


def test_fire_requires_oauth_and_refuses_api_key(tmp_path: Path, monkeypatch):
    path = tmp_path / "input.json"
    path.write_text("{}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fixture")
    monkeypatch.setattr(launch, "verify_live_identity", lambda value: pytest.fail("refuse first"))
    with pytest.raises(ValueError, match="OAuth"):
        launch.main(["--manifest", str(path), "--out", str(tmp_path / "run"), "--fire"])


@pytest.fixture
def identity(tmp_path: Path, monkeypatch):
    python = tmp_path / "python"
    python.write_text("binary")
    archive = tmp_path / "harness-source.zip"
    archive.write_text("frozen")
    configuration = {
        "source_fingerprint": "source",
        "bd_identity": {"version": "bd"},
        "cli_version": "cli",
        "agent_python": str(python),
        "python_resolved": str(python),
        "python_environment": {"version": "python"},
        "repo_absolute": str(tmp_path),
        "base_commit": "commit",
        "candidate_archive_sha256": "archive",
        "dataset_root": str(tmp_path),
        "source_archive_dir": str(tmp_path),
        "runtime_executables": {"claude": "pinned"},
    }
    monkeypatch.setattr(launch, "source_fingerprint", lambda: "source")
    monkeypatch.setattr(launch, "resolve_bd_identity", lambda: {"version": "bd"})
    monkeypatch.setattr(launch, "resolve_cli_version", lambda: "cli")
    monkeypatch.setattr(launch, "environment_identity", lambda p: {"version": "python"})
    monkeypatch.setattr(launch, "archive_identity", lambda p, c: "archive")
    monkeypatch.setattr(launch, "verify_inventory", lambda p: None)
    monkeypatch.setattr(launch, "_archive_source", lambda p: None)
    monkeypatch.setattr(launch, "runtime_executable_identity", lambda: {"claude": "pinned"})
    return {"configuration": configuration}


def test_complete_live_identity_checks_pass(identity):
    launch.verify_live_identity(identity)


@pytest.mark.parametrize(
    "field",
    [
        "source_fingerprint",
        "bd_identity",
        "cli_version",
        "python_resolved",
        "python_environment",
        "candidate_archive_sha256",
        "source_archive_dir",
        "runtime_executables",
    ],
)
def test_live_identity_drift_refused(identity, field):
    changed = {"configuration": {**identity["configuration"], field: "changed"}}
    with pytest.raises(ValueError):
        launch.verify_live_identity(changed)


def test_environment_identity_uses_venv_invocation(tmp_path: Path, monkeypatch):
    calls = []

    def output(argv, **kwargs):
        calls.append(argv)
        return b'{"version":"pinned"}'

    monkeypatch.setattr(launch.subprocess, "check_output", output)
    python = tmp_path / ".venv/bin/python"
    assert launch.environment_identity(python) == {"version": "pinned"}
    assert calls[0][:3] == [str(python), "-I", "-c"]


def test_runtime_executable_identity_binds_paths_and_bytes(tmp_path: Path, monkeypatch):
    binary = tmp_path / "actual"
    binary.write_bytes(b"pinned binary")
    link = tmp_path / "command"
    link.symlink_to(binary)
    monkeypatch.setattr(launch.shutil, "which", lambda name: str(link))
    identities = launch.runtime_executable_identity()
    assert set(identities) == {"claude", "dolt", "bwrap"}
    assert identities["claude"] == {
        "path": str(link),
        "resolved": str(binary),
        "sha256": launch.sha256(b"pinned binary"),
    }


def test_halted_schedule_returns_nonzero(tmp_path: Path, monkeypatch):
    path = tmp_path / "input.json"
    path.write_text('{"configuration":{}}')
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fixture")
    monkeypatch.setattr(launch, "verify_live_identity", lambda value: None)
    monkeypatch.setattr(launch, "freeze", lambda *args: None)
    monkeypatch.setattr(launch, "execute", lambda *args, **kwargs: {"halted": True})
    monkeypatch.setitem(
        sys.modules,
        "membench.runner.bd_component_session",
        SimpleNamespace(run_component_session=lambda *a, **k: None),
    )
    assert launch.main(["--manifest", str(path), "--out", str(tmp_path / "run"), "--fire"]) == 1
