"""Synthetic evidence fixtures exercise independent regrading, not model behavior."""

from __future__ import annotations

import base64
import json
import shlex
import shutil
import sys
import uuid
from pathlib import Path

import pytest

from membench.runner.headless_agent import assistant_event, tool_result_event
from membench.runner.memory_host_receipts import marker, score_correlated
from membench.runner.memory_lifecycle_corpus import build_lifecycles
from membench.runner.memory_routes_grade import grade_artifact
from scripts import memory_hosts_experiment as driver
from scripts.memory_hosts_report import analyze, main, markdown, requested_route


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2))


@pytest.fixture
def run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(driver.base, "BD", Path("/bin/sh").resolve())
    monkeypatch.setattr(driver.base, "PYTHON", Path(sys.executable).resolve())
    coverage = {
        host: {"runnable": False, "blocker": "not available for this fixture", "binary_paths": []}
        for host in driver.HOSTS
    }
    coverage["claude"] = {
        "runnable": True,
        "model": "claude-sonnet-4-6",
        "version": "fixture",
        "smoke": "synthetic fixture only",
        "binary_paths": [],
    }
    root = tmp_path / "run"
    manifest = driver.make_manifest(coverage, 20260908, 0.75, 240)
    write(root / "manifest.json", manifest)
    for name in manifest["source_sha256"]:
        destination = root / "source" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(driver.base.REPO / name, destination)
    return root


def fill(
    root: Path,
    *,
    mode: str = "isolated",
    count: int = 8,
    cost: float | None = 0.1,
    repeat_session: bool = False,
    rewrite_history: bool = False,
) -> Path:
    manifest = json.loads((root / "manifest.json").read_text())
    row = next(
        row for row in manifest["schedule"] if row["mode"] == mode and row["id"].endswith("cache")
    )
    task = next(task for task in build_lifecycles(manifest["seed"]) if task.id == row["task"])
    directory = root / "cases" / row["id"]
    directory.mkdir(parents=True)
    carried = dict(task.task.decoys)
    native: dict[str, str] = {}
    stages = []
    for stage in task.stages[:count]:
        evidence = directory / stage.name
        evidence.mkdir()
        for name in ("workspace", "native-before", "native", "host-evidence"):
            (evidence / name).mkdir()
        for name, text in native.items():
            (evidence / "native-before" / name).write_text(text)
        if mode == "normal":
            native["memory.md"] = "An actual fixture-native note; never seeded from an oracle."
        for name, text in native.items():
            (evidence / "native" / name).write_text(text)
        before = dict(carried)
        write(directory / f"transferred-{stage.name}.json", before)
        scratch = Path("/private/tmp/fixture-host") / row["id"] / stage.name
        session_id = "reused" if repeat_session else row["id"] + "-" + stage.name
        harness_id = uuid.uuid4().hex
        task_id = "trial-" + stage.name
        prompt = (
            driver.base.BASE
            + "\n"
            + driver.guidance(mode)
            + f"\nAssigned task: {task_id}\n\n"
            + stage.prompt
        )
        (evidence / "prompt.txt").write_text(prompt)
        events = [
            {
                "type": "system",
                "subtype": "init",
                "model": manifest["coverage"]["claude"]["model"],
                "session_id": session_id,
            }
        ]
        raw = []

        def bd(
            args: list[str],
            stdout: str,
            *,
            events=events,
            raw=raw,
            harness_id=harness_id,
            stage_name=stage.name,
            scratch=scratch,
        ) -> None:
            invocation = uuid.uuid4().hex
            call_id = f"tool-{len(events)}"
            identity = {
                "schema": "memory-host-receipt.v1",
                "invocation_id": invocation,
                "harness_session_id": harness_id,
                "leg_id": stage_name,
                "argv": [str(driver.base.BD), "-C", str(scratch / "store"), *args],
                "operation_argv": args,
                "start_monotonic_ns": len(events) * 10,
            }
            raw.extend(
                [
                    {**identity, "event": "start"},
                    {
                        **identity,
                        "event": "finish",
                        "returncode": 0,
                        "stdout": stdout,
                        "stderr": "",
                        "stdout_base64": base64.b64encode(stdout.encode()).decode(),
                        "stderr_base64": "",
                        "end_monotonic_ns": len(events) * 10 + 1,
                    },
                ]
            )
            events.append(
                assistant_event([("Bash", {"command": shlex.join(["bd", *args])}, call_id)])
            )
            events.append(tool_result_event(call_id, marker(invocation) + "\n" + stdout))

        def recall(key: str) -> None:
            bd(
                ["recall", key, "--json"],
                json.dumps({"found": True, "key": key, "value": carried[key], "schema_version": 1}),
            )

        def remember(key: str, body: str) -> None:
            action = "updated" if key in carried else "remembered"
            carried[key] = body
            bd(
                ["remember", body, "--key", key, "--json"],
                json.dumps({"action": action, "key": key, "value": body, "schema_version": 1}),
            )

        if stage.retrieval_required:
            if "search" in stage.name:
                bd(
                    ["memories", "cache", "--json"],
                    json.dumps(
                        {
                            "schema_version": 1,
                            task.key: carried[task.key],
                            task.historical_key: carried[task.historical_key],
                        }
                    ),
                )
            recall(task.historical_key if stage.name == "historical" else task.key)
        if stage.capture_required:
            body = "```json\n" + json.dumps(stage.expected_config) + "\n```"
            for key in stage.required_write_keys:
                remember(key, body)
                recall(key)
            if stage.name == "revise" and rewrite_history:
                remember(task.historical_key, carried[task.historical_key] + "\nUnapproved aside.")
        events.append(
            assistant_event(
                [
                    (
                        "Write",
                        {
                            "file_path": str(scratch / "work/config.json"),
                            "content": json.dumps(stage.expected_config),
                        },
                        "write-config",
                    )
                ]
            )
        )
        events.append(tool_result_event("write-config", "File created"))
        events.append(
            {
                "type": "result",
                "subtype": "success",
                "session_id": session_id,
                "is_error": False,
                "total_cost_usd": cost,
                "modelUsage": {"fixture": {"inputTokens": 10}},
            }
        )
        stream = "\n".join(json.dumps(event) for event in events) + "\n"
        (evidence / "stream.jsonl").write_text(stream)
        write(evidence / "workspace/config.json", stage.expected_config)
        observed = driver.observe_host("claude", stream, evidence / "host-evidence")
        score, mapping = score_correlated(
            raw,
            observed.calls,
            session_id,
            leg_id=stage.name,
            status="ok",
            expected_binary=str(driver.base.BD),
            expected_store=str(scratch / "store"),
        )
        assert not score.evidence_unknown
        result = {
            "leg": stage.name,
            "host": "claude",
            "policy": "selective-source-fidelity",
            "mode": mode,
            "model_requested": manifest["coverage"]["claude"]["model"],
            "models_observed": observed.models,
            "model_evidence": observed.model_evidence,
            "model_matches": True,
            "session_id": session_id,
            "harness_session_id": harness_id,
            "exit_code": 0,
            "completed": True,
            "is_error": False,
            "errors": observed.errors,
            "behavioral_limit": False,
            "timed_out": False,
            "cost_usd": cost,
            "model_usage": observed.usage,
            "duration_s": 1.0,
            "artifact": grade_artifact(evidence / "workspace/config.json", stage.expected_config),
            "memory_evidence": score.model_dump(mode="json"),
            "task_id": task_id,
            "scratch": str(scratch),
            "native_file_count": len(native),
            **driver.base.route_summary(
                score.model_dump(mode="json"),
                observed.calls,
                scratch / "work/config.json",
                stage.expected_config,
            ),
        }
        started = {
            "host": "claude",
            "model_requested": result["model_requested"],
            "mode": mode,
            "leg": stage.name,
            "scratch": str(scratch),
            "store": str(scratch / "store"),
            "harness_session_id": harness_id,
            "argv": ["fixture-claude", "-p", prompt],
            "public_settings": {},
            "timeout_s": 240,
        }
        for name, value in (
            ("started.json", started),
            ("result.json", result),
            ("raw-receipts.json", raw),
            ("receipts.json", mapping["derived_receipts"]),
            ("receipt-mapping.json", mapping),
            ("tool-calls.json", [call.model_dump(mode="json") for call in observed.calls]),
            ("memory.json", carried),
            ("task.json", [{"id": task_id, "status": "closed"}]),
        ):
            write(evidence / name, value)
        summary = driver.lifecycle.stage_summary(
            stage,
            task,
            result,
            before,
            carried,
            True,
            mapping["derived_receipts"],
            [],
            evidence / "workspace",
        )
        summary["historical_body_preserved"] = (
            before.get(task.historical_key) == carried.get(task.historical_key)
            if task.historical_key in before
            else None
        )
        assert summary["complete_handoff"]
        write(evidence / "assessment.json", summary)
        stages.append(summary)
    if count == 8:
        write(
            directory / "result.json",
            {
                **row,
                "stages": stages,
                "complete_lifecycle": True,
                "history_immutable": not rewrite_history,
                "literal_handoff_and_immutable_history": not rewrite_history,
            },
        )
    else:
        write(directory / "halt.json", {"type": "FixtureHalt", "message": "Incomplete fixture"})
    return directory


def test_pending_and_blocked_candidates_remain_visible(run: Path) -> None:
    result = analyze(run)
    assert result["planned_sessions"] == 24
    assert result["blocked_host_slots"] == 96
    assert len(result["coverage"]) == 5
    assert result["groups"]["claude/isolated"]["lifecycle"] == {
        "planned": 2,
        "true": 0,
        "false": 0,
        "unknown": 2,
    }
    assert result["groups"]["copilot/normal"]["runnable"] is False
    assert "Blocked:" in markdown(result)


def test_complete_case_is_independently_regraded_and_not_pooled_with_pending(run: Path) -> None:
    fill(run)
    result = analyze(run)
    group = result["groups"]["claude/isolated"]
    assert result["unique_sessions"] == 8
    assert group["lifecycle"]["true"] == group["lifecycle"]["unknown"] == 1
    assert group["recorded_sessions"] == 8 and group["planned_sessions"] == 16
    assert group["cost_known_sessions"] == 8 and group["cost_unknown_sessions"] == 8
    assert group["observed_execution_markers"] > group["accepted_writes"] > 0
    assert group["stages"]["supplied"]["no_writes_changes"]["true"] == 1
    assert group["stages"]["search"]["requested_route_demonstrated"]["true"] == 1
    assert group["stages"]["revised_search"]["search_before_correct_direct_lookup"]["true"] == 1
    assert "Requested route T/F/?" in markdown(result)


@pytest.mark.parametrize(
    "name",
    [
        "workspace/config.json",
        "memory.json",
        "raw-receipts.json",
        "tool-calls.json",
        "stream.jsonl",
        "started.json",
    ],
)
def test_tampered_payload_or_identity_is_rejected(run: Path, name: str) -> None:
    case = fill(run)
    path = case / "direct" / name
    if name == "stream.jsonl":
        path.write_text(path.read_text().replace("claude-sonnet-4-6", "other-model"))
    else:
        value = json.loads(path.read_text())
        if name == "workspace/config.json":
            value["cache"]["cache_misses"] = 1  # bool and integer must remain distinct
        elif name == "memory.json":
            value[next(key for key in value if key.endswith(".config"))] = "stale content"
        elif name == "raw-receipts.json":
            value[-1]["stdout"] = "fabricated output"
        elif name == "tool-calls.json":
            value[0]["tool_use_id"] = "fabricated-host-id"
        else:
            value["harness_session_id"] = "different-session"
        write(path, value)
    with pytest.raises(ValueError):
        analyze(run)


def test_native_transfer_is_compared_to_actual_prior_snapshot(run: Path) -> None:
    case = fill(run, mode="normal")
    assert analyze(run)["groups"]["claude/normal"]["lifecycle"]["true"] == 1
    (case / "direct/native-before/memory.md").write_text("replacement not actually carried")
    with pytest.raises(ValueError, match="native transfer"):
        analyze(run)


def test_duplicate_actual_sessions_are_rejected(run: Path) -> None:
    fill(run, repeat_session=True)
    with pytest.raises(ValueError, match="Fresh session identity reused"):
        analyze(run)


def test_unknown_cost_is_never_reported_as_zero_known_spend(run: Path) -> None:
    fill(run, cost=None)
    result = analyze(run)
    group = result["groups"]["claude/isolated"]
    assert group["cost_known_sessions"] == 0 and group["cost_unknown_sessions"] == 16
    assert "unknown (0/16)" in markdown(result)


def test_history_prose_change_is_separate_from_correct_json(run: Path) -> None:
    fill(run, rewrite_history=True)
    group = analyze(run)["groups"]["claude/isolated"]
    assert group["lifecycle"]["true"] == 1
    assert group["history_immutable"]["false"] == 1
    assert group["stages"]["revise"]["history_body_preserved"]["false"] == 1
    assert group["stages"]["historical"]["historical_capture"]["true"] == 1


def test_halted_case_retains_unexecuted_stages_as_unknown(run: Path) -> None:
    fill(run, count=2)
    group = analyze(run)["groups"]["claude/isolated"]
    assert group["status_counts"]["halted"] == 1
    assert group["recorded_sessions"] == 2
    assert group["stages"]["historical"]["artifact"]["unknown"] == 2


def test_partial_artifact_is_graded_without_claiming_complete_session(run: Path) -> None:
    manifest = json.loads((run / "manifest.json").read_text())
    row = next(row for row in manifest["schedule"] if row["id"] == "claude-isolated-cache")
    task = next(task for task in manifest["tasks"] if task["id"] == row["task"])
    write(run / "cases" / row["id"] / "establish/workspace/config.json", task["initial_config"])
    result = analyze(run)
    stage = next(case for case in result["cases"] if case["id"] == row["id"])["stages"][0]
    assert stage["artifact"] is True
    assert stage["recorded"] is False
    assert stage["objective_handoff"] is None


def test_frozen_source_tampering_is_rejected(run: Path) -> None:
    path = run / "source/memory-bench/membench/runner/memory_routes_grade.py"
    path.write_text(path.read_text() + "\n# tampered fixture\n")
    with pytest.raises(ValueError, match="Frozen source hash differs"):
        analyze(run)


def test_cli_preserves_existing_output_directory(run: Path, tmp_path: Path) -> None:
    out = tmp_path / "analysis"
    assert main(["--run", str(run), "--out", str(out)]) == 0
    original = (out / "analysis.json").read_bytes()
    with pytest.raises(FileExistsError):
        main(["--run", str(run), "--out", str(out)])
    assert (out / "analysis.json").read_bytes() == original


def operation(
    verb: str,
    *,
    body: str = '{"count":7}',
    use: int | None = 1,
    result: int | None = 2,
    tool: str = "tool",
) -> dict:
    return {
        "argv": [verb, "key-or-query", "--json"],
        "content": [body],
        "is_read": True,
        "output_observed": True,
        "returncode": 0,
        "tool_use_index": use,
        "tool_result_index": result,
        "tool_use_id": tool,
    }


@pytest.mark.parametrize("stage", ["search", "revised_search"])
def test_full_recall_without_search_does_not_demonstrate_search_route(stage: str) -> None:
    route = requested_route(stage, [operation("recall")], {"count": 7}, False)
    assert route["full_direct_payload_observed"] is True
    assert route["requested_route_demonstrated"] is False


def test_search_payload_without_full_recall_is_not_direct_lookup() -> None:
    route = requested_route("search", [operation("memories")], {"count": 7}, False)
    assert route["full_direct_payload_observed"] is False
    assert route["search_and_correct_direct_lookup"] is False


@pytest.mark.parametrize(
    "search,direct,expected",
    [
        (operation("memories", tool="search"), operation("recall", use=3, result=4), True),
        (operation("memories", use=3, result=4, tool="search"), operation("recall"), False),
        (operation("memories"), operation("recall"), None),
        (operation("memories", result=None, tool="search"), operation("recall", use=3), None),
        (
            operation("memories", tool="search"),
            operation("recall", body='{"count":8}', use=3),
            False,
        ),
    ],
)
def test_search_to_full_recall_order_is_explicit(
    search: dict, direct: dict, expected: bool | None
) -> None:
    route = requested_route("search", [search, direct], {"count": 7}, False)
    assert route["requested_route_demonstrated"] is expected


def test_direct_route_requires_exact_full_payload_and_preserves_unknowns() -> None:
    assert (
        requested_route("direct", [operation("recall")], {"count": 7}, False)[
            "requested_route_demonstrated"
        ]
        is True
    )
    assert (
        requested_route("direct", [operation("recall", body='{"count":"7"}')], {"count": 7}, False)[
            "requested_route_demonstrated"
        ]
        is False
    )
    assert requested_route("direct", [], {"count": 7}, True)["requested_route_demonstrated"] is None
