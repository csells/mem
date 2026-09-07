"""Cross-host boundary tests: preserve actual mistakes and interrupted trials."""

from __future__ import annotations

import json

import pytest

from membench.runner.memory_lifecycle_corpus import build_lifecycles
from scripts import memory_hosts_experiment as driver


def coverage():
    return {
        host: (
            {"runnable": True, "model": "model-1", "version": "1", "smoke": "evidence"}
            if host == "claude"
            else {"runnable": False, "blocker": "actual observed blocker"}
        )
        for host in driver.HOSTS
    }


def test_manifest_keeps_blocked_candidates_and_matched_stage_denominators(monkeypatch):
    monkeypatch.setattr(driver.base, "sha", lambda path: "digest")
    manifest = driver.make_manifest(coverage(), 20260908, 0.75, 240)
    assert json.loads(json.dumps(manifest)) == manifest
    assert manifest["planned_sessions"] == 24
    assert manifest["intended_max_sessions"] == 120
    assert manifest["blocked_host_slots"] == 96
    assert len(manifest["coverage"]) == 5
    assert len(manifest["schedule"]) == 3
    assert {(r["host"], r["mode"]) for r in manifest["schedule"]} == {
        ("claude", "normal"),
        ("claude", "isolated"),
    }
    assert all(len(task["stages"]) == 8 for task in manifest["tasks"])


def test_installed_without_smoke_is_not_runnable(monkeypatch):
    monkeypatch.setattr(driver.base, "sha", lambda path: "digest")
    info = coverage()
    del info["claude"]["smoke"]
    with pytest.raises(ValueError, match="Unverified"):
        driver.make_manifest(info, 1, 0.75, 240)
    del info["copilot"]
    with pytest.raises(ValueError, match="all five"):
        driver.make_manifest(info, 1, 0.75, 240)


def test_no_repurchase_for_any_started_unfinished_case(tmp_path):
    manifest = {"schedule": [{"id": "started"}, {"id": "untouched"}]}
    path = tmp_path / "cases/started"
    path.mkdir(parents=True)
    (path / "started.json").write_text('{"purchased": true}')
    with pytest.raises(ValueError, match="cannot be repurchased"):
        driver.pending_cases(tmp_path, manifest)
    assert (path / "started.json").read_text() == '{"purchased": true}'
    assert not (tmp_path / "cases/untouched").exists()


@pytest.mark.parametrize("mode", driver.MODES)
def test_actual_bad_records_and_native_records_carry_without_answer_repair(
    tmp_path, monkeypatch, mode
):
    task = build_lifecycles(20260908)[0]
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    out = tmp_path / "out"
    monkeypatch.setattr(driver.tempfile, "mkdtemp", lambda **kwargs: str(scratch))
    monkeypatch.setattr(driver, "experiment_env", lambda *args: {})
    monkeypatch.setattr(driver, "assert_frozen", lambda manifest: None)
    states = {}
    previous = dict(task.task.decoys)
    stages_seen = []
    native_seen = []

    def initialize(store, env, evidence):
        store.mkdir()
        states[store] = {}
        driver.base.new_json(evidence, {})

    def checked(args, store, env):
        if args[0] == "remember":
            states[store][args[3]] = args[1]
            return "ok"
        assert args == ["show", "task-1", "--json"]
        return '[{"id":"task-1","status":"closed"}]'

    def session(**kwargs):
        nonlocal previous
        name, store = kwargs["leg"], kwargs["store"]
        assert states[store] == previous
        assert not (store / "old-approval.txt").exists()
        # Neither target nor an alias is repaired on the next stage.
        states[store][task.key] = "Incomplete prose with unsupported advice"
        states[store][f"alias-{name}"] = "actual extra record"
        previous = dict(states[store])
        (store / "old-approval.txt").write_text(json.dumps(task.initial_config))
        native_from = kwargs["native_from"]
        native_seen.append(native_from)
        if native_from is not None:
            assert (native_from / "lesson.md").read_text() == "An actual wrong native note"
        local = scratch / name
        (local / "work").mkdir(parents=True)
        (local / "native").mkdir()
        (local / "native/lesson.md").write_text("An actual wrong native note")
        evidence = kwargs["evidence"]
        evidence.mkdir()
        driver.base.new_json(evidence / "receipts.json", [])
        stages_seen.append(name)
        return {
            "task_id": "task-1",
            "scratch": str(local),
            "is_error": False,
            "model_matches": True,
            "memory_evidence": {"evidence_unknown": False},
            "timed_out": False,
            "completed": True,
            "exit_code": 0,
        }, local / "native"

    monkeypatch.setattr(driver.base, "initialize_store", initialize)
    monkeypatch.setattr(driver.base, "checked_bd", checked)
    monkeypatch.setattr(driver.base, "memories", lambda store, env: dict(states[store]))
    monkeypatch.setattr(driver, "run_leg", session)
    monkeypatch.setattr(
        driver.lifecycle,
        "stage_summary",
        lambda stage, *args: {
            "name": stage.name,
            "complete_handoff": False,
        },
    )
    row = {"id": f"claude-{mode}-cache", "host": "claude", "mode": mode, "task": task.id}
    manifest = {"coverage": coverage(), "session_budget_usd": 0.75, "timeout_s": 240}
    driver.run_lifecycle(out, task, row, manifest)
    assert stages_seen == [stage.name for stage in task.stages]
    assert native_seen[0] is None
    assert (
        all(value is None for value in native_seen)
        if mode == "isolated"
        else all(value is not None for value in native_seen[1:])
    )
    result = json.loads((out / "cases" / row["id"] / "result.json").read_text())
    assert not result["complete_lifecycle"]


def test_unknown_mode_and_host_are_rejected():
    with pytest.raises(ValueError):
        driver.guidance("invented")
    with pytest.raises(ValueError):
        driver.adapter("invented")


def test_source_or_binary_drift_stops_before_another_session(tmp_path, monkeypatch):
    source = tmp_path / "adapter.py"
    binary = tmp_path / "cli"
    source.write_text("frozen source")
    binary.write_text("frozen binary")
    monkeypatch.setattr(driver.base, "REPO", tmp_path)
    manifest = {
        "source_sha256": {"adapter.py": driver.base.sha(source)},
        "binary_sha256": {str(binary): driver.base.sha(binary)},
    }
    driver.assert_frozen(manifest)
    source.write_text("changed source")
    with pytest.raises(ValueError, match="Frozen source"):
        driver.assert_frozen(manifest)
    manifest["source_sha256"] = {}
    binary.write_text("changed binary")
    with pytest.raises(ValueError, match="Frozen binary"):
        driver.assert_frozen(manifest)
