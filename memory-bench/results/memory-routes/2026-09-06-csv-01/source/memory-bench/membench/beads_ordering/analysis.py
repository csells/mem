from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from statistics import fmean

from membench.beads_ordering.models import OrderingArm, OrderingRunResult


def percentile(values: Sequence[float | int], quantile: float) -> float:
    if not values:
        raise ValueError("percentile needs at least one value")
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be in [0, 1]")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _distribution(values: Sequence[float | int]) -> dict[str, float | int]:
    return {
        "n": len(values),
        "mean": fmean(values),
        "p50": percentile(values, 0.5),
        "p90": percentile(values, 0.9),
        "min": min(values),
        "max": max(values),
    }


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    x_mean, y_mean = fmean(xs), fmean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True))
    x_scale = math.sqrt(sum((x - x_mean) ** 2 for x in xs))
    y_scale = math.sqrt(sum((y - y_mean) ** 2 for y in ys))
    return numerator / (x_scale * y_scale) if x_scale and y_scale else None


def _match_stratum(total: int) -> str:
    if total <= 20:
        return "1-20"
    if total <= 50:
        return "21-50"
    if total <= 100:
        return "51-100"
    return "101+"


def _burial_stratum(page: int) -> str:
    if page == 1:
        return "page-1"
    if page <= 3:
        return "pages-2-3"
    return "page-4+"


def _mean(rows: Sequence[OrderingRunResult], field: str) -> float:
    return fmean(float(getattr(row, field)) for row in rows)


def _slope(rows: Sequence[OrderingRunResult], field: str) -> float | None:
    xs = [float(row.pages_requested) for row in rows]
    ys = [float(getattr(row, field)) for row in rows]
    if len(set(xs)) < 2:
        return None
    x_mean = fmean(xs)
    denominator = sum((value - x_mean) ** 2 for value in xs)
    if not denominator:
        return None
    y_mean = fmean(ys)
    return (
        sum(
            (x_value - x_mean) * (y_value - y_mean) for x_value, y_value in zip(xs, ys, strict=True)
        )
        / denominator
    )


def _page_size_sort(label: str) -> int:
    return 1_000_000 if label == "all" else int(label)


_DECISION_ARMS = (
    OrderingArm.KEY,
    OrderingArm.REVERSE_PAGERANK,
    OrderingArm.HITS_HUB,
    OrderingArm.BM25F,
)
_STRUCTURAL_FINALISTS = (OrderingArm.REVERSE_PAGERANK, OrderingArm.HITS_HUB)
_DECISION_PAGE_SIZES = ("5", "10", "20", "all")
_DECISION_MODES = ("search-only", "navigation")


def _maybe_distribution(values: Sequence[float | int]) -> dict[str, float | int] | None:
    return _distribution(values) if values else None


def _paired_policy_summaries(rows: Sequence[OrderingRunResult]) -> list[dict[str, object]]:
    by_cell = {
        (row.task_id, row.repeat, row.mode.value, row.page_size, row.arm): row for row in rows
    }
    fields = {
        "pages_saved_by_bm25f": "pages_requested",
        "compact_tokens_saved_by_bm25f": "compact_tokens_to_first_useful",
        "retrieval_tokens_saved_by_bm25f": "retrieval_tokens_to_first_useful",
        "tool_calls_saved_by_bm25f": "tool_calls_to_first_useful",
        "retrieval_latency_ms_saved_by_bm25f": "retrieval_latency_ms",
        "end_to_end_ms_saved_by_bm25f": "end_to_end_ms",
        "recalls_saved_by_bm25f": "full_recalls",
        "graph_hops_saved_by_bm25f": "graph_hops_total",
    }
    summaries: list[dict[str, object]] = []
    for mode in sorted({row.mode.value for row in rows}):
        for page_size in sorted({row.page_size for row in rows}, key=_page_size_sort):
            for policy in sorted(
                {row.arm for row in rows if row.arm is not OrderingArm.BM25F},
                key=lambda arm: arm.value,
            ):
                task_values: dict[str, dict[str, list[float]]] = defaultdict(
                    lambda: defaultdict(list)
                )
                pair_count = 0
                for row in rows:
                    if (
                        row.arm is not policy
                        or row.mode.value != mode
                        or row.page_size != page_size
                    ):
                        continue
                    bm25f = by_cell.get(
                        (row.task_id, row.repeat, mode, page_size, OrderingArm.BM25F)
                    )
                    if bm25f is None:
                        continue
                    pair_count += 1
                    for output_name, field in fields.items():
                        task_values[row.task_id][output_name].append(
                            float(getattr(row, field)) - float(getattr(bm25f, field))
                        )
                    policy_tokens = float(row.compact_tokens_to_first_useful)
                    token_fraction = (
                        0.0
                        if policy_tokens == 0
                        else (policy_tokens - float(bm25f.compact_tokens_to_first_useful))
                        / policy_tokens
                    )
                    task_values[row.task_id]["compact_token_reduction_fraction"].append(
                        token_fraction
                    )
                    task_values[row.task_id]["success_delta_bm25f_minus_policy"].append(
                        float(bm25f.task_success) - float(row.task_success)
                    )
                    if (
                        row.time_to_first_useful_ms is not None
                        and bm25f.time_to_first_useful_ms is not None
                    ):
                        task_values[row.task_id]["time_to_useful_ms_saved_by_bm25f"].append(
                            row.time_to_first_useful_ms - bm25f.time_to_first_useful_ms
                        )
                if not pair_count:
                    continue
                metric_names = (
                    *fields,
                    "compact_token_reduction_fraction",
                    "success_delta_bm25f_minus_policy",
                    "time_to_useful_ms_saved_by_bm25f",
                )
                summary: dict[str, object] = {
                    "mode": mode,
                    "policy": policy.value,
                    "page_size": page_size,
                    "n_tasks": len(task_values),
                    "n_pairs": pair_count,
                }
                for metric in metric_names:
                    clustered = [
                        fmean(values[metric])
                        for values in task_values.values()
                        if values.get(metric)
                    ]
                    summary[metric] = _maybe_distribution(clustered)
                summaries.append(summary)
    return summaries


def _targeted_repeat_cells(rows: Sequence[OrderingRunResult]) -> list[dict[str, object]]:
    decision_rows = [row for row in rows if row.arm in _DECISION_ARMS]
    by_attempt: dict[tuple[str, str, str, int], list[OrderingRunResult]] = defaultdict(list)
    for row in decision_rows:
        by_attempt[(row.task_id, row.mode.value, row.page_size, row.repeat)].append(row)
    targets: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for (task_id, mode, page_size, _), group in by_attempt.items():
        if len({row.arm for row in group}) != len(_DECISION_ARMS):
            continue
        if len({row.task_success for row in group}) > 1:
            targets[(task_id, mode, page_size)].add("policy-success-disagreement")
        if any(row.failure is not None for row in group):
            targets[(task_id, mode, page_size)].add("agent-or-tool-failure")
    by_policy_cell: dict[tuple[str, str, str, OrderingArm], list[OrderingRunResult]] = defaultdict(
        list
    )
    for row in decision_rows:
        by_policy_cell[(row.task_id, row.mode.value, row.page_size, row.arm)].append(row)
    for (task_id, mode, page_size, _), group in by_policy_cell.items():
        if len(group) > 1 and len({row.task_success for row in group}) > 1:
            targets[(task_id, mode, page_size)].add("repeat-outcome-variance")
    return [
        {
            "task_id": key[0],
            "mode": key[1],
            "page_size": key[2],
            "reasons": sorted(reasons),
        }
        for key, reasons in sorted(
            targets.items(), key=lambda item: (item[0][0], item[0][1], _page_size_sort(item[0][2]))
        )
    ]


def _mechanism_recommendation(rows: Sequence[OrderingRunResult]) -> dict[str, object]:
    task_ids = sorted({row.task_id for row in rows})
    observed = {
        (row.task_id, row.mode.value, row.page_size, row.arm)
        for row in rows
        if row.arm in _DECISION_ARMS
    }
    expected = {
        (task_id, mode, page_size, arm)
        for task_id in task_ids
        for mode in _DECISION_MODES
        for page_size in _DECISION_PAGE_SIZES
        for arm in _DECISION_ARMS
    }
    complete = len(task_ids) >= 24 and expected <= observed
    base: dict[str, object] = {
        "initial_grid_complete": complete,
        "task_count": len(task_ids),
        "expected_initial_cells": len(expected),
        "observed_initial_cells": len(expected & observed),
        "thresholds": {
            "median_pages_saved": 1.0,
            "median_compact_token_reduction_fraction": 0.2,
            "requires_no_task_success_regression": True,
            "requires_navigation_advantage": True,
        },
    }
    if not complete:
        return {
            **base,
            "status": "insufficient-data",
            "navigation_advantage_material": False,
            "no_task_success_regression": False,
            "comparisons": [],
        }

    by_cell = {
        (row.task_id, row.repeat, row.mode.value, row.page_size, row.arm): row for row in rows
    }
    comparisons: list[dict[str, object]] = []
    for policy in _STRUCTURAL_FINALISTS:
        per_task: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for row in rows:
            if row.arm is not policy:
                continue
            bm25f = by_cell.get(
                (row.task_id, row.repeat, row.mode.value, row.page_size, OrderingArm.BM25F)
            )
            if bm25f is None:
                continue
            per_task[row.task_id]["all_mode_success_delta"].append(
                float(bm25f.task_success) - float(row.task_success)
            )
            if row.mode.value != "navigation" or row.page_size == "all":
                continue
            per_task[row.task_id]["navigation_pages_saved"].append(
                float(row.pages_requested - bm25f.pages_requested)
            )
            policy_tokens = float(row.compact_tokens_to_first_useful)
            per_task[row.task_id]["navigation_token_reduction"].append(
                0.0
                if policy_tokens == 0
                else (policy_tokens - float(bm25f.compact_tokens_to_first_useful)) / policy_tokens
            )
            per_task[row.task_id]["navigation_success_delta"].append(
                float(bm25f.task_success) - float(row.task_success)
            )
        pages = [fmean(values["navigation_pages_saved"]) for values in per_task.values()]
        token_reduction = [
            fmean(values["navigation_token_reduction"]) for values in per_task.values()
        ]
        all_success = [fmean(values["all_mode_success_delta"]) for values in per_task.values()]
        navigation_success = [
            fmean(values["navigation_success_delta"]) for values in per_task.values()
        ]
        pages_distribution = _distribution(pages)
        token_distribution = _distribution(token_reduction)
        all_success_mean = fmean(all_success)
        navigation_success_mean = fmean(navigation_success)
        material = (
            float(pages_distribution["p50"]) >= 1.0 or float(token_distribution["p50"]) >= 0.2
        )
        no_regression = all_success_mean >= 0 and navigation_success_mean >= 0
        comparisons.append(
            {
                "policy": policy.value,
                "n_tasks": len(per_task),
                "navigation_pages_saved_by_bm25f": pages_distribution,
                "navigation_compact_token_reduction_fraction": token_distribution,
                "all_mode_success_delta_bm25f_minus_policy": all_success_mean,
                "navigation_success_delta_bm25f_minus_policy": navigation_success_mean,
                "navigation_advantage_material": material,
                "no_task_success_regression": no_regression,
            }
        )
    navigation_material = len(comparisons) == len(_STRUCTURAL_FINALISTS) and all(
        bool(item["navigation_advantage_material"]) for item in comparisons
    )
    no_regression = len(comparisons) == len(_STRUCTURAL_FINALISTS) and all(
        bool(item["no_task_success_regression"]) for item in comparisons
    )
    return {
        **base,
        "status": (
            "recommend-bm25f-ownership"
            if navigation_material and no_regression
            else "prefer-query-independent-ordering-navigation"
        ),
        "navigation_advantage_material": navigation_material,
        "no_task_success_regression": no_regression,
        "comparisons": comparisons,
    }


def analyze_results(rows: Sequence[OrderingRunResult]) -> dict[str, object]:
    if not rows:
        raise ValueError("analysis needs at least one run")
    metrics = (
        "pages_requested",
        "compact_result_tokens",
        "compact_tokens_to_first_useful",
        "retrieval_tokens_to_first_useful",
        "tool_calls_to_first_useful",
        "retrieval_tool_calls",
        "retrieval_latency_ms",
        "server_candidate_generation_ms",
        "server_ordering_ms",
        "end_to_end_ms",
        "full_recalls",
        "graph_hops_after_first_useful",
        "graph_hops_total",
        "reference_edges_exposed",
    )
    by_arm: dict[str, dict[str, object]] = {}
    for arm in OrderingArm:
        arm_rows = [row for row in rows if row.arm is arm]
        if not arm_rows:
            continue
        by_arm[arm.value] = {
            metric: _distribution([getattr(row, metric) for row in arm_rows]) for metric in metrics
        }
        by_arm[arm.value]["task_success_rate"] = fmean(
            1.0 if row.task_success else 0.0 for row in arm_rows
        )

    by_mode_arm: dict[str, dict[str, object]] = {}
    for mode in sorted({row.mode.value for row in rows}):
        for arm in OrderingArm:
            group = [row for row in rows if row.mode.value == mode and row.arm is arm]
            if not group:
                continue
            key = f"{mode}/{arm.value}"
            by_mode_arm[key] = {
                metric: _distribution([getattr(row, metric) for row in group]) for metric in metrics
            }
            by_mode_arm[key]["task_success_rate"] = fmean(
                1.0 if row.task_success else 0.0 for row in group
            )

    page_size_groups: dict[tuple[str, str, str], list[OrderingRunResult]] = defaultdict(list)
    for row in rows:
        page_size_groups[(row.mode.value, row.arm.value, row.page_size)].append(row)
    page_size_curves = [
        {
            "mode": key[0],
            "arm": key[1],
            "page_size": key[2],
            "n": len(group),
            "page_one_acceptable_probability": fmean(
                1.0 if row.page_one_acceptable_visible else 0.0 for row in group
            ),
            "pages_to_first_useful": (
                _distribution(
                    [
                        row.pages_to_first_useful
                        for row in group
                        if row.pages_to_first_useful is not None
                    ]
                )
                if any(row.pages_to_first_useful is not None for row in group)
                else None
            ),
            "compact_result_tokens": _distribution(
                [row.compact_tokens_to_first_useful for row in group]
            ),
            "tool_calls": _distribution([row.tool_calls_to_first_useful for row in group]),
            "time_to_first_useful_ms": (
                _distribution(
                    [
                        row.time_to_first_useful_ms
                        for row in group
                        if row.time_to_first_useful_ms is not None
                    ]
                )
                if any(row.time_to_first_useful_ms is not None for row in group)
                else None
            ),
            "recalls": _distribution([row.full_recalls for row in group]),
            "graph_hops": _distribution([row.graph_hops_total for row in group]),
            "retrieval_tokens": _distribution(
                [row.retrieval_tokens_to_first_useful for row in group]
            ),
            "branching_factor": _distribution([row.branching_factor_mean for row in group]),
            "task_success_rate": fmean(1.0 if row.task_success else 0.0 for row in group),
            "server_candidate_generation_ms": _distribution(
                [row.server_candidate_generation_ms for row in group]
            ),
            "server_ordering_ms": _distribution([row.server_ordering_ms for row in group]),
        }
        for key, group in sorted(
            page_size_groups.items(),
            key=lambda item: (item[0][0], item[0][1], _page_size_sort(item[0][2])),
        )
    ]

    bounded_vs_unbounded: list[dict[str, object]] = []
    for mode in sorted({row.mode.value for row in rows}):
        for arm in OrderingArm:
            full = page_size_groups.get((mode, arm.value, "all"), [])
            if not full:
                continue
            full_tokens = _mean(full, "compact_result_tokens")
            full_success = _mean(full, "task_success")
            full_time_values = [
                row.time_to_first_useful_ms
                for row in full
                if row.time_to_first_useful_ms is not None
            ]
            full_time = fmean(full_time_values) if full_time_values else None
            for (group_mode, group_arm, size), group in page_size_groups.items():
                if group_mode != mode or group_arm != arm.value or size == "all":
                    continue
                time_values = [
                    row.time_to_first_useful_ms
                    for row in group
                    if row.time_to_first_useful_ms is not None
                ]
                bounded_vs_unbounded.append(
                    {
                        "mode": mode,
                        "arm": arm.value,
                        "page_size": size,
                        "compact_tokens_mean_delta": _mean(group, "compact_result_tokens")
                        - full_tokens,
                        "time_to_useful_mean_delta_ms": (
                            fmean(time_values) - full_time
                            if time_values and full_time is not None
                            else None
                        ),
                        "success_rate_delta": _mean(group, "task_success") - full_success,
                    }
                )

    mechanical_vs_bm25f: list[dict[str, object]] = []
    numeric_material: dict[str, list[int]] = defaultdict(list)
    policy_vs_bm25f: list[dict[str, object]] = []
    for mode in sorted({row.mode.value for row in rows}):
        size_labels = sorted(
            {
                size
                for group_mode, arm, size in page_size_groups
                if group_mode == mode and arm in {OrderingArm.KEY.value, OrderingArm.BM25F.value}
            },
            key=_page_size_sort,
        )
        for size in size_labels:
            bm25f_rows = page_size_groups.get((mode, OrderingArm.BM25F.value, size), [])
            if not bm25f_rows:
                continue
            for arm in OrderingArm:
                if arm is OrderingArm.BM25F:
                    continue
                policy_rows = page_size_groups.get((mode, arm.value, size), [])
                if not policy_rows:
                    continue
                pages_delta = percentile(
                    [row.pages_requested for row in policy_rows], 0.5
                ) - percentile([row.pages_requested for row in bm25f_rows], 0.5)
                policy_tokens = _mean(policy_rows, "compact_result_tokens")
                bm25f_tokens = _mean(bm25f_rows, "compact_result_tokens")
                token_reduction = (
                    0.0 if policy_tokens == 0 else (policy_tokens - bm25f_tokens) / policy_tokens
                )
                success_delta = _mean(bm25f_rows, "task_success") - _mean(
                    policy_rows, "task_success"
                )
                material_gap = (pages_delta >= 1.0 or token_reduction >= 0.2) and success_delta >= 0
                comparison = {
                    "mode": mode,
                    "policy": arm.value,
                    "page_size": size,
                    "policy_pages_p50_minus_bm25f": pages_delta,
                    "bm25f_compact_token_reduction_fraction": token_reduction,
                    "bm25f_success_rate_minus_policy": success_delta,
                    "material_gap": material_gap,
                }
                policy_vs_bm25f.append(comparison)
                if arm is OrderingArm.KEY:
                    mechanical_vs_bm25f.append(comparison)
                    if size != "all" and material_gap:
                        numeric_material[mode].append(int(size))

    baseline = [row for row in rows if row.arm is OrderingArm.KEY]
    correlations = {
        mode: {
            metric: _pearson(
                [
                    float(min(filter(None, (row.primary_page, row.acceptable_page))))
                    for row in baseline
                    if row.mode.value == mode
                ],
                [float(getattr(row, metric)) for row in baseline if row.mode.value == mode],
            )
            for metric in metrics
        }
        for mode in sorted({row.mode.value for row in baseline})
    }

    baseline_pages = {
        (row.task_id, row.repeat, row.page_size, row.mode.value): min(
            filter(None, (row.primary_page, row.acceptable_page))
        )
        for row in baseline
    }
    grouped: dict[tuple[str, int, str, str, str], list[OrderingRunResult]] = defaultdict(list)
    for row in rows:
        baseline_page = baseline_pages.get(
            (row.task_id, row.repeat, row.page_size, row.mode.value),
            min(filter(None, (row.primary_page, row.acceptable_page))),
        )
        grouped[
            (
                row.mode.value,
                row.corpus_size,
                _match_stratum(row.total_matched),
                _burial_stratum(baseline_page),
                row.arm.value,
            )
        ].append(row)
    strata = [
        {
            "mode": key[0],
            "corpus_size": key[1],
            "match_set": key[2],
            "baseline_burial": key[3],
            "arm": key[4],
            "n": len(group),
            "pages_p50": percentile([row.pages_requested for row in group], 0.5),
            "tokens_p50": percentile([row.retrieval_related_tokens for row in group], 0.5),
            "success_rate": fmean(1.0 if row.task_success else 0.0 for row in group),
        }
        for key, group in sorted(grouped.items())
    ]
    page_cost = [
        {
            "mode": key[0],
            "arm": key[1],
            "page_size": key[2],
            "n": len(group),
            "compact_tokens_per_additional_page": _slope(group, "compact_tokens_to_first_useful"),
            "tool_calls_per_additional_page": _slope(group, "tool_calls_to_first_useful"),
            "retrieval_latency_ms_per_additional_page": _slope(group, "retrieval_latency_ms"),
            "end_to_end_ms_per_additional_page": _slope(group, "end_to_end_ms"),
        }
        for key, group in sorted(
            page_size_groups.items(),
            key=lambda item: (item[0][0], item[0][1], _page_size_sort(item[0][2])),
        )
    ]

    navigation_effects: list[dict[str, object]] = []
    for arm in OrderingArm:
        for size in sorted({row.page_size for row in rows}, key=_page_size_sort):
            search_rows = page_size_groups.get(("search-only", arm.value, size), [])
            navigation_rows = page_size_groups.get(("navigation", arm.value, size), [])
            if not search_rows or not navigation_rows:
                continue
            navigation_effects.append(
                {
                    "arm": arm.value,
                    "page_size": size,
                    "navigation_retrieval_tokens_mean_delta": _mean(
                        navigation_rows, "retrieval_related_tokens"
                    )
                    - _mean(search_rows, "retrieval_related_tokens"),
                    "navigation_latency_mean_delta_ms": _mean(
                        navigation_rows, "retrieval_latency_ms"
                    )
                    - _mean(search_rows, "retrieval_latency_ms"),
                    "navigation_success_rate_delta": _mean(navigation_rows, "task_success")
                    - _mean(search_rows, "task_success"),
                    "navigation_primary_reach_rate": _mean(
                        navigation_rows, "navigation_reached_primary"
                    ),
                    "navigation_graph_hops_mean": _mean(navigation_rows, "graph_hops_total"),
                }
            )
    paired_policy_vs_bm25f = _paired_policy_summaries(rows)
    targeted_repeat_cells = _targeted_repeat_cells(rows)
    mechanism_recommendation = _mechanism_recommendation(rows)
    return {
        "runs": len(rows),
        "by_arm": by_arm,
        "by_mode_arm": by_mode_arm,
        "baseline_burial_correlations": correlations,
        "page_size_curves": page_size_curves,
        "bounded_vs_unbounded": sorted(
            bounded_vs_unbounded,
            key=lambda row: (str(row["arm"]), _page_size_sort(str(row["page_size"]))),
        ),
        "mechanical_vs_bm25f": mechanical_vs_bm25f,
        "policy_vs_bm25f": policy_vs_bm25f,
        "largest_page_size_with_material_ranking_gap": {
            mode: max(sizes) if sizes else None for mode, sizes in sorted(numeric_material.items())
        },
        "material_gap_definition": (
            "mechanical p50 pages is >=1 above BM25F or BM25F reduces mean compact tokens "
            "by >=20%, without reducing success"
        ),
        "strata": strata,
        "page_cost_slopes": page_cost,
        "navigation_effects": navigation_effects,
        "paired_policy_vs_bm25f": paired_policy_vs_bm25f,
        "targeted_repeat_cells": targeted_repeat_cells,
        "mechanism_recommendation": mechanism_recommendation,
    }
