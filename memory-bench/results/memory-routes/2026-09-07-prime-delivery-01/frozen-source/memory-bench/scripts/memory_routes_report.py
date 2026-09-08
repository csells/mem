"""Aggregate frozen memory-route evidence without pooling distinct experiment runs."""

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

from membench.runner import memory_routes_grade

LEGS = ("establish", "direct", "search", "unnecessary")
ROUTES = LEGS[1:]
FLAGS = (
    "bd_direct_lookup",
    "bd_search",
    "bd_correct_payload_observed",
    "bd_correct_payload_via_direct",
    "bd_correct_payload_via_search",
    "bd_read_before_first_config_write",
    "bd_correct_payload_before_first_config_write",
)


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _load(path: Path, root: Path, inventory: dict[str, str]) -> Any:
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError(f"Missing, symlink or escaping evidence: {path}")
    raw = path.read_bytes()
    inventory[str(path.relative_to(root))] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw, object_pairs_hook=_pairs)


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {label}")
    return value


def _truth(value: Any) -> bool | None:
    if value is not None and type(value) is not bool:
        raise ValueError("Endpoint must be true, false or null")
    return value


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Cost/duration must be finite and nonnegative")
    return float(value)


def _counts(values: Sequence[bool | None]) -> dict[str, int]:
    return {
        "planned": len(values),
        "true": sum(value is True for value in values),
        "false": sum(value is False for value in values),
        "unknown": sum(value is None for value in values),
    }


def _leg(
    directory: Path, leg: str, policy: str, root: Path, inventory: dict[str, str]
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    path = directory / leg / "result.json"
    raw = _object(_load(path, root, inventory), str(path)) if path.exists() else None
    receipt_path = directory / leg / "receipts.json"
    receipts = _load(receipt_path, root, inventory) if receipt_path.exists() else None
    if receipts is not None and (
        not isinstance(receipts, list) or not all(isinstance(item, dict) for item in receipts)
    ):
        raise ValueError(f"Invalid receipt list: {receipt_path}")
    if raw is not None:
        if raw.get("leg") != leg or raw.get("policy") != policy or receipts is None:
            raise ValueError(f"Incomplete or mismatched leg evidence: {path}")
        artifact = _object(raw.get("artifact"), "artifact")
        memory = _object(raw.get("memory_evidence"), "memory_evidence")
    else:
        artifact, memory = {}, {}
    row = {
        "recorded": raw is not None,
        "artifact_success": _truth(artifact.get("passed")),
        "artifact_reason": artifact.get("reason"),
        **{flag: _truth(raw.get(flag) if raw else None) for flag in FLAGS},
        "cost_usd": _number(raw.get("cost_usd") if raw else None),
        "duration_s": _number(raw.get("duration_s") if raw else None),
        "exit_code": raw.get("exit_code") if raw else None,
        "terminal_subtype": raw.get("terminal_subtype") if raw else None,
        "is_error": _truth(raw.get("is_error") if raw else None),
        "measurement_unknown": _truth(memory.get("evidence_unknown")),
        "receipt_rows": len(receipts) if receipts is not None else None,
        "finished_receipts": (
            sum(item.get("event") == "finish" for item in receipts)
            if receipts is not None
            else None
        ),
    }
    return row, raw


def _capture(
    directory: Path,
    task: dict[str, Any],
    policy: str,
    root: Path,
    inventory: dict[str, str],
) -> dict[str, Any]:
    path = directory / "establish" / "memory.json"
    if not path.exists() or policy == "native":
        return {"exact_key": None, "any_key": None, "matched_keys": []}
    memories = _object(_load(path, root, inventory), "establish memory snapshot")
    if not all(isinstance(body, str) for body in memories.values()):
        raise ValueError("Memory snapshot must contain only key/body strings")
    expected = _object(task.get("expected_config"), "expected task configuration")
    key = task.get("key")
    if not isinstance(key, str) or not key:
        raise ValueError("Frozen task requires an exact memory key")
    exact = memory_routes_grade.grade_capture(memories, key, expected)["passed"]
    verdicts = {
        name: memory_routes_grade.grade_capture(memories, name, expected)["passed"]
        for name in memories
    }
    matching = sorted(name for name, verdict in verdicts.items() if verdict is True)
    any_key = True if matching else None if any(v is None for v in verdicts.values()) else False
    return {"exact_key": exact, "any_key": any_key, "matched_keys": matching}


def _case(
    root: Path,
    scheduled: dict[str, Any],
    task_definition: dict[str, Any],
    inventory: dict[str, str],
) -> dict[str, Any]:
    task, policy = scheduled["task"], scheduled["policy"]
    directory = root / "cases" / f"{task}-{policy}"
    result_path = directory / "result.json"
    raw = (
        _object(_load(result_path, root, inventory), str(result_path))
        if result_path.exists()
        else None
    )
    halted = (directory / "halt.json").exists()
    if raw is not None and halted:
        raise ValueError(f"Case is both completed and halted: {directory}")
    if directory.exists():
        started = _object(_load(directory / "started.json", root, inventory), "started case")
        if started.get("task") != task or started.get("policy") != policy:
            raise ValueError(f"Started case identity differs from schedule: {directory}")
    halt = _load(directory / "halt.json", root, inventory) if halted else None
    legs = {}
    for leg in LEGS:
        summarized, leg_raw = _leg(directory, leg, policy, root, inventory)
        legs[leg] = summarized
        if raw is not None:
            saved = _object(raw.get("legs"), "completed case legs")
            if set(saved) != set(LEGS) or leg_raw is None:
                raise ValueError(f"Completed case lacks four recorded legs: {directory}")
            if json.dumps(saved[leg], sort_keys=True) != json.dumps(leg_raw, sort_keys=True):
                raise ValueError(f"Case/leg saved results differ: {directory / leg}")
            if (
                leg_raw.get("exit_code") != 0
                or leg_raw.get("is_error") is not False
                or summarized["measurement_unknown"] is not False
            ):
                raise ValueError(f"Completed case contains failed/unmeasured session: {directory}")
    if raw is not None and (raw.get("task") != task or raw.get("policy") != policy):
        raise ValueError(f"Completed case identity differs from schedule: {directory}")
    capture = _object(raw.get("capture"), "capture") if raw else {}
    derived_capture = _capture(directory, task_definition, policy, root, inventory)
    status = (
        "complete"
        if raw is not None
        else "halted" if halted else "incomplete" if directory.exists() else "pending"
    )
    return {
        "task": task,
        "policy": policy,
        "status": status,
        "capture_exact_key": _truth(derived_capture["exact_key"]),
        "capture_any_key": _truth(derived_capture["any_key"]),
        "capture_matching_keys": derived_capture["matched_keys"],
        "saved_case_capture": _truth(capture.get("passed")),
        "saved_case_capture_reason": capture.get("reason"),
        "halt": halt,
        "legs": legs,
    }


def _resources(legs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    costs = [leg["cost_usd"] for leg in legs if leg["cost_usd"] is not None]
    durations = [leg["duration_s"] for leg in legs if leg["duration_s"] is not None]
    return {
        "planned_sessions": len(legs),
        "recorded_sessions": sum(leg["recorded"] for leg in legs),
        "estimated_cost_usd_observed": sum(costs),
        "cost_known_sessions": len(costs),
        "cost_unknown_sessions": len(legs) - len(costs),
        "duration_median_s": statistics.median(durations) if durations else None,
        "duration_known_sessions": len(durations),
    }


def _policy(policy: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    routes = {}
    for route in ROUTES:
        legs = [row["legs"][route] for row in rows]
        routes[route] = {
            "artifact_success": _counts([leg["artifact_success"] for leg in legs]),
            **{flag: _counts([leg[flag] for leg in legs]) for flag in FLAGS},
            **_resources(legs),
        }
    states = Counter(row["status"] for row in rows)
    return {
        "policy": policy,
        "planned_cases": len(rows),
        **{
            f"{state}_cases": states[state]
            for state in ("complete", "halted", "incomplete", "pending")
        },
        "capture_exact_key": _counts([row["capture_exact_key"] for row in rows]),
        "capture_any_key": _counts([row["capture_any_key"] for row in rows]),
        "saved_case_capture": _counts([row["saved_case_capture"] for row in rows]),
        "routes": routes,
        **_resources([row["legs"][leg] for row in rows for leg in LEGS]),
    }


def analyze(run: Path) -> dict[str, Any]:
    root = run.resolve(strict=True)
    inventory: dict[str, str] = {}
    manifest = _object(_load(root / "manifest.json", root, inventory), "manifest")
    if manifest.get("schema") != "memory-routes-macos.v1":
        raise ValueError("Unsupported memory-route run schema")
    grader_hash = hashlib.sha256(Path(memory_routes_grade.__file__).read_bytes()).hexdigest()
    grader_pin = manifest.get("source_sha256", {}).get(
        "memory-bench/membench/runner/memory_routes_grade.py"
    )
    if grader_pin != grader_hash:
        raise ValueError("Current literal-capture grader does not match the run's source pin")
    definitions = manifest.get("tasks")
    if not isinstance(definitions, list) or not definitions:
        raise ValueError("Frozen task definitions required for literal-capture grading")
    indexed = {task["id"]: task for task in definitions}
    if len(indexed) != len(definitions):
        raise ValueError("Duplicate frozen task definition")
    schedule = manifest.get("schedule")
    if not isinstance(schedule, list) or not schedule:
        raise ValueError("Nonempty frozen schedule required")
    identities = []
    for value in schedule:
        row = _object(value, "schedule row")
        for key in ("task", "policy"):
            if not isinstance(row.get(key), str) or not re.fullmatch(r"[\w.-]+", row[key]):
                raise ValueError("Unsafe or absent scheduled identity")
        identities.append((row["task"], row["policy"]))
        if row["task"] not in indexed:
            raise ValueError("Scheduled task has no frozen definition")
    if len(set(identities)) != len(identities):
        raise ValueError("Duplicate scheduled case")
    if manifest.get("planned_sessions") != len(schedule) * len(LEGS):
        raise ValueError("Planned session count differs from schedule")
    rows = [_case(root, row, indexed[row["task"]], inventory) for row in schedule]
    policies = sorted({row["policy"] for row in rows})
    # Guard against a file being rewritten during reporting; new pending outputs
    # are outside this snapshot, and are not silently added to its denominators.
    for relative, expected in inventory.items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Evidence changed during reporting: {relative}")
    return {
        "run": str(root),
        "model": manifest.get("model"),
        "claude_version": manifest.get("claude_version"),
        "bd_version": manifest.get("bd_version"),
        "planned_cases": len(rows),
        "case_status_counts": dict(Counter(row["status"] for row in rows)),
        "policies": [
            _policy(policy, [row for row in rows if row["policy"] == policy]) for policy in policies
        ],
        "rows": rows,
        "input_sha256": inventory,
        "derived_capture_grader_sha256": grader_hash,
    }


def _tfu(value: dict[str, int]) -> str:
    return f"{value['true']}/{value['false']}/{value['unknown']}"


def _state(value: bool | None) -> str:
    return "pass" if value is True else "fail" if value is False else "?"


def _median(value: float | None) -> str:
    return "?" if value is None else f"{value:.2f}"


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Memory-route experiment report",
        "",
        "Each run is reported separately. Counts marked T/F/? retain scheduled denominators; "
        "missing sessions and unsupported representations are unknown, not failures. "
        "The three goal routes share one capture and are not independent trials.",
        "",
        "Artifact success checks the actual final JSON. Literal capture/payload checks do not "
        "judge surrounding prose. Exact-key and any-key capture are derived from the saved "
        "establish memory snapshot using the run's pinned grader; the original case verdict "
        "remains in JSON. Native capture stays unknown because that snapshot covers bd only. "
        "Other saved scores are aggregated without recomputation.",
        "",
        "Before-Write timing is unknown without a matching Write tool event. CLI costs are "
        "subscription token-usage estimates, not additional billed dollars; missing costs "
        "are reported separately. Durations are per-session elapsed times.",
    ]
    for run in report["runs"]:
        lines += [
            "",
            f"## {Path(run['run']).name}",
            "",
            f"Source: `{run['run']}`. Model: `{run['model']}`; CLI: `{run['claude_version']}`; "
            f"bd: `{run['bd_version']}`.",
            "",
            "| Policy | Complete/planned | Halted | Incomplete | Pending | "
            "Exact-key capture T/F/? | Any-key capture T/F/? | "
            "Observed cost USD | Cost sessions known/planned | Median seconds |",
            "|---|---:|---:|---:|---:|---|---|---:|---:|---:|",
        ]
        for policy in run["policies"]:
            lines.append(
                f"| {policy['policy']} | {policy['complete_cases']}/{policy['planned_cases']} | "
                f"{policy['halted_cases']} | {policy['incomplete_cases']} | "
                f"{policy['pending_cases']} | "
                f"{_tfu(policy['capture_exact_key'])} | {_tfu(policy['capture_any_key'])} | "
                f"{policy['estimated_cost_usd_observed']:.4f} | "
                f"{policy['cost_known_sessions']}/{policy['planned_sessions']} | "
                f"{_median(policy['duration_median_s'])} |"
            )
        lines += [
            "",
            "| Policy | Goal | Recorded/planned | Artifact T/F/? | Lookup used T/F/? | "
            "Search used T/F/? | Correct payload T/F/? | Correct via lookup T/F/? | "
            "Correct via search T/F/? |",
            "|---|---|---:|---|---|---|---|---|---|",
        ]
        for policy in run["policies"]:
            for route, data in policy["routes"].items():
                metrics = ("artifact_success", *FLAGS[:5])
                cells = " | ".join(_tfu(data[key]) for key in metrics)
                lines.append(
                    f"| {policy['policy']} | {route} | "
                    f"{data['recorded_sessions']}/{data['planned_sessions']} | {cells} |"
                )
        lines += [
            "",
            "| Policy | Goal | Any read before Write T/F/? | Correct payload before Write T/F/? | "
            "Observed cost USD | Median seconds |",
            "|---|---|---|---|---:|---:|",
        ]
        for policy in run["policies"]:
            for route, data in policy["routes"].items():
                lines.append(
                    f"| {policy['policy']} | {route} | "
                    f"{_tfu(data['bd_read_before_first_config_write'])} | "
                    f"{_tfu(data['bd_correct_payload_before_first_config_write'])} | "
                    f"{data['estimated_cost_usd_observed']:.4f} | "
                    f"{_median(data['duration_median_s'])} |"
                )
        lines += [
            "",
            "| Task | Policy | Case state | Exact-key capture | Any-key capture | "
            "Direct artifact | Search artifact | "
            "Supplied control artifact |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for row in run["rows"]:
            goals = " | ".join(_state(row["legs"][route]["artifact_success"]) for route in ROUTES)
            lines.append(
                f"| {row['task']} | {row['policy']} | {row['status']} | "
                f"{_state(row['capture_exact_key'])} | {_state(row['capture_any_key'])} | {goals} |"
            )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    roots = [path.resolve(strict=True) for path in args.run]
    if len(set(roots)) != len(roots):
        raise ValueError("Repeated runs cannot be counted twice")
    out = args.out.resolve()
    if out.exists() or args.out.is_symlink() or any(out.is_relative_to(root) for root in roots):
        raise ValueError("Output must be a new directory outside every run")
    report = {
        "schema": "memory-routes-report.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "reporter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "runs": [analyze(root) for root in roots],
    }
    rendered = markdown(report)
    out.mkdir(parents=True, exist_ok=False)
    with (out / "report.json").open("x", encoding="utf-8") as target:
        json.dump(report, target, indent=2, sort_keys=True)
        target.write("\n")
    with (out / "report.md").open("x", encoding="utf-8") as target:
        target.write(rendered)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
