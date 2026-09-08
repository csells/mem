import importlib.util
import json
import os
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "recover_completed", Path(__file__).with_name("recover_completed.py")
)
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def scaffold(tmp_path, monkeypatch, event="turn.completed"):
    row = {"slot": "case-2", "lifecycle": "case", "stage": 2, "host": "codex"}
    (tmp_path / "manifest.json").write_text(json.dumps({"slots": [row], "timeout_seconds": 420}))
    evidence = tmp_path / "cases/case/stage-2"
    evidence.mkdir(parents=True)
    local = tmp_path / "scratch/stage-2"
    local.mkdir(parents=True)
    (evidence.parent / "state.json").write_text(json.dumps({"scratch": str(local.parent)}))
    (evidence / "process.json").write_text(
        json.dumps({"pid": 99999999, "started_ns": 100000000000})
    )
    stream = local / "stdout-private.jsonl"
    stream.write_text(json.dumps({"type": event}) + "\n")
    os.utime(stream, ns=(200000000000, 200000000000))
    monkeypatch.setattr(recovery.legacy, "assert_frozen", lambda _: None)

    def gone(*args):
        raise ProcessLookupError

    monkeypatch.setattr(recovery.os, "kill", gone)
    return evidence, local


def test_accepts_completed_dead_process_without_writing(tmp_path, monkeypatch):
    evidence, local = scaffold(tmp_path, monkeypatch)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    recovery.preflight(tmp_path, "case-2")
    after = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert before == after


def test_incomplete_turn_is_not_manufactured(tmp_path, monkeypatch):
    evidence, _ = scaffold(tmp_path, monkeypatch, "item.completed")
    with pytest.raises(ValueError, match="No terminal completed-turn"):
        recovery.preflight(tmp_path, "case-2")
    assert not (evidence / "result.json").exists()


def test_existing_result_is_preserved(tmp_path, monkeypatch):
    evidence, _ = scaffold(tmp_path, monkeypatch)
    (evidence / "result.json").write_text("existing-evidence")
    with pytest.raises(FileExistsError):
        recovery.preflight(tmp_path, "case-2")
    assert (evidence / "result.json").read_text() == "existing-evidence"


def test_running_process_is_not_assessed(tmp_path, monkeypatch):
    scaffold(tmp_path, monkeypatch)
    monkeypatch.setattr(recovery.os, "kill", lambda *args: None)
    with pytest.raises(ValueError, match="still exists"):
        recovery.preflight(tmp_path, "case-2")


def test_completion_outside_deadline_is_not_admitted(tmp_path, monkeypatch):
    _, local = scaffold(tmp_path, monkeypatch)
    os.utime(local / "stdout-private.jsonl", ns=(900000000000, 900000000000))
    with pytest.raises(ValueError, match="original deadline"):
        recovery.preflight(tmp_path, "case-2")
