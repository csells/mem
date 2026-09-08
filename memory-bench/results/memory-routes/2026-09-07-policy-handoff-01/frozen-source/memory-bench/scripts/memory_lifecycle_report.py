"""Independently grade frozen lifecycle artifacts without changing run evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from membench.runner import memory_lifecycle_gate, memory_routes_grade

POLICIES = ("existing", "selective", "checked")
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
ROUTE_FLAGS = (
    "bd_direct_lookup",
    "bd_search",
    "bd_correct_payload_observed",
    "bd_correct_payload_via_direct",
    "bd_correct_payload_via_search",
    "bd_read_before_first_config_write",
    "bd_correct_payload_before_first_config_write",
)


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value: str) -> Any:
    raise ValueError(f"Nonfinite JSON constant: {value}")


def _json(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {label}")
    return value


def _same(left: Any, right: Any, label: str) -> None:
    if json.dumps(left, sort_keys=True, allow_nan=False) != json.dumps(
        right, sort_keys=True, allow_nan=False
    ):
        raise ValueError(f"Evidence mismatch: {label}")


def _truth(value: Any) -> bool | None:
    if value is not None and type(value) is not bool:
        raise ValueError("Expected true, false or unknown")
    return value


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Expected a finite nonnegative measurement")
    return float(value)


def _integer(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("Expected a nonnegative integer count")
    return value


def _all(values: Sequence[bool | None]) -> bool | None:
    return False if False in values else None if None in values else True


def _counts(values: Sequence[bool | None]) -> dict[str, int]:
    return {
        "planned": len(values),
        "true": sum(value is True for value in values),
        "false": sum(value is False for value in values),
        "unknown": sum(value is None for value in values),
    }


class Evidence:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=True)
        self.inventory: dict[str, str] = {}

    def path(self, relative: str | Path) -> Path:
        relative = Path(relative)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Escaping evidence path")
        path = self.root / relative
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("Escaping evidence path")
        if any(part.is_symlink() for part in (path, *path.parents) if part != self.root):
            raise ValueError("Symlink evidence is not accepted")
        return path

    def raw(self, relative: str | Path) -> bytes:
        path = self.path(relative)
        if not path.is_file():
            raise ValueError(f"Missing evidence: {relative}")
        raw = path.read_bytes()
        self.inventory[str(path.relative_to(self.root))] = hashlib.sha256(raw).hexdigest()
        return raw

    def load(self, relative: str | Path) -> Any:
        return _json(self.raw(relative).decode("utf-8"))

    def optional(self, relative: str | Path) -> Any:
        return self.load(relative) if self.path(relative).exists() else None

    def snapshot(self, relative: str | Path) -> dict[str, str] | None:
        value = self.optional(relative)
        if value is None:
            return None
        value = _object(value, "memory snapshot")
        if not all(isinstance(body, str) for body in value.values()):
            raise ValueError("Memory bodies must be strings")
        return value

    def verify(self) -> None:
        for name, expected in list(self.inventory.items()):
            if hashlib.sha256(self.raw(name)).hexdigest() != expected:
                raise ValueError(f"Evidence changed while reporting: {name}")


def _stream(
    evidence: Evidence, directory: Path, raw: dict[str, Any] | None, model: str
) -> dict[str, Any]:
    path = directory / "stream.jsonl"
    events = []
    malformed_tail = False
    if evidence.path(path).exists():
        lines = evidence.raw(path).decode("utf-8").splitlines()
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                events.append(_object(_json(line), "stream event"))
            except ValueError:
                if raw is not None or index != len(lines) - 1:
                    raise
                malformed_tail = True
    starts = [e for e in events if e.get("type") == "system" and e.get("subtype") == "init"]
    terminals = [e for e in events if e.get("type") == "result"]
    if len(starts) > 1 or len(terminals) > 1:
        raise ValueError("Repeated session initialization or terminal event")
    if raw is not None and (len(starts) != 1 or len(terminals) != 1):
        raise ValueError("Recorded result lacks one initialized terminal session")
    session_id = None
    if starts:
        session_id = starts[0].get("session_id")
        if (
            not isinstance(session_id, str)
            or not session_id.strip()
            or starts[0].get("model") != model
        ):
            raise ValueError("Stream session/model identity differs")
    terminal = terminals[0] if terminals else {}
    if terminal.get("session_id") not in (None, session_id):
        raise ValueError("Terminal session identity differs")
    if raw is not None:
        _same(raw.get("session_id"), session_id, "result/session identity")
        for field, terminal_field in (
            ("cost_usd", "total_cost_usd"),
            ("terminal_subtype", "subtype"),
            ("is_error", "is_error"),
            ("turns", "num_turns"),
            ("model_usage", "modelUsage"),
        ):
            _same(raw.get(field), terminal.get(terminal_field), f"terminal {field}")
        behavioral_limit = terminal.get("is_error") is True and terminal.get("subtype") in {
            "error_max_turns",
            "error_max_budget_usd",
        }
        _same(raw.get("behavioral_limit", False), behavioral_limit, "behavioral limit")
        if type(raw.get("exit_code")) is not int or type(terminal.get("is_error")) is not bool:
            raise ValueError("Recorded session lacks a valid terminal status")
    duration = _number(raw.get("duration_s")) if raw is not None else None
    duration_source = "recorded_elapsed" if duration is not None else None
    halt = evidence.optional(directory / "halt.json")
    if duration is None and isinstance(halt, dict) and halt.get("elapsed_s") is not None:
        duration, duration_source = _number(halt["elapsed_s"]), "halt_elapsed"
    if duration is None and terminal.get("duration_ms") is not None:
        milliseconds = _number(terminal["duration_ms"])
        assert milliseconds is not None
        duration, duration_source = milliseconds / 1000, "terminal_elapsed"
    return {
        "session_id": session_id,
        "terminal_events": len(terminals),
        "cost_usd": _number(terminal.get("total_cost_usd")),
        "duration_s": duration,
        "duration_source": duration_source,
        "model_usage": terminal.get("modelUsage"),
        "stream_malformed_tail": malformed_tail,
        "halt": halt,
        "behavioral_limit": (
            (
                terminal.get("is_error") is True
                and terminal.get("subtype") in {"error_max_turns", "error_max_budget_usd"}
            )
            if terminal
            else None
        ),
        "execution_ok": (
            raw["exit_code"] == 0 and terminal.get("is_error") is False if raw is not None else None
        ),
    }


def _payload(operations: list[dict[str, Any]], expected: dict[str, Any]) -> bool | None:
    grades = [
        memory_routes_grade.grade_capture({"observed": body}, "observed", expected)["passed"]
        for operation in operations
        for body in operation["content"]
    ]
    return True if True in grades else None if None in grades else False


def _operation_data(
    raw: dict[str, Any], receipts: list[dict[str, Any]], expected: dict[str, Any]
) -> dict[str, Any]:
    memory = _object(raw.get("memory_evidence"), "memory evidence")
    operations = memory.get("operations")
    if not isinstance(operations, list):
        raise ValueError("Recorded memory operations required")
    finishes = [row for row in receipts if row.get("event") == "finish"]
    by_id = {row.get("invocation_id"): row for row in finishes}
    if len(by_id) != len(finishes):
        raise ValueError("Duplicate finish receipts")
    writes: Counter[str] = Counter()
    reads = []
    accepted = 0
    for operation in operations:
        operation = _object(operation, "memory operation")
        receipt = by_id.get(operation.get("invocation_id"))
        if receipt is None:
            raise ValueError("Scored operation has no finish receipt")
        for field in ("tool_use_id", "session_id", "stdout", "stderr", "returncode"):
            _same(operation.get(field), receipt.get(field), f"operation/receipt {field}")
        _same(operation.get("argv"), receipt.get("operation_argv"), "operation/receipt argv")
        receipt_argv = receipt.get("argv")
        if not isinstance(receipt_argv, list) or len(receipt_argv) < 4:
            raise ValueError("Receipt omits its binary/store identity")
        _same(receipt_argv[3:], operation.get("argv"), "receipt invocation suffix")
        _same(operation.get("session_id"), raw.get("session_id"), "operation/session")
        if receipt.get("leg_id") != raw.get("leg"):
            raise ValueError("Operation belongs to another stage")
        args = operation.get("argv")
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise ValueError("Malformed operation arguments")
        content = operation.get("content")
        if not isinstance(content, list) or not all(isinstance(body, str) for body in content):
            raise ValueError("Malformed observed content")
        for field in ("is_read", "is_write", "accepted_write", "output_observed"):
            if _truth(operation.get(field)) is None:
                raise ValueError("Operation classification is missing")
        if operation["accepted_write"]:
            if not operation["is_write"] or operation["returncode"] != 0:
                raise ValueError("Impossible accepted write")
            accepted += 1
            index = args.index("--key") if "--key" in args else -1
            key = args[index + 1] if 0 <= index < len(args) - 1 else "<unresolved-key>"
            writes[key] += 1
        if operation["is_read"] and operation["output_observed"] and operation["returncode"] == 0:
            reads.append(operation)
    _same(accepted, _integer(memory.get("accepted_writes")), "accepted write count")
    direct = [op for op in reads if "recall" in op["argv"]]
    search = [
        op
        for op in reads
        if "memories" in op["argv"]
        and any(not arg.startswith("-") for arg in op["argv"][op["argv"].index("memories") + 1 :])
    ]
    derived = {
        "bd_direct_lookup": bool(direct),
        "bd_search": bool(search),
        "bd_correct_payload_observed": _payload(reads, expected),
        "bd_correct_payload_via_direct": _payload(direct, expected),
        "bd_correct_payload_via_search": _payload(search, expected),
    }
    for flag, value in derived.items():
        _same(raw.get(flag), value, f"derived {flag}")
    return {
        **{flag: _truth(raw.get(flag)) for flag in ROUTE_FLAGS},
        "accepted_writes": accepted,
        "write_counts_by_key": dict(writes),
        "repeated_writes_same_key": sum(max(0, count - 1) for count in writes.values()),
        "measurement_unknown": _truth(memory.get("evidence_unknown")),
    }


def _gate_events(
    evidence: Evidence, directory: Path, policy: str
) -> tuple[list[Any], dict[str, Any]]:
    path = directory / "gate-events.jsonl"
    events = []
    if evidence.path(path).exists():
        events = [
            _object(_json(line), "gate event")
            for line in evidence.raw(path).decode().splitlines()
            if line.strip()
        ]
    if events and policy != "checked":
        raise ValueError("Enforcement events appeared in an unchecked arm")
    counts: Counter[str] = Counter()
    administrative_queries = 0
    durations = []
    for event in events:
        if event.get("event") not in {"close", "stop"} or type(event.get("passed")) is not bool:
            raise ValueError("Malformed gate event")
        counts[event["event"]] += 1
        if event["passed"] is False:
            counts["blocked_" + event["event"]] += 1
        if event.get("infrastructure_error"):
            counts["infrastructure_errors"] += 1
        elif event.get("administrative_bd_queries") is None or event.get("duration_s") is None:
            raise ValueError("Gate event omitted overhead measurements")
        if event.get("administrative_bd_queries") is not None:
            administrative_queries += _integer(event["administrative_bd_queries"])
        value = _number(event.get("duration_s"))
        if value is not None:
            durations.append(value)
    return events, {
        "events": len(events),
        "close_checks": counts["close"],
        "stop_checks": counts["stop"],
        "blocked_close": counts["blocked_close"],
        "blocked_stop": counts["blocked_stop"],
        "infrastructure_errors": counts["infrastructure_errors"],
        "administrative_queries_observed": administrative_queries,
        "duration_s_observed": sum(durations),
        "duration_known_events": len(durations),
    }


def _stage(
    evidence: Evidence,
    case_dir: Path,
    task: dict[str, Any],
    definition: dict[str, Any],
    policy: str,
    model: str,
    guidance: str,
    previous: dict[str, str] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, str] | None]:
    name = definition["name"]
    directory = case_dir / name
    raw_value = evidence.optional(directory / "result.json")
    raw = _object(raw_value, "session result") if raw_value is not None else None
    assessment_value = evidence.optional(directory / "assessment.json")
    assessment = _object(assessment_value, "assessment") if assessment_value is not None else None
    before = evidence.snapshot(case_dir / f"transferred-{name}.json")
    after = evidence.snapshot(directory / "memory.json")
    if before is not None:
        if previous is None:
            raise ValueError("Transfer skips a missing predecessor snapshot")
        _same(before, previous, "cumulative memory transfer")
    if raw is not None and (before is None or after is None):
        raise ValueError("Recorded session lacks before/after memory snapshots")
    started = evidence.optional(directory / "started.json")
    if started is not None:
        started = _object(started, "session start")
        if started.get("leg") != name or started.get("policy") != policy:
            raise ValueError("Session start differs from planned stage")
    if raw is not None:
        if raw.get("leg") != name or raw.get("policy") != policy or started is None:
            raise ValueError("Session result differs from planned stage")
        _same(raw.get("scratch"), started.get("scratch"), "session scratch identity")
        prompt = evidence.raw(directory / "prompt.txt").decode()
        if not prompt.endswith(definition["prompt"]):
            raise ValueError("Session prompt does not contain its frozen task")
        expected_prompt = guidance + f"\nAssigned task: {raw['task_id']}\n\n" + definition["prompt"]
        _same(prompt.split(), expected_prompt.split(), "frozen session guidance")
        argv = started.get("argv")
        if not isinstance(argv, list) or argv.count("-p") != 1:
            raise ValueError("Session invocation has no single prompt")
        _same(argv[argv.index("-p") + 1], prompt, "invocation prompt")
        if argv.count("--model") != 1 or argv[argv.index("--model") + 1] != model:
            raise ValueError("Session invocation model differs from frozen plan")
    stream = _stream(evidence, directory, raw, model)
    receipt_value = evidence.optional(directory / "receipts.json")
    receipts = receipt_value if isinstance(receipt_value, list) else []
    if receipt_value is not None and (
        not isinstance(receipt_value, list) or not all(isinstance(row, dict) for row in receipts)
    ):
        raise ValueError("Malformed receipts")
    if raw is not None and receipt_value is None:
        raise ValueError("Recorded result lacks receipts")
    operations = (
        _operation_data(raw, receipts, definition["expected_config"])
        if raw
        else {
            **dict.fromkeys(ROUTE_FLAGS),
            "accepted_writes": None,
            "write_counts_by_key": {},
            "repeated_writes_same_key": None,
            "measurement_unknown": None,
        }
    )
    artifact_path = directory / "workspace/config.json"
    artifact = None
    if raw is not None or evidence.path(artifact_path).exists():
        if evidence.path(artifact_path).is_file():
            evidence.raw(artifact_path)
        artifact = memory_routes_grade.grade_artifact(
            evidence.path(artifact_path), definition["expected_config"]
        )
    current_expected = task["initial_config"] if name in STAGES[:3] else task["revised_config"]
    current = (
        memory_routes_grade.grade_capture(after, task["key"], current_expected)
        if after is not None
        else None
    )
    history = (
        memory_routes_grade.grade_capture(after, task["historical_key"], task["initial_config"])
        if after is not None
        else None
    )
    assigned = evidence.optional(directory / "task.json")
    closed = None
    if assigned is not None:
        if (
            not isinstance(assigned, list)
            or len(assigned) != 1
            or not isinstance(assigned[0], dict)
        ):
            raise ValueError("Malformed assigned-task snapshot")
        if raw is None or assigned[0].get("id") != raw.get("task_id"):
            raise ValueError("Assigned-task identity differs")
        closed = assigned[0].get("status") == "closed"
    delta = (
        {
            "added": sorted(after.keys() - before.keys()),
            "removed": sorted(before.keys() - after.keys()),
            "changed": sorted(
                key for key in before.keys() & after.keys() if before[key] != after[key]
            ),
        }
        if before is not None and after is not None
        else None
    )
    extra = (
        sorted(
            after.keys() - (task["task"]["decoys"].keys() | {task["key"], task["historical_key"]})
        )
        if after is not None
        else None
    )
    no_curation = (
        not any(delta.values()) and operations["accepted_writes"] == 0
        if delta is not None and operations["accepted_writes"] is not None
        else None
    )
    shadow = (
        memory_lifecycle_gate.evaluate_gate(
            evidence.path(artifact_path),
            after,
            receipts,
            definition["required_write_keys"],
            definition["retrieval_required"],
            name != "revise",
        )
        if raw is not None and after is not None
        else None
    )
    events, enforcement = _gate_events(evidence, directory, policy)
    enforced_completion = (
        bool(events and events[-1].get("event") == "stop" and events[-1].get("passed"))
        if policy == "checked" and raw is not None
        else None
    )
    actual = _all(
        [
            artifact["passed"] if artifact else None,
            closed,
            current["passed"] if current else None,
            history["passed"] if history else None,
            not extra if extra is not None else None,
            True if definition["capture_required"] else no_curation,
            (
                operations["bd_correct_payload_observed"]
                if definition["retrieval_required"] and name != "revise"
                else True
            ),
            not stream["behavioral_limit"] if stream["behavioral_limit"] is not None else None,
            stream["execution_ok"],
        ]
    )
    if raw is not None:
        _same(raw.get("artifact"), artifact, "independently regraded artifact")
    if assessment is not None:
        if raw is None or assessment.get("name") != name:
            raise ValueError("Assessment has no matching session")
        for field, derived in (
            ("result", raw),
            ("artifact", artifact),
            ("task_closed", closed),
            ("current_capture", current),
            ("historical_capture", history),
            ("delta", delta),
            ("extra_keys", extra),
            ("no_unnecessary_curation", no_curation),
            ("public_completion_check", shadow),
            ("gate_events", events),
            ("enforced_completion", enforced_completion),
        ):
            _same(assessment.get(field), derived, f"assessment {field}")
        _same(assessment.get("complete_handoff"), actual is True, "objective handoff endpoint")
    return (
        {
            "name": name,
            "recorded": raw is not None,
            "assessed": assessment is not None,
            "artifact": artifact["passed"] if artifact else None,
            "artifact_grade": artifact,
            "current_capture": current["passed"] if current else None,
            "historical_capture": history["passed"] if history else None,
            "task_closed": closed,
            "delta": delta,
            "extra_keys": extra,
            "no_unnecessary_curation": no_curation,
            "objective_handoff": actual,
            "saved_handoff": _truth(assessment.get("complete_handoff")) if assessment else None,
            "procedural_shadow_check": shadow["passed"] if shadow else None,
            "enforced_completion": enforced_completion,
            "enforcement": enforcement,
            **operations,
            **stream,
        },
        assessment,
        after,
    )


def _case(
    evidence: Evidence, task: dict[str, Any], policy: str, model: str, guidance: str
) -> dict[str, Any]:
    directory = Path("cases") / f"{task['id']}-{policy}"
    saved = evidence.optional(directory / "result.json")
    started = evidence.optional(directory / "started.json")
    halt = evidence.optional(directory / "halt.json")
    if saved is not None and halt is not None:
        raise ValueError("Lifecycle is both complete and halted")
    for value in (saved, started):
        if value is not None:
            value = _object(value, "lifecycle identity")
            if value.get("task") != task["id"] or value.get("policy") != policy:
                raise ValueError("Lifecycle identity differs from schedule")
    if saved is not None and started is None:
        raise ValueError("Completed lifecycle lacks a start record")
    previous = task["task"]["decoys"]
    stages = []
    assessments = []
    for definition in task["stages"]:
        row, assessment, previous = _stage(
            evidence, directory, task, definition, policy, model, guidance, previous
        )
        stages.append(row)
        assessments.append(assessment)
    if saved is not None:
        if any(value is None for value in assessments):
            raise ValueError("Completed lifecycle lacks an assessed stage")
        _same(saved.get("stages"), assessments, "case/assessment chain")
        _same(
            saved.get("complete_lifecycle"),
            all(row["complete_handoff"] for row in assessments if row is not None),
            "saved lifecycle endpoint",
        )
    status = (
        "complete"
        if saved is not None
        else (
            "halted"
            if halt is not None
            else "incomplete" if evidence.path(directory).exists() else "pending"
        )
    )
    return {
        "task": task["id"],
        "domain": task["domain"],
        "policy": policy,
        "status": status,
        "halt": halt,
        "stages": stages,
        "objective_lifecycle": _all([row["objective_handoff"] for row in stages]),
        "saved_lifecycle": saved.get("complete_lifecycle") if saved else None,
    }


def _resources(stages: list[dict[str, Any]]) -> dict[str, Any]:
    costs = [stage["cost_usd"] for stage in stages if stage["cost_usd"] is not None]
    durations = [stage["duration_s"] for stage in stages if stage["duration_s"] is not None]
    usage: dict[str, dict[str, int | float]] = {}
    usage_known = 0
    for stage in stages:
        models = stage["model_usage"]
        if models is None:
            continue
        models = _object(models, "terminal model usage")
        usage_known += 1
        for model, value in models.items():
            value = _object(value, "model usage")
            total = usage.setdefault(model, {})
            for field in (
                "inputTokens",
                "outputTokens",
                "cacheReadInputTokens",
                "cacheCreationInputTokens",
                "webSearchRequests",
                "costUSD",
            ):
                if field not in value:
                    continue
                amount = _number(value[field]) if field == "costUSD" else _integer(value[field])
                if amount is not None:
                    total[field] = total.get(field, 0) + amount
    return {
        "planned_sessions": len(stages),
        "recorded_sessions": sum(stage["recorded"] for stage in stages),
        "terminal_result_events": sum(stage["terminal_events"] for stage in stages),
        "estimated_cost_usd_observed": sum(costs),
        "cost_known_sessions": len(costs),
        "cost_unknown_sessions": len(stages) - len(costs),
        "duration_median_s": statistics.median(durations) if durations else None,
        "duration_known_sessions": len(durations),
        "duration_source_counts": dict(
            Counter(stage["duration_source"] for stage in stages if stage["duration_source"])
        ),
        "model_usage_known_sessions": usage_known,
        "model_usage_observed": usage,
    }


def _policy(cases: list[dict[str, Any]]) -> dict[str, Any]:
    stages = [stage for case in cases for stage in case["stages"]]
    metrics = (
        "artifact",
        "current_capture",
        "historical_capture",
        "task_closed",
        "objective_handoff",
        "procedural_shadow_check",
        "no_unnecessary_curation",
        *ROUTE_FLAGS,
        "behavioral_limit",
        "enforced_completion",
    )
    by_stage = {}
    for name in STAGES:
        rows = [stage for stage in stages if stage["name"] == name]
        by_stage[name] = {
            **{metric: _counts([row[metric] for row in rows]) for metric in metrics},
            "accepted_writes_observed": sum(row["accepted_writes"] or 0 for row in rows),
            "write_count_known_sessions": sum(row["accepted_writes"] is not None for row in rows),
            "repeated_writes_same_key_observed": sum(
                row["repeated_writes_same_key"] or 0 for row in rows
            ),
            "delta_keys_observed": {
                kind: sum(len(row["delta"][kind]) for row in rows if row["delta"] is not None)
                for kind in ("added", "removed", "changed")
            },
            "resources": _resources(rows),
        }
    return {
        "planned_lifecycles": len(cases),
        "status_counts": dict(Counter(case["status"] for case in cases)),
        "whole_lifecycle": _counts([case["objective_lifecycle"] for case in cases]),
        "initial_current_and_v1_capture": _counts(
            [
                _all(
                    [case["stages"][0]["current_capture"], case["stages"][0]["historical_capture"]]
                )
                for case in cases
            ]
        ),
        "resources": _resources(stages),
        "stages": by_stage,
        "enforcement": {
            key: sum(stage["enforcement"][key] for stage in stages)
            for key in (
                "events",
                "close_checks",
                "stop_checks",
                "blocked_close",
                "blocked_stop",
                "infrastructure_errors",
                "administrative_queries_observed",
                "duration_s_observed",
                "duration_known_events",
            )
        },
        "intervened_sessions": sum(
            bool(stage["enforcement"]["blocked_close"] or stage["enforcement"]["blocked_stop"])
            for stage in stages
        ),
    }


def analyze(run: Path) -> dict[str, Any]:
    evidence = Evidence(run)
    manifest = _object(evidence.load("manifest.json"), "manifest")
    if manifest.get("schema") != "memory-lifecycle.v1":
        raise ValueError("Unsupported lifecycle schema")
    pins = _object(manifest.get("source_sha256"), "source pins")
    for name, digest in pins.items():
        if hashlib.sha256(evidence.raw(Path("source") / name)).hexdigest() != digest:
            raise ValueError(f"Frozen source hash differs: {name}")
    for module in (memory_routes_grade, memory_lifecycle_gate):
        assert module.__file__
        path = Path(module.__file__)
        name = "memory-bench/membench/runner/" + path.name
        if pins.get(name) != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError(f"Current grader differs from frozen source: {name}")
    definitions, schedule = manifest.get("tasks"), manifest.get("schedule")
    if not isinstance(definitions, list) or not definitions or not isinstance(schedule, list):
        raise ValueError("Frozen tasks and schedule required")
    indexed = {}
    for task in definitions:
        task = _object(task, "task")
        identity = task.get("id")
        if (
            not isinstance(identity, str)
            or not re.fullmatch(r"[\w.-]+", identity)
            or identity in indexed
        ):
            raise ValueError("Unsafe or duplicate task identity")
        if [stage.get("name") for stage in task.get("stages", [])] != list(STAGES):
            raise ValueError("Frozen lifecycle must contain the ordered eight stages")
        if (
            not isinstance(task.get("key"), str)
            or task.get("historical_key") != task["key"] + ".v1"
        ):
            raise ValueError("Frozen current and historical references are invalid")
        for field in ("initial_config", "revised_config"):
            _object(task.get(field), field)
        if task["initial_config"] == task["revised_config"]:
            raise ValueError("Frozen permanent revision does not change the contract")
        patch = _object(task.get("revision_patch"), "revision patch")
        if len(patch) != 1:
            raise ValueError("Frozen revision must change one field")
        section, changes = next(iter(patch.items()))
        changes = _object(changes, "revision fields")
        if len(changes) != 1:
            raise ValueError("Frozen revision must change one field")
        field, value = next(iter(changes.items()))
        before = task["initial_config"][section][field]
        if type(before) is not type(value) or before == value:
            raise ValueError("Frozen revision must preserve the changed field's type")
        revised = _json(json.dumps(task["initial_config"], allow_nan=False))
        revised[section][field] = value
        _same(revised, task["revised_config"], "one-field frozen revision")
        decoys = _object(_object(task.get("task"), "original task").get("decoys"), "decoys")
        if task["key"] in decoys or task["historical_key"] in decoys:
            raise ValueError("Required memories cannot be seeded as decoys")
        for stage in task["stages"]:
            expected = (
                task["initial_config"]
                if stage["name"] in {*STAGES[:3], "historical"}
                else task["revised_config"]
            )
            _same(stage["expected_config"], expected, "frozen stage oracle")
            capture = stage["name"] in {"establish", "revise"}
            retrieval = stage["name"] not in {"establish", "supplied"}
            required = (
                [task["key"], task["historical_key"]]
                if stage["name"] == "establish"
                else [task["key"]] if stage["name"] == "revise" else []
            )
            _same(stage.get("capture_required"), capture, "public capture condition")
            _same(stage.get("retrieval_required"), retrieval, "public retrieval condition")
            _same(stage.get("required_write_keys"), required, "public write references")
        indexed[identity] = task
    identities: list[tuple[str, str]] = []
    for item in schedule:
        row = _object(item, "schedule row")
        task_id, policy = row.get("task"), row.get("policy")
        if not isinstance(task_id, str) or not isinstance(policy, str):
            raise ValueError("Scheduled identities must be strings")
        identities.append((task_id, policy))
    if len(set(identities)) != len(identities) or set(identities) != {
        (task, policy) for task in indexed for policy in POLICIES
    }:
        raise ValueError("Schedule must contain each task once in each of the three arms")
    if manifest.get("planned_sessions") != len(schedule) * len(STAGES):
        raise ValueError("Planned denominator differs from schedule")
    guidance = _object(manifest.get("policies"), "frozen policies")
    if any(
        not isinstance(guidance.get(policy), str) or not guidance[policy] for policy in POLICIES
    ):
        raise ValueError("All three frozen guidance texts are required")
    cases = [
        _case(evidence, indexed[task], policy, manifest["model"], guidance[policy])
        for task, policy in identities
    ]
    sessions = [
        stage["session_id"]
        for case in cases
        for stage in case["stages"]
        if stage["session_id"] is not None
    ]
    if len(set(sessions)) != len(sessions):
        raise ValueError("A session identity was reused across fresh stages")
    evidence.verify()
    return {
        "schema": "memory-lifecycle-analysis.v1",
        "run": str(evidence.root),
        "model": manifest["model"],
        "bd_version": manifest.get("bd_version"),
        "planned_lifecycles": len(cases),
        "planned_sessions": manifest["planned_sessions"],
        "unique_sessions_observed": len(sessions),
        "revision_contracts": [
            {
                "task": task["id"],
                "domain": task["domain"],
                "current_key": task["key"],
                "historical_key": task["historical_key"],
                "patch": task["revision_patch"],
            }
            for task in definitions
        ],
        "policies": {
            policy: _policy([case for case in cases if case["policy"] == policy])
            for policy in POLICIES
        },
        "cases": cases,
        "input_sha256": evidence.inventory,
        "limits": [
            "Synthetic cumulative legacy key/value lifecycles; stages within a lifecycle "
            "are correlated.",
            "Historical v1 is an explicitly requested manual snapshot, not validation "
            "of a native history feature or new Memory type.",
            "Literal JSON grading does not establish semantic reliability of surrounding prose.",
            "Receipt classifications and before-Write timing reuse the recorded scorer; "
            "operation identity/output and payload grades are crosschecked here.",
            "Procedural checks are diagnostic and are excluded from the objective endpoint.",
            "CLI costs are observed token-usage estimates, not necessarily additional "
            "billed charges.",
        ],
    }


def _tfu(value: dict[str, int]) -> str:
    return f"{value['true']}/{value['false']}/{value['unknown']}"


def markdown(analysis: dict[str, Any]) -> str:
    lines = [
        "# Memory lifecycle experiment",
        "",
        f"Source: `{analysis['run']}`. Model: `{analysis['model']}`.",
        f"Observed {analysis['unique_sessions_observed']} distinct session identities "
        f"across {analysis['planned_sessions']} planned sessions.",
        "Counts are true/false/unknown and retain every planned session. "
        "Whole-lifecycle success requires all eight actual handoffs; passing a procedural "
        "check does not establish that the configuration is correct.",
        "",
        "| Arm | Lifecycles T/F/? | Initial current + v1 T/F/? | Sessions recorded/planned | "
        "Observed cost USD | Cost known/planned | Median seconds |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for policy, data in analysis["policies"].items():
        resource = data["resources"]
        median = resource["duration_median_s"]
        median_text = "?" if median is None else f"{median:.2f}"
        lines.append(
            f"| {policy} | {_tfu(data['whole_lifecycle'])} | "
            f"{_tfu(data['initial_current_and_v1_capture'])} | "
            f"{resource['recorded_sessions']}/{resource['planned_sessions']} | "
            f"{resource['estimated_cost_usd_observed']:.4f} | "
            f"{resource['cost_known_sessions']}/{resource['planned_sessions']} | {median_text} |"
        )
    lines += [
        "",
        "| Arm | Stage | Artifact T/F/? | Current T/F/? | v1 T/F/? | Objective T/F/? | "
        "Shadow check T/F/? | Guarded completion T/F/? | Lookup T/F/? | "
        "Search T/F/? | Before-Write read T/F/? | "
        "Writes | No writes/changes T/F/? |",
        "|---|---|---|---|---|---|---|---|---|---|---|---:|---|",
    ]
    for policy, data in analysis["policies"].items():
        for name, stage in data["stages"].items():
            metrics = (
                "artifact",
                "current_capture",
                "historical_capture",
                "objective_handoff",
                "procedural_shadow_check",
                "enforced_completion",
                "bd_direct_lookup",
                "bd_search",
                "bd_read_before_first_config_write",
            )
            lines.append(
                f"| {policy} | {name} | "
                + " | ".join(_tfu(stage[key]) for key in metrics)
                + f" | {stage['accepted_writes_observed']} | "
                + f"{_tfu(stage['no_unnecessary_curation'])} |"
            )
    lines += [
        "",
        "| Arm | Stage | Same-key repeated writes | Delta added/removed/changed | "
        "Correct payload before Write T/F/? | Behavioral limit T/F/? |",
        "|---|---|---:|---|---|---|",
    ]
    for policy, data in analysis["policies"].items():
        for name, stage in data["stages"].items():
            delta = stage["delta_keys_observed"]
            lines.append(
                f"| {policy} | {name} | {stage['repeated_writes_same_key_observed']} | "
                f"{delta['added']}/{delta['removed']}/{delta['changed']} | "
                f"{_tfu(stage['bd_correct_payload_before_first_config_write'])} | "
                f"{_tfu(stage['behavioral_limit'])} |"
            )
    lines += [
        "",
        "| Arm | Close checks | Stop checks | Blocked close / stop | Intervened sessions | "
        "Administrative queries | Check seconds observed |",
        "|---|---:|---:|---|---:|---:|---:|",
    ]
    for policy, data in analysis["policies"].items():
        events = data["enforcement"]
        lines.append(
            f"| {policy} | {events['close_checks']} | {events['stop_checks']} | "
            f"{events['blocked_close']} / {events['blocked_stop']} | "
            f"{data['intervened_sessions']} | "
            f"{events['administrative_queries_observed']} | {events['duration_s_observed']:.4f} |"
        )
    lines += [
        "",
        "The two requested establishment records are intentional. No writes/changes is "
        "the desired outcome on reproduction stages; writes are required during "
        "establishment and permanent revision. Reproduction writes "
        "remain redundant even if they leave no byte-level delta. Before-Write timing "
        "is unknown when no matching Write tool event exists. Guarded completion refers "
        "to the final successful Stop check in the checked arm; it is separate from "
        "the artifact oracle. Duration-source counts and per-model usage are in analysis.json.",
        "",
        *["- " + limit for limit in analysis["limits"]],
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    root, out = args.run.resolve(strict=True), args.out.resolve()
    if args.out.is_symlink() or out.exists() or out.is_relative_to(root):
        raise ValueError("Output must be a new directory outside the raw run")
    analysis = analyze(root)
    analysis["generated_at"] = datetime.now(UTC).isoformat()
    analysis["reporter_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    rendered = markdown(analysis)
    out.mkdir(parents=True, exist_ok=False)
    with (out / "analysis.json").open("x") as output:
        json.dump(analysis, output, sort_keys=True, indent=2, allow_nan=False)
        output.write("\n")
    with (out / "report.md").open("x") as output:
        output.write(rendered)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
