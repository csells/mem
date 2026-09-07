"""Checks for isolation boundaries, including the real macOS sandbox parser."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from membench.runner.memory_routes_runtime import experiment_env, make_profile, subscription_token


def test_environment_isolates_state_without_changing_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("HOME", "/Users/memory-test-owner")
    monkeypatch.setenv("BEADS_DIR", "/Users/memory-test-owner/real-data")
    monkeypatch.setenv("BEADS_DOLT_SERVER_PORT", "3307")
    monkeypatch.setenv("BD_READONLY", "1")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "fake-inherited-token")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "fake-inherited-bearer")
    monkeypatch.setenv("UNFAMILIAR_CREDENTIAL", "fake-other-credential")
    monkeypatch.setenv("PYTHONPATH", "/Users/memory-test-owner/hidden-evidence")
    monkeypatch.setenv("BASH_ENV", "/Users/memory-test-owner/startup.sh")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("PATH", "/Users/memory-test-owner/bin:/usr/bin:/bin")
    monkeypatch.setenv("LC_ALL", "C")
    before = dict(os.environ)

    env = experiment_env(tmp_path / "config", tmp_path / "tmp", tmp_path / "bin")

    assert dict(os.environ) == before
    assert env["HOME"] == before["HOME"]
    assert env["LC_ALL"] == "C"
    assert not any(key.startswith("BEADS_") for key in env)
    assert {key for key in env if key.startswith("BD_")} == {
        "BD_NON_INTERACTIVE",
        "BD_DISABLE_METRICS",
    }
    assert env["BD_DISABLE_METRICS"] == "1"
    for key in (
        "CLAUDE_CODE_OAUTH_TOKEN",
        "ANTHROPIC_AUTH_TOKEN",
        "UNFAMILIAR_CREDENTIAL",
        "PYTHONPATH",
        "BASH_ENV",
        "GIT_CONFIG_COUNT",
    ):
        assert key not in env
    assert env["CLAUDE_CONFIG_DIR"] == str((tmp_path / "config").resolve())
    assert env["CLAUDE_SECURESTORAGE_CONFIG_DIR"] == ""
    assert env["CLAUDE_CODE_TMPDIR"] == str((tmp_path / "tmp").resolve())
    assert env["TMPDIR"] == env["CLAUDE_CODE_TMPDIR"] == env["XDG_RUNTIME_DIR"]
    assert env["PATH"] == (
        str((tmp_path / "bin").resolve()) + ":/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    )
    assert env["DOLT_ROOT_PATH"] == str((tmp_path / "config/dolt-root").resolve())
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert not (tmp_path / "config").exists()


@pytest.mark.parametrize("value", ["", "fake-api-key-must-not-appear"])
def test_api_key_is_refused_without_disclosing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", value)
    with pytest.raises(ValueError, match="subscription experiment refused") as caught:
        experiment_env(tmp_path / "config", tmp_path / "tmp", tmp_path / "bin")
    if value:
        assert value not in str(caught.value)


def test_profile_escapes_paths_and_does_not_grant_parent(tmp_path: Path) -> None:
    workspace = tmp_path / 'work "quoted" \\ café\nnext'
    workspace.mkdir()
    profile = make_profile(tmp_path / "profile.sb", [workspace], [])
    text = profile.read_text()
    assert f"(subpath {json.dumps(str(workspace.resolve()), ensure_ascii=False)})" in text
    read_line = next(line for line in text.splitlines() if line.startswith("(allow file-read*"))
    assert f"(subpath {json.dumps(str(tmp_path.resolve()))})" not in read_line
    assert '(literal "/dev/null")' in text
    assert '(literal "/dev/tty")' in text
    with pytest.raises(FileExistsError):
        make_profile(profile, [workspace], [])
    assert profile.read_text() == text


@pytest.mark.parametrize("root", ["/", "/Users", "/private", "/private/tmp", "/Volumes"])
def test_broad_allowances_are_refused(tmp_path: Path, root: str) -> None:
    with pytest.raises(ValueError, match="broad sandbox allowance"):
        make_profile(tmp_path / "profile.sb", [], [Path(root)])
    assert not (tmp_path / "profile.sb").exists()


def test_source_repo_and_virtualenv_allowances_are_refused(tmp_path: Path) -> None:
    source_repo = Path(__file__).resolve().parents[2]
    for root in (source_repo, source_repo / "memory-bench/.venv", source_repo.parent):
        with pytest.raises(ValueError, match="source repository sandbox allowance"):
            make_profile(tmp_path / "profile.sb", [], [root])


@pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("sandbox-exec") is None,
    reason="Seatbelt execution requires macOS",
)
def test_real_sandbox_allows_workspace_and_denies_sibling_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / 'work "quoted" \\ café\nnext'
    workspace.mkdir()
    allowed = workspace / "fact.txt"
    allowed.write_text("visible fact")
    hidden = tmp_path / "hidden-evidence.txt"
    hidden.write_text("hidden gold")
    fake_home = tmp_path / "fake-home"
    monkeypatch.setenv("HOME", str(fake_home))
    hidden_configs = [
        fake_home / ".config/bd/config.yaml",
        fake_home / ".beads/config.yaml",
        fake_home / "Library/Application Support/bd/config.yaml",
    ]
    for config in hidden_configs:
        config.parent.mkdir(parents=True)
        config.write_text("private: test configuration")
    profile = make_profile(tmp_path / "profile.sb", [workspace], [])
    sandbox = shutil.which("sandbox-exec")
    assert sandbox is not None

    result = subprocess.run(
        [sandbox, "-f", str(profile), "/bin/cat", str(allowed)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "visible fact"
    refused = subprocess.run(
        [sandbox, "-f", str(profile), "/bin/cat", str(hidden)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert refused.returncode != 0
    assert "hidden gold" not in refused.stdout
    metadata = subprocess.run(
        [sandbox, "-f", str(profile), "/usr/bin/stat", "-f", "%z", str(hidden)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert metadata.returncode == 0, metadata.stderr
    assert metadata.stdout.strip() == str(len("hidden gold"))
    for config in hidden_configs:
        config_metadata = subprocess.run(
            [sandbox, "-f", str(profile), "/usr/bin/stat", "-f", "%z", str(config)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert config_metadata.returncode != 0
    refused_write = subprocess.run(
        [sandbox, "-f", str(profile), "/usr/bin/touch", str(tmp_path / "outside-workspace")],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert refused_write.returncode != 0
    assert not (tmp_path / "outside-workspace").exists()


def test_subscription_token_is_read_only_and_never_printed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = json.dumps(
        {"claudeAiOauth": {"accessToken": "fake-test-token", "expiresAt": 200_000}}
    ).encode()
    calls: list[tuple[list[str], dict[str, object]]] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, payload, b"never-print-this-stderr")

    monkeypatch.setattr("membench.runner.memory_routes_runtime.subprocess.run", run)
    monkeypatch.setattr("membench.runner.memory_routes_runtime.time.time", lambda: 100)
    assert subscription_token() == "fake-test-token"
    assert calls == [
        (
            [
                "/usr/bin/security",
                "find-generic-password",
                "-s",
                "Claude Code-credentials",
                "-w",
            ],
            {
                "capture_output": True,
                "timeout": 10,
                "check": False,
            },
        )
    ]
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize(
    ("returncode", "payload", "message"),
    [
        (1, b"fake-test-secret", "unavailable"),
        (0, b"fake-test-secret", "unavailable"),
        (0, b"[]", "unavailable"),
        (0, b"{}", "unavailable"),
        (0, b'{"claudeAiOauth": {"accessToken": "fake-test-secret"}}', "unavailable"),
        (
            0,
            b'{"claudeAiOauth": {"accessToken": "fake-test-secret", "expiresAt": 100000}}',
            "expired",
        ),
    ],
)
def test_subscription_failures_do_not_expose_credentials(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    returncode: int,
    payload: bytes,
    message: str,
) -> None:
    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(command, returncode, payload, b"fake-test-secret")

    monkeypatch.setattr("membench.runner.memory_routes_runtime.subprocess.run", run)
    monkeypatch.setattr("membench.runner.memory_routes_runtime.time.time", lambda: 100)
    with pytest.raises(RuntimeError, match=message) as caught:
        subscription_token()
    assert "fake-test-secret" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert capsys.readouterr() == ("", "")


def test_subscription_timeout_does_not_expose_captured_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(
            command, 10, output=b"fake-test-secret", stderr=b"fake-test-secret"
        )

    monkeypatch.setattr("membench.runner.memory_routes_runtime.subprocess.run", run)
    with pytest.raises(RuntimeError, match="unavailable") as caught:
        subscription_token()
    assert "fake-test-secret" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert capsys.readouterr() == ("", "")
