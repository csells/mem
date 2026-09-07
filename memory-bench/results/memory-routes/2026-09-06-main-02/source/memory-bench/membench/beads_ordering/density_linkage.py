from __future__ import annotations

import hashlib
import json
import math
import re
from collections import deque
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from membench.beads_ordering.followup_corpus import load_followup_corpora
from membench.beads_ordering.models import (
    ControlIntent,
    FrozenCorpus,
    MemoryFixture,
    OrderingArm,
    OrderingTask,
    TaskSplit,
)
from membench.beads_ordering.mutation import rank_order
from membench.beads_ordering.runner import corpus_digest, file_sha256

CANDIDATE_COUNTS: tuple[int, ...] = (10, 40, 150)


class LinkageLevel(StrEnum):
    SPARSE = "sparse"
    NATIVE = "native"
    ENRICHED = "enriched"


LINKAGE_LEVELS: tuple[LinkageLevel, ...] = tuple(LinkageLevel)


class GraphMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_count: int = Field(ge=1)
    edge_count: int = Field(ge=0)
    nonisolated_node_fraction: float = Field(ge=0, le=1)
    mean_outdegree: float = Field(ge=0)
    p90_outdegree: float = Field(ge=0)
    weak_component_count: int = Field(ge=1)
    largest_weak_component_fraction: float = Field(gt=0, le=1)
    primary_indegree: int = Field(ge=0)
    entry_to_primary_reachable: bool
    shortest_entry_to_primary_hops: int | None = Field(default=None, ge=0)
    candidate_to_useful_reachable_fraction: float = Field(ge=0, le=1)


class DensityLinkageRecipe(BaseModel):
    model_config = ConfigDict(frozen=True)

    variant_id: str
    base_task_id: str
    graph_family: str
    failure_case: str
    candidate_count: int = Field(ge=1)
    linkage_level: LinkageLevel
    candidate_ids: tuple[str, ...]
    graph_metrics: GraphMetrics
    corpus_sha256: str


@dataclass(frozen=True)
class DensityLinkageVariant:
    recipe: DensityLinkageRecipe
    corpus: FrozenCorpus

    @property
    def edge_set(self) -> frozenset[tuple[str, str]]:
        return _edge_set(self.corpus.memories)


def _stable_fraction(*parts: str, denominator: int) -> int:
    digest = hashlib.sha256("\0".join(parts).encode()).digest()
    return int.from_bytes(digest[:8], "big") % denominator


def _replace_query(text: str, query: str) -> str:
    return re.sub(re.escape(query), "related operating control", text, flags=re.IGNORECASE)


def _without_query(memory: MemoryFixture, query: str) -> MemoryFixture:
    return memory.model_copy(
        update={
            "key": _replace_query(memory.key, query),
            "title": _replace_query(memory.title, query),
            "aliases": tuple(_replace_query(alias, query) for alias in memory.aliases),
            "body": _replace_query(memory.body, query),
            "structural_ranks_by_corpus": {},
            "control_ranks_by_task": {},
        }
    )


def _ordered_distractors(corpus: FrozenCorpus, task: OrderingTask) -> tuple[str, ...]:
    useful = {task.primary_relevant, *task.acceptable_entry_points}
    original = [memory_id for memory_id in task.distractors if memory_id not in useful]
    original_set = set(original)
    remainder = sorted(
        (
            memory.id
            for memory in corpus.memories
            if memory.id not in useful and memory.id not in original_set
        ),
        key=lambda memory_id: (
            hashlib.sha256(f"{task.task_id}\0{memory_id}".encode()).hexdigest(),
            memory_id,
        ),
    )
    return (*original, *remainder)


def _candidate_ids(
    corpus: FrozenCorpus, task: OrderingTask, *, candidate_count: int
) -> tuple[str, ...]:
    useful = tuple(dict.fromkeys((task.primary_relevant, *task.acceptable_entry_points)))
    if candidate_count < len(useful) or candidate_count > len(corpus.memories):
        raise ValueError(
            f"candidate count {candidate_count} cannot contain {len(useful)} useful Memories"
        )
    distractors = _ordered_distractors(corpus, task)[: candidate_count - len(useful)]
    return (*useful, *distractors)


def _edge_set(memories: Sequence[MemoryFixture]) -> frozenset[tuple[str, str]]:
    ids = {memory.id for memory in memories}
    return frozenset(
        (memory.id, target)
        for memory in memories
        for target in memory.references
        if target in ids and target != memory.id
    )


def _adjacency(ids: Sequence[str], edges: frozenset[tuple[str, str]]) -> dict[str, tuple[str, ...]]:
    outgoing: dict[str, list[str]] = {memory_id: [] for memory_id in ids}
    for source, target in sorted(edges):
        outgoing[source].append(target)
    return {source: tuple(targets) for source, targets in outgoing.items()}


def _shortest_path_edges(
    adjacency: Mapping[str, tuple[str, ...]], *, start: str, target: str
) -> frozenset[tuple[str, str]]:
    if start == target:
        return frozenset()
    queue: deque[str] = deque([start])
    parent: dict[str, str | None] = {start: None}
    while queue:
        current = queue.popleft()
        for neighbor in adjacency.get(current, ()):
            if neighbor in parent:
                continue
            parent[neighbor] = current
            if neighbor == target:
                path: set[tuple[str, str]] = set()
                cursor = target
                while parent[cursor] is not None:
                    source = parent[cursor]
                    assert source is not None
                    path.add((source, cursor))
                    cursor = source
                return frozenset(path)
            queue.append(neighbor)
    return frozenset()


def _link_edges(
    memories: Sequence[MemoryFixture], task: OrderingTask, level: LinkageLevel
) -> frozenset[tuple[str, str]]:
    native = _edge_set(memories)
    if level is LinkageLevel.NATIVE:
        return native
    if level is LinkageLevel.ENRICHED:
        return native | frozenset((target, source) for source, target in native)

    ids = tuple(memory.id for memory in memories)
    adjacency = _adjacency(ids, native)
    critical: set[tuple[str, str]] = set()
    for entry in task.acceptable_entry_points:
        critical.update(_shortest_path_edges(adjacency, start=entry, target=task.primary_relevant))
    sampled = {
        edge
        for edge in native - critical
        if _stable_fraction(task.task_id, edge[0], edge[1], denominator=4) == 0
    }
    return frozenset((*critical, *sampled))


def _apply_edges(
    memories: Sequence[MemoryFixture], edges: frozenset[tuple[str, str]]
) -> tuple[MemoryFixture, ...]:
    adjacency = _adjacency(tuple(memory.id for memory in memories), edges)
    return tuple(
        memory.model_copy(update={"references": adjacency[memory.id]}) for memory in memories
    )


def _shortest_hops(
    adjacency: Mapping[str, tuple[str, ...]], *, starts: Sequence[str], targets: set[str]
) -> int | None:
    queue: deque[tuple[str, int]] = deque((start, 0) for start in starts)
    visited = set(starts)
    while queue:
        current, depth = queue.popleft()
        if current in targets:
            return depth
        for neighbor in adjacency.get(current, ()):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, depth + 1))
    return None


def _p90(values: Sequence[int]) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = 0.9 * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _graph_metrics(
    memories: Sequence[MemoryFixture], task: OrderingTask, candidate_ids: Sequence[str]
) -> GraphMetrics:
    ids = tuple(memory.id for memory in memories)
    edges = _edge_set(memories)
    adjacency = _adjacency(ids, edges)
    incoming = dict.fromkeys(ids, 0)
    undirected: dict[str, set[str]] = {memory_id: set() for memory_id in ids}
    for source, target in edges:
        incoming[target] += 1
        undirected[source].add(target)
        undirected[target].add(source)
    outdegrees = [len(adjacency[memory_id]) for memory_id in ids]
    nonisolated = sum(bool(adjacency[memory_id]) or incoming[memory_id] > 0 for memory_id in ids)
    remaining = set(ids)
    component_sizes: list[int] = []
    while remaining:
        start = min(remaining)
        stack = [start]
        remaining.remove(start)
        size = 0
        while stack:
            current = stack.pop()
            size += 1
            for neighbor in undirected[current]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
        component_sizes.append(size)

    useful = {task.primary_relevant, *task.acceptable_entry_points}
    reachable_candidates = sum(
        _shortest_hops(adjacency, starts=(memory_id,), targets=useful) is not None
        for memory_id in candidate_ids
    )
    entry_hops = _shortest_hops(
        adjacency,
        starts=task.acceptable_entry_points,
        targets={task.primary_relevant},
    )
    return GraphMetrics(
        node_count=len(ids),
        edge_count=len(edges),
        nonisolated_node_fraction=nonisolated / len(ids),
        mean_outdegree=len(edges) / len(ids),
        p90_outdegree=_p90(outdegrees),
        weak_component_count=len(component_sizes),
        largest_weak_component_fraction=max(component_sizes) / len(ids),
        primary_indegree=incoming[task.primary_relevant],
        entry_to_primary_reachable=entry_hops is not None,
        shortest_entry_to_primary_hops=entry_hops,
        candidate_to_useful_reachable_fraction=reachable_candidates / len(candidate_ids),
    )


def _materialize_ranks(
    memories: tuple[MemoryFixture, ...], *, task_id: str, primary: str, entries: Sequence[str]
) -> tuple[MemoryFixture, ...]:
    rank_maps: dict[str, dict[str, int]] = {memory.id: {} for memory in memories}
    for strategy in ("indegree", "outdegree", "pagerank", "reverse-pagerank"):
        order = rank_order(memories, strategy=strategy, arithmetic="aggregated-dangling-mass")
        for position, memory_id in enumerate(order, start=1):
            rank_maps[memory_id][strategy] = position

    primary_first = tuple(
        dict.fromkeys((primary, *entries, *(sorted(memory.id for memory in memories))))
    )
    control_ranks = {memory_id: position for position, memory_id in enumerate(primary_first, 1)}
    return tuple(
        memory.model_copy(
            update={
                "structural_ranks_by_corpus": {"500": rank_maps[memory.id]},
                "control_ranks_by_task": {
                    task_id: {OrderingArm.CONTROL_SEMANTIC.value: control_ranks[memory.id]}
                },
            }
        )
        for memory in memories
    )


def _variant_id(task: OrderingTask, candidate_count: int, level: LinkageLevel) -> str:
    return f"{task.task_id}--c{candidate_count:03d}--links-{level.value}"


def build_density_linkage_variant(
    corpus: FrozenCorpus,
    *,
    task: OrderingTask,
    candidate_count: int,
    linkage_level: LinkageLevel,
) -> DensityLinkageVariant:
    """Materialize one frozen repeated-measures variant from an existing task."""

    if candidate_count not in CANDIDATE_COUNTS:
        raise ValueError(f"unsupported candidate count: {candidate_count}")
    if task not in corpus.tasks:
        raise ValueError(f"task does not belong to corpus: {task.task_id}")
    if task.split is not TaskSplit.HELDOUT:
        raise ValueError("density/linkage variants use the frozen held-out tasks only")
    if len(corpus.memories) != 500:
        raise ValueError("density/linkage variants require a 500-Memory base corpus")

    selected = _candidate_ids(corpus, task, candidate_count=candidate_count)
    selected_set = set(selected)
    useful = {task.primary_relevant, *task.acceptable_entry_points}
    transformed: list[MemoryFixture] = []
    for memory in corpus.memories:
        current = memory if memory.id in useful else _without_query(memory, task.query)
        current = current.model_copy(
            update={"structural_ranks_by_corpus": {}, "control_ranks_by_task": {}}
        )
        if memory.id in selected_set - useful:
            current = current.model_copy(
                update={
                    "body": (
                        f"{current.body} Historical {task.query} guidance used "
                        f"{task.forbidden_facts[0]}. This is plausible context but not the "
                        "accepted production rule."
                    )
                }
            )
        transformed.append(current)

    edges = _link_edges(transformed, task, linkage_level)
    linked = _apply_edges(transformed, edges)
    variant_id = _variant_id(task, candidate_count, linkage_level)
    distractors = tuple(memory_id for memory_id in selected if memory_id not in useful)
    provenance_hash = hashlib.sha256(
        f"{task.source_provenance_hash}\0{candidate_count}\0{linkage_level.value}".encode()
    ).hexdigest()
    transformed_task = task.model_copy(
        update={
            "task_id": variant_id,
            "corpus_size": 500,
            "distractors": distractors,
            "source_shape": (
                f"density-linkage:{task.task_id}:{candidate_count}:{linkage_level.value}"
            ),
            "source_provenance_hash": provenance_hash,
            "control_intent": ControlIntent(
                pin=(task.primary_relevant,),
                boost=task.acceptable_entry_points,
            ),
        }
    )
    ranked = _materialize_ranks(
        linked,
        task_id=variant_id,
        primary=task.primary_relevant,
        entries=task.acceptable_entry_points,
    )
    variant_corpus = FrozenCorpus(
        seed=5879,
        structural_order_source_git_sha=corpus.structural_order_source_git_sha,
        memories=ranked,
        tasks=(transformed_task,),
    )
    metrics = _graph_metrics(ranked, transformed_task, selected)
    recipe = DensityLinkageRecipe(
        variant_id=variant_id,
        base_task_id=task.task_id,
        graph_family=task.graph_family,
        failure_case=task.failure_case,
        candidate_count=candidate_count,
        linkage_level=linkage_level,
        candidate_ids=selected,
        graph_metrics=metrics,
        corpus_sha256=corpus_digest(variant_corpus),
    )
    return DensityLinkageVariant(recipe=recipe, corpus=variant_corpus)


def build_density_linkage_variants(
    corpora: Mapping[str, FrozenCorpus],
) -> dict[str, DensityLinkageVariant]:
    variants: dict[str, DensityLinkageVariant] = {}
    for family, corpus in sorted(corpora.items()):
        for task in sorted(corpus.tasks, key=lambda item: item.task_id):
            if task.split is not TaskSplit.HELDOUT:
                continue
            if task.graph_family != family:
                raise ValueError(f"graph family mismatch for {task.task_id}")
            for count in CANDIDATE_COUNTS:
                for level in LINKAGE_LEVELS:
                    variant = build_density_linkage_variant(
                        corpus,
                        task=task,
                        candidate_count=count,
                        linkage_level=level,
                    )
                    if variant.recipe.variant_id in variants:
                        raise ValueError(f"duplicate variant ID: {variant.recipe.variant_id}")
                    variants[variant.recipe.variant_id] = variant
    return variants


def _manifest_payload(
    variants: Mapping[str, DensityLinkageVariant],
    *,
    fixture_dir: Path,
    preregistration: Path,
) -> dict[str, Any]:
    source_shas = {variant.corpus.structural_order_source_git_sha for variant in variants.values()}
    if len(source_shas) != 1 or not next(iter(source_shas)):
        raise ValueError("base fixtures do not share one structural-order source SHA")
    base_tasks = {variant.recipe.base_task_id for variant in variants.values()}
    return {
        "schema_version": 1,
        "status": "frozen-before-density-linkage-outcomes",
        "seed": 5879,
        "base_fixture_manifest_sha256": file_sha256(fixture_dir / "manifest.json"),
        "preregistration_sha256": file_sha256(preregistration),
        "structural_order_source_git_sha": next(iter(source_shas)),
        "base_task_count": len(base_tasks),
        "variant_count": len(variants),
        "candidate_counts": list(CANDIDATE_COUNTS),
        "linkage_levels": [level.value for level in LINKAGE_LEVELS],
        "variants": [
            variants[variant_id].recipe.model_dump(mode="json") for variant_id in sorted(variants)
        ],
    }


def write_density_linkage_manifest(
    fixture_dir: Path,
    out: Path,
    *,
    preregistration: Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    if out.exists() and not overwrite:
        raise FileExistsError(f"density/linkage manifest already exists: {out}")
    corpora = load_followup_corpora(fixture_dir)
    variants = build_density_linkage_variants(corpora)
    payload = _manifest_payload(
        variants,
        fixture_dir=fixture_dir.resolve(),
        preregistration=preregistration.resolve(),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def _recipe_entries(payload: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    raw = payload.get("variants")
    if not isinstance(raw, list):
        raise ValueError("density/linkage manifest has no variant inventory")
    for entry in raw:
        if not isinstance(entry, Mapping):
            raise ValueError("density/linkage manifest contains an invalid recipe")
        yield entry


def load_density_linkage_manifest(
    fixture_dir: Path, manifest_path: Path
) -> dict[str, DensityLinkageVariant]:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid density/linkage manifest: {manifest_path}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("unsupported density/linkage manifest schema")
    if payload.get("base_fixture_manifest_sha256") != file_sha256(fixture_dir / "manifest.json"):
        raise ValueError("base fixture manifest drift")

    expected_entries = {
        str(entry.get("variant_id")): dict(entry) for entry in _recipe_entries(payload)
    }
    variants = build_density_linkage_variants(load_followup_corpora(fixture_dir))
    if set(expected_entries) != set(variants):
        raise ValueError("density/linkage variant inventory drift")
    for variant_id, variant in variants.items():
        if expected_entries[variant_id] != variant.recipe.model_dump(mode="json"):
            raise ValueError(f"manifest recipe drift for {variant_id}")
    return variants
