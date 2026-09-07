from __future__ import annotations

import json
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from membench.beads_ordering.density_linkage import DensityLinkageVariant
from membench.beads_ordering.models import (
    BM25FConfig,
    ExperimentMode,
    OrderingArm,
    OrderingRunResult,
)
from membench.beads_ordering.report import write_report
from membench.beads_ordering.runner import (
    RankTruth,
    file_sha256,
    git_diff_sha256,
    git_dirty,
    git_sha,
    run_agent_cell,
    seed_beads_workspace,
    validate_paid_run,
    validate_rank_truth,
    write_raw_results,
)


@dataclass(frozen=True)
class DensityLinkageAgentCell:
    variant_id: str
    arm: OrderingArm
    page_size: int | str
    mode: ExperimentMode
    repeat: int


def density_linkage_agent_run_id(
    variant: DensityLinkageVariant,
    *,
    arm: OrderingArm,
    page_size: int | str,
    mode: str | ExperimentMode,
    repeat: int,
) -> str:
    task = variant.corpus.tasks[0]
    normalized_mode = ExperimentMode(mode)
    return f"{task.task_id}:{normalized_mode.value}:{arm.value}:" f"p{page_size}:r{repeat}"


def plan_density_linkage_agent_cells(
    *,
    variants: Mapping[str, DensityLinkageVariant],
    arms: Sequence[OrderingArm],
    page_sizes: Sequence[int | str],
    modes: Sequence[str | ExperimentMode],
    repeat_indices: Sequence[int],
    shard_index: int,
    shard_count: int,
    order_seed: int,
    selected_run_ids: set[str] | frozenset[str] | None = None,
) -> list[DensityLinkageAgentCell]:
    """Build a stable, disjoint agent shard with the preregistered position control."""

    if shard_count < 1:
        raise ValueError("shard count must be positive")
    if shard_index < 0 or shard_index >= shard_count:
        raise ValueError("shard index must be between zero and shard count minus one")
    family_tasks: dict[str, list[str]] = {}
    for variant in variants.values():
        tasks = family_tasks.setdefault(variant.recipe.graph_family, [])
        if variant.recipe.base_task_id not in tasks:
            tasks.append(variant.recipe.base_task_id)
    family_tasks = {family: sorted(tasks) for family, tasks in family_tasks.items()}
    candidate_counts = sorted({variant.recipe.candidate_count for variant in variants.values()})
    linkage_levels = sorted({variant.recipe.linkage_level.value for variant in variants.values()})

    def assigned_shard(variant_id: str) -> int:
        recipe = variants[variant_id].recipe
        task_index = family_tasks[recipe.graph_family].index(recipe.base_task_id)
        candidate_index = candidate_counts.index(recipe.candidate_count)
        linkage_index = linkage_levels.index(recipe.linkage_level.value)
        return (task_index + candidate_index + linkage_index) % shard_count

    selected_variants = [
        variant_id for variant_id in sorted(variants) if assigned_shard(variant_id) == shard_index
    ]
    normalized_modes = tuple(ExperimentMode(mode) for mode in modes)
    cells = [
        DensityLinkageAgentCell(
            variant_id=variant_id,
            arm=arm,
            page_size=page_size,
            mode=mode,
            repeat=repeat,
        )
        for variant_id in selected_variants
        for arm in arms
        for page_size in page_sizes
        if arm is not OrderingArm.CONTROL_SEMANTIC or page_size == "all"
        for mode in normalized_modes
        for repeat in repeat_indices
    ]
    if selected_run_ids is not None:
        cells = [
            cell
            for cell in cells
            if density_linkage_agent_run_id(
                variants[cell.variant_id],
                arm=cell.arm,
                page_size=cell.page_size,
                mode=cell.mode,
                repeat=cell.repeat,
            )
            in selected_run_ids
        ]
    random.Random(order_seed + shard_index).shuffle(cells)
    return cells


def _repeat_indices(*, start: int, count: int) -> tuple[int, ...]:
    if start < 0 or count < 1:
        raise ValueError("repeat start must be nonnegative and count must be positive")
    return tuple(range(start, start + count))


def _cached_result_matches(
    row: OrderingRunResult,
    *,
    mem_sha: str,
    mem_dirty: bool,
    mem_diff_sha: str,
    beads_sha: str,
    beads_dirty: bool,
    beads_diff_sha: str,
    beads_bin_sha: str,
    structural_source_sha: str,
    model: str,
    cli_version: str,
) -> bool:
    return (
        row.mem_git_sha == mem_sha
        and row.mem_git_dirty == mem_dirty
        and row.mem_git_diff_sha256 == mem_diff_sha
        and row.beads_git_sha == beads_sha
        and row.beads_git_dirty == beads_dirty
        and row.beads_git_diff_sha256 == beads_diff_sha
        and row.beads_bin_sha256 == beads_bin_sha
        and row.structural_order_source_git_sha == structural_source_sha
        and row.agent_model == model
        and row.agent_cli_version == cli_version
    )


def run_density_linkage_agent_shard(
    *,
    variants: Mapping[str, DensityLinkageVariant],
    workspace_root: Path,
    beads_bin: str,
    beads_repo: Path,
    mem_repo: Path,
    arms: Sequence[OrderingArm],
    page_sizes: Sequence[int | str],
    modes: Sequence[str | ExperimentMode],
    repeats: int,
    repeat_start: int,
    shard_index: int,
    shard_count: int,
    order_seed: int,
    bm25f: BM25FConfig,
    model: str,
    claude_credentials: Path | None,
    max_tool_calls: int,
    out: Path,
    suite_provenance: Mapping[str, object],
    selected_run_ids: set[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    """Run one resumable account shard through the existing neutral agent cell."""

    resolved_model, cli_version = validate_paid_run(model, claude_credentials=claude_credentials)
    repeat_indices = _repeat_indices(start=repeat_start, count=repeats)
    cells = plan_density_linkage_agent_cells(
        variants=variants,
        arms=arms,
        page_sizes=page_sizes,
        modes=modes,
        repeat_indices=repeat_indices,
        shard_index=shard_index,
        shard_count=shard_count,
        order_seed=order_seed,
        selected_run_ids=selected_run_ids,
    )
    selected_variant_ids = sorted({cell.variant_id for cell in cells})
    if not selected_variant_ids:
        raise ValueError("agent shard contains no variants")

    rank_truth: dict[str, RankTruth] = {}
    for variant_id in selected_variant_ids:
        variant = variants[variant_id]
        task = variant.corpus.tasks[0]
        workspace = workspace_root / variant_id
        seed_beads_workspace(
            corpus=variant.corpus,
            corpus_size=500,
            beads_bin=beads_bin,
            workspace=workspace,
            control_task_id=task.task_id,
        )
        rank_truth[variant_id] = validate_rank_truth(
            task=task,
            workspace=workspace,
            beads_bin=beads_bin,
            bm25f=bm25f,
            arms=arms,
        )

    mem_sha = git_sha(mem_repo)
    mem_is_dirty = git_dirty(mem_repo)
    mem_diff_sha = git_diff_sha256(mem_repo)
    beads_sha = git_sha(beads_repo)
    beads_is_dirty = git_dirty(beads_repo)
    beads_diff_sha = git_diff_sha256(beads_repo)
    beads_binary_sha = file_sha256(Path(beads_bin))
    structural_shas = {
        variants[variant_id].corpus.structural_order_source_git_sha
        for variant_id in selected_variant_ids
    }
    if len(structural_shas) != 1 or not next(iter(structural_shas)):
        raise ValueError("agent shard variants do not share one structural-order source SHA")
    structural_sha = next(iter(structural_shas))

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "started_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "planned_cell_count": len(cells),
        "variant_count": len(selected_variant_ids),
        "shard_index": shard_index,
        "shard_count": shard_count,
        "mem_git_sha": mem_sha,
        "mem_git_dirty": mem_is_dirty,
        "mem_git_diff_sha256": mem_diff_sha,
        "beads_git_sha": beads_sha,
        "beads_git_dirty": beads_is_dirty,
        "beads_git_diff_sha256": beads_diff_sha,
        "beads_bin": beads_bin,
        "beads_bin_sha256": beads_binary_sha,
        "structural_order_source_git_sha": structural_sha,
        "arms": [arm.value for arm in arms],
        "page_sizes": [str(page_size) for page_size in page_sizes],
        "modes": [ExperimentMode(mode).value for mode in modes],
        "repeats": repeats,
        "repeat_start": repeat_start,
        "order_seed": order_seed,
        "max_tool_calls": max_tool_calls,
        "agent_model": resolved_model,
        "agent_cli_version": cli_version,
        "agent_settings": {"autoMemoryEnabled": False},
        "agent_auth": (
            "oauth-environment" if claude_credentials is None else "copied-oauth-credentials"
        ),
        "sharding_convention": (
            "factor-balanced Latin rotation over task-within-family, candidate count, "
            "and linkage level"
        ),
        "bm25f": bm25f.model_dump(),
        "variant_ids": selected_variant_ids,
        "selection_run_count": None if selected_run_ids is None else len(selected_run_ids),
        **dict(suite_provenance),
    }
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        comparable = {key: value for key, value in manifest.items() if key != "started_at"}
        previous_comparable = {key: value for key, value in previous.items() if key != "started_at"}
        if comparable != previous_comparable:
            raise ValueError(f"{out} contains a run with a different manifest")
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    rows: list[OrderingRunResult] = []
    for index, cell in enumerate(cells, start=1):
        variant = variants[cell.variant_id]
        task = variant.corpus.tasks[0]
        run_id = density_linkage_agent_run_id(
            variant,
            arm=cell.arm,
            page_size=cell.page_size,
            mode=cell.mode,
            repeat=cell.repeat,
        )
        result_path = out / "runs" / run_id.replace(":", "__") / "result.json"
        if result_path.exists():
            row = OrderingRunResult.model_validate_json(result_path.read_text(encoding="utf-8"))
            if not _cached_result_matches(
                row,
                mem_sha=mem_sha,
                mem_dirty=mem_is_dirty,
                mem_diff_sha=mem_diff_sha,
                beads_sha=beads_sha,
                beads_dirty=beads_is_dirty,
                beads_diff_sha=beads_diff_sha,
                beads_bin_sha=beads_binary_sha,
                structural_source_sha=structural_sha,
                model=resolved_model,
                cli_version=cli_version,
            ):
                raise ValueError(f"cached run identity mismatch: {run_id}")
        else:
            print(f"[{index}/{len(cells)}] {run_id}", flush=True)
            row = run_agent_cell(
                task=task,
                arm=cell.arm,
                page_size=cell.page_size,
                mode=cell.mode,
                repeat=cell.repeat,
                workspace=workspace_root / cell.variant_id,
                beads_bin=beads_bin,
                bm25f=bm25f,
                rank_truth=rank_truth[cell.variant_id],
                model=resolved_model,
                cli_version=cli_version,
                mem_sha=mem_sha,
                mem_dirty=mem_is_dirty,
                mem_git_diff_sha256=mem_diff_sha,
                beads_sha=beads_sha,
                beads_dirty=beads_is_dirty,
                beads_git_diff_sha256=beads_diff_sha,
                beads_bin_sha256=beads_binary_sha,
                structural_order_source_git_sha=structural_sha,
                artifacts_dir=out,
                claude_credentials=claude_credentials,
                max_tool_calls=max_tool_calls,
            )
        rows.append(row)
        write_raw_results(out / "raw-results.jsonl", rows)
    write_report(rows, out)
    return manifest
