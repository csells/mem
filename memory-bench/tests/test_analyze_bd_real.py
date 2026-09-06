from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from membench.runner.bd_real_experiment import _directory, _evidence_inventory
from membench.runner.bd_real_metrics import score_real_leg
from membench.runner.resume_cache import digest

SPEC = importlib.util.spec_from_file_location(
    "analyze_bd_real", Path(__file__).parents[1] / "scripts/analyze_bd_real.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def experiment(tmp_path):
    manifest = {
        "schema": "bd-real-experiment.v1",
        "planned_pairs": 2,
        "planned_sessions": 4,
        "schedule": [
            {"task_id": "task", "variant": "briefed", "condition": arm}
            for arm in ["current", "focused"]
        ],
    }
    save(tmp_path / "manifest.json", manifest)
    return tmp_path, manifest


def add_pair(root, manifest, *, complete=True, count=1):
    pair = manifest["schedule"][0]
    directory = _directory(root, pair)
    save(directory / "started.json", {"pair": pair, "manifest_digest": digest(manifest)})
    memory = score_real_leg([], [], leg_id="leg", status="ok").model_dump(mode="json")
    records = []
    for leg in range(2 if complete else 1):
        evidence = {
            **memory,
            "accepted_writes": count,
            "observed_content_reads": count,
            "executed_writes": count,
            "executed_reads": count,
            "observed_reads": count,
            "evidence_unknown": not complete,
        }
        record = {
            "leg": leg,
            "status": "ok" if complete else "timeout",
            "memory": evidence,
            "total_cost_usd": 0.1,
            "duration_s": 2,
            "integrity_errors": [],
        }
        records.append(record)
        base = directory / f"run/leg-{leg}"
        save(base / "result.json", record)
        for name in ["raw.stream.jsonl", "receipts.json", "argv.json", "process.json"]:
            save(base / name, {})
    if complete:
        result = {**pair, "legs": records, "task_check": {"passed": False}}
        save(directory / "run/result.json", result)
        save(directory / "run/task_check.json", result["task_check"])
        (directory / "run/goal-candidate.tar").write_bytes(b"archive")
        save(
            directory / "cell.json",
            {
                "pair": pair,
                "manifest_digest": digest(manifest),
                "result": result,
                "artifact_sha256": _evidence_inventory(directory, result),
            },
        )
    return directory


def test_full_schedule_and_separate_task_success(experiment):
    root, manifest = experiment
    add_pair(root, manifest)
    result = MODULE.analyze(root)
    assert len(result["pairs"]) == 2
    first, missing = result["pairs"]
    assert first["establish_write"] is True
    assert first["goal_content_read"] is True
    assert first["task_check_passed"] is False
    assert missing["establish_write"] is None
    assert result["groups"][0]["scheduled_pairs"] == 1


def test_partial_positive_retained_zero_unknown(experiment):
    root, manifest = experiment
    add_pair(root, manifest, complete=False)
    row = MODULE.analyze(root)["pairs"][0]
    assert row["establish_write"] is True
    assert row["goal_content_read"] is None
    assert row["evidence_unknown"]
    assert row["observed_cost_usd"] == 0.1


def test_partial_zero_unknown(experiment):
    root, manifest = experiment
    add_pair(root, manifest, complete=False, count=0)
    assert MODULE.analyze(root)["pairs"][0]["establish_write"] is None


def test_corrupt_completed_artifact(experiment):
    root, manifest = experiment
    directory = add_pair(root, manifest)
    (directory / "run/leg-0/receipts.json").write_text("changed")
    with pytest.raises(ValueError):
        MODULE.analyze(root)


def test_partial_identity_mismatch(experiment):
    root, manifest = experiment
    directory = add_pair(root, manifest, complete=False)
    save(directory / "started.json", {"pair": {}, "manifest_digest": "bad"})
    with pytest.raises(ValueError):
        MODULE.analyze(root)


def test_duplicate_schedule_rejected(experiment):
    root, manifest = experiment
    save(root / "manifest.json", {**manifest, "schedule": [manifest["schedule"][0]] * 2})
    with pytest.raises(ValueError):
        MODULE.analyze(root)


def test_report_outputs(experiment, tmp_path):
    root, _ = experiment
    MODULE.write_analysis(root, tmp_path / "report")
    assert (tmp_path / "report/analysis.json").is_file()
    assert "redundant" in (tmp_path / "report/report.md").read_text()


@pytest.mark.parametrize("field,value", [("accepted_writes", -1), ("observed_reads", "2")])
def test_invalid_counts_rejected(experiment, field, value):
    root, manifest = experiment
    directory = add_pair(root, manifest, complete=False)
    path = directory / "run/leg-0/result.json"
    record = json.loads(path.read_text())
    record["memory"][field] = value
    save(path, record)
    with pytest.raises(ValueError):
        MODULE.analyze(root)


def test_identity_fault_does_not_credit_experimental_endpoint(experiment):
    root, manifest = experiment
    directory = add_pair(root, manifest, complete=False)
    path = directory / "run/leg-0/result.json"
    record = json.loads(path.read_text())
    record["integrity_errors"] = ["unexpected_model"]
    save(path, record)
    row = MODULE.analyze(root)["pairs"][0]
    assert row["establish_write"] is None
    assert row["legs"][0]["accepted_writes"] == 1


@pytest.mark.parametrize("field,value", [("condition", "other"), ("variant", "other")])
def test_unknown_schedule_labels(experiment, field, value):
    root, manifest = experiment
    manifest["schedule"][0][field] = value
    save(root / "manifest.json", manifest)
    with pytest.raises(ValueError):
        MODULE.analyze(root)


def test_missing_matched_condition_rejected(experiment):
    root, manifest = experiment
    manifest["schedule"] = manifest["schedule"][:1]
    manifest["planned_pairs"] = 1
    manifest["planned_sessions"] = 2
    save(root / "manifest.json", manifest)
    with pytest.raises(ValueError):
        MODULE.analyze(root)


def test_report_uses_actual_cluster_count(experiment, tmp_path):
    root, _ = experiment
    MODULE.write_analysis(root, tmp_path / "report")
    assert "1 task cluster" in (tmp_path / "report/report.md").read_text()


def test_invalid_condition_does_not_credit_task_check(experiment):
    root, manifest = experiment
    directory = add_pair(root, manifest, complete=False)
    path = directory / "run/leg-0/result.json"
    record = json.loads(path.read_text())
    record["integrity_errors"] = ["unexpected_model"]
    save(path, record)
    save(directory / "run/task_check.json", {"passed": True})
    row = MODULE.analyze(root)["pairs"][0]
    assert row["task_check_passed"] is None
    assert row["recorded_task_check_passed"] is True
