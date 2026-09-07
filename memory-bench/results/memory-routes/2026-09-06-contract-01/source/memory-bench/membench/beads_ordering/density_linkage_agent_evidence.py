from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import fmean, median

from membench.beads_ordering.models import OrderingRunResult

_PRIMARY_POLICIES = ("key", "pagerank", "bm25f")
_PROVENANCE_FIELDS = (
    "mem_git_sha",
    "mem_git_dirty",
    "mem_git_diff_sha256",
    "beads_git_sha",
    "beads_git_dirty",
    "beads_git_diff_sha256",
    "beads_bin_sha256",
    "structural_order_source_git_sha",
    "agent_model",
    "agent_cli_version",
)
_CELL_METRICS = (
    "pages_requested",
    "compact_records_visible",
    "compact_tokens_to_first_useful",
    "retrieval_tokens_to_first_useful",
    "retrieval_related_tokens",
    "tool_calls_to_first_useful",
    "retrieval_tool_calls",
    "time_to_first_useful_ms",
    "full_recalls",
    "graph_hops_total",
    "branching_factor_mean",
    "branching_factor_max",
    "retrieval_latency_ms",
    "server_candidate_generation_ms",
    "server_ordering_ms",
    "end_to_end_ms",
    "task_success",
    "abstained",
    "premature_stop",
)
_ContrastValues = dict[str, list[tuple[Mapping[str, object], float]]]


def _as_int(value: object) -> int:
    if isinstance(value, (int, str)):
        return int(value)
    raise TypeError(f"expected integer-compatible value, got {type(value).__name__}")


def _percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _distribution(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "mean": None, "p50": None, "p90": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": fmean(values),
        "p50": _percentile(values, 0.5),
        "p90": _percentile(values, 0.9),
        "min": min(values),
        "max": max(values),
    }


def hierarchical_summary(
    values: Sequence[tuple[str, str, float]],
    *,
    statistic: str = "mean",
    seed: int,
    resamples: int,
) -> dict[str, float | int | None]:
    """Bootstrap graph families, then tasks within family, as preregistered."""

    if not values:
        return {
            **_distribution([]),
            "estimate": None,
            "low": None,
            "high": None,
            "clusters": 0,
            "tasks": 0,
        }
    by_family_task: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for family, task_id, value in values:
        by_family_task[family][task_id].append(value)
    task_values = {
        family: {task: fmean(observations) for task, observations in tasks.items()}
        for family, tasks in by_family_task.items()
    }
    flattened = [value for tasks in task_values.values() for value in tasks.values()]

    def calculate(sample: Sequence[float]) -> float:
        if statistic == "mean":
            return fmean(sample)
        if statistic == "median":
            return median(sample)
        raise ValueError(f"unsupported bootstrap statistic: {statistic}")

    rng = random.Random(seed)
    families = sorted(task_values)
    sampled: list[float] = []
    for _ in range(resamples):
        observations: list[float] = []
        for family in (rng.choice(families) for _ in families):
            tasks = sorted(task_values[family])
            observations.extend(task_values[family][rng.choice(tasks)] for _ in range(len(tasks)))
        sampled.append(calculate(observations))
    return {
        **_distribution(flattened),
        "estimate": calculate(flattened),
        "low": _percentile(sampled, 0.05),
        "high": _percentile(sampled, 0.95),
        "clusters": len(families),
        "tasks": len(flattened),
    }


def validate_density_linkage_agent_grid(
    rows: Sequence[OrderingRunResult],
    task_metadata: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    run_ids = [row.run_id for row in rows]
    counts: dict[str, int] = defaultdict(int)
    for run_id in run_ids:
        counts[run_id] += 1
    duplicate_ids = sorted(run_id for run_id, count in counts.items() if count > 1)
    embedded_failures = sorted(row.run_id for row in rows if row.failure is not None)
    provenance = {
        field: len({str(getattr(row, field)) for row in rows}) for field in _PROVENANCE_FIELDS
    }
    profile_rows: dict[tuple[object, ...], list[OrderingRunResult]] = defaultdict(list)
    for row in rows:
        profile_rows[tuple(getattr(row, field) for field in _PROVENANCE_FIELDS)].append(row)
    provenance_profiles = [
        {
            **dict(zip(_PROVENANCE_FIELDS, profile, strict=True)),
            "observation_count": len(profile_observations),
            "embedded_failure_count": sum(row.failure is not None for row in profile_observations),
        }
        for profile, profile_observations in sorted(profile_rows.items())
    ]
    return {
        "observation_count": len(rows),
        "unique_run_count": len(set(run_ids)),
        "duplicate_run_ids": duplicate_ids,
        "embedded_failure_count": len(embedded_failures),
        "embedded_failure_run_ids": embedded_failures,
        "unknown_task_ids": sorted({row.task_id for row in rows} - set(task_metadata)),
        "provenance_cardinality": provenance,
        "provenance_profiles": provenance_profiles,
        "provenance_consistent": all(count == 1 for count in provenance.values()),
        "factor_inventory": {
            "arms": sorted({row.arm.value for row in rows}),
            "modes": sorted({row.mode.value for row in rows}),
            "page_sizes": sorted(
                {row.page_size for row in rows},
                key=lambda value: 10_000 if value == "all" else int(value),
            ),
            "candidate_counts": sorted({row.total_matched for row in rows}),
        },
    }


def _build_cells(
    rows: Sequence[OrderingRunResult],
    task_metadata: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    baseline_burial = {
        row.task_id: row.primary_rank
        for row in rows
        if row.arm.value == "key" and row.failure is None
    }
    grouped: dict[tuple[str, str, str, str], list[OrderingRunResult]] = defaultdict(list)
    for row in rows:
        if row.failure is None:
            grouped[(row.task_id, row.mode.value, row.page_size, row.arm.value)].append(row)
    cells: list[dict[str, object]] = []
    for (task_id, mode, page_size, arm), observations in sorted(grouped.items()):
        metadata = task_metadata.get(task_id)
        if metadata is None:
            raise ValueError(f"missing density/linkage metadata for {task_id}")
        first = observations[0]
        cell: dict[str, object] = {
            "task_id": task_id,
            "base_task_id": str(metadata["base_task_id"]),
            "graph_family": str(metadata["graph_family"]),
            "failure_case": str(metadata["failure_case"]),
            "candidate_count": _as_int(metadata["candidate_count"]),
            "linkage_level": str(metadata["linkage_level"]),
            "baseline_burial_depth": _as_int(
                metadata["baseline_burial_depth"]
                if "baseline_burial_depth" in metadata
                else baseline_burial[task_id]
            ),
            "mode": mode,
            "page_size": page_size,
            "arm": arm,
            "repeats": len(observations),
            "primary_rank": first.primary_rank,
            "primary_page": first.primary_page,
            "acceptable_rank": first.acceptable_rank,
            "acceptable_page": first.acceptable_page,
            "page_one_acceptable_visible": float(first.page_one_acceptable_visible),
        }
        for metric in _CELL_METRICS:
            numeric = [
                float(value) for row in observations if (value := getattr(row, metric)) is not None
            ]
            cell[metric] = fmean(numeric) if numeric else None
        relevant_first = [row for row in observations if row.first_recalled_relevant is True]
        cell["first_recalled_relevant"] = fmean(
            float(row.first_recalled_relevant is True) for row in observations
        )
        cell["correct_use_failure_after_relevant_first"] = (
            fmean(float(not row.task_success) for row in relevant_first) if relevant_first else None
        )
        cells.append(cell)
    return cells


def _value(cell: Mapping[str, object], field: str) -> float:
    value = cell[field]
    if not isinstance(value, (bool, int, float)):
        raise TypeError(f"{field} is not numeric in {cell['task_id']}")
    return float(value)


def _summary(
    rows: Sequence[tuple[Mapping[str, object], float]],
    *,
    statistic: str,
    seed: int,
    resamples: int,
) -> dict[str, float | int | None]:
    return hierarchical_summary(
        [(str(cell["graph_family"]), str(cell["base_task_id"]), value) for cell, value in rows],
        statistic=statistic,
        seed=seed,
        resamples=resamples,
    )


def _curve_rows(
    cells: Sequence[Mapping[str, object]],
    *,
    seed: int,
    resamples: int,
) -> list[dict[str, object]]:
    grouped: dict[tuple[int, str, str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for cell in cells:
        grouped[
            (
                _as_int(cell["candidate_count"]),
                str(cell["linkage_level"]),
                str(cell["arm"]),
                str(cell["page_size"]),
                str(cell["mode"]),
            )
        ].append(cell)
    curves: list[dict[str, object]] = []
    for key, group in sorted(grouped.items()):
        candidate_count, linkage, arm, page_size, mode = key
        curves.append(
            {
                "candidate_count": candidate_count,
                "linkage_level": linkage,
                "arm": arm,
                "page_size": page_size,
                "mode": mode,
                "task_count": len(group),
                "task_success_rate": _summary(
                    [(cell, _value(cell, "task_success")) for cell in group],
                    statistic="mean",
                    seed=seed,
                    resamples=resamples,
                ),
                "page_one_useful_probability": _summary(
                    [(cell, _value(cell, "page_one_acceptable_visible")) for cell in group],
                    statistic="mean",
                    seed=seed + 1,
                    resamples=resamples,
                ),
                **{
                    field: _distribution([_value(cell, field) for cell in group])
                    for field in (
                        "pages_requested",
                        "compact_tokens_to_first_useful",
                        "retrieval_related_tokens",
                        "retrieval_tool_calls",
                        "time_to_first_useful_ms",
                        "full_recalls",
                        "graph_hops_total",
                        "branching_factor_mean",
                        "retrieval_latency_ms",
                        "server_candidate_generation_ms",
                        "server_ordering_ms",
                        "end_to_end_ms",
                    )
                    if all(cell[field] is not None for cell in group)
                },
            }
        )
    return curves


def _policy_contrasts(
    cells: Sequence[Mapping[str, object]],
    *,
    seed: int,
    resamples: int,
) -> tuple[list[dict[str, object]], dict[tuple[object, ...], _ContrastValues]]:
    by_cell = {
        (
            str(cell["base_task_id"]),
            _as_int(cell["candidate_count"]),
            str(cell["linkage_level"]),
            str(cell["page_size"]),
            str(cell["mode"]),
            str(cell["arm"]),
        ): cell
        for cell in cells
    }
    groups: dict[tuple[object, ...], _ContrastValues] = {}
    output: list[dict[str, object]] = []
    base_tasks = sorted({str(cell["base_task_id"]) for cell in cells})
    factor_cells = sorted(
        {
            (
                _as_int(cell["candidate_count"]),
                str(cell["linkage_level"]),
                str(cell["page_size"]),
                str(cell["mode"]),
            )
            for cell in cells
        }
    )
    for reference, contender in (("key", "pagerank"), ("pagerank", "bm25f")):
        for candidate_count, linkage, page_size, mode in factor_cells:
            metrics: dict[str, list[tuple[Mapping[str, object], float]]] = defaultdict(list)
            for task in base_tasks:
                ref = by_cell.get((task, candidate_count, linkage, page_size, mode, reference))
                alt = by_cell.get((task, candidate_count, linkage, page_size, mode, contender))
                if ref is None or alt is None:
                    continue
                ref_tokens = _value(ref, "compact_tokens_to_first_useful")
                metrics["page_one_gain"].append(
                    (
                        ref,
                        _value(alt, "page_one_acceptable_visible")
                        - _value(ref, "page_one_acceptable_visible"),
                    )
                )
                metrics["pages_saved"].append(
                    (ref, _value(ref, "pages_requested") - _value(alt, "pages_requested"))
                )
                metrics["compact_token_reduction_fraction"].append(
                    (
                        ref,
                        (ref_tokens - _value(alt, "compact_tokens_to_first_useful"))
                        / max(1.0, ref_tokens),
                    )
                )
                metrics["task_success_delta"].append(
                    (ref, _value(alt, "task_success") - _value(ref, "task_success"))
                )
                metrics["retrieval_latency_ms_saved"].append(
                    (ref, _value(ref, "retrieval_latency_ms") - _value(alt, "retrieval_latency_ms"))
                )
                if (
                    ref["time_to_first_useful_ms"] is not None
                    and alt["time_to_first_useful_ms"] is not None
                ):
                    metrics["time_to_first_useful_ms_saved"].append(
                        (
                            ref,
                            _value(ref, "time_to_first_useful_ms")
                            - _value(alt, "time_to_first_useful_ms"),
                        )
                    )
            if not metrics:
                continue
            key = (candidate_count, linkage, page_size, mode, reference, contender)
            groups[key] = metrics
            output.append(
                {
                    "candidate_count": candidate_count,
                    "linkage_level": linkage,
                    "page_size": page_size,
                    "mode": mode,
                    "reference": reference,
                    "contender": contender,
                    "pair_count": len(metrics["pages_saved"]),
                    **{
                        name: _summary(
                            values,
                            statistic=(
                                "median"
                                if name in {"pages_saved", "compact_token_reduction_fraction"}
                                else "mean"
                            ),
                            seed=seed + index,
                            resamples=resamples,
                        )
                        for index, (name, values) in enumerate(sorted(metrics.items()))
                    },
                }
            )
    return output, groups


def _tail_distribution(values: Sequence[float]) -> dict[str, float | int | None]:
    result = _distribution(values)
    result["p10"] = _percentile(values, 0.1)
    return result


def _task_tail_summary(
    values: Sequence[tuple[Mapping[str, object], float]],
) -> dict[str, object]:
    ordered = sorted(
        values,
        key=lambda item: (item[1], str(item[0]["base_task_id"])),
    )

    def project(item: tuple[Mapping[str, object], float]) -> dict[str, object]:
        cell, value = item
        return {
            "base_task_id": str(cell["base_task_id"]),
            "graph_family": str(cell["graph_family"]),
            "value": value,
        }

    numeric = [value for _cell, value in values]
    return {
        **_tail_distribution(numeric),
        "negative_count": sum(value < 0 for value in numeric),
        "zero_count": sum(value == 0 for value in numeric),
        "positive_count": sum(value > 0 for value in numeric),
        "bottom": [project(item) for item in ordered[:3]],
        "top": [project(item) for item in reversed(ordered[-3:])],
    }


def _task_policy_tails(
    groups: Mapping[tuple[object, ...], _ContrastValues],
) -> list[dict[str, object]]:
    return [
        {
            "candidate_count": key[0],
            "linkage_level": key[1],
            "page_size": key[2],
            "mode": key[3],
            "reference": key[4],
            "contender": key[5],
            "pair_count": len(metrics["pages_saved"]),
            "metrics": {
                name: _task_tail_summary(values) for name, values in sorted(metrics.items())
            },
        }
        for key, metrics in sorted(groups.items())
    ]


def _family_policy_tails(
    groups: Mapping[tuple[object, ...], _ContrastValues],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for key, metrics in sorted(groups.items()):
        families = sorted(
            {str(cell["graph_family"]) for values in metrics.values() for cell, _value in values}
        )
        for family in families:
            family_metrics = {
                name: [(cell, value) for cell, value in values if cell["graph_family"] == family]
                for name, values in metrics.items()
            }
            output.append(
                {
                    "candidate_count": key[0],
                    "linkage_level": key[1],
                    "page_size": key[2],
                    "mode": key[3],
                    "reference": key[4],
                    "contender": key[5],
                    "graph_family": family,
                    "pair_count": len(family_metrics["pages_saved"]),
                    "metrics": {
                        name: _tail_distribution([value for _cell, value in values])
                        for name, values in sorted(family_metrics.items())
                        if values
                    },
                }
            )
    return output


def _linkage_interactions(
    groups: Mapping[tuple[object, ...], Mapping[str, Sequence[tuple[Mapping[str, object], float]]]],
    *,
    seed: int,
    resamples: int,
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    factor_keys = sorted({(key[0], key[2], key[3], key[4], key[5]) for key in groups})
    metric_names = {
        "page_one_gain": "page_one_gain_change_enriched_minus_sparse",
        "pages_saved": "pages_saved_change_enriched_minus_sparse",
        "compact_token_reduction_fraction": "compact_token_saving_change_enriched_minus_sparse",
        "task_success_delta": "task_success_change_enriched_minus_sparse",
    }
    for candidate_count, page_size, mode, reference, contender in factor_keys:
        sparse = groups.get((candidate_count, "sparse", page_size, mode, reference, contender))
        enriched = groups.get((candidate_count, "enriched", page_size, mode, reference, contender))
        if sparse is None or enriched is None:
            continue
        row: dict[str, object] = {
            "candidate_count": candidate_count,
            "page_size": page_size,
            "mode": mode,
            "reference": reference,
            "contender": contender,
        }
        for index, (metric, output_name) in enumerate(metric_names.items()):
            sparse_by_task = {
                str(cell["base_task_id"]): (cell, value) for cell, value in sparse[metric]
            }
            paired = [
                (cell, value - sparse_by_task[str(cell["base_task_id"])][1])
                for cell, value in enriched[metric]
                if str(cell["base_task_id"]) in sparse_by_task
            ]
            row[output_name] = _summary(
                paired,
                statistic=(
                    "median"
                    if metric in {"pages_saved", "compact_token_reduction_fraction"}
                    else "mean"
                ),
                seed=seed + index,
                resamples=resamples,
            )
        output.append(row)
    return output


def _density_contrasts(
    cells: Sequence[Mapping[str, object]],
    *,
    seed: int,
    resamples: int,
) -> list[dict[str, object]]:
    controls = {
        (
            str(cell["base_task_id"]),
            str(cell["linkage_level"]),
            str(cell["mode"]),
            _as_int(cell["candidate_count"]),
        ): cell
        for cell in cells
        if cell["arm"] == "control-semantic" and cell["page_size"] == "all"
    }
    grouped: dict[tuple[str, str], dict[str, list[tuple[Mapping[str, object], float]]]] = {}
    base_tasks = sorted({key[0] for key in controls})
    for linkage in sorted({key[1] for key in controls}):
        for mode in sorted({key[2] for key in controls}):
            metrics: dict[str, list[tuple[Mapping[str, object], float]]] = defaultdict(list)
            for task in base_tasks:
                low = controls.get((task, linkage, mode, 10))
                high = controls.get((task, linkage, mode, 150))
                if low is None or high is None:
                    continue
                metrics["task_success_drop_10_to_150"].append(
                    (low, _value(low, "task_success") - _value(high, "task_success"))
                )
                low_failure = low["correct_use_failure_after_relevant_first"]
                high_failure = high["correct_use_failure_after_relevant_first"]
                if isinstance(low_failure, (int, float)) and isinstance(high_failure, (int, float)):
                    metrics["correct_use_failure_increase_10_to_150"].append(
                        (low, float(high_failure) - float(low_failure))
                    )
                metrics["retrieval_token_growth_10_to_150"].append(
                    (
                        low,
                        _value(high, "retrieval_related_tokens")
                        - _value(low, "retrieval_related_tokens"),
                    )
                )
                metrics["end_to_end_ms_growth_10_to_150"].append(
                    (low, _value(high, "end_to_end_ms") - _value(low, "end_to_end_ms"))
                )
            grouped[(linkage, mode)] = metrics
    return [
        {
            "linkage_level": linkage,
            "mode": mode,
            "pair_count": len(metrics["task_success_drop_10_to_150"]),
            **{
                name: _summary(
                    values,
                    statistic=("mean" if "success" in name or "failure" in name else "median"),
                    seed=seed + index,
                    resamples=resamples,
                )
                for index, (name, values) in enumerate(sorted(metrics.items()))
            },
        }
        for (linkage, mode), metrics in sorted(grouped.items())
        if metrics
    ]


def _repeat_triggers(
    rows: Sequence[OrderingRunResult],
    task_metadata: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    initial = [row for row in rows if row.repeat == 0]
    policy_groups: dict[tuple[str, str, str], list[OrderingRunResult]] = defaultdict(list)
    for row in initial:
        if row.arm.value in _PRIMARY_POLICIES and row.failure is None:
            policy_groups[(row.task_id, row.mode.value, row.page_size)].append(row)
    policy_disagreements = [
        {
            "task_id": task_id,
            "mode": mode,
            "page_size": page_size,
            "repeat_indices": [1, 2],
        }
        for (task_id, mode, page_size), group in sorted(policy_groups.items())
        if len({row.arm.value for row in group}) == len(_PRIMARY_POLICIES)
        and len({row.task_success for row in group}) > 1
    ]
    controls: dict[tuple[str, str, str], dict[int, OrderingRunResult]] = defaultdict(dict)
    for row in initial:
        if row.arm.value != "control-semantic" or row.failure is not None:
            continue
        metadata = task_metadata[row.task_id]
        controls[
            (
                str(metadata["base_task_id"]),
                str(metadata["linkage_level"]),
                row.mode.value,
            )
        ][_as_int(metadata["candidate_count"])] = row
    density_disagreements = [
        {
            "base_task_id": key[0],
            "linkage_level": key[1],
            "mode": key[2],
            "repeat_indices": [1, 2],
        }
        for key, endpoints in sorted(controls.items())
        if {10, 150} <= endpoints.keys()
        and endpoints[10].task_success != endpoints[150].task_success
    ]
    return {
        "infrastructure_failures": [
            {"run_id": row.run_id, "repeat_indices": [1, 2]}
            for row in initial
            if row.failure is not None
        ],
        "policy_task_success_disagreements": policy_disagreements,
        "density_endpoint_disagreements": density_disagreements,
    }


def _bound(summary: object, name: str) -> float | None:
    if not isinstance(summary, Mapping):
        return None
    value = summary.get(name)
    return float(value) if isinstance(value, (int, float)) else None


def _lower_bound_at_least(summary: object, threshold: float) -> bool:
    low = _bound(summary, "low")
    return low is not None and low >= threshold


def _clears_magnitude(summary: object, threshold: float) -> bool:
    low = _bound(summary, "low")
    high = _bound(summary, "high")
    return low is not None and high is not None and (low >= threshold or high <= -threshold)


def _evaluate_decision_gates(
    density: Sequence[Mapping[str, object]],
    policies: Sequence[Mapping[str, object]],
    interactions: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    density_evidence = [
        {
            "linkage_level": row["linkage_level"],
            "mode": row["mode"],
            "success_drop_clears": _lower_bound_at_least(
                row.get("task_success_drop_10_to_150"), 0.1
            ),
            "correct_use_failure_clears": _lower_bound_at_least(
                row.get("correct_use_failure_increase_10_to_150"), 0.1
            ),
        }
        for row in density
    ]
    policy_index = {
        (
            row.get("candidate_count"),
            row.get("linkage_level"),
            row.get("page_size"),
            row.get("mode"),
            row.get("reference"),
            row.get("contender"),
        ): row
        for row in policies
    }
    interaction_evidence: list[dict[str, object]] = []
    for row in interactions:
        if (
            row.get("reference") != "key"
            or row.get("contender") != "pagerank"
            or row.get("mode") != "navigation"
            or row.get("page_size") != "5"
        ):
            continue
        candidate_count = row.get("candidate_count")
        enriched = policy_index.get(
            (candidate_count, "enriched", "5", "navigation", "key", "pagerank")
        )
        success_estimate = (
            _bound(enriched.get("task_success_delta"), "estimate") if enriched is not None else None
        )
        clears = (
            any(
                (
                    _clears_magnitude(row.get("page_one_gain_change_enriched_minus_sparse"), 0.15),
                    _clears_magnitude(row.get("pages_saved_change_enriched_minus_sparse"), 1.0),
                    _clears_magnitude(
                        row.get("compact_token_saving_change_enriched_minus_sparse"), 0.2
                    ),
                )
            )
            and success_estimate is not None
            and success_estimate >= -0.05
        )
        interaction_evidence.append({"candidate_count": candidate_count, "clears": clears})

    structural_evidence: list[dict[str, object]] = []
    for row in policies:
        if (
            row.get("reference") != "key"
            or row.get("contender") != "pagerank"
            or row.get("mode") != "navigation"
            or row.get("page_size") != "5"
            or row.get("linkage_level") not in {"sparse", "native"}
        ):
            continue
        benefit = _lower_bound_at_least(row.get("page_one_gain"), 0.15) or _lower_bound_at_least(
            row.get("compact_token_reduction_fraction"), 0.1
        )
        noninferior = _lower_bound_at_least(row.get("task_success_delta"), -0.05)
        structural_evidence.append(
            {
                "candidate_count": row["candidate_count"],
                "linkage_level": row["linkage_level"],
                "benefit_clears": benefit,
                "success_noninferior": noninferior,
                "supports": benefit and noninferior,
            }
        )

    query_evidence: list[dict[str, object]] = []
    for row in policies:
        if (
            row.get("reference") != "pagerank"
            or row.get("contender") != "bm25f"
            or row.get("candidate_count") != 150
            or row.get("mode") != "navigation"
            or row.get("page_size") != "5"
            or row.get("linkage_level") not in {"native", "enriched"}
        ):
            continue
        cost_clears = _lower_bound_at_least(row.get("pages_saved"), 1.0) or _lower_bound_at_least(
            row.get("compact_token_reduction_fraction"), 0.2
        )
        no_regression = _lower_bound_at_least(row.get("task_success_delta"), 0)
        query_evidence.append(
            {
                "linkage_level": row["linkage_level"],
                "cost_clears": cost_clears,
                "no_success_regression": no_regression,
                "supports": cost_clears and no_regression,
            }
        )
    query_levels = {str(row["linkage_level"]) for row in query_evidence if row["supports"]}
    return {
        "candidate_density_behaviorally_material": any(
            row["success_drop_clears"] or row["correct_use_failure_clears"]
            for row in density_evidence
        ),
        "pagerank_benefit_link_dependent": any(bool(row["clears"]) for row in interaction_evidence),
        "structural_default_supported": any(bool(row["supports"]) for row in structural_evidence),
        "query_specific_beads_ownership_supported": query_levels == {"native", "enriched"},
        "density_evidence": density_evidence,
        "linkage_interaction_evidence": interaction_evidence,
        "structural_default_evidence": structural_evidence,
        "query_specific_ownership_evidence": query_evidence,
    }


def analyze_density_linkage_agents(
    rows: Sequence[OrderingRunResult],
    task_metadata: Mapping[str, Mapping[str, object]],
    *,
    bootstrap_seed: int = 5879,
    bootstrap_resamples: int = 5000,
) -> dict[str, object]:
    if not rows:
        raise ValueError("density/linkage agent analysis needs observations")
    integrity = validate_density_linkage_agent_grid(rows, task_metadata)
    if integrity["duplicate_run_ids"]:
        raise ValueError("density/linkage agent inputs contain duplicate run IDs")
    if integrity["unknown_task_ids"]:
        raise ValueError("density/linkage agent inputs contain unknown task IDs")
    cells = _build_cells(rows, task_metadata)
    policy_contrasts, contrast_groups = _policy_contrasts(
        cells, seed=bootstrap_seed, resamples=bootstrap_resamples
    )
    interactions = _linkage_interactions(
        contrast_groups, seed=bootstrap_seed + 100, resamples=bootstrap_resamples
    )
    density = _density_contrasts(cells, seed=bootstrap_seed + 200, resamples=bootstrap_resamples)
    return {
        "schema_version": 1,
        "evidence_kind": "repeat-balanced agent outcomes over frozen candidate sets",
        "integrity": integrity,
        "usable_observation_count": sum(row.failure is None for row in rows),
        "cell_count": len(cells),
        "base_task_count": len({str(cell["base_task_id"]) for cell in cells}),
        "variant_count": len({str(cell["task_id"]) for cell in cells}),
        "bootstrap": {
            "confidence_level": 0.9,
            "seed": bootstrap_seed,
            "resamples": bootstrap_resamples,
            "cluster_order": ["graph_family", "base_task_id"],
        },
        "curves": _curve_rows(cells, seed=bootstrap_seed, resamples=bootstrap_resamples),
        "density_endpoint_contrasts": density,
        "policy_contrasts": policy_contrasts,
        "family_policy_tails": _family_policy_tails(contrast_groups),
        "task_policy_tails": _task_policy_tails(contrast_groups),
        "linkage_interactions": interactions,
        "decision_gates": _evaluate_decision_gates(density, policy_contrasts, interactions),
        "targeted_repeat_triggers": _repeat_triggers(rows, task_metadata),
        "cells": cells,
    }


def _repeat_run_id(row: OrderingRunResult, repeat: int) -> str:
    return f"{row.task_id}:{row.mode.value}:{row.arm.value}:" f"p{row.page_size}:r{repeat}"


def build_density_linkage_replication_manifest(
    task_metadata: Mapping[str, Mapping[str, object]],
    *,
    primary_analysis_sha256: str,
    model: str,
    expected_base_task_count: int = 21,
) -> dict[str, object]:
    """Seal the smallest factor slice that exercises all ordering decision gates."""

    if len(primary_analysis_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in primary_analysis_sha256
    ):
        raise ValueError("primary analysis SHA-256 must be lowercase hexadecimal")
    if not model or expected_base_task_count < 1:
        raise ValueError("model and expected base-task count are required")

    linkage_levels = ("sparse", "native", "enriched")
    arms = _PRIMARY_POLICIES
    selected_tasks: list[str] = []
    base_tasks_by_linkage: dict[str, set[str]] = defaultdict(set)
    for task_id, metadata in sorted(task_metadata.items()):
        linkage = str(metadata["linkage_level"])
        if _as_int(metadata["candidate_count"]) != 150 or linkage not in linkage_levels:
            continue
        selected_tasks.append(task_id)
        base_tasks_by_linkage[linkage].add(str(metadata["base_task_id"]))

    expected = set.union(*(base_tasks_by_linkage[level] for level in linkage_levels))
    if len(expected) != expected_base_task_count or any(
        base_tasks_by_linkage[level] != expected for level in linkage_levels
    ):
        raise ValueError("replication slice does not contain every base task at each linkage level")

    run_ids = sorted(
        f"{task_id}:navigation:{arm}:p5:r0" for task_id in selected_tasks for arm in arms
    )
    return {
        "schema_version": 1,
        "status": "sealed-before-secondary-configuration-outcomes",
        "selection_rule": "registered decision-edge factors only",
        "primary_analysis_sha256": primary_analysis_sha256,
        "selected_cell_count": len(run_ids),
        "base_task_count": len(expected),
        "factors": {
            "candidate_count": 150,
            "page_size": "5",
            "mode": "navigation",
            "linkage_levels": list(linkage_levels),
            "arms": list(arms),
            "repeat": 0,
        },
        "secondary_configuration": {
            "model": model,
            "max_tool_calls": 12,
            "agent_settings": {"autoMemoryEnabled": False},
        },
        "run_ids": run_ids,
    }


def _interval_touches_magnitude(summary: Mapping[str, object], threshold: float) -> bool:
    low = summary.get("low")
    high = summary.get("high")
    if not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
        return False
    return float(low) <= threshold <= float(high) or float(low) <= -threshold <= float(high)


def build_density_linkage_repeat_manifest(
    rows: Sequence[OrderingRunResult],
    task_metadata: Mapping[str, Mapping[str, object]],
    analysis: Mapping[str, object],
) -> dict[str, object]:
    """Expand the locked repeat rules into exact, deduplicated run IDs."""

    by_key = {
        (row.task_id, row.mode.value, row.page_size, row.arm.value): row
        for row in rows
        if row.repeat == 0
    }
    reasons_by_run: dict[str, set[str]] = defaultdict(set)

    def select(row: OrderingRunResult, reason: str) -> None:
        for repeat in (1, 2):
            reasons_by_run[_repeat_run_id(row, repeat)].add(reason)

    triggers = analysis.get("targeted_repeat_triggers")
    if not isinstance(triggers, Mapping):
        raise ValueError("analysis has no targeted repeat triggers")
    failures = triggers.get("infrastructure_failures")
    if isinstance(failures, Sequence):
        by_run_id = {row.run_id: row for row in rows if row.repeat == 0}
        for trigger in failures:
            if isinstance(trigger, Mapping) and str(trigger["run_id"]) in by_run_id:
                select(by_run_id[str(trigger["run_id"])], "infrastructure-failure")
    disagreements = triggers.get("policy_task_success_disagreements")
    if isinstance(disagreements, Sequence):
        for trigger in disagreements:
            if not isinstance(trigger, Mapping):
                continue
            for arm in _PRIMARY_POLICIES:
                row = by_key.get(
                    (
                        str(trigger["task_id"]),
                        str(trigger["mode"]),
                        str(trigger["page_size"]),
                        arm,
                    )
                )
                if row is not None:
                    select(row, "policy-task-success-disagreement")
    density = triggers.get("density_endpoint_disagreements")
    if isinstance(density, Sequence):
        for trigger in density:
            if not isinstance(trigger, Mapping):
                continue
            for task_id, metadata in task_metadata.items():
                if (
                    str(metadata["base_task_id"]) != str(trigger["base_task_id"])
                    or str(metadata["linkage_level"]) != str(trigger["linkage_level"])
                    or _as_int(metadata["candidate_count"]) not in {10, 150}
                ):
                    continue
                row = by_key.get(
                    (
                        task_id,
                        str(trigger["mode"]),
                        "all",
                        "control-semantic",
                    )
                )
                if row is not None:
                    select(row, "density-endpoint-disagreement")

    interactions = analysis.get("linkage_interactions")
    interaction_thresholds = {
        "page_one_gain_change_enriched_minus_sparse": 0.15,
        "pages_saved_change_enriched_minus_sparse": 1.0,
        "compact_token_saving_change_enriched_minus_sparse": 0.2,
    }
    if isinstance(interactions, Sequence):
        for interaction in interactions:
            if not isinstance(interaction, Mapping):
                continue
            if (
                interaction.get("reference") != "key"
                or interaction.get("contender") != "pagerank"
                or interaction.get("mode") != "navigation"
                or interaction.get("page_size") != "5"
            ):
                continue
            touched: list[str] = []
            for name, threshold in interaction_thresholds.items():
                summary = interaction.get(name)
                if isinstance(summary, Mapping) and _interval_touches_magnitude(summary, threshold):
                    touched.append(name)
            if not touched:
                continue
            candidate_count = _as_int(interaction["candidate_count"])
            reason = "interaction-ci-touches-threshold:" + ",".join(sorted(touched))
            for task_id, metadata in task_metadata.items():
                if _as_int(metadata["candidate_count"]) != candidate_count:
                    continue
                if str(metadata["linkage_level"]) not in {"sparse", "enriched"}:
                    continue
                for arm in ("key", "pagerank"):
                    row = by_key.get((task_id, "navigation", "5", arm))
                    if row is not None:
                        select(row, reason)

    cells = [
        {"run_id": run_id, "reasons": sorted(reasons)}
        for run_id, reasons in sorted(reasons_by_run.items())
    ]
    reason_counts: dict[str, int] = defaultdict(int)
    for cell in cells:
        for reason in cell["reasons"]:
            prefix = str(reason).split(":", 1)[0]
            reason_counts[prefix] += 1
    return {
        "schema_version": 1,
        "status": "selected-after-initial-grid-before-targeted-repeat-outcomes",
        "selection_rule": "density-linkage-preregistration targeted-repeat rule",
        "repeat_indices": [1, 2],
        "selected_cell_count": len(cells),
        "reason_counts": dict(sorted(reason_counts.items())),
        "cells": cells,
        "run_ids": [str(cell["run_id"]) for cell in cells],
    }


def write_density_linkage_repeat_manifest(
    rows: Sequence[OrderingRunResult],
    task_metadata: Mapping[str, Mapping[str, object]],
    analysis: Mapping[str, object],
    out: Path,
    *,
    initial_analysis_sha256: str,
) -> dict[str, object]:
    manifest = build_density_linkage_repeat_manifest(rows, task_metadata, analysis)
    manifest["initial_analysis_sha256"] = initial_analysis_sha256
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def render_density_linkage_agent_report(analysis: Mapping[str, object]) -> str:
    integrity = analysis["integrity"]
    if not isinstance(integrity, Mapping):
        raise ValueError("analysis has no integrity summary")
    lines = [
        "# Candidate-density and linkage agent evidence",
        "",
        (
            f"{analysis['usable_observation_count']} usable observations from "
            f"{analysis['base_task_count']} base tasks; "
            f"{integrity['embedded_failure_count']} embedded infrastructure failures."
        ),
        "",
        "Repeated density and linkage variants are paired within base task and graph family. "
        "Intervals are 90% hierarchical cluster bootstraps (family, then task).",
        "",
        "## Registered decision gates",
        "",
    ]
    gates = analysis.get("decision_gates")
    if isinstance(gates, Mapping):
        for key in (
            "candidate_density_behaviorally_material",
            "pagerank_benefit_link_dependent",
            "structural_default_supported",
            "query_specific_beads_ownership_supported",
        ):
            lines.append(f"- {key.replace('_', ' ')}: **{bool(gates.get(key))}**")
    lines.extend(
        [
            "",
            "## Navigation, page size 5",
            "",
            "| candidates | links | policy | success [90% CI] | page-one useful | "
            "pages p50/p90 | compact tokens p50/p90 |",
            "|---:|---|---|---:|---:|---:|---:|",
        ]
    )
    curves = analysis["curves"]
    if not isinstance(curves, Sequence):
        raise ValueError("analysis has no curves")
    for curve in curves:
        if not isinstance(curve, Mapping):
            continue
        if curve["mode"] != "navigation" or curve["page_size"] != "5":
            continue
        success = curve["task_success_rate"]
        visible = curve["page_one_useful_probability"]
        pages = curve["pages_requested"]
        tokens = curve["compact_tokens_to_first_useful"]
        if not all(isinstance(value, Mapping) for value in (success, visible, pages, tokens)):
            raise ValueError("invalid curve summary")
        lines.append(
            f"| {curve['candidate_count']} | {curve['linkage_level']} | {curve['arm']} | "
            f"{float(success['estimate']):.3f} [{float(success['low']):.3f}, "
            f"{float(success['high']):.3f}] | {float(visible['estimate']):.3f} | "
            f"{float(pages['p50']):.1f}/{float(pages['p90']):.1f} | "
            f"{float(tokens['p50']):.0f}/{float(tokens['p90']):.0f} |"
        )

    def summary(raw: object, field: str = "estimate", *, percent: bool = False) -> str:
        if not isinstance(raw, Mapping):
            return "—"
        value = raw.get(field)
        if not isinstance(value, (int, float)):
            return "—"
        return f"{float(value):+.1%}" if percent else f"{float(value):+.2f}"

    lines.extend(
        [
            "",
            "## Candidate-density control",
            "",
            "Primary-first, unbounded visibility. Positive success/failure values mean the "
            "150-candidate condition was worse than 10 candidates.",
            "",
            "| links | mode | success drop [90% CI] | correct-use failure increase | "
            "retrieval-token growth p50 |",
            "|---|---|---:|---:|---:|",
        ]
    )
    density = analysis.get("density_endpoint_contrasts")
    if isinstance(density, Sequence):
        for contrast in density:
            if not isinstance(contrast, Mapping):
                continue
            success = contrast["task_success_drop_10_to_150"]
            if not isinstance(success, Mapping):
                continue
            lines.append(
                f"| {contrast['linkage_level']} | {contrast['mode']} | "
                f"{summary(success, percent=True)} "
                f"[{summary(success, 'low', percent=True)}, "
                f"{summary(success, 'high', percent=True)}] | "
                f"{summary(contrast['correct_use_failure_increase_10_to_150'], percent=True)} | "
                f"{summary(contrast['retrieval_token_growth_10_to_150'], 'p50')} |"
            )

    policy = analysis.get("policy_contrasts")
    policy_rows = (
        [row for row in policy if isinstance(row, Mapping)] if isinstance(policy, Sequence) else []
    )
    for reference, contender, heading in (
        ("key", "pagerank", "PageRank versus key"),
        ("pagerank", "bm25f", "BM25F versus PageRank"),
    ):
        lines.extend(
            [
                "",
                f"## {heading}",
                "",
                "Navigation with five-result pages. Positive values favor the contender.",
                "",
                "| candidates | links | page-one gain | pages saved p50 | "
                "compact-token saving p50 | success delta [90% CI] |",
                "|---:|---|---:|---:|---:|---:|",
            ]
        )
        for contrast in policy_rows:
            if (
                contrast.get("reference") != reference
                or contrast.get("contender") != contender
                or contrast.get("mode") != "navigation"
                or contrast.get("page_size") != "5"
            ):
                continue
            success = contrast["task_success_delta"]
            if not isinstance(success, Mapping):
                continue
            lines.append(
                f"| {contrast['candidate_count']} | {contrast['linkage_level']} | "
                f"{summary(contrast['page_one_gain'], percent=True)} | "
                f"{summary(contrast['pages_saved'], 'p50')} | "
                f"{summary(contrast['compact_token_reduction_fraction'], 'p50', percent=True)} | "
                f"{summary(success, percent=True)} "
                f"[{summary(success, 'low', percent=True)}, "
                f"{summary(success, 'high', percent=True)}] |"
            )

    lines.extend(
        [
            "",
            "## Linkage interaction",
            "",
            "Enriched-minus-sparse change in PageRank's advantage over key order, under "
            "navigation with five-result pages.",
            "",
            "| candidates | page-one change | pages-saved change p50 | "
            "compact-saving change p50 | success-advantage change |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    interactions = analysis.get("linkage_interactions")
    if isinstance(interactions, Sequence):
        for contrast in interactions:
            if not isinstance(contrast, Mapping):
                continue
            if (
                contrast.get("reference") != "key"
                or contrast.get("contender") != "pagerank"
                or contrast.get("mode") != "navigation"
                or contrast.get("page_size") != "5"
            ):
                continue
            page_one = summary(contrast["page_one_gain_change_enriched_minus_sparse"], percent=True)
            pages = summary(contrast["pages_saved_change_enriched_minus_sparse"], "p50")
            tokens = summary(
                contrast["compact_token_saving_change_enriched_minus_sparse"],
                "p50",
                percent=True,
            )
            lines.append(
                f"| {contrast['candidate_count']} | "
                f"{page_one} | {pages} | {tokens} | "
                f"{summary(contrast['task_success_change_enriched_minus_sparse'], percent=True)} |"
            )

    lines.extend(
        [
            "",
            "## Graph-family tails",
            "",
            "Decision-edge cells only: 150 candidates, navigation, five-result pages. "
            "Positive values favor the contender.",
            "",
            "| links | comparison | family | pairs | pages saved p50/p90 | "
            "compact saving p50/p90 | success delta p50/p90 |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
    )
    family_tails = analysis.get("family_policy_tails")
    if isinstance(family_tails, Sequence):
        for row in family_tails:
            if not isinstance(row, Mapping):
                continue
            if (
                row.get("candidate_count") != 150
                or row.get("mode") != "navigation"
                or row.get("page_size") != "5"
                or row.get("linkage_level") not in {"native", "enriched"}
            ):
                continue
            metrics = row.get("metrics")
            if not isinstance(metrics, Mapping):
                continue
            pages = metrics.get("pages_saved")
            tokens = metrics.get("compact_token_reduction_fraction")
            success = metrics.get("task_success_delta")
            if not all(isinstance(metric, Mapping) for metric in (pages, tokens, success)):
                continue
            comparison = f"{row['reference']}→{row['contender']}"
            lines.append(
                f"| {row['linkage_level']} | {comparison} | {row['graph_family']} | "
                f"{row['pair_count']} | {summary(pages, 'p50')}/{summary(pages, 'p90')} | "
                f"{summary(tokens, 'p50', percent=True)}/"
                f"{summary(tokens, 'p90', percent=True)} | "
                f"{summary(success, 'p50', percent=True)}/"
                f"{summary(success, 'p90', percent=True)} |"
            )

    lines.extend(
        [
            "",
            "## Task-level tails",
            "",
            "The bottom task is the least favorable observed paired result for the contender. "
            "Full bottom/top-three records for every metric are retained in `analysis.json`.",
            "",
            "| links | comparison | metric | p10/p50/p90 | negative tasks | bottom task |",
            "|---|---|---|---:|---:|---|",
        ]
    )
    task_tails = analysis.get("task_policy_tails")
    if isinstance(task_tails, Sequence):
        for row in task_tails:
            if not isinstance(row, Mapping):
                continue
            if (
                row.get("candidate_count") != 150
                or row.get("mode") != "navigation"
                or row.get("page_size") != "5"
                or row.get("linkage_level") not in {"native", "enriched"}
            ):
                continue
            metrics = row.get("metrics")
            if not isinstance(metrics, Mapping):
                continue
            comparison = f"{row['reference']}→{row['contender']}"
            for metric_name in (
                "pages_saved",
                "compact_token_reduction_fraction",
                "task_success_delta",
            ):
                metric = metrics.get(metric_name)
                if not isinstance(metric, Mapping):
                    continue
                bottom = metric.get("bottom")
                bottom_task = "—"
                if isinstance(bottom, Sequence) and bottom and isinstance(bottom[0], Mapping):
                    bottom_task = str(bottom[0].get("base_task_id", "—"))
                percent = metric_name != "pages_saved"
                lines.append(
                    f"| {row['linkage_level']} | {comparison} | {metric_name} | "
                    f"{summary(metric, 'p10', percent=percent)}/"
                    f"{summary(metric, 'p50', percent=percent)}/"
                    f"{summary(metric, 'p90', percent=percent)} | "
                    f"{metric.get('negative_count', '—')} | {bottom_task} |"
                )

    lines.extend(["", "## Provenance profiles", ""])
    profiles = integrity.get("provenance_profiles")
    if isinstance(profiles, Sequence):
        for profile in profiles:
            if not isinstance(profile, Mapping):
                continue
            lines.append(
                f"- observations={profile['observation_count']}; "
                f"infrastructure failures={profile['embedded_failure_count']}; "
                f"mem={profile['mem_git_sha']} "
                f"(dirty={profile['mem_git_dirty']}, diff={profile['mem_git_diff_sha256']}); "
                f"Beads={profile['beads_git_sha']} "
                f"(dirty={profile['beads_git_dirty']}, diff={profile['beads_git_diff_sha256']}); "
                f"binary={profile['beads_bin_sha256']}; model={profile['agent_model']}; "
                f"agent CLI={profile['agent_cli_version']}"
            )

    triggers = analysis.get("targeted_repeat_triggers")
    lines.extend(["", "## Targeted repeats", ""])
    if isinstance(triggers, Mapping):
        for name, raw in triggers.items():
            count = len(raw) if isinstance(raw, Sequence) else 0
            lines.append(f"- {str(name).replace('_', ' ')}: {count} groups")
    lines.extend(
        [
            "",
            "## Machine-readable evidence",
            "",
            "The machine-readable density, policy, linkage-interaction, and repeat-trigger "
            "tables, including all graph-family and task-level tails, are in `analysis.json`. "
            "Raw model text is deliberately excluded from the shareable observation projection.",
            "",
        ]
    )
    return "\n".join(lines)


def write_density_linkage_agent_evidence(
    rows: Sequence[OrderingRunResult],
    task_metadata: Mapping[str, Mapping[str, object]],
    out: Path,
    *,
    provenance: Mapping[str, object],
    bootstrap_seed: int = 5879,
    bootstrap_resamples: int = 5000,
    locked_repeat_manifest: Path | None = None,
) -> dict[str, object]:
    analysis = analyze_density_linkage_agents(
        rows,
        task_metadata,
        bootstrap_seed=bootstrap_seed,
        bootstrap_resamples=bootstrap_resamples,
    )
    out.mkdir(parents=True, exist_ok=True)
    encoded_analysis = (json.dumps(analysis, indent=2) + "\n").encode()
    (out / "analysis.json").write_bytes(encoded_analysis)
    repeat_path = out / "targeted-repeat-manifest.json"
    if locked_repeat_manifest is None:
        write_density_linkage_repeat_manifest(
            rows,
            task_metadata,
            analysis,
            repeat_path,
            initial_analysis_sha256=hashlib.sha256(encoded_analysis).hexdigest(),
        )
        repeat_manifest_source = "generated-from-current-analysis"
    else:
        encoded_locked = locked_repeat_manifest.read_bytes()
        locked_payload = json.loads(encoded_locked)
        if not isinstance(locked_payload.get("run_ids"), list):
            raise ValueError("locked repeat manifest must contain a run_ids list")
        repeat_path.write_bytes(encoded_locked)
        repeat_manifest_source = "locked-pre-outcome-input"
    encoded_repeat_manifest = repeat_path.read_bytes()
    (out / "report.md").write_text(render_density_linkage_agent_report(analysis), encoding="utf-8")
    sanitized: list[dict[str, object]] = []
    for row in sorted(rows, key=lambda item: item.run_id):
        projection = row.model_dump(mode="json")
        for excluded in ("query", "final_answer", "failure"):
            projection.pop(excluded, None)
        projection["failure_present"] = row.failure is not None
        sanitized.append(projection)
    encoded_observations = "".join(
        json.dumps(row, sort_keys=True) + "\n" for row in sanitized
    ).encode()
    (out / "sanitized-observations.jsonl").write_bytes(encoded_observations)
    cells = analysis["cells"]
    if not isinstance(cells, Sequence):
        raise ValueError("analysis has no cells")
    encoded_cells = "".join(json.dumps(cell, sort_keys=True) + "\n" for cell in cells).encode()
    (out / "cell-estimates.jsonl").write_bytes(encoded_cells)
    canonical = "".join(
        row.model_dump_json() + "\n" for row in sorted(rows, key=lambda item: item.run_id)
    ).encode()
    manifest: dict[str, object] = {
        "schema_version": 1,
        "observation_count": len(rows),
        "usable_observation_count": analysis["usable_observation_count"],
        "source_observations_sha256": hashlib.sha256(canonical).hexdigest(),
        "sanitized_observations_sha256": hashlib.sha256(encoded_observations).hexdigest(),
        "cell_estimates_sha256": hashlib.sha256(encoded_cells).hexdigest(),
        "analysis_sha256": hashlib.sha256(encoded_analysis).hexdigest(),
        "targeted_repeat_manifest_sha256": hashlib.sha256(encoded_repeat_manifest).hexdigest(),
        "targeted_repeat_manifest_source": repeat_manifest_source,
        "privacy_projection": (
            "per-run metrics only; excludes queries, model text, failure text, and credential paths"
        ),
        **dict(provenance),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
