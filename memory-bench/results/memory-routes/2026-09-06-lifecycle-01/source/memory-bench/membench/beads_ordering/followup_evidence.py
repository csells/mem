from __future__ import annotations

import hashlib
import html
import json
import math
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import fmean
from typing import Any

from membench.beads_ordering.client import BeadsExperimentClient
from membench.beads_ordering.models import (
    BM25FConfig,
    FrozenCorpus,
    OrderingArm,
    OrderingRunResult,
    TaskSplit,
)
from membench.beads_ordering.runner import task_workspace


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
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


def _response_size(payload: Mapping[str, Any]) -> tuple[int, int]:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    return len(encoded), (len(encoded) + 3) // 4


def _as_float(value: object) -> float:
    if isinstance(value, (bool, int, float)):
        return float(value)
    raise TypeError(f"expected numeric value, got {type(value).__name__}")


def select_targeted_repeat_groups(
    rows: Sequence[OrderingRunResult],
) -> list[dict[str, object]]:
    """Apply the preregistered repeat rule to repeat-zero outcomes only."""

    grouped: dict[tuple[str, str, str], list[OrderingRunResult]] = defaultdict(list)
    for row in rows:
        if row.repeat == 0:
            grouped[(row.task_id, row.mode.value, row.page_size)].append(row)
    selected: list[dict[str, object]] = []
    for (task_id, mode, page_size), group in grouped.items():
        reasons: list[str] = []
        if len({row.task_success for row in group}) > 1:
            reasons.append("task-success-disagreement")
        if any(row.failure is not None for row in group):
            reasons.append("infrastructure-failure")
        if reasons:
            selected.append(
                {
                    "task_id": task_id,
                    "mode": mode,
                    "page_size": page_size,
                    "reasons": reasons,
                    "repeat_indices": [1, 2],
                }
            )
    return sorted(
        selected,
        key=lambda row: (
            str(row["task_id"]),
            str(row["mode"]),
            10_000 if row["page_size"] == "all" else int(str(row["page_size"])),
        ),
    )


_AGENT_CELL_METRICS = (
    "pages_requested",
    "compact_tokens_to_first_useful",
    "retrieval_tokens_to_first_useful",
    "tool_calls_to_first_useful",
    "retrieval_tool_calls",
    "time_to_first_useful_ms",
    "full_recalls",
    "graph_hops_total",
    "branching_factor_mean",
    "retrieval_latency_ms",
    "server_candidate_generation_ms",
    "server_ordering_ms",
    "end_to_end_ms",
    "task_success",
    "abstained",
    "premature_stop",
)


def analyze_agent_followup(
    rows: Sequence[OrderingRunResult],
    task_metadata: Mapping[str, Mapping[str, object]],
    *,
    bootstrap_seed: int = 5878,
    bootstrap_resamples: int = 5000,
) -> dict[str, object]:
    """Analyze targeted repeats with one equally weighted estimate per policy cell."""

    if not rows:
        raise ValueError("agent follow-up analysis needs at least one observation")
    grouped: dict[tuple[str, str, str, str], list[OrderingRunResult]] = defaultdict(list)
    for row in rows:
        grouped[(row.task_id, row.mode.value, row.page_size, row.arm.value)].append(row)
    cells: list[dict[str, object]] = []
    for (task_id, mode, page_size, arm), observations in sorted(grouped.items()):
        first = observations[0]
        metadata = task_metadata.get(task_id)
        if metadata is None:
            raise ValueError(f"missing task metadata for {task_id}")
        cell: dict[str, object] = {
            "task_id": task_id,
            "mode": mode,
            "page_size": page_size,
            "arm": arm,
            "repeats": len(observations),
            "graph_family": str(metadata["graph_family"]),
            "failure_case": str(metadata["failure_case"]),
            "corpus_size": first.corpus_size,
            "total_matched": first.total_matched,
            "primary_page": first.primary_page,
            "acceptable_page": first.acceptable_page,
            "page_one_acceptable_visible": first.page_one_acceptable_visible,
        }
        for metric in _AGENT_CELL_METRICS:
            values = [getattr(row, metric) for row in observations]
            numeric = [float(value) for value in values if value is not None]
            cell[metric] = fmean(numeric) if numeric else None
        cells.append(cell)

    curve_groups: dict[tuple[str, str, str], list[Mapping[str, object]]] = defaultdict(list)
    for cell in cells:
        curve_groups[(str(cell["mode"]), str(cell["arm"]), str(cell["page_size"]))].append(cell)
    curves: list[dict[str, object]] = []
    for (mode, arm, page_size), group in sorted(
        curve_groups.items(),
        key=lambda item: (
            item[0][0],
            item[0][1],
            10_000 if item[0][2] == "all" else int(item[0][2]),
        ),
    ):
        success_rows = [
            {"graph_family": row["graph_family"], "task_success": row["task_success"]}
            for row in group
        ]
        curves.append(
            {
                "mode": mode,
                "arm": arm,
                "page_size": page_size,
                "n_cells": len(group),
                "task_success_rate": _task_cluster_ci(
                    success_rows,
                    field="task_success",
                    seed=bootstrap_seed,
                    resamples=bootstrap_resamples,
                ),
                **{
                    metric: _distribution([_as_float(row[metric]) for row in group])
                    for metric in _AGENT_CELL_METRICS
                    if metric not in {"task_success", "abstained", "premature_stop"}
                    and all(row[metric] is not None for row in group)
                },
            }
        )

    by_cell = {
        (str(row["task_id"]), str(row["mode"]), str(row["page_size"]), str(row["arm"])): row
        for row in cells
    }
    arms = sorted({str(row["arm"]) for row in cells})
    comparisons: list[dict[str, object]] = []
    for reference in ("key", "pagerank", "reverse-pagerank", "control-automatic"):
        if reference not in arms:
            continue
        for contender in arms:
            if contender == reference:
                continue
            if reference == "control-automatic" and not contender.startswith("control-"):
                continue
            for mode in sorted({str(row["mode"]) for row in cells}):
                for page_size in sorted(
                    {str(row["page_size"]) for row in cells},
                    key=lambda value: 10_000 if value == "all" else int(value),
                ):
                    pairs = [
                        (row, by_cell[(str(row["task_id"]), mode, page_size, contender)])
                        for row in cells
                        if row["mode"] == mode
                        and row["page_size"] == page_size
                        and row["arm"] == reference
                        and (str(row["task_id"]), mode, page_size, contender) in by_cell
                    ]
                    if not pairs:
                        continue
                    success_rows = [
                        {
                            "graph_family": base["graph_family"],
                            "delta": _as_float(candidate["task_success"])
                            - _as_float(base["task_success"]),
                        }
                        for base, candidate in pairs
                    ]
                    comparisons.append(
                        {
                            "reference": reference,
                            "contender": contender,
                            "mode": mode,
                            "page_size": page_size,
                            "n_cells": len(pairs),
                            "pages_saved": _distribution(
                                [
                                    _as_float(base["pages_requested"])
                                    - _as_float(candidate["pages_requested"])
                                    for base, candidate in pairs
                                ]
                            ),
                            "compact_token_reduction_fraction": _distribution(
                                [
                                    (
                                        _as_float(base["compact_tokens_to_first_useful"])
                                        - _as_float(candidate["compact_tokens_to_first_useful"])
                                    )
                                    / max(
                                        1.0,
                                        _as_float(base["compact_tokens_to_first_useful"]),
                                    )
                                    for base, candidate in pairs
                                ]
                            ),
                            "task_success_delta": _task_cluster_ci(
                                success_rows,
                                field="delta",
                                seed=bootstrap_seed,
                                resamples=bootstrap_resamples,
                            ),
                        }
                    )

    control_arms = {
        "control-automatic",
        "control-semantic",
        "control-strategy",
        "control-raw",
    }
    control_results: list[dict[str, object]] = []
    if "control-automatic" in arms:
        for contender in sorted(control_arms - {"control-automatic"}):
            if contender not in arms:
                continue
            for mode in sorted({str(row["mode"]) for row in cells}):
                for page_size in sorted(
                    {str(row["page_size"]) for row in cells},
                    key=lambda value: 10_000 if value == "all" else int(value),
                ):
                    pairs = [
                        (row, by_cell[(str(row["task_id"]), mode, page_size, contender)])
                        for row in cells
                        if row["mode"] == mode
                        and row["page_size"] == page_size
                        and row["arm"] == "control-automatic"
                        and (str(row["task_id"]), mode, page_size, contender) in by_cell
                    ]
                    if not pairs:
                        continue
                    affected = [
                        pair for pair in pairs if not pair[0]["page_one_acceptable_visible"]
                    ]
                    neutral = [pair for pair in pairs if pair[0]["page_one_acceptable_visible"]]

                    def success_delta(
                        selected: Sequence[tuple[Mapping[str, object], Mapping[str, object]]],
                        *,
                        seed_offset: int,
                    ) -> dict[str, float | int | None]:
                        return _task_cluster_ci(
                            [
                                {
                                    "graph_family": base["graph_family"],
                                    "delta": _as_float(candidate["task_success"])
                                    - _as_float(base["task_success"]),
                                }
                                for base, candidate in selected
                            ],
                            field="delta",
                            seed=bootstrap_seed + seed_offset,
                            resamples=bootstrap_resamples,
                        )

                    control_results.append(
                        {
                            "reference": "control-automatic",
                            "contender": contender,
                            "mode": mode,
                            "page_size": page_size,
                            "pair_count": len(pairs),
                            "affected_pair_count": len(affected),
                            "neutral_pair_count": len(neutral),
                            "placement_changed_pair_count": sum(
                                base["primary_page"] != candidate["primary_page"]
                                or base["acceptable_page"] != candidate["acceptable_page"]
                                for base, candidate in pairs
                            ),
                            "page_one_recovery_fraction": (
                                sum(
                                    bool(candidate["page_one_acceptable_visible"])
                                    for _, candidate in affected
                                )
                                / len(affected)
                                if affected
                                else None
                            ),
                            "affected_task_success_delta": success_delta(affected, seed_offset=101),
                            "neutral_task_success_delta": success_delta(neutral, seed_offset=211),
                            "task_success_delta": success_delta(pairs, seed_offset=307),
                        }
                    )

    semantic_results = [
        result for result in control_results if result["contender"] == "control-semantic"
    ]
    control_gate_rows: list[dict[str, object]] = []
    for control_result in semantic_results:
        neutral_summary = control_result["neutral_task_success_delta"]
        assert isinstance(neutral_summary, Mapping)
        recovery = control_result["page_one_recovery_fraction"]
        recovery_clears = isinstance(recovery, (int, float)) and recovery >= 0.25
        neutral_low = neutral_summary.get("low")
        neutral_clears = isinstance(neutral_low, (int, float)) and neutral_low >= -0.03
        control_gate_rows.append(
            {
                "mode": control_result["mode"],
                "page_size": control_result["page_size"],
                "recovery_clears_0_25": recovery_clears,
                "neutral_nonregression_clears_minus_0_03": neutral_clears,
                "clears": recovery_clears and neutral_clears,
            }
        )

    semantic_raw_results: list[dict[str, object]] = []
    if {"control-semantic", "control-raw"} <= set(arms):
        for mode in sorted({str(row["mode"]) for row in cells}):
            for page_size in sorted(
                {str(row["page_size"]) for row in cells},
                key=lambda value: 10_000 if value == "all" else int(value),
            ):
                pairs = [
                    (row, by_cell[(str(row["task_id"]), mode, page_size, "control-raw")])
                    for row in cells
                    if row["mode"] == mode
                    and row["page_size"] == page_size
                    and row["arm"] == "control-semantic"
                    and (str(row["task_id"]), mode, page_size, "control-raw") in by_cell
                ]
                if not pairs:
                    continue
                delta = _task_cluster_ci(
                    [
                        {
                            "graph_family": semantic["graph_family"],
                            "delta": _as_float(semantic["task_success"])
                            - _as_float(raw["task_success"]),
                        }
                        for semantic, raw in pairs
                    ],
                    field="delta",
                    seed=bootstrap_seed + 401,
                    resamples=bootstrap_resamples,
                )
                low = delta.get("low")
                high = delta.get("high")
                semantic_raw_results.append(
                    {
                        "mode": mode,
                        "page_size": page_size,
                        "pair_count": len(pairs),
                        "semantic_minus_raw_task_success": delta,
                        "equivalence_margin": 0.05,
                        "equivalence_clears": isinstance(low, (int, float))
                        and isinstance(high, (int, float))
                        and low >= -0.05
                        and high <= 0.05,
                    }
                )

    observed_control_cells = {
        (str(row["mode"]), str(row["page_size"]), str(row["arm"]))
        for row in cells
        if str(row["arm"]) in control_arms
    }
    observed_modes = {str(row["mode"]) for row in cells}
    observed_pages = {str(row["page_size"]) for row in cells}
    expected_control_cells = {
        (mode, page, arm)
        for mode in observed_modes
        for page in observed_pages
        for arm in control_arms
    }
    control_matrix_complete = expected_control_cells <= observed_control_cells
    return {
        "observation_count": len(rows),
        "cell_count": len(cells),
        "repeat_averaging": "equal weight per task/mode/page/policy cell",
        "targeted_repeat_groups": select_targeted_repeat_groups(rows),
        "curves": curves,
        "paired_policy_comparisons": comparisons,
        "control_surface": {
            "status": ("measured" if control_arms <= set(arms) else "incomplete-control-arms"),
            "thresholds": {
                "minimum_failure_case_recovery_fraction": 0.25,
                "maximum_neutral_task_success_regression": 0.03,
            },
            "comparisons": control_results,
            "semantic_gate_cells": control_gate_rows,
            "semantic_gate_passed_all_cells": bool(control_gate_rows)
            and all(bool(row["clears"]) for row in control_gate_rows),
            "semantic_vs_raw": semantic_raw_results,
            "semantic_equivalent_to_raw_all_cells": bool(semantic_raw_results)
            and all(bool(row["equivalence_clears"]) for row in semantic_raw_results),
            "matrix_complete_for_observed_modes_and_pages": control_matrix_complete,
            "decision_ready": control_arms <= set(arms)
            and control_matrix_complete
            and bool(semantic_raw_results),
        },
        "cells": cells,
    }


def render_agent_followup_report(analysis: Mapping[str, object]) -> str:
    curves = analysis.get("curves")
    if not isinstance(curves, list):
        raise ValueError("agent follow-up analysis has no curves")
    lines = [
        "# Follow-up agent retrieval evidence",
        "",
        (
            f"{analysis['observation_count']} observations were averaged into "
            f"{analysis['cell_count']} equally weighted policy cells."
        ),
        "",
        "## Navigation at page size 5",
        "",
        "| policy | success | compact tokens p50 / p90 | pages p50 / p90 |",
        "|---|---:|---:|---:|",
    ]
    for raw_curve in curves:
        if not isinstance(raw_curve, dict):
            continue
        if raw_curve.get("mode") != "navigation" or raw_curve.get("page_size") != "5":
            continue
        success = raw_curve["task_success_rate"]
        tokens = raw_curve["compact_tokens_to_first_useful"]
        pages = raw_curve["pages_requested"]
        if not all(isinstance(value, dict) for value in (success, tokens, pages)):
            raise ValueError("invalid curve distributions")
        lines.append(
            f"| {raw_curve['arm']} | {float(success['estimate']):.3f} "
            f"[{float(success['low']):.3f}, {float(success['high']):.3f}] | "
            f"{float(tokens['p50']):.0f} / {float(tokens['p90']):.0f} | "
            f"{float(pages['p50']):.1f} / {float(pages['p90']):.1f} |"
        )
    lines.extend(
        [
            "",
            "Success intervals are 90% graph-family-clustered bootstrap intervals. "
            "Raw model text is intentionally excluded from this derived evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def render_agent_followup_svg(analysis: Mapping[str, object], *, mode: str = "navigation") -> str:
    """Plot repeat-balanced median pages without reweighting repeated cells."""

    raw_curves = analysis.get("curves")
    if not isinstance(raw_curves, list):
        raise ValueError("agent follow-up analysis has no curves")
    curves = [
        curve
        for curve in raw_curves
        if isinstance(curve, dict)
        and curve.get("mode") == mode
        and isinstance(curve.get("pages_requested"), dict)
    ]
    if not curves:
        raise ValueError(f"agent follow-up analysis has no {mode} page curves")
    labels = sorted(
        {str(curve["page_size"]) for curve in curves},
        key=lambda value: 10_000 if value == "all" else int(value),
    )
    width, height = 900, 470
    left, right, top, bottom = 70, 35, 45, 70
    plot_width = width - left - right
    plot_height = height - top - bottom
    colors = {
        "key": "#555555",
        "indegree": "#0072b2",
        "outdegree": "#56b4e9",
        "pagerank": "#009e73",
        "reverse-pagerank": "#cc79a7",
        "bm25f": "#d55e00",
    }
    ymax = max(
        float(curve["pages_requested"]["p50"])
        for curve in curves
        if curve["pages_requested"].get("p50") is not None
    )

    def x(label: str) -> float:
        if len(labels) == 1:
            return left + plot_width / 2
        return left + labels.index(label) * plot_width / (len(labels) - 1)

    def y(value: float) -> float:
        return top + plot_height * (1 - value / max(1.0, ymax))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="70" y="25" font-family="sans-serif" font-size="17">'
        f"Repeat-balanced pages consumed (p50, {html.escape(mode)})</text>",
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" ' 'stroke="#777"/>',
        f'<line x1="{left}" y1="{top + plot_height}" x2="{width-right}" '
        f'y2="{top + plot_height}" stroke="#777"/>',
    ]
    for label in labels:
        parts.append(
            f'<text x="{x(label)}" y="{height-35}" text-anchor="middle" '
            f'font-family="sans-serif" font-size="13">{html.escape(label)}</text>'
        )
    for tick in range(5):
        value = ymax * tick / 4
        parts.append(
            f'<text x="{left-10}" y="{y(value)+4}" text-anchor="end" '
            f'font-family="sans-serif" font-size="12">{value:.1f}</text>'
        )
    for arm in sorted({str(curve["arm"]) for curve in curves}):
        arm_rows = {
            str(curve["page_size"]): curve
            for curve in curves
            if curve["arm"] == arm and curve["pages_requested"].get("p50") is not None
        }
        points = [
            (x(label), y(float(arm_rows[label]["pages_requested"]["p50"])))
            for label in labels
            if label in arm_rows
        ]
        if not points:
            continue
        color = colors.get(arm, "#333333")
        encoded = " ".join(f"{px:.1f},{py:.1f}" for px, py in points)
        parts.append(
            f'<polyline points="{encoded}" fill="none" stroke="{color}" ' 'stroke-width="2.5"/>'
        )
        for px, py in points:
            parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3" fill="{color}"/>')
        last_x, last_y = points[-1]
        parts.append(
            f'<text x="{last_x-8}" y="{last_y-8}" text-anchor="end" '
            f'font-family="sans-serif" font-size="13" fill="{color}">{arm}</text>'
        )
    parts.append(
        f'<text x="{left + plot_width/2}" y="{height-8}" text-anchor="middle" '
        'font-family="sans-serif" font-size="13">page size</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def write_agent_followup_evidence(
    rows: Sequence[OrderingRunResult],
    task_metadata: Mapping[str, Mapping[str, object]],
    out: Path,
    *,
    provenance: Mapping[str, object],
) -> dict[str, object]:
    analysis = analyze_agent_followup(rows, task_metadata)
    out.mkdir(parents=True, exist_ok=True)
    cells = analysis["cells"]
    if not isinstance(cells, list):
        raise ValueError("agent follow-up analysis has no cell estimates")
    encoded_cells = "".join(json.dumps(cell, sort_keys=True) + "\n" for cell in cells).encode()
    (out / "cell-estimates.jsonl").write_bytes(encoded_cells)
    encoded_analysis = (json.dumps(analysis, indent=2) + "\n").encode()
    (out / "analysis.json").write_bytes(encoded_analysis)
    (out / "report.md").write_text(render_agent_followup_report(analysis), encoding="utf-8")
    for mode in sorted({row.mode.value for row in rows}):
        (out / f"page-size-pages-{mode}.svg").write_text(
            render_agent_followup_svg(analysis, mode=mode), encoding="utf-8"
        )
    sanitized_observations = []
    for row in sorted(rows, key=lambda item: item.run_id):
        projection = row.model_dump(mode="json")
        for excluded in ("query", "final_answer", "failure"):
            projection.pop(excluded, None)
        sanitized_observations.append(projection)
    encoded_observations = "".join(
        json.dumps(row, sort_keys=True) + "\n" for row in sanitized_observations
    ).encode()
    (out / "sanitized-observations.jsonl").write_bytes(encoded_observations)
    canonical_observations = "".join(
        row.model_dump_json() + "\n" for row in sorted(rows, key=lambda row: row.run_id)
    ).encode()
    manifest = {
        "schema_version": 1,
        "observation_count": len(rows),
        "cell_count": len(cells),
        "source_observations_sha256": hashlib.sha256(canonical_observations).hexdigest(),
        "sanitized_observations_sha256": hashlib.sha256(encoded_observations).hexdigest(),
        "cell_estimates_sha256": hashlib.sha256(encoded_cells).hexdigest(),
        "analysis_sha256": hashlib.sha256(encoded_analysis).hexdigest(),
        "privacy_projection": (
            "per-run and derived metrics only; excludes queries, model text, failures, "
            "and credential paths"
        ),
        **dict(provenance),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def oracle_page_metrics(
    *,
    items: tuple[Mapping[str, Any], ...],
    useful_ids: set[str],
    page_size: int | str,
    query: str,
) -> dict[str, int | bool]:
    """Account for complete compact responses through first useful visibility."""

    if not items:
        raise ValueError("oracle pagination requires at least one lexical candidate")
    useful_ranks = [index for index, item in enumerate(items, start=1) if item["id"] in useful_ids]
    if not useful_ranks:
        raise ValueError("no frozen useful Memory appears in the lexical candidate set")
    first_useful_rank = min(useful_ranks)
    effective_size = len(items) if page_size == "all" else int(page_size)
    if effective_size < 1:
        raise ValueError("page size must be positive or 'all'")
    pages_to_useful = 1 if page_size == "all" else math.ceil(first_useful_rank / effective_size)
    response_bytes = 0
    response_tokens = 0
    records = 0
    for page_index in range(pages_to_useful):
        start = page_index * effective_size
        end = min(len(items), start + effective_size)
        page_items = list(items[start:end])
        payload = {
            "items": page_items,
            "query": query,
            "total_matched": len(items),
            "page_size": str(page_size),
            "complete": end == len(items),
            "continuation_available": end < len(items),
        }
        page_bytes, page_tokens = _response_size(payload)
        response_bytes += page_bytes
        response_tokens += page_tokens
        records += len(page_items)
    return {
        "first_useful_rank": first_useful_rank,
        "pages_to_first_useful": pages_to_useful,
        "records_to_first_useful": records,
        "response_bytes_to_first_useful": response_bytes,
        "response_tokens_to_first_useful": response_tokens,
        "page_one_useful": first_useful_rank <= effective_size,
    }


def depth_first_navigation(
    graph: Mapping[str, tuple[str, ...]], *, start: str, target: str
) -> dict[str, int | float | bool]:
    """Measure deterministic reference-order DFS without revisiting cycles."""

    stack: list[tuple[str, int]] = [(start, 0)]
    visited: set[str] = set()
    recalls = 0
    hops = 0
    edges_exposed = 0
    branch_counts: list[int] = []
    reached = False
    while stack:
        memory_id, depth = stack.pop()
        if memory_id in visited or memory_id not in graph:
            continue
        visited.add(memory_id)
        recalls += 1
        if depth > 0:
            hops += 1
        references = graph[memory_id]
        branch_counts.append(len(references))
        edges_exposed += len(references)
        if memory_id == target:
            reached = True
            break
        for reference in reversed(references):
            if reference not in visited:
                stack.append((reference, depth + 1))
    return {
        "reached": reached,
        "hops": hops,
        "recalls": recalls,
        "edges_exposed": edges_exposed,
        "branching_factor_mean": fmean(branch_counts) if branch_counts else 0.0,
        "branching_factor_max": max(branch_counts, default=0),
    }


def summarize_oracle_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["arm"]), str(row["page_size"]))].append(row)
    curves: list[dict[str, object]] = []
    for (arm, page_size), cell in sorted(
        grouped.items(),
        key=lambda item: (item[0][0], 10_000 if item[0][1] == "all" else int(item[0][1])),
    ):
        probability_values = [1.0 if bool(row["page_one_useful"]) else 0.0 for row in cell]
        curves.append(
            {
                "arm": arm,
                "page_size": page_size,
                "n_tasks": len(cell),
                "page_one_useful_probability": fmean(probability_values),
                "pages_to_first_useful": _distribution(
                    [float(row["pages_to_first_useful"]) for row in cell]
                ),
                "response_tokens_to_first_useful": _distribution(
                    [float(row["response_tokens_to_first_useful"]) for row in cell]
                ),
            }
        )
    return {"row_count": len(rows), "curves": curves}


def _task_cluster_ci(
    rows: Sequence[Mapping[str, Any]], *, field: str, seed: int = 5878, resamples: int = 5000
) -> dict[str, float | int | None]:
    if not rows:
        return {"estimate": None, "low": None, "high": None, "clusters": 0}
    by_family: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_family[str(row["graph_family"])].append(row)
    families = sorted(by_family)
    observed = fmean(float(row[field]) for row in rows)
    rng = random.Random(seed)
    sampled: list[float] = []
    for _ in range(resamples):
        chosen = [rng.choice(families) for _ in families]
        values = [float(row[field]) for family in chosen for row in by_family[family]]
        sampled.append(fmean(values))
    return {
        "estimate": observed,
        "low": _percentile(sampled, 0.05),
        "high": _percentile(sampled, 0.95),
        "clusters": len(families),
    }


def _paired_comparisons(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, object]]:
    by_cell = {(str(row["task_id"]), str(row["arm"]), str(row["page_size"])): row for row in rows}
    tasks = sorted({str(row["task_id"]) for row in rows})
    page_sizes = sorted(
        {str(row["page_size"]) for row in rows},
        key=lambda value: 10_000 if value == "all" else int(value),
    )
    arms = sorted({str(row["arm"]) for row in rows})
    comparisons: list[dict[str, object]] = []
    for reference in ("key", "reverse-pagerank", "control-automatic"):
        if reference not in arms:
            continue
        for contender in arms:
            if contender == reference:
                continue
            if reference == "key" and contender.startswith("control-"):
                continue
            if reference == "control-automatic" and not contender.startswith("control-"):
                continue
            for page_size in page_sizes:
                pairs = [
                    (by_cell[(task, reference, page_size)], by_cell[(task, contender, page_size)])
                    for task in tasks
                    if (task, reference, page_size) in by_cell
                    and (task, contender, page_size) in by_cell
                ]
                if not pairs:
                    continue
                pages_saved = [
                    float(base["pages_to_first_useful"]) - float(candidate["pages_to_first_useful"])
                    for base, candidate in pairs
                ]
                token_reduction = [
                    (
                        float(base["response_tokens_to_first_useful"])
                        - float(candidate["response_tokens_to_first_useful"])
                    )
                    / max(1.0, float(base["response_tokens_to_first_useful"]))
                    for base, candidate in pairs
                ]
                comparisons.append(
                    {
                        "reference": reference,
                        "contender": contender,
                        "page_size": page_size,
                        "n_tasks": len(pairs),
                        "page_one_probability_delta": fmean(
                            float(candidate["page_one_useful"]) - float(base["page_one_useful"])
                            for base, candidate in pairs
                        ),
                        "pages_saved": _distribution(pages_saved),
                        "compact_token_reduction_fraction": _distribution(token_reduction),
                    }
                )
    return comparisons


def analyze_oracle_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    basic = summarize_oracle_rows(rows)
    curves = basic["curves"]
    assert isinstance(curves, list)
    by_cell: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_cell[(str(row["arm"]), str(row["page_size"]))].append(row)
    for curve in curves:
        assert isinstance(curve, dict)
        cell = by_cell[(str(curve["arm"]), str(curve["page_size"]))]
        curve["page_one_useful_probability_ci90"] = _task_cluster_ci(
            [dict(row, page_one_useful=float(bool(row["page_one_useful"]))) for row in cell],
            field="page_one_useful",
        )
        curve["primary_rank"] = _distribution([float(row["primary_rank"]) for row in cell])
        curve["first_useful_rank"] = _distribution(
            [float(row["first_useful_rank"]) for row in cell]
        )
        curve["records_to_first_useful"] = _distribution(
            [float(row["records_to_first_useful"]) for row in cell]
        )
        curve["one_shot_candidate_generation_ms"] = _distribution(
            [float(row["one_shot_candidate_generation_ms"]) for row in cell]
        )
        curve["one_shot_ordering_ms"] = _distribution(
            [float(row["one_shot_ordering_ms"]) for row in cell]
        )
        curve["dfs_primary_reach_probability"] = fmean(
            1.0 if bool(row["dfs_reached_primary"]) else 0.0 for row in cell
        )
        curve["dfs_graph_hops"] = _distribution([float(row["dfs_graph_hops"]) for row in cell])

    strata: dict[str, list[dict[str, object]]] = {}
    for field in (
        "graph_family",
        "failure_case",
        "corpus_size",
        "total_matched",
        "baseline_burial_depth",
    ):
        grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row[field])].append(row)
        strata[field] = [
            {
                "value": value,
                "n_rows": len(cell),
                "page_one_useful_probability": fmean(
                    1.0 if bool(row["page_one_useful"]) else 0.0 for row in cell
                ),
                "pages_to_first_useful": _distribution(
                    [float(row["pages_to_first_useful"]) for row in cell]
                ),
            }
            for value, cell in sorted(grouped.items())
        ]
    return {
        "row_count": len(rows),
        "task_count": len({str(row["task_id"]) for row in rows}),
        "graph_family_count": len({str(row["graph_family"]) for row in rows}),
        "curves": curves,
        "paired_comparisons": _paired_comparisons(rows),
        "strata": strata,
        "agent_followup_status": "blocked-authentication; rank/navigation-oracle evidence only",
    }


def render_oracle_report(analysis: Mapping[str, Any]) -> str:
    curves = analysis.get("curves", [])
    if not isinstance(curves, list):
        raise ValueError("oracle analysis has no curve list")
    lines = [
        "# Structural Memory ordering follow-up",
        "",
        "This is a deterministic ordering and navigation oracle over the frozen held-out graph "
        "families. It uses the real experimental Beads CLI and compact projection; these are "
        "not agent outcomes.",
        "",
        "| order | page | page-1 useful | pages p50 / p90 | compact tokens p50 / p90 |",
        "|---|---:|---:|---:|---:|",
    ]
    for curve in curves:
        if not isinstance(curve, Mapping):
            continue
        pages = curve["pages_to_first_useful"]
        tokens = curve["response_tokens_to_first_useful"]
        if not isinstance(pages, Mapping) or not isinstance(tokens, Mapping):
            continue
        lines.append(
            f"| {curve['arm']} | {curve['page_size']} | "
            f"{float(curve['page_one_useful_probability']):.0%} | "
            f"{float(pages['p50']):.1f} / {float(pages['p90']):.1f} | "
            f"{float(tokens['p50']):.0f} / {float(tokens['p90']):.0f} |"
        )
    lines.extend(
        (
            "",
            "Agent-side stopping, recall choice, task success, and latency remain unmeasured in "
            "this follow-up because the recorded OAuth probe could not authenticate. Use the "
            "completed original 1,085-run agent experiment for those outcomes.",
            "",
        )
    )
    return "\n".join(lines)


def render_oracle_svg(analysis: Mapping[str, Any], *, metric: str) -> str:
    curves = analysis.get("curves", [])
    if not isinstance(curves, list):
        raise ValueError("oracle analysis has no curve list")
    main_arms = ("key", "indegree", "outdegree", "pagerank", "reverse-pagerank", "bm25f")
    page_labels = ("5", "10", "20", "all")
    colors = {
        "key": "#555555",
        "indegree": "#0072b2",
        "outdegree": "#56b4e9",
        "pagerank": "#009e73",
        "reverse-pagerank": "#cc79a7",
        "bm25f": "#d55e00",
    }
    values: dict[tuple[str, str], float] = {}
    for curve in curves:
        if not isinstance(curve, Mapping):
            continue
        arm = str(curve["arm"])
        page = str(curve["page_size"])
        if arm not in main_arms or page not in page_labels:
            continue
        if metric == "page_one":
            values[(arm, page)] = float(curve["page_one_useful_probability"])
        elif metric == "pages_p90":
            distribution = curve["pages_to_first_useful"]
            if isinstance(distribution, Mapping):
                values[(arm, page)] = float(distribution["p90"])
        else:
            raise ValueError(f"unknown oracle plot metric: {metric}")
    width, height = 900, 480
    left, right, top, bottom = 70, 190, 50, 65
    plot_width = width - left - right
    plot_height = height - top - bottom
    maximum = 1.0 if metric == "page_one" else max(values.values(), default=1.0)

    def x(index: int) -> float:
        return left + index * plot_width / (len(page_labels) - 1)

    def y(value: float) -> float:
        return top + plot_height * (1 - value / max(1.0, maximum))

    title = (
        "Useful Memory visible on page 1"
        if metric == "page_one"
        else "Pages to first useful Memory (p90 oracle)"
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="28" font-family="sans-serif" font-size="18">'
        f"{html.escape(title)}</text>",
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" ' 'stroke="#777"/>',
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" '
        f'y2="{top + plot_height}" stroke="#777"/>',
    ]
    for tick in range(5):
        value = maximum * tick / 4
        label = f"{value:.0%}" if metric == "page_one" else f"{value:.1f}"
        parts.append(
            f'<text x="{left - 10}" y="{y(value) + 4:.1f}" text-anchor="end" '
            f'font-family="sans-serif" font-size="12">{label}</text>'
        )
    for index, label in enumerate(page_labels):
        parts.append(
            f'<text x="{x(index):.1f}" y="{height - 32}" text-anchor="middle" '
            f'font-family="sans-serif" font-size="13">{label}</text>'
        )
    for arm_index, arm in enumerate(main_arms):
        points = [
            (x(index), y(values[(arm, label)]))
            for index, label in enumerate(page_labels)
            if (arm, label) in values
        ]
        color = colors[arm]
        if points:
            encoded = " ".join(f"{point_x:.1f},{point_y:.1f}" for point_x, point_y in points)
            parts.append(
                f'<polyline points="{encoded}" fill="none" stroke="{color}" ' 'stroke-width="2.5"/>'
            )
            parts.extend(
                f'<circle cx="{point_x:.1f}" cy="{point_y:.1f}" r="3" fill="{color}"/>'
                for point_x, point_y in points
            )
        legend_y = top + 20 + arm_index * 26
        parts.append(
            f'<line x1="{left + plot_width + 18}" y1="{legend_y}" '
            f'x2="{left + plot_width + 45}" y2="{legend_y}" stroke="{color}" '
            'stroke-width="3"/>'
        )
        parts.append(
            f'<text x="{left + plot_width + 52}" y="{legend_y + 4}" '
            f'font-family="sans-serif" font-size="13">{html.escape(arm)}</text>'
        )
    parts.append(
        f'<text x="{left + plot_width / 2}" y="{height - 8}" text-anchor="middle" '
        'font-family="sans-serif" font-size="13">page size</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def collect_oracle_evidence(
    *,
    corpora: Mapping[str, FrozenCorpus],
    validation_dir: Path,
    workspace_root: Path,
    beads_bin: str,
    arms: Sequence[OrderingArm],
    page_sizes: Sequence[int | str],
    bm25f: BM25FConfig,
    split: TaskSplit = TaskSplit.HELDOUT,
) -> list[dict[str, Any]]:
    """Collect rank and deterministic DFS evidence from the real experimental CLI."""

    rows: list[dict[str, Any]] = []
    for family, corpus in sorted(corpora.items()):
        validation = json.loads((validation_dir / f"{family}.json").read_text(encoding="utf-8"))
        task_truth = validation["tasks"]
        for task in corpus.tasks:
            if task.split is not split:
                continue
            raw_truth = task_truth[task.task_id]
            graph = {memory.id: memory.references for memory in corpus.memories[: task.corpus_size]}
            useful = {task.primary_relevant, *task.acceptable_entry_points}
            workspace = task_workspace(workspace_root / family, task, task_scoped=True)
            for arm in arms:
                client = BeadsExperimentClient(
                    beads_bin=beads_bin,
                    workspace=str(workspace),
                    page_size="all",
                    bm25f=bm25f,
                )
                discovery = client.exhaust(task.query, arm)
                if discovery.candidate_digest != raw_truth["candidate_digest"]:
                    raise ValueError(f"candidate digest drift for {task.task_id}/{arm.value}")
                items = tuple(item.model_dump(mode="json") for item in discovery.items)
                observed_ranks = {str(item["id"]): int(item["rank"]) for item in items}
                expected_ranks = {
                    str(memory_id): int(rank)
                    for memory_id, rank in raw_truth["ranks"][arm.value].items()
                }
                if observed_ranks != expected_ranks:
                    raise ValueError(f"rank truth drift for {task.task_id}/{arm.value}")
                primary_rank = observed_ranks[task.primary_relevant]
                entry_ranks = {
                    memory_id: observed_ranks[memory_id]
                    for memory_id in task.acceptable_entry_points
                }
                first_entry = min(entry_ranks, key=lambda memory_id: entry_ranks[memory_id])
                start = (
                    task.primary_relevant
                    if primary_rank <= entry_ranks[first_entry]
                    else first_entry
                )
                navigation = depth_first_navigation(
                    graph, start=start, target=task.primary_relevant
                )
                page = discovery.pages[0]
                for page_size in page_sizes:
                    metrics = oracle_page_metrics(
                        items=items,
                        useful_ids=useful,
                        page_size=page_size,
                        query=task.query,
                    )
                    rows.append(
                        {
                            "task_id": task.task_id,
                            "graph_family": family,
                            "failure_case": task.failure_case,
                            "corpus_size": task.corpus_size,
                            "total_matched": int(raw_truth["total_matched"]),
                            "baseline_burial_depth": int(
                                raw_truth["ranks"][OrderingArm.KEY.value][task.primary_relevant]
                            ),
                            "arm": arm.value,
                            "page_size": str(page_size),
                            "primary_rank": primary_rank,
                            "acceptable_rank": entry_ranks[first_entry],
                            **metrics,
                            "dfs_start_id": start,
                            "dfs_reached_primary": navigation["reached"],
                            "dfs_graph_hops": navigation["hops"],
                            "dfs_recalls": navigation["recalls"],
                            "dfs_edges_exposed": navigation["edges_exposed"],
                            "dfs_branching_factor_mean": navigation["branching_factor_mean"],
                            "dfs_branching_factor_max": navigation["branching_factor_max"],
                            "one_shot_candidate_generation_ms": page.candidate_generation_ms,
                            "one_shot_ordering_ms": page.ordering_ms,
                            "estimated_repeated_candidate_generation_ms": (
                                page.candidate_generation_ms * int(metrics["pages_to_first_useful"])
                            ),
                            "estimated_repeated_ordering_ms": (
                                page.ordering_ms * int(metrics["pages_to_first_useful"])
                            ),
                        }
                    )
    return rows


def write_oracle_evidence(
    rows: Sequence[Mapping[str, Any]], out: Path, *, provenance: Mapping[str, Any]
) -> dict[str, object]:
    out.mkdir(parents=True, exist_ok=True)
    raw = "".join(json.dumps(dict(row), sort_keys=True) + "\n" for row in rows).encode()
    (out / "raw-oracle-results.jsonl").write_bytes(raw)
    analysis = analyze_oracle_rows(rows)
    (out / "analysis.json").write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8")
    (out / "report.md").write_text(render_oracle_report(analysis), encoding="utf-8")
    for metric in ("page_one", "pages_p90"):
        (out / f"{metric.replace('_', '-')}.svg").write_text(
            render_oracle_svg(analysis, metric=metric), encoding="utf-8"
        )
    manifest = {
        "schema_version": 1,
        "row_count": len(rows),
        "raw_results_sha256": hashlib.sha256(raw).hexdigest(),
        "analysis_sha256": hashlib.sha256(
            (json.dumps(analysis, indent=2) + "\n").encode()
        ).hexdigest(),
        "evidence_kind": "deterministic rank and reference-order DFS oracle; not agent outcomes",
        **dict(provenance),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
