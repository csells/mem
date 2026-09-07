"""Independently regrade the frozen multi-host handoffs without invoking a model."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import shlex
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from statistics import median
from typing import Any

from membench.runner.memory_host_receipts import score_correlated
from membench.runner.memory_lifecycle_corpus import build_lifecycles
from membench.runner.memory_routes_grade import grade_artifact, grade_capture
from membench.runner.tool_surface import memory_invocations_in_command
from scripts import memory_hosts_experiment as driver
from scripts import memory_routes_experiment as base
from scripts.memory_lifecycle_report import Evidence, _all, _counts, _number, _object, _same

STAGES = (
    "establish",
    "direct",
    "search",
    "revise",
    "revised_direct",
    "revised_search",
    "supplied",
    "historical",
)
ROUTES = (
    "bd_direct_lookup",
    "bd_search",
    "bd_correct_payload_observed",
    "bd_correct_payload_before_first_config_write",
)
ROUTE_JOINT = (
    "full_direct_payload_observed",
    "requested_route_demonstrated",
    "search_and_correct_direct_lookup",
    "search_before_correct_direct_lookup",
)
SEARCH_STAGES = {"search", "revised_search"}
DIRECT_STAGES = {"direct", "revised_direct", "historical"}


def requested_route(
    stage: str, operations: list[dict[str, Any]], expected: dict[str, Any], unknown: bool
) -> dict[str, bool | None]:
    """Keep requested-route evidence separate from the actual artifact endpoint.

    Search occurrence plus correct full recall is not a claim that search caused
    the selection. Ordering requires delivery of search before issuing recall;
    two commands inside one host call do not establish that model-visible order.
    """
    searches = []
    correct_direct = []
    grades = []
    for op in operations:
        if not op["is_read"] or not op["output_observed"] or op["returncode"] != 0:
            continue
        invocations = memory_invocations_in_command(shlex.join(["bd", *op["argv"]]))
        if len(invocations) != 1:
            continue
        invocation = invocations[0]
        if invocation.verb == "memories" and invocation.operands:
            searches.append(op)
        if invocation.verb == "recall":
            payload_grades = [
                grade_capture({"body": body}, "body", expected)["passed"] for body in op["content"]
            ]
            grades.extend(payload_grades)
            if True in payload_grades:
                correct_direct.append(op)
    full_direct = True if True in grades else None if None in grades or unknown else False
    search = True if searches else None if unknown else False
    joint = _all([search, full_direct])
    order: bool | None = joint
    if joint is True:
        pairs = [
            (
                search_op["tool_result_index"] < direct_op["tool_use_index"]
                if search_op["tool_result_index"] is not None
                and direct_op["tool_use_index"] is not None
                and search_op["tool_use_id"] != direct_op["tool_use_id"]
                else None
            )
            for search_op in searches
            for direct_op in correct_direct
        ]
        order = True if True in pairs else None if None in pairs else False
    return {
        "full_direct_payload_observed": full_direct,
        "requested_route_demonstrated": (
            _all([joint, order])
            if stage in SEARCH_STAGES
            else full_direct if stage in DIRECT_STAGES else None
        ),
        "search_and_correct_direct_lookup": joint if stage in SEARCH_STAGES else None,
        "search_before_correct_direct_lookup": order if stage in SEARCH_STAGES else None,
    }


def _files(evidence: Evidence, relative: Path, *, required: bool = True) -> dict[str, str] | None:
    root = evidence.path(relative)
    if not root.exists():
        if required:
            raise ValueError(f"Missing native snapshot: {relative}")
        return None
    if not root.is_dir():
        raise ValueError("Native snapshot must be a directory")
    files = {}
    for path in sorted(root.rglob("*")):
        evidence.path(path.relative_to(evidence.root))
        if path.is_file():
            files[str(path.relative_to(root))] = hashlib.sha256(
                evidence.raw(path.relative_to(evidence.root))
            ).hexdigest()
    return files


def _manifest(evidence: Evidence) -> dict[str, Any]:
    manifest = _object(evidence.load("manifest.json"), "manifest")
    if manifest.get("schema") != "memory-hosts.v1":
        raise ValueError("Unsupported host experiment schema")
    pins = _object(manifest.get("source_sha256"), "source pins")
    if not pins:
        raise ValueError("Frozen source inventory required")
    for name, digest in pins.items():
        if hashlib.sha256(evidence.raw(Path("source") / name)).hexdigest() != digest:
            raise ValueError(f"Frozen source hash differs: {name}")
        current = base.REPO / name
        if not current.is_file() or hashlib.sha256(current.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Current analysis dependency differs from frozen source: {name}")
    required = {
        "memory-bench/scripts/memory_hosts_experiment.py",
        "memory-bench/scripts/memory_lifecycle_report.py",
        "memory-bench/membench/runner/memory_host_receipts.py",
        "memory-bench/membench/runner/memory_lifecycle_corpus.py",
        "memory-bench/membench/runner/memory_routes_grade.py",
        "memory-bench/membench/runner/bd_real_metrics.py",
    }
    if not required <= pins.keys():
        raise ValueError("Required analysis dependencies lack frozen pins")
    coverage = _object(manifest.get("coverage"), "host coverage")
    if set(coverage) != set(driver.HOSTS):
        raise ValueError("Coverage must retain all five candidate hosts")
    for host, entry in coverage.items():
        entry = _object(entry, "host coverage entry")
        if type(entry.get("runnable")) is not bool:
            raise ValueError("Host runnable state must be explicit")
        if entry["runnable"] and not all(entry.get(key) for key in ("model", "version", "smoke")):
            raise ValueError("Runnable host lacks verified identity")
        if not entry["runnable"] and not entry.get("blocker"):
            raise ValueError("Blocked host lacks its reason")
        if entry["runnable"]:
            module = driver.adapter(host)
            name = str(Path(module.__file__).resolve().relative_to(base.REPO))
            if name not in pins:
                raise ValueError("Active host normalizer lacks a source pin")
    tasks = json.loads(
        json.dumps(
            [
                dataclasses.asdict(task)
                for task in build_lifecycles(manifest["seed"])
                if task.domain in driver.DOMAINS
            ]
        )
    )
    _same(manifest.get("tasks"), tasks, "frozen task corpus")
    planned = [
        {"id": f"{host}-{mode}-{task['domain']}", "host": host, "mode": mode, "task": task["id"]}
        for host in driver.HOSTS
        if coverage[host]["runnable"]
        for mode in driver.MODES
        for task in tasks
        if mode == "isolated" or task["domain"] == "cache"
    ]
    schedule = manifest.get("schedule")
    if not isinstance(schedule, list):
        raise ValueError("Frozen schedule required")
    _same(
        sorted(schedule, key=lambda row: row["id"]),
        sorted(planned, key=lambda row: row["id"]),
        "host schedule",
    )
    _same(manifest.get("planned_sessions"), len(planned) * 8, "planned session denominator")
    _same(manifest.get("intended_max_sessions"), 120, "candidate denominator")
    _same(manifest.get("blocked_host_slots"), 120 - len(planned) * 8, "blocked denominator")
    return manifest


def _stage(
    evidence: Evidence,
    row: dict[str, Any],
    definition: dict[str, Any],
    task: dict[str, Any],
    manifest: dict[str, Any],
    before_expected: dict[str, str] | None,
    native_expected: dict[str, str] | None,
) -> tuple[dict[str, Any], dict[str, str] | None, dict[str, str] | None]:
    stage = definition["name"]
    case = Path("cases") / row["id"]
    directory = case / stage
    raw = evidence.optional(directory / "result.json")
    before = evidence.snapshot(case / f"transferred-{stage}.json")
    after = evidence.snapshot(directory / "memory.json")
    if before is not None:
        if before_expected is None:
            raise ValueError("Memory transfer skips a missing predecessor")
        _same(before, before_expected, "actual cumulative memory transfer")
    empty = {
        "name": stage,
        "recorded": raw is not None,
        **dict.fromkeys(
            (
                "artifact",
                "current_capture",
                "historical_capture",
                "history_body_preserved",
                "no_extra_keys",
                "no_writes_changes",
                "task_closed",
                "objective_handoff",
                "session_id",
                "harness_session_id",
                "cost_usd",
                "duration_s",
                "native_files",
                "accepted_writes",
                "observed_reads",
                "observed_markers",
                "model_matches",
                "measurement_unknown",
                *ROUTES,
                *ROUTE_JOINT,
            )
        ),
        "models_observed": [],
        "model_usage": {},
    }
    if raw is None:
        if evidence.optional(directory / "assessment.json") is not None:
            raise ValueError("Assessment exists without session result")
        artifact_path = directory / "workspace/config.json"
        if evidence.path(artifact_path).is_file():
            evidence.raw(artifact_path)
            empty["artifact"] = grade_artifact(
                evidence.path(artifact_path), definition["expected_config"]
            )["passed"]
        if after is not None:
            empty["current_capture"] = grade_capture(
                after,
                task["key"],
                task["initial_config"] if stage in STAGES[:3] else task["revised_config"],
            )["passed"]
            empty["historical_capture"] = grade_capture(
                after, task["historical_key"], task["initial_config"]
            )["passed"]
        if evidence.path(directory / "stream.jsonl").is_file():
            if evidence.path(directory / "host-evidence").exists():
                _files(evidence, directory / "host-evidence")
            observed = driver.observe_host(
                row["host"],
                evidence.raw(directory / "stream.jsonl").decode(),
                evidence.path(directory / "host-evidence"),
            )
            empty.update(
                session_id=observed.session_id,
                models_observed=observed.models,
                cost_usd=_number(observed.cost_usd),
                model_usage=observed.usage,
            )
        return empty, after, _files(evidence, directory / "native", required=False)
    raw = _object(raw, "session result")
    if before is None or after is None:
        raise ValueError("Recorded session lacks memory snapshots")
    started = _object(evidence.load(directory / "started.json"), "session start")
    for field, expected in (
        ("host", row["host"]),
        ("mode", row["mode"]),
        ("leg", stage),
        ("model_requested", manifest["coverage"][row["host"]]["model"]),
    ):
        _same(started.get(field), expected, f"start {field}")
        _same(raw.get(field), expected, f"result {field}")
    for field in ("scratch", "harness_session_id"):
        _same(raw.get(field), started.get(field), f"session {field}")
    if not isinstance(raw.get("harness_session_id"), str) or not raw["harness_session_id"].strip():
        raise ValueError("Missing harness session identity")
    prompt = evidence.raw(directory / "prompt.txt").decode()
    expected_prompt = (
        manifest["guidance"][row["mode"]]
        + f"\nAssigned task: {raw['task_id']}\n\n"
        + definition["prompt"]
    )
    _same(prompt.split(), expected_prompt.split(), "actual frozen guidance and task")
    argv = started.get("argv")
    if not isinstance(argv, list) or argv.count(prompt) != 1:
        raise ValueError("Invocation does not carry its exact prompt")
    native_before = _files(evidence, directory / "native-before")
    _same(
        native_before, native_expected if row["mode"] == "normal" else {}, "actual native transfer"
    )
    native_after = _files(evidence, directory / "native")
    assert native_after is not None
    _same(raw.get("native_file_count"), len(native_after), "native file count")
    model_dir = directory / "host-evidence"
    if evidence.path(model_dir).exists():
        _files(evidence, model_dir)
    observed = driver.observe_host(
        row["host"], evidence.raw(directory / "stream.jsonl").decode(), evidence.path(model_dir)
    )
    for field, actual in (
        ("session_id", observed.session_id),
        ("models_observed", observed.models),
        ("model_evidence", observed.model_evidence),
        ("completed", observed.completed),
        ("is_error", not observed.success),
        ("errors", observed.errors),
        ("cost_usd", observed.cost_usd),
        ("model_usage", observed.usage),
    ):
        _same(raw.get(field), actual, f"actual host {field}")
    _same(
        evidence.load(directory / "tool-calls.json"),
        [call.model_dump(mode="json") for call in observed.calls],
        "normalized real host calls",
    )
    receipts = evidence.load(directory / "raw-receipts.json")
    if not isinstance(receipts, list) or not all(isinstance(receipt, dict) for receipt in receipts):
        raise ValueError("Malformed raw receipts")
    if any(
        receipt.get("harness_session_id") != started["harness_session_id"]
        or receipt.get("leg_id") != stage
        for receipt in receipts
    ):
        raise ValueError("Raw execution belongs to another harness session")
    scored, mapping = score_correlated(
        receipts,
        observed.calls,
        observed.session_id or "",
        leg_id=stage,
        status="ok" if observed.completed else "error",
        expected_binary=str(base.BD),
        expected_store=started["store"],
    )
    _same(raw.get("memory_evidence"), scored.model_dump(mode="json"), "recomputed receipt evidence")
    _same(evidence.load(directory / "receipt-mapping.json"), mapping, "receipt correlation")
    _same(
        evidence.load(directory / "receipts.json"), mapping["derived_receipts"], "derived receipts"
    )
    routes = base.route_summary(
        scored.model_dump(mode="json"),
        observed.calls,
        Path(started["scratch"]) / "work/config.json",
        definition["expected_config"],
    )
    for field, actual in routes.items():
        _same(raw.get(field), actual, f"recomputed route {field}")
    artifact_path = directory / "workspace/config.json"
    if evidence.path(artifact_path).is_file():
        evidence.raw(artifact_path)
    artifact = grade_artifact(evidence.path(artifact_path), definition["expected_config"])
    _same(raw.get("artifact"), artifact, "actual configuration artifact")
    current = grade_capture(
        after,
        task["key"],
        task["initial_config"] if stage in STAGES[:3] else task["revised_config"],
    )
    historical = grade_capture(after, task["historical_key"], task["initial_config"])
    task_data = evidence.load(directory / "task.json")
    if (
        not isinstance(task_data, list)
        or len(task_data) != 1
        or task_data[0].get("id") != raw["task_id"]
    ):
        raise ValueError("Assigned task snapshot identity differs")
    closed = task_data[0].get("status") == "closed"
    no_extra = not (
        after.keys() - (task["task"]["decoys"].keys() | {task["key"], task["historical_key"]})
    )
    no_writes = before == after and scored.accepted_writes == 0
    history_preserved = (
        before[task["historical_key"]] == after.get(task["historical_key"])
        if task["historical_key"] in before
        else None
    )
    matches = observed.models == [raw["model_requested"]] if observed.models else None
    _same(raw.get("model_matches"), matches is True, "resolved model identity")
    behavioral = raw.get("timed_out") is True or any(
        error in {"error_max_turns", "error_max_budget_usd"} for error in observed.errors
    )
    _same(raw.get("behavioral_limit"), behavioral, "behavioral limit")
    if type(raw.get("exit_code")) is not int or type(raw.get("timed_out")) is not bool:
        raise ValueError("Missing process exit status")
    objective = _all(
        [
            artifact["passed"],
            closed,
            current["passed"],
            historical["passed"],
            no_extra,
            True if definition["capture_required"] else no_writes,
            (
                routes["bd_correct_payload_observed"]
                if definition["retrieval_required"] and stage != "revise"
                else True
            ),
            not behavioral,
            observed.success,
            matches,
            None if scored.evidence_unknown else True,
            raw["exit_code"] == 0,
        ]
    )
    assessment = evidence.optional(directory / "assessment.json")
    if assessment is not None:
        for field, actual in (
            ("result", raw),
            ("artifact", artifact),
            ("task_closed", closed),
            ("current_capture", current),
            ("historical_capture", historical),
            ("historical_body_preserved", history_preserved),
            ("no_unnecessary_curation", no_writes),
            ("complete_handoff", objective is True),
        ):
            _same(assessment.get(field), actual, f"assessment {field}")
    return (
        {
            **empty,
            "artifact": artifact["passed"],
            "current_capture": current["passed"],
            "historical_capture": historical["passed"],
            "history_body_preserved": history_preserved,
            "no_extra_keys": no_extra,
            "no_writes_changes": no_writes,
            "task_closed": closed,
            "objective_handoff": objective,
            "session_id": observed.session_id,
            "harness_session_id": raw["harness_session_id"],
            "cost_usd": _number(observed.cost_usd),
            "duration_s": _number(raw.get("duration_s")),
            "native_files": len(native_after),
            "native_before_sha256": native_before,
            "native_after_sha256": native_after,
            "accepted_writes": scored.accepted_writes,
            "observed_reads": scored.observed_reads,
            "observed_markers": len(mapping["associations"]),
            "models_observed": observed.models,
            "model_matches": matches,
            "model_usage": observed.usage,
            "measurement_unknown": scored.evidence_unknown,
            "unknown_reasons": list(scored.unknown_reasons),
            **{
                field: None if scored.evidence_unknown and routes[field] is False else routes[field]
                for field in ROUTES
            },
            **requested_route(
                stage,
                scored.model_dump(mode="json")["operations"],
                definition["expected_config"],
                scored.evidence_unknown,
            ),
        },
        after,
        native_after,
    )


def _group(cases: list[dict[str, Any]]) -> dict[str, Any]:
    stages = [stage for case in cases for stage in case["stages"]]
    costs = [stage["cost_usd"] for stage in stages if stage["cost_usd"] is not None]
    durations = [stage["duration_s"] for stage in stages if stage["duration_s"] is not None]
    metrics = (
        "artifact",
        "current_capture",
        "historical_capture",
        "history_body_preserved",
        "no_extra_keys",
        "no_writes_changes",
        "objective_handoff",
        *ROUTES,
        *ROUTE_JOINT,
    )
    return {
        "planned_lifecycles": len(cases),
        "recorded_sessions": sum(stage["recorded"] for stage in stages),
        "planned_sessions": len(stages),
        "status_counts": dict(Counter(case["status"] for case in cases)),
        "lifecycle": _counts([case["objective_lifecycle"] for case in cases]),
        "history_immutable": _counts([case["history_immutable"] for case in cases]),
        "literal_handoff_and_immutable_history": _counts(
            [_all([case["objective_lifecycle"], case["history_immutable"]]) for case in cases]
        ),
        "cost_usd_observed": sum(costs),
        "cost_known_sessions": len(costs),
        "cost_unknown_sessions": len(stages) - len(costs),
        "duration_median_s": median(durations) if durations else None,
        "duration_known_sessions": len(durations),
        "accepted_writes": sum(stage["accepted_writes"] or 0 for stage in stages),
        "observed_reads": sum(stage["observed_reads"] or 0 for stage in stages),
        "observed_execution_markers": sum(stage["observed_markers"] or 0 for stage in stages),
        "guard_queries": 0,
        "memory_count_known_sessions": sum(
            stage["measurement_unknown"] is False for stage in stages
        ),
        "models_observed": sorted(
            {model for stage in stages for model in stage["models_observed"]}
        ),
        "stages": {
            name: {
                metric: _counts([stage[metric] for stage in stages if stage["name"] == name])
                for metric in metrics
            }
            for name in STAGES
        },
    }


def analyze(run: Path) -> dict[str, Any]:
    evidence = Evidence(run)
    manifest = _manifest(evidence)
    tasks = {task["id"]: task for task in manifest["tasks"]}
    cases = []
    for row in manifest["schedule"]:
        directory = Path("cases") / row["id"]
        task = tasks[row["task"]]
        before = task["task"]["decoys"]
        native: dict[str, str] | None = {}
        stages = []
        for definition in task["stages"]:
            stage, before, native = _stage(
                evidence, row, definition, task, manifest, before, native
            )
            stages.append(stage)
        objective = _all([stage["objective_handoff"] for stage in stages])
        history = _all([stage["history_body_preserved"] for stage in stages[1:]])
        saved = evidence.optional(directory / "result.json")
        if saved is not None:
            for field, value in row.items():
                _same(saved.get(field), value, f"completed case {field}")
            _same(saved.get("complete_lifecycle"), objective is True, "whole lifecycle")
            _same(
                saved.get("history_immutable"),
                all(stage["history_body_preserved"] is not False for stage in stages),
                "saved absence of historical body rewrites",
            )
            _same(
                saved.get("literal_handoff_and_immutable_history"),
                _all([objective, history]) is True,
                "combined literal handoff and historical preservation",
            )
            _same(
                saved.get("stages"),
                [evidence.load(directory / name / "assessment.json") for name in STAGES],
                "case/stage assessments",
            )
        halt = evidence.optional(directory / "halt.json")
        status = (
            "complete"
            if saved is not None
            else (
                "halted"
                if halt is not None
                else "running" if evidence.path(directory).exists() else "pending"
            )
        )
        cases.append(
            {
                **row,
                "status": status,
                "halt": halt,
                "objective_lifecycle": objective,
                "history_immutable": history,
                "stages": stages,
            }
        )
    sessions = [
        (case["host"], stage["session_id"])
        for case in cases
        for stage in case["stages"]
        if stage["session_id"] is not None
    ]
    harness_ids = [
        stage["harness_session_id"]
        for case in cases
        for stage in case["stages"]
        if stage["harness_session_id"] is not None
    ]
    if len(set(sessions)) != len(sessions) or len(set(harness_ids)) != len(harness_ids):
        raise ValueError("Fresh session identity reused")
    groups = {
        f"{host}/{mode}": {
            "host": host,
            "mode": mode,
            "model_requested": manifest["coverage"][host].get("model"),
            "runnable": manifest["coverage"][host]["runnable"],
            "blocker": manifest["coverage"][host].get("blocker"),
            **_group([case for case in cases if case["host"] == host and case["mode"] == mode]),
        }
        for host in driver.HOSTS
        for mode in driver.MODES
    }
    evidence.verify()
    return {
        "schema": "memory-hosts-analysis.v1",
        "run": str(evidence.root),
        "coverage": manifest["coverage"],
        "planned_sessions": manifest["planned_sessions"],
        "intended_max_sessions": manifest["intended_max_sessions"],
        "blocked_host_slots": manifest["blocked_host_slots"],
        "unique_sessions": len(sessions),
        "groups": groups,
        "cases": cases,
        "input_sha256": evidence.inventory,
        "limits": [
            "Synthetic legacy KV lifecycles; eight stages share captured state and are correlated.",
            "Host and model vary together; this is not a controlled comparison "
            "of host-only effects.",
            "Normal retains the installed native-memory default in isolated state, "
            "not the operator's personal history.",
            "An installed native-memory default can be off in both conditions; "
            "saved native files alone do not prove their delivery to the model.",
            "Context windows and effective budgets differ across installed hosts; "
            "common prompts do not establish equal retained context or token budgets.",
            "Literal JSON scores do not certify surrounding prose or source attribution.",
            "Execution markers add instrumented stderr; they establish attribution, "
            "not model attention.",
            "No completion guards run in this extension; zero guard queries is a design property.",
            "Reported CLI costs are usage estimates; unknown costs are not zero "
            "or additional billed charges.",
            "The previous experiments are separate and are not pooled here.",
        ],
    }


def markdown(analysis: dict[str, Any]) -> str:
    lines = [
        "# Memory handoffs across CLI hosts",
        "",
        f"Observed {analysis['unique_sessions']} unique host sessions; "
        f"{analysis['planned_sessions']} scheduled and {analysis['blocked_host_slots']} "
        f"blocked candidate slots out of {analysis['intended_max_sessions']}.",
        "",
        "Lifecycle counts are true/false/unknown. Eight stages share one capture; "
        "blocked hosts are retained in coverage, not silently dropped.",
        "",
        "| Host / native mode | Actual model(s) | Lifecycles T/F/? | Sessions recorded/planned "
        "| Estimated cost (known/planned) | Median seconds | Writes / reads | History rewrites |",
        "| --- | --- | --- | ---: | --- | ---: | ---: | ---: |",
    ]
    for key, group in analysis["groups"].items():
        if not group["runnable"]:
            lines.append(
                f"| {key} | Blocked: {str(group['blocker']).replace('|', '/')} "
                "| — | 0/0 | unknown | — | — | — |"
            )
            continue
        count = group["lifecycle"]
        lifecycle = f"{count['true']}/{count['false']}/{count['unknown']}"
        rewrites = sum(row["history_body_preserved"]["false"] for row in group["stages"].values())
        models = ", ".join(group["models_observed"]) or "unobserved"
        duration = (
            f"{group['duration_median_s']:.2f}"
            if group["duration_median_s"] is not None
            else "unknown"
        )
        cost = (
            f"${group['cost_usd_observed']:.4f} "
            f"({group['cost_known_sessions']}/{group['planned_sessions']})"
            if group["cost_known_sessions"]
            else f"unknown (0/{group['planned_sessions']})"
        )
        lines.append(
            f"| {key} | {models} | {lifecycle} | "
            f"{group['recorded_sessions']}/{group['planned_sessions']} | {cost} | {duration} | "
            f"{group['accepted_writes']} / {group['observed_reads']} | {rewrites} |"
        )
    lines.extend(
        [
            "",
            "## Stage outcomes",
            "",
            "| Host / mode / stage | Exact artifact T/F/? | Current capture T/F/? "
            "| History capture T/F/? | Full direct payload T/F/? | No writes/changes T/F/? "
            "| Requested route T/F/? | Search → recall order T/F/? |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for key, group in analysis["groups"].items():
        if not group["runnable"]:
            continue
        for name, metrics in group["stages"].items():
            values = [
                metrics[metric]
                for metric in (
                    "artifact",
                    "current_capture",
                    "historical_capture",
                    "full_direct_payload_observed",
                    "no_writes_changes",
                )
            ]
            counts = " | ".join(f"{v['true']}/{v['false']}/{v['unknown']}" for v in values)
            extra = []
            for metric, applies in (
                ("requested_route_demonstrated", name in SEARCH_STAGES | DIRECT_STAGES),
                ("search_before_correct_direct_lookup", name in SEARCH_STAGES),
            ):
                v = metrics[metric]
                extra.append(f"{v['true']}/{v['false']}/{v['unknown']}" if applies else "—")
            lines.append(f"| {key}/{name} | {counts} | {' | '.join(extra)} |")
    markers = sum(group["observed_execution_markers"] for group in analysis["groups"].values())
    lines.extend(
        [
            "",
            f"Observed {markers} execution markers. Completion guards were absent; "
            "no administrative guard queries were added. Native file inventories, read routes, "
            "timing unknowns, source hashes, and per-stage model usage remain in analysis.json.",
            "",
            "No writes/changes is desired on reproduction stages; establishment and revision "
            "require writes. Historical rewrite counts concern complete bodies, "
            "independently of correct historical JSON.",
            "Requested route requires a complete correct direct recall on lookup stages. "
            "Search stages additionally require a successful observed search delivered before "
            "that recall was issued. Missing order or a shared compound tool result remains "
            "unknown. This metric does not alter artifact correctness or prove search caused "
            "the key selection. The unordered search-plus-full-recall joint is in analysis.json.",
            "",
            *[f"- {limit}" for limit in analysis["limits"]],
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    analysis = analyze(args.run)
    args.out.mkdir(parents=True, exist_ok=False)
    for name, content in (
        ("analysis.json", json.dumps(analysis, indent=2) + "\n"),
        ("report.md", markdown(analysis)),
    ):
        with (args.out / name).open("x") as target:
            target.write(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
