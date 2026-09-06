"""Describe real-task bd use with frozen schedule denominators and immutable evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from membench.runner.bd_real_experiment import _completed, _directory
from membench.runner.bd_real_metrics import RealLegEvidence
from membench.runner.resume_cache import digest

ENDPOINTS = ("establish_write", "goal_read", "goal_content_read", "task_check_passed")
COUNTS = (
    "accepted_writes",
    "observed_reads",
    "observed_content_reads",
    "executed_reads",
    "executed_writes",
    "empty_reads",
    "syntactic_read_attempts",
    "syntactic_write_attempts",
)


def _json(path: Path) -> dict[str, Any]:
    body = json.loads(path.read_bytes())
    if not isinstance(body, dict):
        raise ValueError(f"Expected object: {path}")
    return body


def _leg(path: Path, leg: int) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    record = _json(path)
    if record.get("leg") != leg:
        raise ValueError("Leg identity mismatch")
    memory = record.get("memory")
    if not isinstance(memory, dict):
        raise ValueError("Missing memory evidence")
    for field in COUNTS:
        if type(memory[field]) is not int or memory[field] < 0:
            raise ValueError("Invalid memory count")
    memory = RealLegEvidence.model_validate(memory).model_dump(mode="json")
    for field in ("duration_s", "total_cost_usd"):
        value = record.get(field)
        if value is not None and (
            type(value) not in (int, float) or not math.isfinite(value) or value < 0
        ):
            raise ValueError(f"Invalid {field}")
    return {**record, "memory": memory}


def _positive(record: dict[str, Any] | None, field: str) -> bool | None:
    if record is None or record.get("integrity_errors"):
        return None
    if record["memory"][field] > 0:
        return True
    if (
        record.get("status") != "ok"
        or record["memory"]["evidence_unknown"]
        or record.get("integrity_errors")
    ):
        return None
    return False


def _pair(root: Path, pair: dict[str, Any], manifest_digest: str) -> dict[str, Any]:
    directory = _directory(root, pair)
    complete = (directory / "cell.json").is_file()
    if complete:
        _completed(directory, pair, manifest_digest)
    if directory.exists():
        started = _json(directory / "started.json")
        if started.get("pair") != pair or started.get("manifest_digest") != manifest_digest:
            raise ValueError("Started pair identity mismatch")
    legs = [_leg(directory / f"run/leg-{leg}/result.json", leg) for leg in range(2)]
    check_path = directory / "run/task_check.json"
    check = _json(check_path).get("passed") if check_path.exists() else None
    if check is not None and type(check) is not bool:
        raise ValueError("Task check must be bool or unknown")
    if complete and _json(directory / "cell.json")["result"]["task_check"] != _json(check_path):
        raise ValueError("Task check differs from completed result")
    observed = [leg for leg in legs if leg is not None]
    costs = [leg["total_cost_usd"] for leg in observed if leg.get("total_cost_usd") is not None]
    durations = [leg["duration_s"] for leg in observed if leg.get("duration_s") is not None]
    return {
        **pair,
        "complete": complete,
        "saved_legs": len(observed),
        "establish_write": _positive(legs[0], "accepted_writes"),
        "goal_read": _positive(legs[1], "observed_reads"),
        "goal_content_read": _positive(legs[1], "observed_content_reads"),
        "task_check_passed": (
            None if any(leg.get("integrity_errors") for leg in observed) else check
        ),
        "recorded_task_check_passed": check,
        "evidence_unknown": len(observed) != 2
        or any(
            leg["memory"]["evidence_unknown"]
            or leg.get("status") != "ok"
            or bool(leg.get("integrity_errors"))
            for leg in observed
        ),
        "legs": [
            (
                {field: leg["memory"][field] for field in COUNTS}
                | {"status": leg["status"], "unknown_reasons": leg["memory"]["unknown_reasons"]}
                if leg is not None
                else None
            )
            for leg in legs
        ],
        "observed_cost_usd": sum(costs),
        "cost_known_legs": len(costs),
        "observed_duration_s": sum(durations),
        "duration_known_legs": len(durations),
    }


def _bounds(values: list[bool | None]) -> dict[str, Any]:
    yes = sum(value is True for value in values)
    no = sum(value is False for value in values)
    unknown = len(values) - yes - no
    return {
        "yes": yes,
        "no": no,
        "unknown": unknown,
        "lower": yes / len(values),
        "upper": (yes + unknown) / len(values),
    }


def _groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for condition in sorted({row["condition"] for row in rows}):
        for variant in ["all", *sorted({row["variant"] for row in rows})]:
            selected = [
                row
                for row in rows
                if row["condition"] == condition and (variant == "all" or row["variant"] == variant)
            ]
            if not selected:
                continue
            result.append(
                {
                    "condition": condition,
                    "variant": variant,
                    "scheduled_pairs": len(selected),
                    "endpoints": {
                        field: _bounds([row[field] for row in selected]) for field in ENDPOINTS
                    },
                    "observed_cost_usd": sum(row["observed_cost_usd"] for row in selected),
                    "cost_known_legs": sum(row["cost_known_legs"] for row in selected),
                    "duration_known_legs": sum(row["duration_known_legs"] for row in selected),
                    "evidence_unknown_pairs": sum(row["evidence_unknown"] for row in selected),
                    "observed_duration_s": sum(row["observed_duration_s"] for row in selected),
                }
            )
    return result


def _contrasts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = {(row["task_id"], row["variant"], row["condition"]): row for row in rows}
    result = []
    for task, variant in sorted({(row["task_id"], row["variant"]) for row in rows}):
        current = indexed.get((task, variant, "current"))
        focused = indexed.get((task, variant, "focused"))
        if current is not None and focused is not None:
            result.append(
                {
                    "task_id": task,
                    "variant": variant,
                    "focused_minus_current": {
                        field: (
                            int(focused[field]) - int(current[field])
                            if focused[field] is not None and current[field] is not None
                            else None
                        )
                        for field in ENDPOINTS
                    },
                }
            )
    return result


def analyze(root: Path) -> dict[str, Any]:
    manifest = _json(root / "manifest.json")
    schedule = manifest.get("schedule")
    if (
        manifest.get("schema") != "bd-real-experiment.v1"
        or not isinstance(schedule, list)
        or not schedule
    ):
        raise ValueError("Invalid frozen schedule")
    if len(schedule) != manifest.get("planned_pairs") or manifest.get(
        "planned_sessions"
    ) != 2 * len(schedule):
        raise ValueError("Schedule denominator mismatch")
    keys = []
    for pair in schedule:
        if not isinstance(pair, dict) or set(pair) != {"task_id", "variant", "condition"}:
            raise ValueError("Invalid pair identity")
        if not all(isinstance(value, str) and value for value in pair.values()):
            raise ValueError("Invalid pair identity fields")
        if pair["condition"] not in ("current", "focused") or pair["variant"] not in (
            "briefed",
            "unbriefed",
        ):
            raise ValueError("Unknown schedule condition or variant")
        keys.append(tuple(pair[key] for key in ("task_id", "variant", "condition")))
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate scheduled pair")
    expected = {
        (task, variant, condition)
        for task in {key[0] for key in keys}
        for variant in {key[1] for key in keys}
        for condition in ("current", "focused")
    }
    if set(keys) != expected:
        raise ValueError("Schedule must balance matched conditions and variants across tasks")
    rows = [_pair(root, pair, digest(manifest)) for pair in schedule]
    inventory = {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((root / "pairs").rglob("*"))
        if path.is_file()
    }
    return {
        "schema": "bd-real-analysis.v1",
        "manifest": manifest,
        "manifest_digest": digest(manifest),
        "artifact_sha256": inventory,
        "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "task_clusters": len({row["task_id"] for row in rows}),
        "pairs": rows,
        "groups": _groups(rows),
        "paired_contrasts": _contrasts(rows),
    }


def write_analysis(root: Path, out: Path) -> None:
    result = analyze(root)
    out.mkdir(parents=True, exist_ok=True)
    (out / "analysis.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = [
        "# Real-task bd memory pilot",
        "",
        "Counts describe executed memory use, not semantic fidelity or usefulness. "
        "Briefed goal reads are a redundant-retrieval diagnostic, not automatically useless.",
        "",
        "Every frozen pair remains in the denominator. Ranges bound unknown outcomes; "
        "Positive observed memory use survives incomplete sessions. "
        "Costs are CLI estimates, not bills. "
        f"{result['task_clusters']} task clusters; comparisons are descriptive only, "
        "with no confidence intervals.",
        "",
        "| Condition | Variant | Pairs | Saved memory | Content read | Task check passed |",
        "|---|---|---:|---|---|---|",
    ]
    for group in result["groups"]:
        cells = [
            f"{group['endpoints'][key]['yes']}/{group['scheduled_pairs']} "
            f"({group['endpoints'][key]['unknown']} unknown)"
            for key in ("establish_write", "goal_content_read", "task_check_passed")
        ]
        lines.append(
            f"| {group['condition']} | {group['variant']} | {group['scheduled_pairs']} | "
            + " | ".join(cells)
            + " |"
        )
    (out / "report.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    write_analysis(args.root, args.out)


if __name__ == "__main__":
    main()
