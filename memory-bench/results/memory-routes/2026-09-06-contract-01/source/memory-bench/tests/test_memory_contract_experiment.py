"""Contract intervention preserves controls, paid attempts, and actual mistakes."""

from __future__ import annotations

import hashlib
import json
import sys

import pytest

from membench.runner.memory_e2e_corpus import build_e2e_case, initial_scaffold, stage_task
from scripts import memory_contract_experiment as driver


def proof_files(tmp_path, monkeypatch):
    old = tmp_path / "old.py"
    old.write_text("unchanged")
    source = {"old.py": hashlib.sha256(old.read_bytes()).hexdigest()}
    monkeypatch.setattr(driver.e2e.base, "REPO", tmp_path)
    monkeypatch.setattr(driver.e2e, "sources", lambda: {**source, "new.py": "newhash"})
    monkeypatch.setattr(driver.e2e, "binary_hashes", lambda: {"/binary": "hash"})
    (tmp_path / "new.py").write_text("new")
    smokes = {}
    for host in driver.e2e.MODELS:
        path = tmp_path / host
        path.mkdir()
        (path / "result.json").write_text(
            json.dumps({"admitted": True, "host": host, "execution": {"model_matches": True}})
        )
        (path / "source-sha256.json").write_text(json.dumps(source))
        (path / "binary-sha256.json").write_text(json.dumps({"/binary": "hash"}))
        smokes[host] = path
    offline = tmp_path / "offline.json"
    offline.write_text(
        json.dumps(
            {
                "schema": "memory-contract-check-static.v1",
                "public_test_sha256": driver.checker_digest(),
                "target_passed": 19,
                "target_rejected": 13,
                "all_target_results_match_prior_shape_verdict": True,
                "rows": [{"input_files_preserved": True} for _ in range(32)],
                "source_sha256": {},
            }
        )
    )
    return smokes, offline


def test_freeze_accepts_only_additions_to_smoke_inputs_and_records_matched_arms(
    tmp_path, monkeypatch
):
    smokes, offline = proof_files(tmp_path, monkeypatch)
    manifest = driver.freeze(tmp_path / "cohort", smokes, offline)
    assert manifest["planned_sessions"] == 32
    assert [(r["host"], r["condition"]) for r in manifest["cases"]] == [
        ("claude", "baseline"),
        ("claude", "checker"),
        ("codex", "checker"),
        ("codex", "baseline"),
    ]
    assert all(row["arm"] == "installed" for row in manifest["cases"])
    assert manifest["source_additions_since_smoke"] == ["new.py"]
    assert manifest["checker"]["source_sha256"] == driver.checker_digest()
    assert manifest["smoke_reuse"]["claude"]["input_hashes_unchanged"]
    assert (tmp_path / "cohort/source/old.py").read_text() == "unchanged"


def test_changed_prior_source_or_unverified_checker_blocks_before_output(tmp_path, monkeypatch):
    smokes, offline = proof_files(tmp_path, monkeypatch)
    monkeypatch.setattr(driver.e2e, "sources", lambda: {"old.py": "changed"})
    with pytest.raises(ValueError, match="smoke"):
        driver.freeze(tmp_path / "changed", smokes, offline)
    assert not (tmp_path / "changed").exists()
    monkeypatch.setattr(
        driver.e2e,
        "sources",
        lambda: json.loads((smokes["claude"] / "source-sha256.json").read_text()),
    )
    value = json.loads(offline.read_text())
    value["public_test_sha256"] = "wrong"
    offline.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="checker"):
        driver.freeze(tmp_path / "unverified", smokes, offline)
    assert not (tmp_path / "unverified").exists()


def test_checker_install_is_one_file_and_never_overwrites_agent_output(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    driver.install_checker(work, "baseline")
    assert list(work.iterdir()) == []
    driver.install_checker(work, "checker")
    path = work / driver.PUBLIC_TEST_PATH
    assert path.read_text() == driver.PUBLIC_TEST_SOURCE
    assert driver.checker_state(work)["canonical"]
    path.write_text("agent changed this test")
    before = driver.checker_state(work)
    assert before["exists"] and not before["canonical"]
    with pytest.raises(FileExistsError):
        driver.install_checker(work, "checker")
    assert path.read_text() == "agent changed this test"


def test_checker_state_does_not_read_through_agent_created_parent_symlink(tmp_path):
    work, outside = tmp_path / "work", tmp_path / "outside"
    work.mkdir()
    outside.mkdir()
    (outside / "test_component_contract.py").write_text(driver.PUBLIC_TEST_SOURCE)
    (work / "tests").symlink_to(outside, target_is_directory=True)
    state = driver.checker_state(work)
    assert state["exists"]
    assert state["resolved_within_workspace"] is False
    assert state["sha256"] is None
    assert state["canonical"] is False


def test_canonical_audit_ignores_agent_replaced_test_and_checks_prior_components(tmp_path):
    case = build_e2e_case()
    for name, source in initial_scaffold(case).items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    flat = case.v1_policy["cache"]
    correct = case.v2_policy
    (tmp_path / "catalog_cache.py").write_text(
        f"POLICY={flat!r}\nSOURCE='source'\nRATIONALE='rationale'\n"
        "def create_cache(clock): return None\n"
    )
    (tmp_path / "catalog_refresh_cache.py").write_text(
        f"POLICY={correct!r}\nSOURCE='source'\nRATIONALE='rationale'\n"
        "def create_cache(clock): return None\n"
    )
    path = tmp_path / driver.PUBLIC_TEST_PATH
    path.write_text("raise RuntimeError('agent test must never run in canonical audit')\n")
    before = path.read_bytes()
    result = driver.audit_checker(
        tmp_path, "catalog_refresh_cache.py", process_prefix=(), python_executable=sys.executable
    )
    assert not result["whole_workspace"]["passed"]
    assert result["component"]["passed"]
    assert "agent test must never run" not in result["stderr"]
    assert path.read_bytes() == before
    assert not list(tmp_path.rglob("__pycache__"))


def lifecycle_fakes(tmp_path, monkeypatch, mutate=False, interrupt=False, missing_direct=False):
    case = build_e2e_case()
    work, store, scratch = (tmp_path / x for x in ("work", "store", "scratch"))
    for path in (work, store, scratch):
        path.mkdir()
    (work / "tests").mkdir()
    (work / "preserved.txt").write_text("original data")
    calls = []
    actual_tasks = []
    ids = 0

    def setup(out, arm, corpus):
        out.mkdir(parents=True)
        assert arm == "installed"
        return {
            "workspace": str(work),
            "store": str(store),
            "scratch": str(scratch),
            "arm": arm,
            "env": {},
            "package": {"files": [], "symlinks": []},
        }

    def create(state, title, body):
        nonlocal ids
        ids += 1
        task = {"id": f"task-{ids}", "title": title, "description": body}
        actual_tasks.append(task)
        return task

    def run(evidence, state, host, task, leg, native):
        calls.append((leg, task, native, driver.checker_state(work)))
        evidence.mkdir()
        (evidence / "process.json").write_text('{"pid":1}')
        if interrupt and leg == "establish":
            raise RuntimeError("paid interrupted process")
        before = {"chosen-key": "actual mistake retained"}
        for name in ("memory-before.json", "memory-after.json"):
            (evidence / name).write_text(json.dumps(before))
        if mutate and leg == "establish":
            (work / driver.PUBLIC_TEST_PATH).write_text("agent replacement")
        if leg in {"establish", "revise"}:
            target = "direct" if leg == "establish" else "revised_direct"
            if not (missing_direct and target == "direct"):
                stage = next(s for s in case.stages if s.name == target)
                create(
                    state,
                    stage_task(case, stage)["title"],
                    "Actual authored body with bad reference",
                )
        local = scratch / leg
        local.mkdir()
        native_path = local / "native"
        native_path.mkdir()
        (native_path / "actual.txt").write_text(leg)
        return {
            "success": True,
            "model_matches": True,
            "scratch": str(local),
            "cost_usd": None,
            "arm": "installed",
            "task_id": task["id"],
            "memory_operations": {"executions": []},
        }, native_path

    monkeypatch.setattr(driver.e2e, "setup_case", setup)
    monkeypatch.setattr(driver.e2e, "create_task", create)
    monkeypatch.setattr(driver.e2e, "all_tasks", lambda store, env: actual_tasks)
    monkeypatch.setattr(driver.e2e, "run_session", run)
    monkeypatch.setattr(driver.e2e, "assess_feature", lambda *args: {"passed": False})
    monkeypatch.setattr(driver, "assert_frozen", lambda manifest: None)
    monkeypatch.setattr(
        driver, "assess_checker", lambda *args: {"whole_workspace": {"passed": False}}
    )
    return calls, work


def test_checker_mutation_is_retained_and_does_not_halt_or_change_installed_arm(
    tmp_path, monkeypatch
):
    calls, work = lifecycle_fakes(tmp_path, monkeypatch, mutate=True)
    row = {"id": "claude-checker", "host": "claude", "condition": "checker", "arm": "installed"}
    manifest = {"coverage": {"claude": {"admitted": True}}}
    driver.run_lifecycle(tmp_path / "cohort", row, manifest)
    result = json.loads((tmp_path / "cohort/cases/claude-checker/result.json").read_text())
    assert len(calls) == 8
    assert calls[1][3]["canonical"] is False
    assert calls[1][1]["description"] == "Actual authored body with bad reference"
    assert calls[1][2].name == "native"
    assert all(s["execution"]["arm"] == "installed" for s in result["stages"])
    assert result["condition"] == "checker"
    assert result["stages"][0]["checker_after"]["canonical"] is False
    assert (work / driver.PUBLIC_TEST_PATH).read_text() == "agent replacement"
    assert (work / "preserved.txt").read_text() == "original data"


def test_missing_authored_task_skips_only_dependent_stage_without_repair(tmp_path, monkeypatch):
    calls, _ = lifecycle_fakes(tmp_path, monkeypatch, missing_direct=True)
    row = {"id": "claude-baseline", "host": "claude", "condition": "baseline", "arm": "installed"}
    driver.run_lifecycle(tmp_path / "cohort", row, {"coverage": {"claude": {"admitted": True}}})
    result = json.loads((tmp_path / "cohort/cases/claude-baseline/result.json").read_text())
    assert [leg for leg, *_ in calls] == [
        s.name for s in build_e2e_case().stages if s.name != "direct"
    ]
    assert result["stages"][1]["status"] == "unrun"
    assert result["stages"][1]["reason"] == "author handoff missing"
    assert result["stages"][-1]["status"] == "completed"


def test_started_interruption_is_never_purchased_again(tmp_path, monkeypatch):
    calls, _ = lifecycle_fakes(tmp_path, monkeypatch, interrupt=True)
    row = {"id": "claude-baseline", "host": "claude", "condition": "baseline", "arm": "installed"}
    out = tmp_path / "cohort"
    manifest = {"coverage": {"claude": {"admitted": True}}}
    driver.run_lifecycle(out, row, manifest)
    result = json.loads((out / "cases/claude-baseline/result.json").read_text())
    assert len(calls) == 1
    assert result["stages"][0]["status"] == "interrupted"
    assert all(s["status"] == "unrun" for s in result["stages"][1:])
    with pytest.raises(FileExistsError):
        driver.run_lifecycle(out, row, manifest)
    assert len(calls) == 1


def test_report_counts_assessed_stage_even_without_lifecycle_result_and_never_overwrites(tmp_path):
    out = tmp_path / "cohort"
    evidence = out / "cases/claude-checker/establish"
    evidence.mkdir(parents=True)
    case = build_e2e_case()
    manifest = {
        "planned_sessions": 32,
        "stages": [stage.name for stage in case.stages],
        "cases": [
            {"host": host, "condition": condition, "id": f"{host}-{condition}", "arm": "installed"}
            for host in ("claude", "codex")
            for condition in driver.CONDITIONS
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest))
    assessment = {
        "leg": "establish",
        "status": "completed",
        "artifact": {"passed": False},
        "canonical_public_check": {
            "component": {"passed": False},
            "whole_workspace": {"passed": False},
        },
        "checker_before": {"canonical": True},
        "checker_after": {"canonical": False},
        "execution": {"cost_usd": 0.25},
    }
    (evidence / "assessment.json").write_text(json.dumps(assessment))
    direct = evidence.parent / "direct"
    direct.mkdir()
    (direct / "stdout.jsonl").write_text("partial output before process result")
    first = driver.report(out)
    assert first["planned"] == 32 and first["completed"] == 1
    assert len(first["stages"]) == 32
    assert first["known_cost_usd"] == 0.25
    interrupted = next(
        r for r in first["stages"] if r["id"] == "claude-checker" and r["leg"] == "direct"
    )
    assert interrupted["status"] == "interrupted"
    original = (out / "analysis-01.json").read_bytes()
    driver.report(out)
    assert (out / "analysis-01.json").read_bytes() == original
    assert (out / "analysis-02.json").exists()


def test_fire_preserves_recorded_cases_and_refuses_partial_paid_lifecycle(tmp_path, monkeypatch):
    out = tmp_path / "cohort"
    recorded = out / "cases/claude-baseline"
    partial = out / "cases/claude-checker"
    recorded.mkdir(parents=True)
    partial.mkdir()
    (recorded / "result.json").write_text('{"status":"finished"}')
    (partial / "process.json").write_text('{"pid":1}')
    manifest = {"cases": [{"id": "claude-baseline"}, {"id": "claude-checker"}]}
    (out / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(driver, "assert_frozen", lambda manifest: None)
    calls = []
    monkeypatch.setattr(driver, "run_lifecycle", lambda *args: calls.append(args))
    with pytest.raises(FileExistsError, match="Partial lifecycle"):
        driver.fire(out)
    assert calls == []
    assert (partial / "process.json").read_text() == '{"pid":1}'
