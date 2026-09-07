from __future__ import annotations

import hashlib
import json
import random
import time
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from membench.beads_ordering.models import FrozenCorpus, MemoryFixture, OrderingTask, TaskSplit


class MutationKind(StrEnum):
    CREATE = "create-memory"
    EDIT = "edit-content"
    ADD_REFERENCE = "add-reference"
    REMOVE_REFERENCE = "remove-reference"
    ARCHIVE = "archive-memory"
    SUPERSEDE = "supersede-memory"
    RESTORE = "restore-memory"


class RankRefreshPolicy(StrEnum):
    EXACT_GLOBAL = "exact-global"
    PERIODIC_5 = "periodic-5"
    PERIODIC_20 = "periodic-20"
    STALE_UNTIL_READ = "stale-until-read"
    INCREMENTAL_IF_FEASIBLE = "incremental-if-feasible"


class MutationEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    sequence: int = Field(ge=1)
    kind: MutationKind
    memory_id: str
    target_id: str = ""
    new_memory_id: str = ""
    value: str = ""


class GraphState(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: int = Field(default=0, ge=0)
    memories: tuple[MemoryFixture, ...]

    @property
    def digest(self) -> str:
        payload = {
            "version": self.version,
            "memories": [memory.model_dump(mode="json") for memory in self.memories],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


class ContinuationEpoch(BaseModel):
    model_config = ConfigDict(frozen=True)

    state_digest: str
    rank_epoch: int = Field(ge=0)


class RankReplayStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    sequence: int = Field(ge=1)
    event_kind: MutationKind
    policy: RankRefreshPolicy
    supported: bool
    feasibility_reason: str = ""
    state_digest: str
    rank_epoch: int = Field(ge=0)
    rank_age_events: int = Field(ge=0)
    refresh_phase: str
    mutation_ms: float = Field(ge=0)
    oracle_compute_ms: float = Field(ge=0)
    refresh_ms: float = Field(ge=0)
    top_10_overlap: float = Field(ge=0, le=1)
    exact_top_10: tuple[str, ...] = ()
    effective_top_10: tuple[str, ...] = ()
    exact_order: tuple[str, ...] = Field(default=(), exclude=True)
    effective_order: tuple[str, ...] = Field(default=(), exclude=True)


class MutationReplayRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    graph_family: str
    failure_case: str
    corpus_size: int = Field(ge=1)
    task_id: str
    sequence: int = Field(ge=1)
    event_kind: MutationKind
    policy: RankRefreshPolicy
    strategy: str
    supported: bool
    feasibility_reason: str = ""
    state_digest: str
    candidate_digest: str
    total_matched: int = Field(ge=0)
    page_size: int = Field(ge=1)
    exact_primary_rank: int = Field(ge=1)
    effective_primary_rank: int = Field(ge=1)
    exact_useful_rank: int = Field(ge=1)
    effective_useful_rank: int = Field(ge=1)
    exact_page_to_first_useful: int = Field(ge=1)
    effective_page_to_first_useful: int = Field(ge=1)
    extra_pages_to_first_useful: int
    rank_epoch: int = Field(ge=0)
    rank_age_events: int = Field(ge=0)
    refresh_phase: str
    mutation_ms: float = Field(ge=0)
    oracle_compute_ms: float = Field(ge=0)
    rank_refresh_ms: float = Field(ge=0)
    top_10_overlap: float = Field(ge=0, le=1)
    continuation_invalidated: bool


class RankScalingRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    graph_family: str
    corpus_size: int = Field(ge=1)
    repeat: int = Field(ge=0)
    strategy: str
    arithmetic: str
    iterations: int = Field(ge=1)
    damping: float = Field(gt=0, lt=1)
    edge_count: int = Field(ge=0)
    compute_ms: float = Field(ge=0)
    order_digest: str
    pinned_top_10_overlap: float | None = Field(default=None, ge=0, le=1)


def build_graph_state(corpus: FrozenCorpus, *, size: int) -> GraphState:
    if size < 1 or size > len(corpus.memories):
        raise ValueError(f"graph size must be between 1 and {len(corpus.memories)}")
    return GraphState(memories=corpus.memories[:size])


def _replace_memory(
    memories: tuple[MemoryFixture, ...], memory_id: str, replacement: MemoryFixture
) -> tuple[MemoryFixture, ...]:
    if replacement.id != memory_id:
        raise ValueError("replacement Memory ID must remain stable")
    found = False
    updated: list[MemoryFixture] = []
    for memory in memories:
        if memory.id == memory_id:
            found = True
            updated.append(replacement)
        else:
            updated.append(memory)
    if not found:
        raise ValueError(f"unknown Memory ID: {memory_id}")
    return tuple(updated)


def _find_memory(memories: tuple[MemoryFixture, ...], memory_id: str) -> MemoryFixture:
    for memory in memories:
        if memory.id == memory_id:
            return memory
    raise ValueError(f"unknown Memory ID: {memory_id}")


def apply_mutation(state: GraphState, event: MutationEvent) -> GraphState:
    """Apply one deterministic event without mutating the prior snapshot."""

    if event.sequence != state.version + 1:
        raise ValueError(
            f"mutation sequence {event.sequence} does not follow state version {state.version}"
        )
    memories = state.memories
    ids = {memory.id for memory in memories}
    if event.kind is MutationKind.CREATE:
        if not event.new_memory_id or event.new_memory_id in ids:
            raise ValueError("create-memory requires a new unique Memory ID")
        memories = (
            *memories,
            MemoryFixture(
                id=event.new_memory_id,
                key=event.new_memory_id,
                title=f"New operational note {event.sequence}",
                body=f"Mutation replay note {event.sequence}. {event.value}",
                provenance="agent",
            ),
        )
    elif event.kind is MutationKind.EDIT:
        memory = _find_memory(memories, event.memory_id)
        memories = _replace_memory(
            memories,
            event.memory_id,
            memory.model_copy(update={"body": f"{memory.body} {event.value}"}),
        )
    elif event.kind is MutationKind.ADD_REFERENCE:
        memory = _find_memory(memories, event.memory_id)
        if event.target_id not in ids or event.target_id == event.memory_id:
            raise ValueError("add-reference requires a distinct existing target")
        if event.target_id in memory.references:
            raise ValueError("add-reference target already exists")
        memories = _replace_memory(
            memories,
            event.memory_id,
            memory.model_copy(update={"references": (*memory.references, event.target_id)}),
        )
    elif event.kind is MutationKind.REMOVE_REFERENCE:
        memory = _find_memory(memories, event.memory_id)
        if event.target_id not in memory.references:
            raise ValueError("remove-reference target does not exist")
        memories = _replace_memory(
            memories,
            event.memory_id,
            memory.model_copy(
                update={
                    "references": tuple(
                        target for target in memory.references if target != event.target_id
                    )
                }
            ),
        )
    elif event.kind is MutationKind.ARCHIVE:
        memory = _find_memory(memories, event.memory_id)
        if memory.lifecycle == "archived":
            raise ValueError("archive-memory target is already archived")
        memories = _replace_memory(
            memories,
            event.memory_id,
            memory.model_copy(update={"lifecycle": "archived"}),
        )
    elif event.kind is MutationKind.SUPERSEDE:
        memory = _find_memory(memories, event.memory_id)
        if not event.new_memory_id or event.new_memory_id in ids:
            raise ValueError("supersede-memory requires a new unique Memory ID")
        old = memory.model_copy(
            update={
                "lifecycle": "archived",
                "references": tuple(dict.fromkeys((*memory.references, event.new_memory_id))),
            }
        )
        memories = (
            *_replace_memory(memories, event.memory_id, old),
            MemoryFixture(
                id=event.new_memory_id,
                key=event.new_memory_id,
                title=f"Superseding operational note {event.sequence}",
                body=f"Current replacement for {event.memory_id}. {event.value}",
                provenance="human",
            ),
        )
    elif event.kind is MutationKind.RESTORE:
        memory = _find_memory(memories, event.memory_id)
        if memory.lifecycle != "archived":
            raise ValueError("restore-memory target is not archived")
        memories = _replace_memory(
            memories,
            event.memory_id,
            memory.model_copy(update={"lifecycle": "active"}),
        )
    else:  # pragma: no cover - exhaustive StrEnum handling
        raise ValueError(f"unsupported mutation: {event.kind}")
    return GraphState(version=event.sequence, memories=memories)


def _select_id(memories: tuple[MemoryFixture, ...], offset: int, *, active: bool | None) -> str:
    eligible = [
        memory.id
        for memory in memories
        if active is None or (memory.lifecycle != "archived") is active
    ]
    if not eligible:
        raise ValueError("mutation schedule has no eligible Memory")
    return eligible[offset % len(eligible)]


def _add_reference_event(state: GraphState, sequence: int, offset: int) -> MutationEvent:
    memories = state.memories
    ids = [memory.id for memory in memories]
    for shift in range(len(memories)):
        source = memories[(offset + shift) % len(memories)]
        for target in ids:
            if target != source.id and target not in source.references:
                return MutationEvent(
                    sequence=sequence,
                    kind=MutationKind.ADD_REFERENCE,
                    memory_id=source.id,
                    target_id=target,
                )
    raise ValueError("graph is complete; cannot add a reference")


def _remove_reference_event(state: GraphState, sequence: int, offset: int) -> MutationEvent:
    memories = state.memories
    for shift in range(len(memories)):
        source = memories[(offset + shift) % len(memories)]
        if source.references:
            return MutationEvent(
                sequence=sequence,
                kind=MutationKind.REMOVE_REFERENCE,
                memory_id=source.id,
                target_id=source.references[0],
            )
    raise ValueError("graph has no reference to remove")


def build_mutation_schedule(
    state: GraphState, *, count: int = 40, seed: int = 5878
) -> tuple[MutationEvent, ...]:
    if count < 1:
        raise ValueError("mutation schedule must contain at least one event")
    rng = random.Random(seed)
    kinds = tuple(MutationKind)
    events: list[MutationEvent] = []
    current = state
    for sequence in range(1, count + 1):
        kind = kinds[(sequence - 1) % len(kinds)]
        offset = rng.randrange(len(current.memories))
        if kind is MutationKind.CREATE:
            event = MutationEvent(
                sequence=sequence,
                kind=kind,
                memory_id="",
                new_memory_id=f"mutation-{seed}-{sequence:04d}",
                value="Query-neutral newly authored guidance.",
            )
        elif kind is MutationKind.EDIT:
            event = MutationEvent(
                sequence=sequence,
                kind=kind,
                memory_id=_select_id(current.memories, offset, active=None),
                value=f"Content revision {sequence}.",
            )
        elif kind is MutationKind.ADD_REFERENCE:
            event = _add_reference_event(current, sequence, offset)
        elif kind is MutationKind.REMOVE_REFERENCE:
            event = _remove_reference_event(current, sequence, offset)
        elif kind is MutationKind.ARCHIVE:
            event = MutationEvent(
                sequence=sequence,
                kind=kind,
                memory_id=_select_id(current.memories, offset, active=True),
            )
        elif kind is MutationKind.SUPERSEDE:
            event = MutationEvent(
                sequence=sequence,
                kind=kind,
                memory_id=_select_id(current.memories, offset, active=True),
                new_memory_id=f"superseding-{seed}-{sequence:04d}",
                value="Query-neutral replacement guidance.",
            )
        else:
            event = MutationEvent(
                sequence=sequence,
                kind=kind,
                memory_id=_select_id(current.memories, offset, active=False),
            )
        events.append(event)
        current = apply_mutation(current, event)
    return tuple(events)


def _graph_edges(
    memories: tuple[MemoryFixture, ...], *, reverse: bool
) -> tuple[tuple[str, ...], list[list[int]]]:
    ids = tuple(memory.id for memory in memories)
    index = {memory_id: position for position, memory_id in enumerate(ids)}
    outgoing: list[list[int]] = [[] for _ in memories]
    incoming: list[list[int]] = [[] for _ in memories]
    for source, memory in enumerate(memories):
        seen: set[int] = set()
        for target_id in memory.references:
            target = index.get(target_id)
            if target is None or target == source or target in seen:
                continue
            seen.add(target)
            outgoing[source].append(target)
            incoming[target].append(source)
    return ids, incoming if reverse else outgoing


def _degree_scores(memories: tuple[MemoryFixture, ...], *, incoming: bool) -> dict[str, float]:
    ids, outgoing = _graph_edges(memories, reverse=False)
    if incoming:
        counts = [0] * len(ids)
        for targets in outgoing:
            for target in targets:
                counts[target] += 1
    else:
        counts = [len(targets) for targets in outgoing]
    return {memory_id: float(counts[index]) for index, memory_id in enumerate(ids)}


def _pagerank_scores(
    memories: tuple[MemoryFixture, ...],
    *,
    reverse: bool,
    damping: float,
    iterations: int,
    arithmetic: str,
) -> dict[str, float]:
    ids, edges = _graph_edges(memories, reverse=reverse)
    count = len(ids)
    if count == 0:
        return {}
    scores = [1.0 / count] * count
    for _ in range(iterations):
        if arithmetic == "pinned-update-order":
            updated = [(1.0 - damping) / count] * count
            for source, targets in enumerate(edges):
                if targets:
                    share = damping * scores[source] / len(targets)
                    for target in targets:
                        updated[target] += share
                else:
                    # Preserve the pinned scorer's update order exactly. This is
                    # deliberately not algebraically collapsed: tiny floating-point
                    # differences would otherwise reorder tied nodes before the ID
                    # tie-breaker is reached.
                    share = damping * scores[source] / count
                    for target in range(count):
                        updated[target] += share
        elif arithmetic == "aggregated-dangling-mass":
            base = (1.0 - damping) / count
            for source, targets in enumerate(edges):
                if not targets:
                    base += damping * scores[source] / count
            updated = [base] * count
            for source, targets in enumerate(edges):
                if not targets:
                    continue
                share = damping * scores[source] / len(targets)
                for target in targets:
                    updated[target] += share
        else:
            raise ValueError(f"unsupported PageRank arithmetic: {arithmetic}")
        scores = updated
    return {memory_id: scores[index] for index, memory_id in enumerate(ids)}


def rank_order(
    memories: tuple[MemoryFixture, ...],
    *,
    strategy: str,
    damping: float = 0.85,
    iterations: int = 100,
    arithmetic: str = "pinned-update-order",
) -> tuple[str, ...]:
    """Small experimental scorer, differentially checked against the pinned source."""

    if strategy == "indegree":
        scores = _degree_scores(memories, incoming=True)
    elif strategy == "outdegree":
        scores = _degree_scores(memories, incoming=False)
    elif strategy == "pagerank":
        scores = _pagerank_scores(
            memories,
            reverse=False,
            damping=damping,
            iterations=iterations,
            arithmetic=arithmetic,
        )
    elif strategy == "reverse-pagerank":
        scores = _pagerank_scores(
            memories,
            reverse=True,
            damping=damping,
            iterations=iterations,
            arithmetic=arithmetic,
        )
    else:
        raise ValueError(f"unsupported structural strategy: {strategy}")
    return tuple(sorted(scores, key=lambda memory_id: (-scores[memory_id], memory_id)))


def candidate_ids(state: GraphState, query: str) -> tuple[str, ...]:
    lowered = query.lower()
    return tuple(
        memory.id
        for memory in state.memories
        if lowered in memory.key.lower()
        or lowered in memory.stored_value(len(state.memories)).lower()
    )


def _aligned_stale_order(order: tuple[str, ...], state: GraphState) -> tuple[str, ...]:
    current = {memory.id for memory in state.memories}
    surviving = tuple(memory_id for memory_id in order if memory_id in current)
    new = tuple(sorted(current - set(surviving)))
    return (*surviving, *new)


def _top_k_overlap(left: tuple[str, ...], right: tuple[str, ...], k: int = 10) -> float:
    denominator = min(k, len(left), len(right))
    if denominator == 0:
        return 1.0
    return len(set(left[:k]) & set(right[:k])) / denominator


_INCREMENTAL_REASON = (
    "batch-only scorer exposes complete-corpus PageRank; an exact local update would require "
    "a new algorithm or dependency and is not feasible under the preregistered PoC boundary"
)


def replay_rank_refresh(
    initial: GraphState,
    events: tuple[MutationEvent, ...],
    *,
    policy: RankRefreshPolicy,
    strategy: str,
) -> tuple[RankReplayStep, ...]:
    current = initial
    effective_order = rank_order(current.memories, strategy=strategy)
    rank_epoch = 0
    last_refresh = 0
    steps: list[RankReplayStep] = []
    interval = 5 if policy is RankRefreshPolicy.PERIODIC_5 else 20
    for event in events:
        started = time.perf_counter_ns()
        current = apply_mutation(current, event)
        mutation_ms = (time.perf_counter_ns() - started) / 1_000_000

        oracle_started = time.perf_counter_ns()
        exact_order = rank_order(current.memories, strategy=strategy)
        oracle_ms = (time.perf_counter_ns() - oracle_started) / 1_000_000
        refresh_phase = "none"
        refresh_ms = 0.0
        supported = policy is not RankRefreshPolicy.INCREMENTAL_IF_FEASIBLE
        reason = "" if supported else _INCREMENTAL_REASON
        if policy is RankRefreshPolicy.EXACT_GLOBAL:
            effective_order = exact_order
            refresh_ms = oracle_ms
            refresh_phase = "mutation"
            rank_epoch += 1
            last_refresh = event.sequence
        elif policy in {RankRefreshPolicy.PERIODIC_5, RankRefreshPolicy.PERIODIC_20}:
            if event.sequence % interval == 0:
                effective_order = exact_order
                refresh_ms = oracle_ms
                refresh_phase = "mutation"
                rank_epoch += 1
                last_refresh = event.sequence
            else:
                effective_order = _aligned_stale_order(effective_order, current)
        elif policy is RankRefreshPolicy.STALE_UNTIL_READ:
            effective_order = exact_order
            refresh_ms = oracle_ms
            refresh_phase = "read"
            rank_epoch += 1
            last_refresh = event.sequence
        elif policy is RankRefreshPolicy.INCREMENTAL_IF_FEASIBLE:
            effective_order = _aligned_stale_order(effective_order, current)
        else:  # pragma: no cover - exhaustive StrEnum handling
            raise ValueError(f"unsupported refresh policy: {policy}")
        steps.append(
            RankReplayStep(
                sequence=event.sequence,
                event_kind=event.kind,
                policy=policy,
                supported=supported,
                feasibility_reason=reason,
                state_digest=current.digest,
                rank_epoch=rank_epoch,
                rank_age_events=event.sequence - last_refresh,
                refresh_phase=refresh_phase,
                mutation_ms=mutation_ms,
                oracle_compute_ms=oracle_ms,
                refresh_ms=refresh_ms,
                top_10_overlap=_top_k_overlap(exact_order, effective_order),
                exact_top_10=exact_order[:10],
                effective_top_10=effective_order[:10],
                exact_order=exact_order,
                effective_order=effective_order,
            )
        )
    return tuple(steps)


def continuation_is_valid(token: ContinuationEpoch, *, state_digest: str, rank_epoch: int) -> bool:
    return token.state_digest == state_digest and token.rank_epoch == rank_epoch


def _candidate_rank(order: tuple[str, ...], candidates: set[str], memory_id: str) -> int:
    filtered = [item for item in order if item in candidates]
    try:
        return filtered.index(memory_id) + 1
    except ValueError as exc:  # pragma: no cover - guarded by fixture parity validation
        raise ValueError(f"candidate order omitted labelled Memory {memory_id}") from exc


def _useful_rank(order: tuple[str, ...], candidates: set[str], task: OrderingTask) -> int:
    useful = {task.primary_relevant, *task.acceptable_entry_points}
    return min(_candidate_rank(order, candidates, memory_id) for memory_id in useful)


def _candidate_digest(candidates: set[str]) -> str:
    return hashlib.sha256("\n".join(sorted(candidates)).encode()).hexdigest()


def _retrieval_snapshot_digest(
    state: GraphState,
    order: tuple[str, ...],
    candidates: set[str],
) -> str:
    """Digest only candidate projection and order relevant to continuation."""

    by_id = {memory.id: memory for memory in state.memories}
    payload = [
        by_id[memory_id].model_dump(mode="json") for memory_id in order if memory_id in candidates
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def run_mutation_experiment(
    corpora: Mapping[str, FrozenCorpus],
    *,
    sizes: tuple[int, ...] = (50, 100, 500),
    event_count: int = 40,
    seed: int = 5878,
    strategy: str = "reverse-pagerank",
    page_size: int = 10,
    policies: tuple[RankRefreshPolicy, ...] = tuple(RankRefreshPolicy),
    ranker: Callable[[tuple[MemoryFixture, ...], str], tuple[str, ...]] | None = None,
) -> tuple[MutationReplayRow, ...]:
    """Replay matched rank-refresh policies against one exact per-event oracle."""

    def compute_order(memories: tuple[MemoryFixture, ...]) -> tuple[str, ...]:
        if ranker is None:
            return rank_order(memories, strategy=strategy)
        return ranker(memories, strategy)

    rows: list[MutationReplayRow] = []
    for family, corpus in sorted(corpora.items()):
        for size in sizes:
            tasks = tuple(
                task
                for task in corpus.tasks
                if task.split is TaskSplit.HELDOUT and task.corpus_size == size
            )
            if not tasks:
                continue
            initial = build_graph_state(corpus, size=size)
            events = build_mutation_schedule(
                initial,
                count=event_count,
                seed=seed + sum(family.encode()) + size,
            )
            initial_order = compute_order(initial.memories)
            effective_orders = dict.fromkeys(policies, initial_order)
            rank_epochs = dict.fromkeys(policies, 0)
            last_refreshes = dict.fromkeys(policies, 0)
            previous_digests: dict[tuple[RankRefreshPolicy, str], str] = {}
            previous_epochs: dict[tuple[RankRefreshPolicy, str], int] = {}
            for policy in policies:
                for task in tasks:
                    candidates = set(candidate_ids(initial, task.query))
                    key = (policy, task.task_id)
                    previous_digests[key] = _retrieval_snapshot_digest(
                        initial, effective_orders[policy], candidates
                    )
                    previous_epochs[key] = 0
            current = initial
            for event in events:
                mutation_started = time.perf_counter_ns()
                current = apply_mutation(current, event)
                mutation_ms = (time.perf_counter_ns() - mutation_started) / 1_000_000
                oracle_started = time.perf_counter_ns()
                exact_order = compute_order(current.memories)
                oracle_ms = (time.perf_counter_ns() - oracle_started) / 1_000_000
                task_candidates: dict[str, set[str]] = {}
                for task in tasks:
                    candidates = set(candidate_ids(current, task.query))
                    labels = {
                        task.primary_relevant,
                        *task.acceptable_entry_points,
                        *task.distractors,
                    }
                    if candidates != labels:
                        raise ValueError(
                            f"mutation changed lexical labels for {task.task_id} at "
                            f"event {event.sequence}"
                        )
                    task_candidates[task.task_id] = candidates

                for policy in policies:
                    supported = policy is not RankRefreshPolicy.INCREMENTAL_IF_FEASIBLE
                    reason = "" if supported else _INCREMENTAL_REASON
                    refresh_phase = "none"
                    refresh_ms = 0.0
                    interval = 5 if policy is RankRefreshPolicy.PERIODIC_5 else 20
                    if policy is RankRefreshPolicy.EXACT_GLOBAL:
                        effective_orders[policy] = exact_order
                        refresh_phase = "mutation"
                        refresh_ms = oracle_ms
                        rank_epochs[policy] += 1
                        last_refreshes[policy] = event.sequence
                    elif policy in {
                        RankRefreshPolicy.PERIODIC_5,
                        RankRefreshPolicy.PERIODIC_20,
                    }:
                        if event.sequence % interval == 0:
                            effective_orders[policy] = exact_order
                            refresh_phase = "mutation"
                            refresh_ms = oracle_ms
                            rank_epochs[policy] += 1
                            last_refreshes[policy] = event.sequence
                        else:
                            effective_orders[policy] = _aligned_stale_order(
                                effective_orders[policy], current
                            )
                    elif policy is RankRefreshPolicy.STALE_UNTIL_READ:
                        effective_orders[policy] = exact_order
                        refresh_phase = "read"
                        refresh_ms = oracle_ms
                        rank_epochs[policy] += 1
                        last_refreshes[policy] = event.sequence
                    elif policy is RankRefreshPolicy.INCREMENTAL_IF_FEASIBLE:
                        effective_orders[policy] = _aligned_stale_order(
                            effective_orders[policy], current
                        )
                    else:  # pragma: no cover - exhaustive StrEnum handling
                        raise ValueError(f"unsupported refresh policy: {policy}")

                    for task in tasks:
                        candidates = task_candidates[task.task_id]
                        effective_order = effective_orders[policy]
                        continuation_key = (policy, task.task_id)
                        snapshot_digest = _retrieval_snapshot_digest(
                            current, effective_order, candidates
                        )
                        token = ContinuationEpoch(
                            state_digest=previous_digests[continuation_key],
                            rank_epoch=previous_epochs[continuation_key],
                        )
                        invalidated = not continuation_is_valid(
                            token,
                            state_digest=snapshot_digest,
                            rank_epoch=rank_epochs[policy],
                        )
                        previous_digests[continuation_key] = snapshot_digest
                        previous_epochs[continuation_key] = rank_epochs[policy]
                        exact_useful = _useful_rank(exact_order, candidates, task)
                        effective_useful = _useful_rank(effective_order, candidates, task)
                        rows.append(
                            MutationReplayRow(
                                graph_family=family,
                                failure_case=task.failure_case,
                                corpus_size=size,
                                task_id=task.task_id,
                                sequence=event.sequence,
                                event_kind=event.kind,
                                policy=policy,
                                strategy=strategy,
                                supported=supported,
                                feasibility_reason=reason,
                                state_digest=current.digest,
                                candidate_digest=_candidate_digest(candidates),
                                total_matched=len(candidates),
                                page_size=page_size,
                                exact_primary_rank=_candidate_rank(
                                    exact_order, candidates, task.primary_relevant
                                ),
                                effective_primary_rank=_candidate_rank(
                                    effective_order, candidates, task.primary_relevant
                                ),
                                exact_useful_rank=exact_useful,
                                effective_useful_rank=effective_useful,
                                exact_page_to_first_useful=(exact_useful - 1) // page_size + 1,
                                effective_page_to_first_useful=(
                                    (effective_useful - 1) // page_size + 1
                                ),
                                extra_pages_to_first_useful=(
                                    (effective_useful - 1) // page_size
                                    - (exact_useful - 1) // page_size
                                ),
                                rank_epoch=rank_epochs[policy],
                                rank_age_events=event.sequence - last_refreshes[policy],
                                refresh_phase=refresh_phase,
                                mutation_ms=mutation_ms,
                                oracle_compute_ms=oracle_ms,
                                rank_refresh_ms=refresh_ms,
                                top_10_overlap=_top_k_overlap(exact_order, effective_order),
                                continuation_invalidated=invalidated,
                            )
                        )
    return tuple(rows)


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _distribution(values: Sequence[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0, "p50": 0.0, "p90": 0.0, "mean": 0.0}
    return {
        "count": len(values),
        "p50": _percentile(values, 0.5),
        "p90": _percentile(values, 0.9),
        "mean": sum(values) / len(values),
        "min": min(values),
        "max": max(values),
    }


def analyze_mutation_experiment(
    rows: Sequence[MutationReplayRow],
) -> dict[str, Any]:
    operational_fields = (
        "event_kind",
        "strategy",
        "supported",
        "feasibility_reason",
        "state_digest",
        "rank_epoch",
        "rank_age_events",
        "refresh_phase",
        "mutation_ms",
        "oracle_compute_ms",
        "rank_refresh_ms",
        "top_10_overlap",
    )
    unique: dict[tuple[str, int, int, RankRefreshPolicy], MutationReplayRow] = {}
    for row in rows:
        key = (row.graph_family, row.corpus_size, row.sequence, row.policy)
        prior = unique.get(key)
        if prior is None:
            unique[key] = row
            continue
        if any(getattr(prior, field) != getattr(row, field) for field in operational_fields):
            raise ValueError(f"inconsistent operational metrics for snapshot {key}")
    operational_rows = list(unique.values())

    def summarize_policy(
        task_rows: Sequence[MutationReplayRow],
        operation_rows: Sequence[MutationReplayRow],
    ) -> dict[str, object]:
        refreshes = [row for row in operation_rows if row.refresh_phase != "none"]
        extra_pages = [float(row.extra_pages_to_first_useful) for row in task_rows]
        overlap = [row.top_10_overlap for row in operation_rows]
        invalidations = sum(row.continuation_invalidated for row in task_rows)
        supported = bool(operation_rows) and all(row.supported for row in operation_rows)
        p90_extra_pages = _percentile(extra_pages, 0.9)
        minimum_overlap = min(overlap, default=0.0)
        invalidation_rate = invalidations / len(task_rows) if task_rows else 0.0
        surrogate_checks = {
            "p90_extra_pages_at_most_1": p90_extra_pages <= 1.0,
            "minimum_top_10_overlap_at_least_0_9": minimum_overlap >= 0.9,
            "continuation_changes_fail_closed": invalidation_rate > 0.0,
        }
        refresh_distribution = _distribution([row.rank_refresh_ms for row in operation_rows])
        mean_refresh_ms = float(refresh_distribution["mean"])
        return {
            "rows": len(task_rows),
            "supported_rows": sum(row.supported for row in task_rows),
            "task_snapshots": len(task_rows),
            "operational_snapshots": len(operation_rows),
            "supported_operational_snapshots": sum(row.supported for row in operation_rows),
            "refresh_event_count": len(refreshes),
            "refresh_event_rate": len(refreshes) / len(operation_rows) if operation_rows else 0.0,
            "rank_refresh_ms": refresh_distribution,
            "rank_refresh_when_run_ms": _distribution([row.rank_refresh_ms for row in refreshes]),
            "amortized_refresh_ms_per_mutation": mean_refresh_ms,
            "single_core_mutations_per_second_at_mean_refresh_cost": (
                1000.0 / mean_refresh_ms if mean_refresh_ms > 0 else None
            ),
            "oracle_compute_ms": _distribution([row.oracle_compute_ms for row in operation_rows]),
            "mutation_latency_ms": _distribution([row.mutation_ms for row in operation_rows]),
            "top_10_overlap": _distribution(overlap),
            "extra_pages_to_first_useful": _distribution(extra_pages),
            "useful_page_parity_rate": (
                sum(row.extra_pages_to_first_useful == 0 for row in task_rows) / len(task_rows)
                if task_rows
                else 0.0
            ),
            "worse_useful_page_rate": (
                sum(row.extra_pages_to_first_useful > 0 for row in task_rows) / len(task_rows)
                if task_rows
                else 0.0
            ),
            "continuation_invalidations": invalidations,
            "continuation_invalidation_rate": invalidation_rate,
            "retrieval_surrogate_checks": surrogate_checks,
            "retrieval_surrogate_gate_passed": supported and all(surrogate_checks.values()),
            "task_success_not_measured": True,
            "rank_freshness_decision_ready": False,
        }

    by_policy: dict[str, dict[str, object]] = {}
    for policy in RankRefreshPolicy:
        selected = [row for row in rows if row.policy is policy]
        selected_operational = [row for row in operational_rows if row.policy is policy]
        by_policy[policy.value] = summarize_policy(selected, selected_operational)

    dimensions: dict[str, Callable[[MutationReplayRow], str]] = {
        "corpus_size": lambda row: str(row.corpus_size),
        "mutation_kind": lambda row: row.event_kind.value,
        "rank_age_events": lambda row: str(row.rank_age_events),
        "graph_family": lambda row: row.graph_family,
        "failure_case": lambda row: row.failure_case,
    }
    strata: dict[str, dict[str, dict[str, object]]] = {}
    for dimension, key_fn in dimensions.items():
        values = sorted({key_fn(row) for row in rows})
        strata[dimension] = {}
        for value in values:
            stratum_tasks = [row for row in rows if key_fn(row) == value]
            stratum_operations = [row for row in operational_rows if key_fn(row) == value]
            strata[dimension][value] = {
                policy.value: summarize_policy(
                    [row for row in stratum_tasks if row.policy is policy],
                    [row for row in stratum_operations if row.policy is policy],
                )
                for policy in RankRefreshPolicy
            }
    return {
        "schema_version": 2,
        "row_count": len(rows),
        "task_snapshot_count": len(rows),
        "operational_snapshot_count": len(operational_rows),
        "by_policy": by_policy,
        "strata": strata,
    }


def write_mutation_experiment(
    rows: Sequence[MutationReplayRow],
    out: Path,
    *,
    provenance: Mapping[str, object],
    seed: int,
    event_count: int,
    damping: float = 0.85,
    iterations: int = 100,
) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    raw_path = out / "raw-results.jsonl"
    raw_path.write_text("".join(row.model_dump_json() + "\n" for row in rows), encoding="utf-8")
    analysis = analyze_mutation_experiment(rows)
    (out / "analysis.json").write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8")
    manifest: dict[str, Any] = {
        "schema_version": 2,
        "status": "compute-and-retrieval-behavior-replay",
        "row_count": len(rows),
        "seed": seed,
        "event_count": event_count,
        "policies": [policy.value for policy in RankRefreshPolicy],
        "rank_strategy": "reverse-pagerank",
        "rank_parameters": {"damping": damping, "iterations": iterations},
        "continuation_binding": (
            "task candidate projection and effective order digest plus rank epoch"
        ),
        "incremental_feasibility": {
            "supported": False,
            "reason": _INCREMENTAL_REASON,
        },
        "provenance": dict(provenance),
        "raw_results_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "analysis_sha256": hashlib.sha256((out / "analysis.json").read_bytes()).hexdigest(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def scale_graph_state(corpus: FrozenCorpus, *, size: int) -> GraphState:
    """Repeat a frozen graph in isolated shards for compute-only scaling."""

    if size < 1:
        raise ValueError("scaled graph size must be positive")
    base = corpus.memories
    base_index = {memory.id: index for index, memory in enumerate(base)}

    def scaled_id(shard: int, index: int) -> str:
        if shard == 0:
            return base[index].id
        return f"scale-{shard:04d}-{base[index].id}"

    ids = [scaled_id(index // len(base), index % len(base)) for index in range(size)]
    available = set(ids)
    memories: list[MemoryFixture] = []
    for absolute in range(size):
        shard, index = divmod(absolute, len(base))
        memory = base[index]
        translated = tuple(
            target
            for target in (
                scaled_id(shard, base_index[reference])
                for reference in memory.references
                if reference in base_index
            )
            if target in available
        )
        if shard == 0 and size >= len(base):
            memories.append(memory)
        else:
            memory_id = ids[absolute]
            memories.append(
                memory.model_copy(
                    update={
                        "id": memory_id,
                        "key": memory_id,
                        "references": translated,
                        "structural_ranks_by_corpus": {},
                    }
                )
            )
    return GraphState(memories=tuple(memories))


def benchmark_rank_scaling(
    corpora: Mapping[str, FrozenCorpus],
    *,
    sizes: tuple[int, ...] = (50, 100, 500, 2000, 10000),
    repeats: int = 3,
    strategy: str = "reverse-pagerank",
    damping: float = 0.85,
    iterations: int = 100,
    arithmetic: str = "boundary",
) -> tuple[RankScalingRow, ...]:
    if repeats < 1:
        raise ValueError("rank-scaling repeats must be positive")
    rows: list[RankScalingRow] = []
    for family, corpus in sorted(corpora.items()):
        for size in sizes:
            state = scale_graph_state(corpus, size=size)
            selected_arithmetic = (
                "pinned-update-order"
                if arithmetic == "boundary" and size <= 500
                else "aggregated-dangling-mass" if arithmetic == "boundary" else arithmetic
            )
            if selected_arithmetic not in {
                "pinned-update-order",
                "aggregated-dangling-mass",
            }:
                raise ValueError(f"unsupported rank-scaling arithmetic: {arithmetic}")
            _, edges = _graph_edges(state.memories, reverse=False)
            edge_count = sum(len(targets) for targets in edges)
            pinned_order = (
                rank_order(
                    state.memories,
                    strategy=strategy,
                    damping=damping,
                    iterations=iterations,
                    arithmetic="pinned-update-order",
                )
                if selected_arithmetic == "aggregated-dangling-mass" and size <= 500
                else None
            )
            for repeat in range(repeats):
                started = time.perf_counter_ns()
                order = rank_order(
                    state.memories,
                    strategy=strategy,
                    damping=damping,
                    iterations=iterations,
                    arithmetic=selected_arithmetic,
                )
                compute_ms = (time.perf_counter_ns() - started) / 1_000_000
                if len(order) != size or set(order) != {memory.id for memory in state.memories}:
                    raise ValueError("rank scaling did not emit a complete permutation")
                rows.append(
                    RankScalingRow(
                        graph_family=family,
                        corpus_size=size,
                        repeat=repeat,
                        strategy=strategy,
                        arithmetic=selected_arithmetic,
                        iterations=iterations,
                        damping=damping,
                        edge_count=edge_count,
                        compute_ms=compute_ms,
                        order_digest=hashlib.sha256("\n".join(order).encode()).hexdigest(),
                        pinned_top_10_overlap=(
                            _top_k_overlap(pinned_order, order)
                            if pinned_order is not None
                            else 1.0 if selected_arithmetic == "pinned-update-order" else None
                        ),
                    )
                )
    return tuple(rows)


def write_rank_scaling(
    rows: Sequence[RankScalingRow],
    out: Path,
    *,
    provenance: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    raw_path = out / "rank-scaling.jsonl"
    raw_path.write_text("".join(row.model_dump_json() + "\n" for row in rows), encoding="utf-8")
    by_size: dict[str, dict[str, object]] = {}
    for size in sorted({row.corpus_size for row in rows}):
        selected = [row for row in rows if row.corpus_size == size]
        by_size[str(size)] = {
            "rows": len(selected),
            "graph_families": len({row.graph_family for row in selected}),
            "arithmetic": sorted({row.arithmetic for row in selected}),
            "compute_ms": _distribution([row.compute_ms for row in selected]),
            "edge_count": _distribution([float(row.edge_count) for row in selected]),
            "pinned_top_10_overlap": _distribution(
                [
                    row.pinned_top_10_overlap
                    for row in selected
                    if row.pinned_top_10_overlap is not None
                ]
            ),
        }
    analysis = {
        "schema_version": 1,
        "row_count": len(rows),
        "by_corpus_size": by_size,
    }
    analysis_path = out / "rank-scaling-analysis.json"
    analysis_path.write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8")
    arithmetic_modes = sorted({row.arithmetic for row in rows})
    pinned_parity_sizes = [row.corpus_size for row in rows if row.pinned_top_10_overlap is not None]
    pinned_overlap = [
        row.pinned_top_10_overlap for row in rows if row.pinned_top_10_overlap is not None
    ]
    manifest = {
        "schema_version": 1,
        "row_count": len(rows),
        "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "analysis_sha256": hashlib.sha256(analysis_path.read_bytes()).hexdigest(),
        "rank_strategy": "reverse-pagerank",
        "rank_parameters": {"damping": 0.85, "iterations": 100},
        "arithmetic_modes": arithmetic_modes,
        "pinned_parity_measured_through_size": max(pinned_parity_sizes, default=None),
        "pinned_top_10_overlap": _distribution(pinned_overlap),
        "arithmetic_boundary": {
            "behavior_sizes": "pinned-update-order",
            "compute-only-sizes": "aggregated-dangling-mass",
        },
        "provenance": dict(provenance or {}),
    }
    (out / "rank-scaling-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest
