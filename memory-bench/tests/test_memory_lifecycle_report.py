from __future__ import annotations

import base64
import copy
import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from membench.runner import memory_lifecycle_gate, memory_routes_grade
from membench.runner.memory_lifecycle_corpus import build_lifecycles
from scripts import memory_lifecycle_report as report


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def frozen_run(tmp_path):
    root = tmp_path / "run"
    task = dataclasses.asdict(build_lifecycles()[0])
    pins = {}
    for module in (memory_routes_grade, memory_lifecycle_gate):
        source = Path(module.__file__)
        name = "memory-bench/membench/runner/" + source.name
        target = root / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        pins[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = {
        "schema": "memory-lifecycle.v1",
        "model": "test-model",
        "tasks": [task],
        "schedule": [{"task": task["id"], "policy": arm} for arm in report.POLICIES],
        "planned_sessions": 24,
        "source_sha256": pins,
        "policies": dict.fromkeys(report.POLICIES, "Common guidance"),
    }
    save(root / "manifest.json", manifest)
    return root, task


def test_unstarted_lifecycles_remain_in_every_planned_denominator(tmp_path):
    root, _ = frozen_run(tmp_path)
    result = report.analyze(root)
    assert result["planned_lifecycles"] == 3
    for arm in result["policies"].values():
        assert arm["planned_lifecycles"] == 1
        assert arm["resources"]["planned_sessions"] == 8
        assert arm["whole_lifecycle"] == {"planned": 1, "true": 0, "false": 0, "unknown": 1}
        assert arm["stages"]["historical"]["artifact"] == {
            "planned": 1,
            "true": 0,
            "false": 0,
            "unknown": 1,
        }
        assert arm["resources"]["cost_unknown_sessions"] == 8


def stage_fixture(
    root,
    task,
    name,
    before,
    *,
    policy="existing",
    wrong=False,
    duplicate=False,
    search_only=False,
    cap=False,
):
    definition = next(stage for stage in task["stages"] if stage["name"] == name)
    directory = root / "cases" / f"{task['id']}-{policy}"
    save(directory / "started.json", {"task": task["id"], "policy": policy, "scratch": "/scratch"})
    local = directory / name
    actual = copy.deepcopy(definition["expected_config"])
    if wrong:
        actual["cache"]["max_entries"] += 1
    after = dict(before)
    body = json.dumps(actual)
    if name == "establish":
        after[task["key"]] = body
        after[task["historical_key"]] = body
    elif name == "revise":
        after[task["key"]] = body
    local.mkdir(parents=True, exist_ok=True)
    save(local / "workspace/config.json", actual)
    save(directory / f"transferred-{name}.json", before)
    save(local / "memory.json", after)
    session_id = f"session-{policy}-{name}"
    receipts, operations = [], []

    def operation(verb, key, value):
        index = len(operations) * 3 + 1
        args = (
            [verb, value, "--key", key, "--json"]
            if verb == "remember"
            else [
                verb,
                "catalog" if verb == "memories" else key,
                "--json",
            ]
        )
        payload = (
            {"action": "remembered", "key": key}
            if verb == "remember"
            else (
                {"schema_version": 1, key: value}
                if verb == "memories"
                else {"key": key, "found": True, "value": value}
            )
        )
        output = json.dumps(payload)
        start = {
            "event": "start",
            "invocation_id": f"inv-{index}",
            "tool_use_id": f"call-{index}",
            "session_id": session_id,
            "leg_id": name,
            "operation_argv": args,
            "argv": ["/bin/bd", "-C", "/store", *args],
            "start_monotonic_ns": index,
        }
        finish = {
            **start,
            "event": "finish",
            "end_monotonic_ns": index + 1,
            "returncode": 0,
            "stdout": output,
            "stderr": "",
            "stdout_base64": base64.b64encode(output.encode()).decode(),
            "stderr_base64": "",
        }
        receipts.extend([start, finish])
        operations.append(
            {
                "invocation_id": start["invocation_id"],
                "tool_use_id": start["tool_use_id"],
                "session_id": session_id,
                "argv": args,
                "stdout": output,
                "stderr": "",
                "returncode": 0,
                "is_read": verb != "remember",
                "is_write": verb == "remember",
                "accepted_write": verb == "remember",
                "output_observed": True,
                "content": [value],
            }
        )

    if definition["retrieval_required"]:
        key = task["historical_key"] if name == "historical" else task["key"]
        value = before.get(key, "{}")
        if name in {"search", "revised_search"}:
            operation("memories", key, value)
        if not search_only or name not in {"search", "revised_search"}:
            operation("recall", key, value)
    for key in definition["required_write_keys"]:
        operation("remember", key, after[key])
        operation("recall", key, after[key])
    if duplicate:
        operation("remember", task["key"], after[task["key"]])
    reads = [op for op in operations if op["is_read"]]

    def payload_match(items):
        grades = [
            memory_routes_grade.grade_capture({"k": value}, "k", definition["expected_config"])[
                "passed"
            ]
            for op in items
            for value in op["content"]
        ]
        return True if True in grades else None if None in grades else False

    direct = [op for op in reads if "recall" in op["argv"]]
    searches = [op for op in reads if "memories" in op["argv"]]
    terminal = {
        "type": "result",
        "session_id": session_id,
        "subtype": "error_max_budget_usd" if cap else "success",
        "is_error": cap,
        "total_cost_usd": 0.125,
        "num_turns": 2,
        "duration_ms": 1900,
        "modelUsage": {"test-model": {"inputTokens": 20, "outputTokens": 10, "costUSD": 0.125}},
    }
    stream = [
        {"type": "system", "subtype": "init", "model": "test-model", "session_id": session_id},
        terminal,
    ]
    (local / "stream.jsonl").write_text("\n".join(json.dumps(event) for event in stream) + "\n")
    prompt = "Common guidance\nAssigned task: task-1\n\n" + definition["prompt"]
    (local / "prompt.txt").write_text(prompt)
    save(
        local / "started.json",
        {
            "leg": name,
            "policy": policy,
            "scratch": "/scratch/" + name,
            "argv": ["claude", "-p", prompt, "--model", "test-model"],
        },
    )
    save(local / "task.json", [{"id": "task-1", "status": "closed"}])
    artifact = memory_routes_grade.grade_artifact(
        local / "workspace/config.json", definition["expected_config"]
    )
    raw = {
        "leg": name,
        "policy": policy,
        "scratch": "/scratch/" + name,
        "session_id": session_id,
        "task_id": "task-1",
        "cost_usd": 0.125,
        "duration_s": 2.0,
        "terminal_subtype": terminal["subtype"],
        "is_error": cap,
        "turns": 2,
        "model_usage": terminal["modelUsage"],
        "exit_code": 0,
        "behavioral_limit": cap,
        "artifact": artifact,
        "memory_evidence": {
            "accepted_writes": sum(op["accepted_write"] for op in operations),
            "evidence_unknown": False,
            "operations": operations,
        },
        "bd_direct_lookup": bool(direct),
        "bd_search": bool(searches),
        "bd_correct_payload_observed": payload_match(reads),
        "bd_correct_payload_via_direct": payload_match(direct),
        "bd_correct_payload_via_search": payload_match(searches),
        "bd_read_before_first_config_write": definition["retrieval_required"],
        "bd_correct_payload_before_first_config_write": definition["retrieval_required"]
        and name != "revise"
        and payload_match(reads),
    }
    save(local / "result.json", raw)
    save(local / "receipts.json", receipts)
    current_expected = (
        task["initial_config"]
        if name in ("establish", "direct", "search")
        else task["revised_config"]
    )
    current = memory_routes_grade.grade_capture(after, task["key"], current_expected)
    history = memory_routes_grade.grade_capture(
        after, task["historical_key"], task["initial_config"]
    )
    delta = {
        "added": sorted(after.keys() - before.keys()),
        "removed": sorted(before.keys() - after.keys()),
        "changed": sorted(key for key in before.keys() & after.keys() if before[key] != after[key]),
    }
    no_curation = not any(delta.values()) and raw["memory_evidence"]["accepted_writes"] == 0
    shadow = memory_lifecycle_gate.evaluate_gate(
        local / "workspace/config.json",
        after,
        receipts,
        definition["required_write_keys"],
        definition["retrieval_required"],
        name != "revise",
    )
    success = bool(
        artifact["passed"]
        and current["passed"]
        and history["passed"]
        and (definition["capture_required"] or no_curation)
        and not cap
    )
    summary = {
        "name": name,
        "artifact": artifact,
        "task_closed": True,
        "current_capture": current,
        "historical_capture": history,
        "delta": delta,
        "extra_keys": [],
        "no_unnecessary_curation": no_curation,
        "public_completion_check": shadow,
        "complete_handoff": success,
        "gate_events": [],
        "result": raw,
        "enforced_completion": False if policy == "checked" else None,
    }
    save(local / "assessment.json", summary)
    return after, summary


def complete_fixture(root, task, *, duplicate_supplied=False, search_only=False):
    state = task["task"]["decoys"]
    summaries = []
    for name in report.STAGES:
        state, summary = stage_fixture(
            root,
            task,
            name,
            state,
            duplicate=duplicate_supplied and name == "supplied",
            search_only=search_only,
        )
        summaries.append(summary)
    save(
        root / "cases" / f"{task['id']}-existing" / "result.json",
        {
            "task": task["id"],
            "policy": "existing",
            "stages": summaries,
            "complete_lifecycle": all(summary["complete_handoff"] for summary in summaries),
        },
    )


def test_full_cumulative_lifecycle_objective_does_not_require_procedural_shadow_pass(tmp_path):
    root, task = frozen_run(tmp_path)
    complete_fixture(root, task, search_only=True)
    result = report.analyze(root)["policies"]["existing"]
    assert result["whole_lifecycle"] == {"planned": 1, "true": 1, "false": 0, "unknown": 0}
    assert result["stages"]["search"]["procedural_shadow_check"]["false"] == 1
    assert result["stages"]["search"]["objective_handoff"]["true"] == 1
    assert result["stages"]["historical"]["current_capture"]["true"] == 1
    assert result["resources"]["estimated_cost_usd_observed"] == 1.0
    assert result["resources"]["duration_median_s"] == 2.0
    assert result["resources"]["model_usage_observed"]["test-model"] == {
        "inputTokens": 160,
        "outputTokens": 80,
        "costUSD": 1.0,
    }


def test_wrong_but_internally_consistent_state_can_pass_gate_and_fail_actual_contract(tmp_path):
    root, task = frozen_run(tmp_path)
    stage_fixture(root, task, "establish", task["task"]["decoys"], wrong=True)
    stage = report.analyze(root)["cases"][0]["stages"][0]
    assert stage["procedural_shadow_check"] is True
    assert stage["artifact"] is False
    assert stage["current_capture"] is False
    assert stage["objective_handoff"] is False


def test_same_body_rewrite_fails_no_curation_even_with_empty_delta_and_no_extra_keys(tmp_path):
    root, task = frozen_run(tmp_path)
    complete_fixture(root, task, duplicate_supplied=True)
    result = report.analyze(root)
    supplied = result["cases"][0]["stages"][6]
    assert supplied["delta"] == {"added": [], "removed": [], "changed": []}
    assert supplied["extra_keys"] == []
    assert supplied["accepted_writes"] == 1
    assert supplied["no_unnecessary_curation"] is False
    assert supplied["bd_read_before_first_config_write"] is False
    assert supplied["objective_handoff"] is False
    assert result["policies"]["existing"]["whole_lifecycle"]["false"] == 1


def test_transfer_is_compared_to_actual_previous_snapshot(tmp_path):
    root, task = frozen_run(tmp_path)
    complete_fixture(root, task)
    path = root / "cases" / f"{task['id']}-existing" / "transferred-direct.json"
    value = json.loads(path.read_text())
    value[task["key"]] = "a different transfer"
    save(path, value)
    with pytest.raises(ValueError, match="cumulative memory transfer"):
        report.analyze(root)


def test_crossmatching_fabricated_scores_cannot_overrule_actual_artifact(tmp_path):
    root, task = frozen_run(tmp_path)
    _, summary = stage_fixture(root, task, "establish", task["task"]["decoys"], wrong=True)
    path = root / "cases" / f"{task['id']}-existing" / "establish"
    forged = {"passed": True, "reason": "exact_match"}
    summary["artifact"] = forged
    summary["result"]["artifact"] = forged
    save(path / "result.json", summary["result"])
    save(path / "assessment.json", summary)
    with pytest.raises(ValueError, match="independently regraded artifact"):
        report.analyze(root)


def test_terminal_cost_is_counted_without_a_saved_result_or_assessment(tmp_path):
    root, task = frozen_run(tmp_path)
    local = root / "cases" / f"{task['id']}-existing" / "establish"
    local.mkdir(parents=True)
    events = [
        {"type": "system", "subtype": "init", "model": "test-model", "session_id": "interrupted"},
        {
            "type": "result",
            "session_id": "interrupted",
            "total_cost_usd": 0.25,
            "duration_ms": 7000,
        },
    ]
    (local / "stream.jsonl").write_text("\n".join(json.dumps(event) for event in events))
    result = report.analyze(root)["policies"]["existing"]
    assert result["resources"]["estimated_cost_usd_observed"] == 0.25
    assert result["resources"]["cost_known_sessions"] == 1
    assert result["resources"]["cost_unknown_sessions"] == 7
    assert result["resources"]["duration_median_s"] == 7.0
    assert result["stages"]["establish"]["artifact"]["unknown"] == 1


def test_behavioral_limit_is_failure_with_known_usage_and_preserved_snapshot(tmp_path):
    root, task = frozen_run(tmp_path)
    stage_fixture(root, task, "establish", task["task"]["decoys"], policy="checked", cap=True)
    stage = report.analyze(root)["cases"][2]["stages"][0]
    assert stage["artifact"] is True
    assert stage["current_capture"] is True
    assert stage["behavioral_limit"] is True
    assert stage["objective_handoff"] is False
    assert stage["enforced_completion"] is False
    assert stage["enforcement"]["infrastructure_errors"] == 0
    assert stage["cost_usd"] == 0.125


def test_terminal_summary_mismatch_refuses_even_if_assessment_agrees(tmp_path):
    root, task = frozen_run(tmp_path)
    _, summary = stage_fixture(root, task, "establish", task["task"]["decoys"])
    path = root / "cases" / f"{task['id']}-existing" / "establish"
    summary["result"]["cost_usd"] = 999
    save(path / "result.json", summary["result"])
    save(path / "assessment.json", summary)
    with pytest.raises(ValueError, match="terminal cost_usd"):
        report.analyze(root)


def test_cli_writes_exclusive_outputs_and_preserves_all_run_bytes(tmp_path):
    root, _ = frozen_run(tmp_path)
    before = {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }
    out = tmp_path / "report"
    assert report.main(["--run", str(root), "--out", str(out)]) == 0
    assert (out / "analysis.json").is_file()
    rendered = (out / "report.md").read_text()
    assert "procedural" in rendered
    assert "| No writes/changes T/F/? |" in rendered
    assert "No redundant curation" not in rendered
    assert "writes are required during establishment and permanent revision." in rendered
    after = {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }
    assert before == after
    with pytest.raises(ValueError, match="new directory"):
        report.main(["--run", str(root), "--out", str(out)])
    with pytest.raises(ValueError, match="outside"):
        report.main(["--run", str(root), "--out", str(root / "report")])


def test_procedural_shadow_pass_does_not_hide_forged_objective_summary(tmp_path):
    root, task = frozen_run(tmp_path)
    _, summary = stage_fixture(root, task, "establish", task["task"]["decoys"], wrong=True)
    path = root / "cases" / f"{task['id']}-existing" / "establish" / "assessment.json"
    summary["complete_handoff"] = True
    save(path, summary)
    with pytest.raises(ValueError, match="objective handoff endpoint"):
        report.analyze(root)


def test_duplicate_json_fields_are_rejected(tmp_path):
    root, _ = frozen_run(tmp_path)
    manifest = root / "manifest.json"
    original = manifest.read_text()
    manifest.write_text('{"schema":"discarded",' + original[1:])
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        report.analyze(root)


def test_malformed_artifact_is_a_task_failure_when_honestly_recorded(tmp_path):
    root, task = frozen_run(tmp_path)
    _, summary = stage_fixture(root, task, "establish", task["task"]["decoys"])
    path = root / "cases" / f"{task['id']}-existing" / "establish"
    (path / "workspace/config.json").write_text('{"broken":')
    failure = {"passed": False, "reason": "malformed_json", "path": "$"}
    summary["artifact"] = failure
    summary["result"]["artifact"] = failure
    summary["public_completion_check"] = {"passed": False, "reasons": ["invalid_artifact"]}
    summary["complete_handoff"] = False
    save(path / "result.json", summary["result"])
    save(path / "assessment.json", summary)
    result = report.analyze(root)["cases"][0]["stages"][0]
    assert result["artifact"] is False
    assert result["objective_handoff"] is False


def test_gate_blocks_and_administrative_queries_are_separate_from_agent_operations(tmp_path):
    root, task = frozen_run(tmp_path)
    _, summary = stage_fixture(root, task, "establish", task["task"]["decoys"], policy="checked")
    path = root / "cases" / f"{task['id']}-checked" / "establish"
    events = [
        {
            "event": "close",
            "passed": False,
            "reasons": ["missing_readback"],
            "duration_s": 0.2,
            "administrative_bd_queries": 1,
        },
        {
            "event": "close",
            "passed": True,
            "reasons": [],
            "duration_s": 0.1,
            "administrative_bd_queries": 1,
        },
        {
            "event": "stop",
            "passed": True,
            "reasons": [],
            "duration_s": 0.3,
            "administrative_bd_queries": 2,
        },
    ]
    (path / "gate-events.jsonl").write_text("\n".join(json.dumps(event) for event in events))
    summary["gate_events"] = events
    summary["enforced_completion"] = True
    save(path / "assessment.json", summary)
    result = report.analyze(root)["policies"]["checked"]
    assert result["intervened_sessions"] == 1
    assert result["enforcement"]["administrative_queries_observed"] == 4
    assert result["enforcement"]["close_checks"] == 2
    assert result["enforcement"]["stop_checks"] == 1
    assert result["enforcement"]["blocked_close"] == 1
    assert result["enforcement"]["duration_s_observed"] == pytest.approx(0.6)
    assert result["stages"]["establish"]["accepted_writes_observed"] == 2


def test_source_pin_mismatch_refuses_grading_drift(tmp_path):
    root, _ = frozen_run(tmp_path)
    path = root / "source/memory-bench/membench/runner/memory_routes_grade.py"
    path.write_text(path.read_text() + "\n# changed snapshot\n")
    with pytest.raises(ValueError, match="Frozen source hash"):
        report.analyze(root)


def test_evidence_symlink_cannot_read_outside_run(tmp_path):
    root, _ = frozen_run(tmp_path)
    snapshot = root / "manifest.json"
    outside = tmp_path / "outside.json"
    outside.write_bytes(snapshot.read_bytes())
    # Only this test's own freshly created fixture is replaced.
    snapshot.rename(root / "preserved-manifest.json")
    snapshot.symlink_to(outside)
    with pytest.raises(ValueError, match=r"Escaping|Symlink"):
        report.analyze(root)
