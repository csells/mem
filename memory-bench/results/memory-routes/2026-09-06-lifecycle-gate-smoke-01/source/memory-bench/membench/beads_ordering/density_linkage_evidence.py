from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from statistics import fmean, median
from typing import Any

from membench.beads_ordering.client import BeadsExperimentClient, candidate_parity
from membench.beads_ordering.density_linkage import DensityLinkageVariant
from membench.beads_ordering.followup_evidence import (
    depth_first_navigation,
    oracle_page_metrics,
)
from membench.beads_ordering.models import BM25FConfig, OrderingArm
from membench.beads_ordering.runner import seed_beads_workspace


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return float(ordered[0])
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _distribution(values: Sequence[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "p50": 0.0, "p90": 0.0}
    return {
        "mean": fmean(values),
        "p50": median(values),
        "p90": _quantile(values, 0.9),
    }


def collect_density_linkage_oracle(
    *,
    variants: Mapping[str, DensityLinkageVariant],
    workspace_root: Path,
    beads_bin: str,
    arms: Sequence[OrderingArm],
    page_sizes: Sequence[int | str],
    bm25f: BM25FConfig,
) -> list[dict[str, Any]]:
    """Query the real experimental CLI and collect deterministic variant evidence."""

    rows: list[dict[str, Any]] = []
    for variant_id, variant in sorted(variants.items()):
        corpus = variant.corpus
        task = corpus.tasks[0]
        workspace = workspace_root / variant_id
        seed_beads_workspace(
            corpus=corpus,
            corpus_size=500,
            beads_bin=beads_bin,
            workspace=workspace,
            control_task_id=task.task_id,
        )
        discoveries = {
            arm: BeadsExperimentClient(
                beads_bin=beads_bin,
                workspace=str(workspace),
                page_size="all",
                bm25f=bm25f,
            ).exhaust(task.query, arm)
            for arm in arms
        }
        pages = {
            arm: discovery.pages[0].model_dump(mode="json")
            for arm, discovery in discoveries.items()
        }
        parity = candidate_parity(pages)
        labelled = {task.primary_relevant, *task.acceptable_entry_points, *task.distractors}
        if set(parity["candidate_ids"]) != labelled:
            raise ValueError(f"candidate labels drift for {variant_id}")
        if int(parity["total_matched"]) != variant.recipe.candidate_count:
            raise ValueError(f"candidate count drift for {variant_id}")

        graph = {memory.id: memory.references for memory in corpus.memories}
        useful = {task.primary_relevant, *task.acceptable_entry_points}
        rank_by_arm = {
            arm: {item.id: item.rank for item in discovery.items}
            for arm, discovery in discoveries.items()
        }
        baseline_burial = rank_by_arm[OrderingArm.KEY][task.primary_relevant]
        for arm, discovery in discoveries.items():
            ranks = rank_by_arm[arm]
            primary_rank = ranks[task.primary_relevant]
            entry_ranks = {
                memory_id: ranks[memory_id] for memory_id in task.acceptable_entry_points
            }
            first_entry = min(entry_ranks, key=lambda memory_id: entry_ranks[memory_id])
            start = (
                task.primary_relevant if primary_rank <= entry_ranks[first_entry] else first_entry
            )
            navigation = depth_first_navigation(graph, start=start, target=task.primary_relevant)
            items = tuple(item.model_dump(mode="json") for item in discovery.items)
            first_page = discovery.pages[0]
            for page_size in page_sizes:
                if arm is OrderingArm.CONTROL_SEMANTIC and page_size != "all":
                    continue
                page_metrics = oracle_page_metrics(
                    items=items,
                    useful_ids=useful,
                    page_size=page_size,
                    query=task.query,
                )
                rows.append(
                    {
                        "variant_id": variant_id,
                        "base_task_id": variant.recipe.base_task_id,
                        "task_id": task.task_id,
                        "graph_family": variant.recipe.graph_family,
                        "failure_case": variant.recipe.failure_case,
                        "corpus_size": 500,
                        "candidate_count": variant.recipe.candidate_count,
                        "linkage_level": variant.recipe.linkage_level.value,
                        "candidate_digest": parity["candidate_digest"],
                        "baseline_burial_depth": baseline_burial,
                        "arm": arm.value,
                        "page_size": str(page_size),
                        "primary_rank": primary_rank,
                        "acceptable_rank": entry_ranks[first_entry],
                        **page_metrics,
                        "dfs_start_id": start,
                        "dfs_reached_primary": navigation["reached"],
                        "dfs_graph_hops": navigation["hops"],
                        "dfs_recalls": navigation["recalls"],
                        "dfs_edges_exposed": navigation["edges_exposed"],
                        "dfs_branching_factor_mean": navigation["branching_factor_mean"],
                        "dfs_branching_factor_max": navigation["branching_factor_max"],
                        "one_shot_candidate_generation_ms": (first_page.candidate_generation_ms),
                        "one_shot_ordering_ms": first_page.ordering_ms,
                        **{
                            f"graph_{name}": value
                            for name, value in variant.recipe.graph_metrics.model_dump().items()
                        },
                    }
                )
    return rows


def _curve_key(row: Mapping[str, Any]) -> tuple[int, str, str, str]:
    return (
        int(row["candidate_count"]),
        str(row["linkage_level"]),
        str(row["arm"]),
        str(row["page_size"]),
    )


def _paired_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    candidate_count: int,
    linkage_level: str,
    page_size: str,
    reference: str,
    contender: str,
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    selected = [
        row
        for row in rows
        if int(row["candidate_count"]) == candidate_count
        and str(row["linkage_level"]) == linkage_level
        and str(row["page_size"]) == page_size
        and str(row["arm"]) in {reference, contender}
    ]
    by_task: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in selected:
        by_task[str(row["base_task_id"])][str(row["arm"])] = row
    return [
        (arms[reference], arms[contender])
        for arms in by_task.values()
        if reference in arms and contender in arms
    ]


def _policy_contrast(
    pairs: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
) -> dict[str, float]:
    page_one = [
        float(bool(contender["page_one_useful"])) - float(bool(reference["page_one_useful"]))
        for reference, contender in pairs
    ]
    pages = [
        float(reference["pages_to_first_useful"]) - float(contender["pages_to_first_useful"])
        for reference, contender in pairs
    ]
    token_fraction = [
        (
            float(reference["response_tokens_to_first_useful"])
            - float(contender["response_tokens_to_first_useful"])
        )
        / max(1.0, float(reference["response_tokens_to_first_useful"]))
        for reference, contender in pairs
    ]
    return {
        "page_one_gain": fmean(page_one) if page_one else 0.0,
        "median_pages_saved": median(pages) if pages else 0.0,
        "median_compact_token_saving_fraction": (median(token_fraction) if token_fraction else 0.0),
    }


def analyze_density_linkage_oracle(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    grouped: dict[tuple[int, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_curve_key(row)].append(row)
    curves: list[dict[str, Any]] = []
    for (candidate_count, linkage, arm, page_size), cell in sorted(grouped.items()):
        curves.append(
            {
                "candidate_count": candidate_count,
                "linkage_level": linkage,
                "arm": arm,
                "page_size": page_size,
                "task_count": len({str(row["base_task_id"]) for row in cell}),
                "page_one_useful_probability": fmean(
                    float(bool(row["page_one_useful"])) for row in cell
                ),
                "pages_to_first_useful": _distribution(
                    [float(row["pages_to_first_useful"]) for row in cell]
                ),
                "response_tokens_to_first_useful": _distribution(
                    [float(row["response_tokens_to_first_useful"]) for row in cell]
                ),
                "dfs_reached_primary_probability": fmean(
                    float(bool(row["dfs_reached_primary"])) for row in cell
                ),
                "dfs_graph_hops": _distribution([float(row["dfs_graph_hops"]) for row in cell]),
                "dfs_branching_factor_mean": _distribution(
                    [float(row["dfs_branching_factor_mean"]) for row in cell]
                ),
            }
        )

    candidate_counts = sorted({int(row["candidate_count"]) for row in rows})
    linkage_levels = sorted({str(row["linkage_level"]) for row in rows})
    page_sizes = sorted(
        {str(row["page_size"]) for row in rows},
        key=lambda value: 10_000 if value == "all" else int(value),
    )
    arms = {str(row["arm"]) for row in rows}
    contrasts: list[dict[str, Any]] = []
    for reference, contender in (("key", "pagerank"), ("pagerank", "bm25f")):
        if not {reference, contender} <= arms:
            continue
        for candidate_count in candidate_counts:
            for linkage in linkage_levels:
                for page_size in page_sizes:
                    pairs = _paired_rows(
                        rows,
                        candidate_count=candidate_count,
                        linkage_level=linkage,
                        page_size=page_size,
                        reference=reference,
                        contender=contender,
                    )
                    if not pairs:
                        continue
                    contrasts.append(
                        {
                            "candidate_count": candidate_count,
                            "linkage_level": linkage,
                            "page_size": page_size,
                            "reference": reference,
                            "contender": contender,
                            "pair_count": len(pairs),
                            **_policy_contrast(pairs),
                        }
                    )

    interactions: list[dict[str, Any]] = []
    by_contrast = {
        (
            int(item["candidate_count"]),
            str(item["page_size"]),
            str(item["reference"]),
            str(item["contender"]),
            str(item["linkage_level"]),
        ): item
        for item in contrasts
    }
    for candidate_count in candidate_counts:
        for page_size in page_sizes:
            for reference, contender in (("key", "pagerank"), ("pagerank", "bm25f")):
                sparse = by_contrast.get(
                    (candidate_count, page_size, reference, contender, "sparse")
                )
                enriched = by_contrast.get(
                    (candidate_count, page_size, reference, contender, "enriched")
                )
                if sparse is None or enriched is None:
                    continue
                interactions.append(
                    {
                        "candidate_count": candidate_count,
                        "page_size": page_size,
                        "reference": reference,
                        "contender": contender,
                        "page_one_gain_change_enriched_minus_sparse": (
                            float(enriched["page_one_gain"]) - float(sparse["page_one_gain"])
                        ),
                        "median_pages_saved_change_enriched_minus_sparse": (
                            float(enriched["median_pages_saved"])
                            - float(sparse["median_pages_saved"])
                        ),
                        "compact_token_saving_change_enriched_minus_sparse": (
                            float(enriched["median_compact_token_saving_fraction"])
                            - float(sparse["median_compact_token_saving_fraction"])
                        ),
                    }
                )
    return {
        "schema_version": 1,
        "evidence_kind": "deterministic ordering and navigation oracle; not agent outcomes",
        "row_count": len(rows),
        "base_task_count": len({str(row["base_task_id"]) for row in rows}),
        "variant_count": len({str(row["variant_id"]) for row in rows}),
        "curves": curves,
        "paired_policy_contrasts": contrasts,
        "linkage_interactions": interactions,
    }


def render_density_linkage_oracle_report(analysis: Mapping[str, Any]) -> str:
    lines = [
        "# Candidate-density and linkage oracle",
        "",
        "Deterministic rank/page/reference evidence only; these are not agent outcomes.",
        "",
        "| candidates | links | arm | page | page-one useful | pages p50/p90 | "
        "compact tokens p50/p90 |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in analysis["curves"]:
        pages = row["pages_to_first_useful"]
        tokens = row["response_tokens_to_first_useful"]
        lines.append(
            f"| {row['candidate_count']} | {row['linkage_level']} | {row['arm']} | "
            f"{row['page_size']} | {row['page_one_useful_probability']:.3f} | "
            f"{pages['p50']:.1f}/{pages['p90']:.1f} | "
            f"{tokens['p50']:.0f}/{tokens['p90']:.0f} |"
        )
    return "\n".join(lines) + "\n"


def write_density_linkage_oracle(
    rows: Sequence[Mapping[str, Any]], out: Path, *, provenance: Mapping[str, Any]
) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    raw = "".join(json.dumps(dict(row), sort_keys=True) + "\n" for row in rows).encode()
    (out / "raw-oracle-results.jsonl").write_bytes(raw)
    analysis = analyze_density_linkage_oracle(rows)
    encoded_analysis = (json.dumps(analysis, indent=2) + "\n").encode()
    (out / "analysis.json").write_bytes(encoded_analysis)
    (out / "report.md").write_text(render_density_linkage_oracle_report(analysis), encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "row_count": len(rows),
        "raw_results_sha256": hashlib.sha256(raw).hexdigest(),
        "analysis_sha256": hashlib.sha256(encoded_analysis).hexdigest(),
        "provenance": dict(provenance),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
