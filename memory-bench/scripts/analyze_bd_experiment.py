#!/usr/bin/env python3
"""Analyze a frozen local bd experiment without running agents or rescoring transcripts.

Run from memory-bench: python scripts/analyze_bd_experiment.py EXPERIMENT --out ANALYSIS.
The schedule, not completed artifacts, supplies every denominator. Bootstrap units are
work IDs, retaining their repeats, twins and conditions; incomplete observations stay visible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import fmean
from typing import Any

from membench.runner.bd_experiment import _pair_dir
from membench.runner.resume_cache import digest

ROLES = ("establish", "goal")
ENDPOINTS = ("capture", "observed_recall", "recall_before_action", "handoff", "goal_action_success")
COUNTERS = (
    "bd_read_attempts",
    "bd_write_attempts",
    "bd_accepted_writes",
    "native_read_attempts",
    "native_write_attempts",
    "hook_reaches",
)
COSTS = (
    "duration_ms",
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "estimated_usd",
)
SMALL_CLUSTER_COUNT = 10  # Reporting caution, not a significance or quality gate.


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Expected numeric evidence, got {value!r}")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"Invalid numeric evidence: {value!r}")
    return float(value)


def leg_costs(leg: Mapping[str, Any]) -> dict[str, float | None]:
    """Final CLI result is a cumulative session snapshot; never sum duplicate snapshots."""
    result: dict[str, Any] = {}
    for line in str(leg.get("stream", "")).splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            result = event
    usage = result.get("usage") or {}
    if not isinstance(usage, dict):
        raise ValueError("CLI result usage is not an object")
    return {
        "duration_ms": number(result.get("duration_ms")),
        "estimated_usd": number(result.get("total_cost_usd")),
        **{key: number(usage.get(key)) for key in COSTS if key.endswith("tokens")},
    }


def endpoint(leg: Mapping[str, Any] | None, key: str) -> bool | None:
    if leg is None or leg.get("status") != "ok":
        return None
    evidence = leg.get("bd_evidence")
    if not isinstance(evidence, dict):
        return None
    value = evidence.get(key)
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"Nonboolean endpoint {key}: {value!r}")
    if value is False and key != "goal_action_success" and evidence.get("bd_evidence_unknown"):
        return None
    return value


def load_legs(
    directory: Path, pair: Mapping[str, Any], cell: Mapping[str, Any]
) -> list[dict[str, Any]]:
    legs: list[dict[str, Any]] = []
    for path in sorted((directory / "legs").glob("*.json")):
        leg = read_object(path)
        role = leg.get("role")
        if role not in ROLES or any(old["role"] == role for old in legs):
            raise ValueError(f"Unexpected or duplicate leg role: {path}")
        if any(leg.get(key) != pair[key] for key in ("work_id", "variant")):
            raise ValueError(f"Leg identity mismatch: {path}")
        if leg.get("leg") != ROLES.index(role):
            raise ValueError(f"Leg index mismatch: {path}")
        ev = leg.get("bd_evidence")
        if ev is not None and any(ev.get(key) != leg.get(key) for key in ("role", "leg", "status")):
            raise ValueError(f"Leg evidence identity mismatch: {path}")
        legs.append(leg)
    saved_evidence = cell.get("bd_evidence")
    if saved_evidence is not None:
        indexed = {ev["leg"]: ev for ev in saved_evidence}
        if len(indexed) != len(saved_evidence) or any(
            indexed.get(leg["leg"]) != leg.get("bd_evidence") for leg in legs
        ):
            raise ValueError(f"Cell and leg evidence disagree: {directory}")
    return legs


def hook_delta(leg: Mapping[str, Any], by_role: Mapping[str, Mapping[str, Any]]) -> float | None:
    """The stored hook log spans both legs; the goal's recorded count is cumulative."""
    count = number(leg.get("hook_reaches"))
    if leg["role"] == "establish" or count is None:
        return count
    previous = number(by_role.get("establish", {}).get("hook_reaches"))
    if previous is None:
        return None
    if count < previous:
        raise ValueError("Cumulative hook reaches decreased between legs")
    return count - previous


def load_pair(root: Path, manifest: Mapping[str, Any], pair: Mapping[str, Any]) -> dict[str, Any]:
    directory = _pair_dir(root, pair)
    cell_path = directory / "cell.json"
    cell: dict[str, Any] = {}
    for path in (directory / "started.json", cell_path):
        if path.exists():
            saved = read_object(path)
            if saved.get("pair") != pair or saved.get("manifest_digest") != digest(manifest):
                raise ValueError(f"Pair identity mismatch: {path}")
            if path == cell_path:
                cell = saved["cell"]
    legs = load_legs(directory, pair, cell)
    by_role = {leg["role"]: leg for leg in legs}
    capture = endpoint(by_role.get("establish"), "bd_capture_complete")
    goal = by_role.get("goal")
    metrics = {
        "capture": capture,
        "observed_recall": endpoint(goal, "bd_recall_complete"),
        "recall_before_action": endpoint(goal, "bd_recall_before_action"),
        "goal_action_success": endpoint(goal, "goal_action_success"),
    }
    values = list(metrics.values())
    metrics["handoff"] = False if False in values else (True if all(values) else None)
    return {
        **pair,
        "completed": cell_path.exists(),
        "recorded_legs": len(legs),
        "measured_legs": sum(leg.get("status") == "ok" for leg in legs),
        "metrics": metrics,
        "legs": [
            {
                "role": leg["role"],
                "status": leg["status"],
                "costs": leg_costs(leg),
                "counters": {
                    key: (
                        hook_delta(leg, by_role)
                        if key == "hook_reaches"
                        else number((leg.get("bd_evidence") or {}).get(key))
                    )
                    for key in COUNTERS
                },
                "unknown_reasons": (leg.get("bd_evidence") or {}).get(
                    "bd_evidence_unknown_reasons", []
                ),
            }
            for leg in legs
        ],
    }


def binary_summary(values: Sequence[bool | None]) -> dict[str, Any]:
    success = sum(value is True for value in values)
    failure = sum(value is False for value in values)
    unknown = len(values) - success - failure
    return {
        "success": success,
        "failure": failure,
        "unknown": unknown,
        "scheduled": len(values),
        "observed_rate": success / (success + failure) if success + failure else None,
        "scheduled_rate_bounds": (
            [success / len(values), (success + unknown) / len(values)] if values else [None, None]
        ),
    }


def numeric_summary(values: Sequence[float | None], scheduled: int) -> dict[str, Any]:
    known = [v for v in values if v is not None]
    return {
        "sum": sum(known) if known else None,
        "mean_per_observed_leg": fmean(known) if known else None,
        "observed_legs": len(known),
        "unknown_legs": scheduled - len(known),
    }


def group_summary(rows: Sequence[dict[str, Any]], condition: str, variant: str) -> dict[str, Any]:
    selected = [
        r
        for r in rows
        if r["condition"] == condition and (variant == "all" or r["variant"] == variant)
    ]
    legs = [leg for row in selected for leg in row["legs"]]
    scheduled_legs = 2 * len(selected)
    return {
        "condition": condition,
        "variant": variant,
        "scheduled_pairs": len(selected),
        "completed_pairs": sum(row["completed"] for row in selected),
        "incomplete_pairs": sum(not row["completed"] for row in selected),
        "recorded_legs": len(legs),
        "missing_legs": scheduled_legs - len(legs),
        "metrics": {
            key: binary_summary([r["metrics"][key] for r in selected]) for key in ENDPOINTS
        },
        "counters": {
            key: numeric_summary([leg["counters"][key] for leg in legs], scheduled_legs)
            for key in COUNTERS
        },
        "unnecessary_goal_bd_reads": numeric_summary(
            [
                leg["counters"]["bd_read_attempts"]
                for row in selected
                if row["variant"] == "unnecessary"
                for leg in row["legs"]
                if leg["role"] == "goal"
            ],
            sum(row["variant"] == "unnecessary" for row in selected),
        ),
        "costs": {
            key: numeric_summary([leg["costs"][key] for leg in legs], scheduled_legs)
            for key in COSTS
        },
    }


def contrast(
    rows: Sequence[dict[str, Any]],
    condition: str,
    variant: str,
    metric: str,
    *,
    samples: int,
    seed: int,
    baseline: str = "generic",
) -> dict[str, Any]:
    selected = [r for r in rows if variant == "all" or r["variant"] == variant]
    baseline_values = {
        (r["work_id"], r["variant"], r["repeat"]): r["metrics"][metric]
        for r in selected
        if r["condition"] == baseline
    }
    treatment = [r for r in selected if r["condition"] == condition]
    clusters: dict[str, list[float]] = {}
    for row in treatment:
        base = baseline_values.get((row["work_id"], row["variant"], row["repeat"]))
        value = row["metrics"][metric]
        if base is not None and value is not None:
            clusters.setdefault(row["work_id"], []).append(float(value) - float(base))
    differences = [v for values in clusters.values() for v in values]
    rng = random.Random(seed)
    ids = sorted(clusters)
    draws = (
        sorted(
            fmean(v for task in rng.choices(ids, k=len(ids)) for v in clusters[task])
            for _ in range(samples)
        )
        if ids
        else []
    )
    low, high = binary_summary([r["metrics"][metric] for r in treatment])["scheduled_rate_bounds"]
    base_low, base_high = binary_summary(list(baseline_values.values()))["scheduled_rate_bounds"]
    bounds = (
        [low - base_high, high - base_low]
        if low is not None and base_low is not None
        else [None, None]
    )
    return {
        "condition": condition,
        "baseline": baseline,
        "variant": variant,
        "metric": metric,
        "matched_pairs": len(differences),
        "unmatched_or_unknown_pairs": len(treatment) - len(differences),
        "task_clusters": len(ids),
        "difference": fmean(differences) if differences else None,
        "bootstrap_95_interval": (
            [draws[int(0.025 * (samples - 1))], draws[int(0.975 * (samples - 1))]]
            if len(ids) >= 2
            else [None, None]
        ),
        "scheduled_difference_bounds": bounds,
        "interpretation": (
            "descriptive; few independent task clusters"
            if len(ids) < SMALL_CLUSTER_COUNT
            else "paired task-cluster percentile bootstrap; complete matched observations only"
        ),
    }


def analyze(root: Path, *, bootstrap_samples: int = 2000, seed: int = 20260904) -> dict[str, Any]:
    if bootstrap_samples < 1:
        raise ValueError("bootstrap_samples must be positive")
    manifest = read_object(root / "manifest.json")
    schedule = manifest["schedule"]
    conditions = list(manifest["conditions"])
    if "generic" not in conditions or len({digest(pair) for pair in schedule}) != len(schedule):
        raise ValueError("Schedule must have a generic baseline and unique pairs")
    for pair in schedule:
        if pair["condition"] not in conditions or pair["variant"] not in (
            "necessary",
            "unnecessary",
        ):
            raise ValueError("Unknown schedule condition or variant")
    units = {(p["work_id"], p["variant"], p["repeat"]) for p in schedule}
    identities = {(p["work_id"], p["variant"], p["repeat"], p["condition"]) for p in schedule}
    if identities != {(*unit, condition) for unit in units for condition in conditions}:
        raise ValueError("Schedule must be balanced across conditions for each task/variant/repeat")
    if manifest.get("planned_pairs", len(schedule)) != len(schedule):
        raise ValueError("Scheduled pair count disagrees with manifest")
    rows = [load_pair(root, manifest, pair) for pair in schedule]
    groups = [
        group_summary(rows, c, v) for c in conditions for v in ("necessary", "unnecessary", "all")
    ]
    comparisons = [(c, "generic") for c in conditions if c != "generic"]
    if "redirect" in conditions and "explicit" in conditions:
        comparisons.append(("redirect", "explicit"))
    contrasts = [
        contrast(rows, c, v, metric, samples=bootstrap_samples, seed=seed, baseline=base)
        for c, base in comparisons
        for v in ("necessary", "unnecessary", "all")
        for metric in ("handoff", "goal_action_success")
    ]
    return {
        "analysis_version": 1,
        "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "manifest_digest": digest(manifest),
        "manifest": manifest,
        "scheduled_pairs": len(rows),
        "bootstrap_samples": bootstrap_samples,
        "bootstrap_seed": seed,
        "notes": [
            "Endpoints use saved leg evidence; no post hoc transcript rescoring.",
            "Unknown outcomes remain in scheduled bounds; observed rates omit them explicitly.",
            "Bootstrap resamples work IDs retaining matched repeats, twins and conditions.",
            "Bootstrap intervals are descriptive for small task counts, not confirmatory claims.",
            "CLI final-result cost estimates are not billing receipts; missing costs are unknown.",
            "Duration is CLI-reported session duration, not independent wall-clock measurement.",
            "Counters include partial legs as observed lower bounds "
            "when transcripts are incomplete.",
            "Hook reaches are differenced within pairs because their saved counts are cumulative.",
        ],
        "groups": groups,
        "contrasts": contrasts,
        "pairs": rows,
    }


def markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# bd memory experiment",
        "",
        f"Scheduled pairs: {report['scheduled_pairs']}. "
        f"Manifest: `{report['manifest_digest']}`.",
        "",
        "| Condition | Variant | Complete / scheduled | Handoff yes / no / unknown "
        "| Goal yes / no / unknown |",
        "|---|---|---:|---:|---:|",
    ]
    for group in report["groups"]:
        if group["variant"] == "all":
            continue
        counts = [
            " / ".join(
                str(group["metrics"][key][part]) for part in ("success", "failure", "unknown")
            )
            for key in ("handoff", "goal_action_success")
        ]
        lines.append(
            f"| {group['condition']} | {group['variant']} | {group['completed_pairs']} / "
            f"{group['scheduled_pairs']} | {counts[0]} | {counts[1]} |"
        )
    lines += [
        "",
        "Unknown outcomes are retained in the JSON scheduled-denominator bounds.",
        "",
        "| Treatment minus baseline | Variant | Endpoint | Difference "
        "| Cluster bootstrap 95% | Task clusters |",
        "|---|---|---|---:|---|---:|",
    ]
    for row in report["contrasts"]:
        if row["variant"] != "all":
            lines.append(
                f"| {row['condition']} minus {row['baseline']} | {row['variant']} | "
                f"{row['metric']} | "
                f"{row['difference']} | {row['bootstrap_95_interval']} | {row['task_clusters']} |"
            )
    lines += [
        "",
        "| Condition | Variant | bd reads / writes | Unnecessary goal reads "
        "| Native reads / writes | CLI estimated USD | Cost-unknown legs |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for group in report["groups"]:
        if group["variant"] == "all":
            continue
        counts = group["counters"]
        cost = group["costs"]["estimated_usd"]
        lines.append(
            f"| {group['condition']} | {group['variant']} | "
            f"{counts['bd_read_attempts']['sum']} / {counts['bd_write_attempts']['sum']} | "
            f"{group['unnecessary_goal_bd_reads']['sum']} | "
            f"{counts['native_read_attempts']['sum']} / {counts['native_write_attempts']['sum']} | "
            f"{cost['sum']} | {cost['unknown_legs']} |"
        )
    return "\n".join([*lines, "", *report["notes"], ""])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260904)
    args = parser.parse_args(argv)
    report = analyze(args.experiment, bootstrap_samples=args.bootstrap_samples, seed=args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "analysis.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    (args.out / "report.md").write_text(markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
