"""Single-session lifecycle without provider calls."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from membench.runner import bd_component_session as component
from membench.runner import bd_real_pair as pair
from membench.runner.tool_surface import MemoryToolSurface


@pytest.fixture
def inputs(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = tmp_path / "inputs"
    root.mkdir()
    artifacts = {}
    for name, text in {
        "prompt": "literal task",
        "source": "prior evidence",
        "seed": "known fact",
    }.items():
        (root / name).write_text(text)
        artifacts[name] = {"path": name, "sha256": hashlib.sha256(text.encode()).hexdigest()}
    return {
        "row_id": "capture-current",
        "component": "capture",
        "intervention": "capture",
        "condition": "current",
        "initial_store": "seeded",
        "prompt": artifacts["prompt"],
        "sources": [{**artifacts["source"], "target_path": "source.md"}],
        "seed": artifacts["seed"],
    }, {
        "input_root": str(root),
        "repo_absolute": "/unused",
        "base_commit": "unused",
        "agent_python": "/usr/bin/python3",
        "python_paths": ["lib"],
        "bd_binary": "/fake/bd",
        "model": "model",
        "cli_version": "version",
        "timeout_s": 10,
        "seed_key": "known",
    }


@pytest.fixture
def fake_bd(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def provision(root: Path, **_: Any) -> MemoryToolSurface:
        (root / "store").mkdir(parents=True)
        (root / "bin").mkdir()
        return MemoryToolSurface(
            root / "store", root / "bin", "/fake/bd", bd_context={"AGENTS.md": "bd guidance"}
        )

    def run(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        store = Path(argv[2])
        saved = store / "saved.json"
        memory = json.loads(saved.read_text()) if saved.exists() else {}
        if argv[3] == "remember":
            memory = {argv[6]: argv[4]}
            saved.write_text(json.dumps(memory))
            output = "Remembered"
        elif argv[3] == "recall":
            output = json.dumps(
                {"schema_version": 1, "found": True, "key": argv[4], "value": memory[argv[4]]}
            )
        else:
            output = json.dumps({"schema_version": 1, **memory})
        return subprocess.CompletedProcess(argv, 0, output, "")

    monkeypatch.setattr(component, "provision_memory_tool", provision)
    monkeypatch.setattr(component, "BD_RUNNER", run)
    return calls


def test_fresh_seeded_stores_literal_input_and_one_leg(
    tmp_path: Path, inputs: Any, fake_bd: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    row, config = inputs
    calls = []

    def leg(**kwargs: Any) -> dict[str, Any]:
        cwd, out = kwargs["cwd"], kwargs["out"]
        kwargs["surface"].config_dir.mkdir(parents=True)
        calls.append((cwd, kwargs["surface"].store_dir, kwargs["prompt"]))
        assert kwargs["leg"] == 0
        assert (cwd / "source.md").read_text() == "prior evidence"
        assert pair.COMMON_R4 in (cwd / "CLAUDE.md").read_text()
        assert not (out.parent / "harness-seed/agent-receipts.json").exists()
        out.mkdir()
        record = {"status": "ok", "memory": {"accepted_writes": 0}, "integrity_errors": []}
        (out / "result.json").write_text(json.dumps(record))
        return record

    monkeypatch.setattr(pair, "_leg", leg)
    for index in range(2):
        result = component.run_component_session(row, config, tmp_path / f"out-{index}")
        assert result["status"] == "completed"
        assert result["initial_memory"] == {"known": "known fact"}
        assert result["agent"]["memory"]["accepted_writes"] == 0
        assert (tmp_path / f"out-{index}/initial-bd-store.tar").exists()
    assert len(calls) == 2
    assert calls[0][0] != calls[1][0] and calls[0][1] != calls[1][1]
    assert [call[2] for call in calls] == ["literal task", "literal task"]


def test_timeout_preserves_workspace_and_store(
    tmp_path: Path, inputs: Any, fake_bd: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    row, config = inputs

    def leg(**kwargs: Any) -> Any:
        out = kwargs["out"]
        out.mkdir()
        (kwargs["cwd"] / "partial").write_text("partial artifact")
        (out / "result.json").write_text(
            '{"status":"timeout","session_id":"valid-session","integrity_errors":[]}'
        )
        (out / "process.json").write_text('{"status":"timeout"}')
        raise RuntimeError("leg timeout")

    monkeypatch.setattr(pair, "_leg", leg)
    result = component.run_component_session(row, config, tmp_path / "out")
    assert result["status"] == "terminal_timeout"
    assert (tmp_path / "out/establish-output.tar").exists()
    assert (tmp_path / "out/leg-0-bd-store.tar").exists()


def test_changed_artifact_refuses_before_agent(
    tmp_path: Path, inputs: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    row, config = inputs
    (Path(config["input_root"]) / "prompt").write_text("changed")
    monkeypatch.setattr(pair, "_leg", lambda **_: pytest.fail("agent must not run"))
    result = component.run_component_session(row, config, tmp_path / "out")
    assert result["status"] == "blocked_integrity_or_infrastructure"


def test_existing_output_cannot_repurchase(tmp_path: Path, inputs: Any) -> None:
    row, config = inputs
    with pytest.raises(RuntimeError, match="exists"):
        component.run_component_session(row, config, tmp_path)


@pytest.mark.parametrize("target", ["", "../escape", "/absolute", ".git/config", "seed", "prompt"])
def test_invalid_source_destination(tmp_path: Path, inputs: Any, target: str) -> None:
    row, config = inputs
    row = {**row, "sources": [{**row["sources"][0], "target_path": target}]}
    result = component.run_component_session(row, config, tmp_path / "out")
    assert result["status"] == "blocked_integrity_or_infrastructure"
    assert result["error"]["type"] == "ValueError"


def test_failed_seed_retains_store(
    tmp_path: Path, inputs: Any, fake_bd: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    row, config = inputs
    original = component.BD_RUNNER

    def runner(argv: list[str], **kwargs: Any) -> Any:
        if argv[3] == "recall":
            return subprocess.CompletedProcess(argv, 0, "{}", "")
        return original(argv, **kwargs)

    monkeypatch.setattr(component, "BD_RUNNER", runner)
    result = component.run_component_session(row, config, tmp_path / "out")
    assert result["status"] == "blocked_integrity_or_infrastructure"
    assert (tmp_path / "out/setup-or-failed-store.tar").exists()
    assert not (tmp_path / "out/leg-0-snapshots.json").exists()


def test_empty_condition_never_seeds(
    tmp_path: Path, inputs: Any, fake_bd: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    row, config = inputs
    row = {**row, "initial_store": "empty", "seed": None}

    def leg(**kwargs: Any) -> dict[str, Any]:
        kwargs["surface"].config_dir.mkdir(parents=True)
        return {"status": "ok", "integrity_errors": []}

    monkeypatch.setattr(pair, "_leg", leg)
    result = component.run_component_session(row, config, tmp_path / "out")
    assert result["status"] == "completed"
    assert result["initial_memory"] == {}
    assert [argv[3] for argv in fake_bd] == ["memories", "memories"]


@pytest.mark.parametrize("raw", ["[]", '{"schema_version":2}', '{"schema_version":1,"key":42}'])
def test_invalid_inventory_schema(raw: str) -> None:
    with pytest.raises(ValueError):
        component._inventory(raw)


@pytest.mark.parametrize("failure", ["exit", "timeout"])
def test_bd_error_is_explicit(
    tmp_path: Path, inputs: Any, fake_bd: Any, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    row, config = inputs

    def run(argv: list[str], **_: Any) -> Any:
        if failure == "timeout":
            raise subprocess.TimeoutExpired(argv, 30)
        return subprocess.CompletedProcess(argv, 3, "", "failed")

    monkeypatch.setattr(component, "BD_RUNNER", run)
    result = component.run_component_session(row, config, tmp_path / "out")
    assert result["status"] == "blocked_integrity_or_infrastructure"
    assert result["error"]
    assert (tmp_path / "out/harness-seed/empty-check.json").exists()
    assert (tmp_path / "out/setup-or-failed-store.tar").exists()


@pytest.mark.parametrize(
    "fault", [None, "receipt_instrumentation_error", "init_model_mismatch", "unexpected_hook_event"]
)
def test_realistic_timeout_integrity(
    tmp_path: Path, inputs: Any, fake_bd: Any, monkeypatch: pytest.MonkeyPatch, fault: str | None
) -> None:
    row, config = inputs
    observed = {"accepted_writes": 1, "observed_content_reads": 1}

    def leg(**kwargs: Any) -> Any:
        out = kwargs["out"]
        out.mkdir()
        errors = ["missing_or_failed_terminal_result"] + ([fault] if fault else [])
        pair._json(
            out / "result.json",
            {
                "status": "timeout",
                "session_id": "valid-session",
                "integrity_errors": errors,
                "memory": observed,
            },
        )
        pair._json(out / "process.json", {"status": "timeout", "returncode": None})
        raise RuntimeError("actual timeout")

    monkeypatch.setattr(pair, "_leg", leg)
    result = component.run_component_session(row, config, tmp_path / "out")
    assert result["status"] == (
        "blocked_integrity_or_infrastructure" if fault else "terminal_timeout"
    )
    assert result["agent"]["memory"] == observed
    assert (tmp_path / "out/leg-0-snapshots.json").exists()
