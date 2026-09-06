"""Scheduled denominators and receipt-only component analysis."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from membench.runner.bd_component_experiment import execute, freeze, reconcile_timeout
from tests.test_bd_component_experiment import fake_runner, manifest

SPEC = importlib.util.spec_from_file_location(
    "analyze_bd_component", Path(__file__).parents[1] / "scripts/analyze_bd_component.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def runner(status="completed", unknown=False):
    def run(row, config, out):
        value = fake_runner([], status)(row, config, out)
        memory = dict.fromkeys(MODULE.COUNTS, 0)
        memory.update(accepted_writes=1, executed_writes=1, evidence_unknown=unknown)
        agent = {**value["agent"], "memory": memory, "total_cost_usd": 0.25}
        value = {
            **value,
            "agent": agent,
            "initial_memory": {"seed": "harness knowledge"},
            "task_check": {"status": "pending_offline_grading"},
        }
        for name, body in [
            ("component-result.json", value),
            ("leg-0/result.json", agent),
            ("initial-memory.json", value["initial_memory"]),
        ]:
            (out / name).write_text(json.dumps(body))
        return value

    return run


def setup(tmp_path, status="completed", unknown=False):
    m = manifest(tmp_path)
    out = tmp_path / "run"
    freeze(out, m)
    execute(
        out, m, session_runner=runner(status, unknown), identity_check=lambda: None, max_sessions=1
    )
    return out, m


def test_planned_denominator_and_seed_does_not_count(tmp_path):
    out, _ = setup(tmp_path)
    report = MODULE.analyze(out)
    assert report["planned_sessions"] == 8
    assert len(report["rows"]) == 8
    assert report["session_status_counts"] == {"completed": 1, "missing": 7}
    assert report["memory_totals"]["accepted_writes"] == {"observed_total": 1, "known_rows": 1}
    assert report["rows"][1]["memory"]["accepted_writes"] is None
    assert report["rows"][1]["memory"]["evidence_unknown"] is True
    assert report["cost_known_sessions"] == 1 and report["observed_cost_usd"] == 0.25
    assert report["cost_unknown_sessions"] == 7
    assert report["rows"][0]["task_check_status"] == "pending_offline_grading"


def test_timeout_keeps_positive_operations_and_review_status(tmp_path):
    out, m = setup(tmp_path, "terminal_timeout", True)
    first = MODULE.analyze(out)["rows"][0]
    assert first["session_status"] == "terminal_timeout"
    assert first["memory"]["accepted_writes"] == 1
    assert first["memory"]["evidence_unknown"] is True
    reconcile_timeout(out, m, m["schedule"][0]["row_id"], reviewer="reviewer", reason="retained")
    assert MODULE.analyze(out)["rows"][0]["session_status"] == "reconciled_timeout"


def test_tampered_raw_refused(tmp_path):
    out, m = setup(tmp_path)
    (out / "sessions" / m["schedule"][0]["row_id"] / "run/leg-0/raw.stream.jsonl").write_text(
        "tamper"
    )
    with pytest.raises(ValueError, match="changed"):
        MODULE.analyze(out)


def test_missing_metric_unknown_not_zero(tmp_path):
    m = manifest(tmp_path)
    out = tmp_path / "run"
    freeze(out, m)
    execute(out, m, session_runner=fake_runner([]), identity_check=lambda: None, max_sessions=1)
    row = MODULE.analyze(out)["rows"][0]
    assert row["memory"]["observed_content_reads"] is None
    assert row["memory"]["evidence_unknown"] is True
    assert row["total_cost_usd"] is None


def test_cli_writes_json(tmp_path):
    out, _ = setup(tmp_path)
    target = tmp_path / "analysis.json"
    assert MODULE.main(["--run", str(out), "--out-json", str(target)]) == 0
    assert json.loads(target.read_text())["planned_sessions"] == 8


def test_partial_start_refuses_unaudited_summary(tmp_path):
    m = manifest(tmp_path)
    out = tmp_path / "run"
    freeze(out, m)
    partial = out / "sessions" / m["schedule"][-1]["row_id"]
    partial.mkdir(parents=True)
    (partial / "started.json").write_text("{}")
    with pytest.raises(ValueError):
        MODULE.analyze(out)


@pytest.mark.parametrize(
    "field,value",
    [("accepted_writes", -1), ("executed_reads", True), ("evidence_unknown", "false")],
)
def test_malformed_metrics_are_not_silently_counted(field, value):
    with pytest.raises(ValueError):
        MODULE._memory({"memory": {field: value}})


def test_cli_refuses_writing_inside_run(tmp_path):
    out, _ = setup(tmp_path)
    with pytest.raises(ValueError, match="outside"):
        MODULE.main(["--run", str(out), "--out-json", str(out / "analysis.json")])


def test_invalid_cost_refused(tmp_path):
    m = manifest(tmp_path)
    out = tmp_path / "run"
    freeze(out, m)

    def bad(row, config, path):
        value = runner()(row, config, path)
        value["agent"]["total_cost_usd"] = -1
        (path / "component-result.json").write_text(json.dumps(value))
        (path / "leg-0/result.json").write_text(json.dumps(value["agent"]))
        return value

    execute(out, m, session_runner=bad, identity_check=lambda: None, max_sessions=1)
    with pytest.raises(ValueError, match="cost"):
        MODULE.analyze(out)
