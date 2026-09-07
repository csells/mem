"""Lifecycle boundaries and enforcement policy must not expose the hidden oracle."""

from __future__ import annotations

import json

import pytest

from membench.runner.memory_lifecycle_corpus import build_lifecycles
from membench.runner.memory_lifecycle_hooks import closing, load_spec
from scripts import memory_lifecycle_experiment as driver


def test_policy_changes_preserve_the_successful_baseline():
    baseline = driver.base.EXAMPLES + driver.base.PROCEDURE
    assert driver.policy_guidance("existing") == baseline
    for policy in ("selective", "checked"):
        assert driver.policy_guidance(policy).startswith(baseline)
    assert driver.policy_guidance("checked").startswith(driver.policy_guidance("selective"))
    with pytest.raises(ValueError):
        driver.policy_guidance("invented")


def test_manifest_tasks_survive_json_freeze_without_tuple_drift(monkeypatch):
    monkeypatch.setattr(driver.base, "sha", lambda path: "digest")
    monkeypatch.setattr(driver.subprocess, "check_output", lambda *args, **kwargs: "version")
    manifest = driver.make_manifest(20260907, ["cache"], 0.75)
    assert json.loads(json.dumps(manifest)) == manifest


@pytest.mark.parametrize("stage_name", ["establish", "search", "revise", "supplied"])
def test_installed_guard_contains_no_hidden_expected_values(tmp_path, stage_name):
    stage = next(s for s in build_lifecycles()[0].stages if s.name == stage_name)
    local = tmp_path / "local"
    (local / "bin").mkdir(parents=True)
    (local / "bin/bd").write_text("original shim")
    hooks = driver.install_checks(local, tmp_path / "store", "task-1", stage=stage)
    assert (local / "bin/bd-without-completion-check").read_text() == "original shim"
    spec = load_spec(local / "bin/gate-policy.json")
    assert set(hooks) == {"Stop"}
    assert "expected_config" not in spec
    assert "expected_version" not in spec
    assert "lookup_key" not in spec
    assert "prompt" not in spec
    assert spec["required_write_keys"] == list(stage.required_write_keys)
    if stage_name in {"search", "supplied"}:
        assert spec["required_write_keys"] == []
    spec["expected_config"] = stage.expected_config
    (local / "invalid-spec.json").write_text(json.dumps(spec))
    with pytest.raises(ValueError):
        load_spec(local / "invalid-spec.json")


@pytest.mark.parametrize(
    "args,expected",
    [
        (["close", "task-1"], True),
        (["close", "--help"], False),
        (["update", "task-1", "--status", "closed"], True),
        (["update", "task-1", "--status=closed"], True),
        (["update", "task-1", "--status", "in_progress"], False),
        (["recall", "task-1"], False),
    ],
)
def test_completion_guard_covers_supported_task_close_forms(args, expected):
    assert closing(args) is expected


def test_memory_delta_distinguishes_no_change_from_alias_and_rewrite():
    assert driver.memory_delta({"a": "old"}, {"a": "old"}) == {
        "added": [],
        "removed": [],
        "changed": [],
    }
    assert driver.memory_delta({"a": "old", "b": "gone"}, {"a": "new", "c": "alias"}) == {
        "added": ["c"],
        "removed": ["b"],
        "changed": ["a"],
    }


def test_actual_mutations_cross_every_fresh_session_without_repair(tmp_path, monkeypatch):
    task = build_lifecycles()[0]
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    out = tmp_path / "out"
    monkeypatch.setattr(driver.tempfile, "mkdtemp", lambda **kwargs: str(scratch))
    monkeypatch.setattr(driver, "experiment_env", lambda *args: {})
    states = {}
    previous = dict(task.task.decoys)
    seen = []

    def initialize(store, env, evidence):
        store.mkdir()
        states[store] = {}
        driver.base.new_json(evidence, {})

    def checked(args, store, env):
        if args[0] == "remember":
            states[store][args[3]] = args[1]
            return "ok"
        assert args[:2] == ["show", "task-1"]
        return '[{"id":"task-1","status":"closed"}]'

    def session(**kwargs):
        nonlocal previous
        store, name, evidence = kwargs["store"], kwargs["leg"], kwargs["evidence"]
        assert states[store] == previous
        assert not (store / "task-history.json").exists()
        assert not (scratch / name / "work/config.json").exists()
        assert kwargs["native_from"] is None
        assert kwargs["guidance_override"] == driver.policy_guidance("selective")
        # Deliberately bad target and unsolicited alias must survive, unrepaired.
        states[store][task.key] = "Incomplete captured prose"
        states[store][f"alias-{name}"] = name
        previous = dict(states[store])
        (store / "task-history.json").write_text(json.dumps(task.initial_config))
        evidence.mkdir()
        (evidence / "workspace").mkdir()
        driver.base.new_json(evidence / "receipts.json", [])
        seen.append(name)
        return {"task_id": "task-1", "scratch": str(scratch / name)}, scratch / "native"

    monkeypatch.setattr(driver.base, "initialize_store", initialize)
    monkeypatch.setattr(driver.base, "checked_bd", checked)
    monkeypatch.setattr(driver.base, "memories", lambda store, env: dict(states[store]))
    monkeypatch.setattr(driver.base, "run_leg", session)
    monkeypatch.setattr(
        driver,
        "stage_summary",
        lambda stage, *args: {
            "name": stage.name,
            "complete_handoff": False,
        },
    )
    driver.run_lifecycle(out, task, "selective", 0.75)
    assert seen == [stage.name for stage in task.stages]
    result = json.loads(next((out / "cases").glob("*/result.json")).read_text())
    assert result["complete_lifecycle"] is False


def test_interrupted_purchase_is_never_reused(tmp_path):
    manifest = {"schedule": [{"task": "t", "policy": "existing"}]}
    (tmp_path / "cases/t-existing").mkdir(parents=True)
    with pytest.raises(ValueError, match="cannot be repurchased"):
        driver.pending_cases(tmp_path, manifest)


@pytest.mark.parametrize("subtype", ["error_max_turns", "error_max_budget_usd"])
def test_budget_caps_remain_measured_failures_when_explicitly_enabled(subtype):
    terminal = {"subtype": subtype, "is_error": True}
    assert driver.base.is_behavioral_limit(terminal, allow=True)
    assert not driver.base.is_behavioral_limit(terminal, allow=False)
    assert not driver.base.is_behavioral_limit(
        {"subtype": "error_during_execution", "is_error": True}, allow=True
    )
    assert not driver.base.is_behavioral_limit({"subtype": subtype, "is_error": False}, allow=True)


@pytest.mark.parametrize(
    "subtype", ["error_max_turns", "error_max_budget_usd", "error_during_execution"]
)
def test_session_retains_terminal_caps_and_actual_state_but_rejects_runtime_failure(
    tmp_path, monkeypatch, subtype
):
    base = driver.base
    case = tmp_path / "case"
    case.mkdir()
    monkeypatch.setattr(base, "experiment_env", lambda *args: {})
    monkeypatch.setattr(base, "subscription_token", lambda: "test-only-not-a-credential")
    monkeypatch.setattr(base, "checked_bd", lambda *args: '{"id":"task-1"}')
    monkeypatch.setattr(base, "memories", lambda *args: {})
    monkeypatch.setattr(base, "make_profile", lambda path, *args, **kwargs: path)
    monkeypatch.setattr(
        base,
        "prepare_instrumentation",
        lambda directory, store, leg: (directory / "hook.py", directory.parent / "receipts.jsonl"),
    )

    class Process:
        def __init__(self, args, **kwargs):
            stream = [
                {"type": "system", "subtype": "init", "model": base.MODEL, "session_id": "s-1"},
                {"type": "result", "subtype": subtype, "is_error": True, "total_cost_usd": 0.01},
            ]
            kwargs["stdout"].write("\n".join(json.dumps(event) for event in stream))
            kwargs["stdout"].flush()

        def wait(self, **kwargs):
            return 1

    monkeypatch.setattr(base.subprocess, "Popen", Process)
    kwargs = {
        "case": case,
        "evidence": tmp_path / "evidence",
        "leg": "establish",
        "policy": "checked",
        "prompt": "Public task only",
        "store": tmp_path / "store",
        "native_from": None,
        "expected": {"approved": True},
        "budget": 0.75,
        "retain_behavioral_limits": True,
    }
    if subtype == "error_during_execution":
        with pytest.raises(RuntimeError, match="infrastructure/measurement"):
            base.run_leg(**kwargs)
    else:
        result, _ = base.run_leg(**kwargs)
        assert result["behavioral_limit"] is True
        assert result["is_error"] is True
        assert result["artifact"]["passed"] is False
        assert result["memory_evidence"]["evidence_unknown"] is False
        assert json.loads((tmp_path / "evidence/memory.json").read_text()) == {}


def test_historical_work_must_preserve_revised_current_agreement(tmp_path):
    task = build_lifecycles()[0]
    stage = task.stages[-1]
    before = {
        **task.task.decoys,
        task.key: json.dumps(task.revised_config),
        task.historical_key: json.dumps(task.initial_config),
    }
    result = {
        "artifact": {"passed": True},
        "memory_evidence": {"accepted_writes": 0},
        "bd_correct_payload_observed": True,
    }
    (tmp_path / "config.json").write_text(json.dumps(stage.expected_config))
    summary = driver.stage_summary(stage, task, result, before, before, True, [], [], tmp_path)
    assert summary["current_capture"]["passed"] is True
    # Receipt compliance remains a diagnostic; actual lifecycle correctness is separate.
    assert summary["public_completion_check"]["passed"] is False
    assert summary["complete_handoff"] is True
    changed = {**before, task.key: json.dumps(task.initial_config)}
    summary = driver.stage_summary(stage, task, result, before, changed, True, [], [], tmp_path)
    assert summary["complete_handoff"] is False
