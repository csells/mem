"""Local artifact analysis preserves missing trials and task-cluster pairing."""

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from membench.runner.bd_experiment import _pair_dir
from membench.runner.resume_cache import digest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "analyze_bd_experiment.py"


def analyzer() -> Any:
    spec = importlib.util.spec_from_file_location("analyze_bd_experiment", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(root: Path, *, tasks: int = 2) -> dict[str, Any]:
    schedule = [
        {"condition": c, "work_id": str(t), "variant": v, "repeat": r}
        for t in range(tasks)
        for v in ("necessary", "unnecessary")
        for r in range(2)
        for c in ("generic", "explicit", "redirect")
    ]
    manifest = {
        "schedule": schedule,
        "conditions": {c: {} for c in ("generic", "explicit", "redirect")},
        "planned_pairs": len(schedule),
        "model": "fixture",
    }
    (root / "manifest.json").write_text(json.dumps(manifest))
    return manifest


def save_pair(
    root: Path,
    manifest: dict[str, Any],
    pair: dict[str, Any],
    *,
    success: bool,
    unknown: bool = False,
) -> None:
    directory = _pair_dir(root, pair)
    (directory / "legs").mkdir(parents=True)
    evidence = []
    for index, role in enumerate(("establish", "goal")):
        ev = {
            "role": role,
            "leg": index,
            "status": "ok",
            "bd_capture_complete": success,
            "bd_recall_complete": success,
            "bd_recall_before_action": success,
            "goal_action_success": success,
            "bd_evidence_unknown": unknown,
            "bd_read_attempts": 2,
            "bd_write_attempts": 1,
            "bd_accepted_writes": int(success),
            "native_read_attempts": 1,
            "native_write_attempts": 0,
        }
        evidence.append(ev)
        result = {
            "type": "result",
            "duration_ms": 1000,
            "total_cost_usd": 0.01,
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "cache_read_input_tokens": 2,
                "cache_creation_input_tokens": 3,
            },
        }
        leg = {
            **pair,
            "leg": index,
            "role": role,
            "status": "ok",
            "bd_evidence": ev,
            "hook_reaches": 1,
            "stream": json.dumps(result),
        }
        (directory / "legs" / f"{index}.json").write_text(json.dumps(leg))
    cell = {
        "pair": pair,
        "manifest_digest": digest(manifest),
        "cell": {"bd_evidence": evidence, "paid": True},
    }
    (directory / "cell.json").write_text(json.dumps(cell))


def test_missing_schedule_entries_stay_in_denominators(tmp_path: Path) -> None:
    manifest = fixture(tmp_path)
    save_pair(tmp_path, manifest, manifest["schedule"][0], success=True)
    report = analyzer().analyze(tmp_path, bootstrap_samples=100, seed=4)
    group = next(
        g for g in report["groups"] if g["condition"] == "generic" and g["variant"] == "necessary"
    )
    assert group["scheduled_pairs"] == 4
    assert group["completed_pairs"] == 1
    assert group["metrics"]["handoff"] == {
        "success": 1,
        "failure": 0,
        "unknown": 3,
        "scheduled": 4,
        "observed_rate": 1.0,
        "scheduled_rate_bounds": [0.25, 1.0],
    }
    assert group["costs"]["estimated_usd"]["sum"] == 0.02
    assert group["costs"]["estimated_usd"]["unknown_legs"] == 6


def test_receipt_uncertainty_does_not_become_a_negative(tmp_path: Path) -> None:
    manifest = fixture(tmp_path)
    pair = manifest["schedule"][0]
    save_pair(tmp_path, manifest, pair, success=False, unknown=True)
    row = analyzer().analyze(tmp_path, bootstrap_samples=30, seed=1)["pairs"][0]
    assert row["metrics"]["capture"] is None
    assert row["metrics"]["handoff"] is False
    assert row["metrics"]["goal_action_success"] is False


def test_unknown_capture_with_successful_goal_remains_unknown(tmp_path: Path) -> None:
    manifest = fixture(tmp_path)
    pair = manifest["schedule"][0]
    save_pair(tmp_path, manifest, pair, success=True)
    directory = _pair_dir(tmp_path, pair)
    leg_path = directory / "legs" / "0.json"
    leg = json.loads(leg_path.read_text())
    leg["bd_evidence"] = {
        **leg["bd_evidence"],
        "bd_capture_complete": False,
        "bd_evidence_unknown": True,
    }
    leg_path.write_text(json.dumps(leg))
    cell_path = directory / "cell.json"
    saved = json.loads(cell_path.read_text())
    saved["cell"]["bd_evidence"][0] = leg["bd_evidence"]
    cell_path.write_text(json.dumps(saved))
    row = analyzer().analyze(tmp_path, bootstrap_samples=30)["pairs"][0]
    assert row["metrics"]["goal_action_success"] is True
    assert row["metrics"]["capture"] is None
    assert row["metrics"]["handoff"] is None


def test_task_cluster_bootstrap_keeps_twin_repeat_dependence(tmp_path: Path) -> None:
    manifest = fixture(tmp_path)
    for pair in manifest["schedule"]:
        success = pair["condition"] != "generic" and pair["work_id"] == "0"
        save_pair(tmp_path, manifest, pair, success=success)
    report = analyzer().analyze(tmp_path, bootstrap_samples=1000, seed=5)
    contrast = next(
        c
        for c in report["contrasts"]
        if c["condition"] == "explicit" and c["variant"] == "all" and c["metric"] == "handoff"
    )
    assert contrast["task_clusters"] == 2
    assert contrast["matched_pairs"] == 8
    assert contrast["difference"] == 0.5
    assert contrast["bootstrap_95_interval"] == [0.0, 1.0]
    assert contrast["scheduled_difference_bounds"] == [0.5, 0.5]
    assert contrast["interpretation"] == "descriptive; few independent task clusters"
    assert report == analyzer().analyze(tmp_path, bootstrap_samples=1000, seed=5)


def test_identity_mismatch_refuses_analysis(tmp_path: Path) -> None:
    manifest = fixture(tmp_path)
    pair = manifest["schedule"][0]
    save_pair(tmp_path, manifest, pair, success=True)
    path = _pair_dir(tmp_path, pair) / "cell.json"
    row = json.loads(path.read_text())
    path.write_text(json.dumps({**row, "manifest_digest": "wrong"}))
    with pytest.raises(ValueError, match="identity"):
        analyzer().analyze(tmp_path)


def test_cli_writes_both_local_artifacts(tmp_path: Path) -> None:
    fixture(tmp_path)
    out = tmp_path / "analysis"
    assert analyzer().main([str(tmp_path), "--out", str(out), "--bootstrap-samples", "30"]) == 0
    assert json.loads((out / "analysis.json").read_text())["scheduled_pairs"] == 24
    assert "Unknown" in (out / "report.md").read_text()


def test_hook_reaches_are_cumulative_within_a_pair(tmp_path: Path) -> None:
    manifest = fixture(tmp_path)
    save_pair(tmp_path, manifest, manifest["schedule"][0], success=True)
    report = analyzer().analyze(tmp_path, bootstrap_samples=30)
    assert [leg["counters"]["hook_reaches"] for leg in report["pairs"][0]["legs"]] == [1, 0]


def test_partial_pair_preserves_observed_capture_and_unknown_goal(tmp_path: Path) -> None:
    manifest = fixture(tmp_path)
    pair = manifest["schedule"][0]
    save_pair(tmp_path, manifest, pair, success=True)
    directory = _pair_dir(tmp_path, pair)
    (directory / "cell.json").unlink()
    (directory / "legs" / "1.json").unlink()
    row = analyzer().analyze(tmp_path, bootstrap_samples=30)["pairs"][0]
    assert row["completed"] is False
    assert row["metrics"]["capture"] is True
    assert row["metrics"]["handoff"] is None
    assert row["metrics"]["goal_action_success"] is None


def test_missing_raw_leg_is_unknown_even_when_a_cell_exists(tmp_path: Path) -> None:
    manifest = fixture(tmp_path)
    pair = manifest["schedule"][0]
    save_pair(tmp_path, manifest, pair, success=True)
    (_pair_dir(tmp_path, pair) / "legs" / "1.json").unlink()
    row = analyzer().analyze(tmp_path, bootstrap_samples=30)["pairs"][0]
    assert row["completed"] is True
    assert row["recorded_legs"] == 1
    assert row["metrics"]["handoff"] is None


def test_final_cli_cost_snapshot_is_not_double_counted() -> None:
    mod = analyzer()
    costs = mod.leg_costs(
        {
            "stream": "\n".join(
                json.dumps({"type": "result", "total_cost_usd": cost}) for cost in (0.01, 0.02)
            )
        }
    )
    assert costs["estimated_usd"] == 0.02
    assert costs["duration_ms"] is None
    with pytest.raises(ValueError, match="numeric"):
        mod.leg_costs({"stream": json.dumps({"type": "result", "total_cost_usd": "free"})})


def test_unbalanced_schedule_is_not_an_unpaired_comparison(tmp_path: Path) -> None:
    manifest = fixture(tmp_path)
    manifest["schedule"] = manifest["schedule"][1:]
    manifest["planned_pairs"] -= 1
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="balanced"):
        analyzer().analyze(tmp_path)


def test_redirect_increment_is_paired_against_explicit(tmp_path: Path) -> None:
    manifest = fixture(tmp_path)
    for pair in manifest["schedule"]:
        success = pair["condition"] == "redirect" or (
            pair["condition"] == "explicit" and pair["work_id"] == "0"
        )
        save_pair(tmp_path, manifest, pair, success=success)
    mod = analyzer()
    report = mod.analyze(tmp_path, bootstrap_samples=1000, seed=5)
    for metric in ("handoff", "goal_action_success"):
        increment = next(
            c
            for c in report["contrasts"]
            if c["condition"] == "redirect"
            and c["baseline"] == "explicit"
            and c["variant"] == "all"
            and c["metric"] == metric
        )
        assert increment["difference"] == 0.5
        assert increment["matched_pairs"] == 8
        assert increment["task_clusters"] == 2
        assert increment["bootstrap_95_interval"] == [0.0, 1.0]
        assert increment["scheduled_difference_bounds"] == [0.5, 0.5]
    generic = next(
        c
        for c in report["contrasts"]
        if c["condition"] == "redirect"
        and c["baseline"] == "generic"
        and c["variant"] == "all"
        and c["metric"] == "handoff"
    )
    assert generic["difference"] == 1.0
    assert "redirect minus explicit" in mod.markdown(report)
    assert "redirect minus generic" in mod.markdown(report)
