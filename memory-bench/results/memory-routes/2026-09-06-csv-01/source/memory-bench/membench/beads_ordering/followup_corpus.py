from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from membench.beads_ordering.models import (
    ControlIntent,
    ControlPolicy,
    FrozenCorpus,
    MemoryFixture,
    OrderingArm,
    OrderingTask,
    TaskSourceKind,
    TaskSplit,
)
from membench.beads_ordering.ranked_searching import (
    artifact_structural_orders,
    enrich_with_ranked_searching,
)


@dataclass(frozen=True)
class TaskSurface:
    slug: str
    query: str
    expected: str
    forbidden: str
    instruction: str


@dataclass(frozen=True)
class GraphFamily:
    failure_case: str
    description: str
    surfaces: tuple[TaskSurface, TaskSurface, TaskSurface, TaskSurface]


FAILURE_CASES: tuple[str, ...] = (
    "archived-or-stale-hub",
    "new-unlinked-relevant-memory",
    "reference-cycle",
    "disconnected-component",
    "high-outdegree-distractor",
    "superseding-chain",
    "link-inflation",
)

# These choices are frozen operator preferences, not policies selected from outcomes.
# They deliberately span simple query-independent strategies so the control arm tests
# strategy selection itself rather than silently aliasing the automatic default.
SELECTED_STRATEGY_BY_FAILURE: dict[str, OrderingArm] = {
    "archived-or-stale-hub": OrderingArm.OUTDEGREE,
    "new-unlinked-relevant-memory": OrderingArm.KEY,
    "reference-cycle": OrderingArm.INDEGREE,
    "disconnected-component": OrderingArm.PAGERANK,
    "high-outdegree-distractor": OrderingArm.INDEGREE,
    "superseding-chain": OrderingArm.REVERSE_PAGERANK,
    "link-inflation": OrderingArm.OUTDEGREE,
}

CONTROL_ARM_BY_POLICY: dict[ControlPolicy, OrderingArm] = {
    ControlPolicy.AUTOMATIC: OrderingArm.CONTROL_AUTOMATIC,
    ControlPolicy.SEMANTIC: OrderingArm.CONTROL_SEMANTIC,
    ControlPolicy.STRATEGY_SELECTION: OrderingArm.CONTROL_STRATEGY,
    ControlPolicy.RAW_NUMERIC: OrderingArm.CONTROL_RAW,
}


def _surface(slug: str, query: str, expected: str, forbidden: str, instruction: str) -> TaskSurface:
    return TaskSurface(slug, query, expected, forbidden, instruction)


GRAPH_FAMILIES: dict[str, GraphFamily] = {
    "incident-runbook-sparse-authority": GraphFamily(
        "archived-or-stale-hub",
        "Incident response runbooks with a retired but heavily linked index.",
        (
            _surface(
                "alert-dedup",
                "alert dedup window",
                "DEDUP_WINDOW=90s",
                "DEDUP_WINDOW=10m",
                "Choose the incident alert deduplication window.",
            ),
            _surface(
                "lease-fence",
                "incident lease fence",
                "LEASE_FENCE=epoch",
                "LEASE_FENCE=wall-clock",
                "Identify the safe incident-coordinator fencing token.",
            ),
            _surface(
                "pager-drain",
                "pager drain handoff",
                "HANDOFF_MODE=ack-before-close",
                "HANDOFF_MODE=close-before-ack",
                "Select the on-call handoff sequence.",
            ),
            _surface(
                "rollback-signal",
                "incident rollback signal",
                "ROLLBACK_SIGNAL=error-budget-breach",
                "ROLLBACK_SIGNAL=elapsed-time",
                "Choose the automatic incident rollback trigger.",
            ),
        ),
    ),
    "platform-documentation-hub-spoke": GraphFamily(
        "new-unlinked-relevant-memory",
        "Platform documentation with a newly authored correction outside the established hub.",
        (
            _surface(
                "config-precedence",
                "platform config precedence",
                "CONFIG_ORDER=flag-env-file",
                "CONFIG_ORDER=file-env-flag",
                "State the platform configuration precedence.",
            ),
            _surface(
                "token-scope",
                "platform token scope",
                "TOKEN_SCOPE=project",
                "TOKEN_SCOPE=global",
                "Choose the narrow platform automation token scope.",
            ),
            _surface(
                "hook-path",
                "platform hook isolation",
                "HOOKS_PATH=.git/hooks",
                "HOOKS_PATH=global",
                "State how project hooks remain isolated.",
            ),
            _surface(
                "cache-owner",
                "platform cache ownership",
                "CACHE_OWNER=workspace",
                "CACHE_OWNER=user-home",
                "Choose the cache ownership boundary.",
            ),
        ),
    ),
    "migration-correction-temporal-chain": GraphFamily(
        "superseding-chain",
        "Migration guidance with explicit corrections and superseding follow-ups.",
        (
            _surface(
                "freeze-sentinel",
                "migration freeze sentinel",
                "FREEZE_SENTINEL=MIGRATION-FREEZE",
                "FREEZE_SENTINEL=.freeze",
                "Name the migration write-freeze sentinel.",
            ),
            _surface(
                "shadow-suffix",
                "migration shadow suffix",
                "SHADOW_SUFFIX=_next",
                "SHADOW_SUFFIX=_tmp",
                "Choose the collision-safe shadow-table suffix.",
            ),
            _surface(
                "backfill-batch",
                "migration backfill batch",
                "BACKFILL_BATCH=750",
                "BACKFILL_BATCH=10000",
                "Choose the production-safe migration batch size.",
            ),
            _surface(
                "cutover-check",
                "migration cutover check",
                "CUTOVER_CHECK=dual-read",
                "CUTOVER_CHECK=row-count-only",
                "State the cutover verification requirement.",
            ),
        ),
    ),
    "distributed-system-clustered-components": GraphFamily(
        "disconnected-component",
        "Distributed-system operations split across independently maintained service clusters.",
        (
            _surface(
                "replica-fence",
                "replica promotion fence",
                "PROMOTION_FENCE=epoch",
                "PROMOTION_FENCE=timestamp",
                "Identify the replica promotion fence.",
            ),
            _surface(
                "outbox-cursor",
                "outbox replay cursor",
                "OUTBOX_CURSOR=commit_lsn",
                "OUTBOX_CURSOR=created_at",
                "Choose the durable outbox replay cursor.",
            ),
            _surface(
                "quorum-loss",
                "quorum loss recovery",
                "RECOVERY_MODE=read-only",
                "RECOVERY_MODE=force-write",
                "Select the safe quorum-loss behavior.",
            ),
            _surface(
                "clock-skew",
                "clock skew budget",
                "CLOCK_SKEW_BUDGET=250ms",
                "CLOCK_SKEW_BUDGET=5s",
                "State the distributed lease clock-skew budget.",
            ),
        ),
    ),
    "release-engineering-branching-playbooks": GraphFamily(
        "high-outdegree-distractor",
        "Release playbooks where a generic index fans out to many plausible but irrelevant paths.",
        (
            _surface(
                "canary-step",
                "canary promotion step",
                "PROMOTION_STEP=10-percent",
                "PROMOTION_STEP=100-percent",
                "Choose the first canary promotion step.",
            ),
            _surface(
                "manifest-signing",
                "release manifest signing",
                "SIGN_TARGET=canonical-manifest-bytes",
                "SIGN_TARGET=archive-mtime",
                "Choose the artifact representation to sign.",
            ),
            _surface(
                "provenance-gate",
                "release provenance gate",
                "PROVENANCE_GATE=verified-builder",
                "PROVENANCE_GATE=branch-name",
                "State the release provenance gate.",
            ),
            _surface(
                "rollback-window",
                "release rollback window",
                "ROLLBACK_WINDOW=30m",
                "ROLLBACK_WINDOW=24h",
                "Choose the automatic rollback observation window.",
            ),
        ),
    ),
    "data-schema-dependency-dag": GraphFamily(
        "reference-cycle",
        "Data-schema notes organized as a dependency DAG with one accidental cycle.",
        (
            _surface(
                "foreign-key-order",
                "foreign key rollout order",
                "FK_ORDER=parent-before-child",
                "FK_ORDER=child-before-parent",
                "State the safe foreign-key rollout order.",
            ),
            _surface(
                "index-build",
                "schema index build",
                "INDEX_BUILD=concurrent",
                "INDEX_BUILD=blocking",
                "Choose the production index-build mode.",
            ),
            _surface(
                "column-retire",
                "column retirement gate",
                "RETIRE_GATE=no-readers",
                "RETIRE_GATE=deploy-complete",
                "State the column retirement gate.",
            ),
            _surface(
                "type-widen",
                "schema type widening",
                "TYPE_CHANGE=expand-contract",
                "TYPE_CHANGE=in-place",
                "Choose the compatible type-widening procedure.",
            ),
        ),
    ),
    "security-policy-cross-team-network": GraphFamily(
        "link-inflation",
        "Cross-team security guidance with an over-linked but non-authoritative policy note.",
        (
            _surface(
                "secret-rotation",
                "secret rotation overlap",
                "ROTATION_OVERLAP=15m",
                "ROTATION_OVERLAP=0m",
                "Choose the credential rotation overlap.",
            ),
            _surface(
                "audit-retention",
                "audit event retention",
                "AUDIT_RETENTION=400d",
                "AUDIT_RETENTION=30d",
                "State the audit event retention period.",
            ),
            _surface(
                "break-glass",
                "break glass approval",
                "BREAK_GLASS=two-person",
                "BREAK_GLASS=self-approve",
                "State the emergency-access approval rule.",
            ),
            _surface(
                "artifact-quarantine",
                "artifact quarantine release",
                "QUARANTINE_RELEASE=two-clean-scans",
                "QUARANTINE_RELEASE=timeout-only",
                "Choose the artifact quarantine release gate.",
            ),
        ),
    ),
}


_TASK_LAYOUT: tuple[tuple[TaskSplit, int, int], ...] = (
    (TaskSplit.DEVELOPMENT, 100, 24),
    (TaskSplit.HELDOUT, 50, 12),
    (TaskSplit.HELDOUT, 100, 24),
    (TaskSplit.HELDOUT, 500, 96),
)


def _memory_id(family_index: int, index: int) -> str:
    return f"f{family_index + 1:02d}-mem-{index + 1:04d}"


def _candidate_indices(
    *, size: int, count: int, primary: int, entry: int, reserved: set[int]
) -> list[int]:
    result = [primary, entry]
    for index in range(size):
        if index in reserved or index in result:
            continue
        result.append(index)
        if len(result) == count:
            return result
    raise ValueError(f"cannot allocate {count} candidates in a {size}-Memory corpus")


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _apply_failure_shape(
    *,
    failure_case: str,
    primary: int,
    entry: int,
    distractors: list[int],
    size: int,
    references: list[list[str]],
    lifecycle: list[str],
    family_index: int,
) -> None:
    primary_id = _memory_id(family_index, primary)
    entry_id = _memory_id(family_index, entry)
    hub = distractors[0]
    hub_id = _memory_id(family_index, hub)
    lifecycle[hub] = "archived"

    if failure_case != "new-unlinked-relevant-memory":
        references[entry].append(primary_id)

    if failure_case == "archived-or-stale-hub":
        references[hub].extend(_memory_id(family_index, index) for index in distractors[1:12])
        for supporter in range(min(size, 36)):
            if supporter not in {primary, entry, hub}:
                references[supporter].append(hub_id)
    elif failure_case == "new-unlinked-relevant-memory":
        references[primary].clear()
        for source in range(size):
            references[source] = [target for target in references[source] if target != primary_id]
    elif failure_case == "reference-cycle":
        cycle = distractors[:4]
        for index, source in enumerate(cycle):
            references[source].append(_memory_id(family_index, cycle[(index + 1) % len(cycle)]))
    elif failure_case == "disconnected-component":
        component = {primary_id, entry_id}
        references[primary].clear()
        references[entry] = [primary_id]
        for source in range(size):
            if source not in {primary, entry}:
                references[source] = [
                    target for target in references[source] if target not in component
                ]
    elif failure_case == "high-outdegree-distractor":
        references[hub].extend(
            _memory_id(family_index, index)
            for index in range(size)
            if index not in {hub, primary, entry}
        )
    elif failure_case == "superseding-chain":
        chain = distractors[:3]
        for index in chain:
            lifecycle[index] = "archived"
        references[entry] = [_memory_id(family_index, chain[0])]
        references[chain[0]] = [_memory_id(family_index, chain[1])]
        references[chain[1]] = [_memory_id(family_index, chain[2])]
        references[chain[2]] = [primary_id]
    elif failure_case == "link-inflation":
        targets = [index for index in range(size) if index not in {hub, primary, entry}][
            : min(80, size - 3)
        ]
        references[hub].extend(_memory_id(family_index, index) for index in targets)
        for index in targets[:24]:
            references[index].append(hub_id)
    else:  # pragma: no cover - guarded by the frozen family registry
        raise ValueError(f"unknown structural failure case: {failure_case}")


def _build_family(family: str, spec: GraphFamily, *, family_index: int, seed: int) -> FrozenCorpus:
    ids = [_memory_id(family_index, index) for index in range(500)]
    titles = [
        f"{family.replace('-', ' ').title()} operating note {index + 1:03d}" for index in range(500)
    ]
    bodies = [
        f"Operational note {index + 1} for {spec.description.lower()} "
        "It records routine software-factory context and reference provenance."
        for index in range(500)
    ]
    aliases: list[list[str]] = [[] for _ in range(500)]
    references: list[list[str]] = [[] for _ in range(500)]
    lifecycle = ["active"] * 500
    provenance = ["human" if index % 2 == 0 else "agent" for index in range(500)]

    # A sparse background chain makes isolated components and hubs meaningful.
    for index in range(1, 500):
        if index % 3 == 0:
            references[index].append(ids[index - 1])

    positions = ((91, 70), (47, 31), (96, 65), (487, 230))
    reserved = {index for pair in positions for index in pair}
    tasks: list[OrderingTask] = []
    for ordinal, (surface, layout, position) in enumerate(
        zip(spec.surfaces, _TASK_LAYOUT, positions, strict=True)
    ):
        split, size, match_count = layout
        primary, entry = position
        candidates = _candidate_indices(
            size=size,
            count=match_count,
            primary=primary,
            entry=entry,
            reserved=reserved,
        )
        remainder = candidates[2:]
        entry_indices = [entry]
        if ordinal % 2 == 1:
            entry_indices.append(remainder.pop(0))

        if ordinal % 2 == 0:
            titles[primary] = "Corrected production safeguard"
        else:
            titles[primary] = f"Correction for {surface.query}"
        bodies[primary] += (
            f" {surface.query}. The accepted correction is {surface.expected}. "
            f"Do not use {surface.forbidden}; it belongs to a retired rollout."
        )

        for entry_index in entry_indices:
            titles[entry_index] = f"{surface.query.title()} navigation entry"
            aliases[entry_index].append(surface.query)
            bodies[entry_index] += (
                f" Start here for {surface.query}. The current operator decision is "
                f"{surface.expected}; inspect references for the correction history."
            )

        distractors: list[int] = []
        for offset, index in enumerate(remainder):
            distractors.append(index)
            if offset % 3 == 0:
                titles[index] += f" — historical {surface.query} discussion"
            elif offset % 3 == 1:
                aliases[index].append(surface.query)
            bodies[index] += (
                f" Historical {surface.query} guidance used {surface.forbidden}. "
                "This is plausible context but not the accepted production rule."
            )

        for entry_index in entry_indices[1:]:
            references[entry_index].append(ids[primary])
        _apply_failure_shape(
            failure_case=spec.failure_case,
            primary=primary,
            entry=entry,
            distractors=distractors,
            size=size,
            references=references,
            lifecycle=lifecycle,
            family_index=family_index,
        )

        demote = (ids[distractors[0]],) if distractors else ()
        raw_ranks = {ids[entry_indices[0]]: 1, ids[primary]: 2}
        raw_ranks.update({ids[index]: position + 10 for position, index in enumerate(distractors)})
        task_id = f"ordering-followup-{family_index + 1:02d}-{size}-{surface.slug}"
        tasks.append(
            OrderingTask(
                task_id=task_id,
                corpus_size=size,
                query=surface.query,
                instruction=(
                    f"{surface.instruction} Search project Memory using the supplied tool, "
                    "recall what you judge useful, and return the exact configuration token."
                ),
                primary_relevant=ids[primary],
                acceptable_entry_points=tuple(ids[index] for index in entry_indices),
                distractors=tuple(ids[index] for index in distractors),
                expected_facts=(surface.expected,),
                forbidden_facts=(surface.forbidden,),
                split=split,
                source_kind=TaskSourceKind.AUTHORED,
                source_shape=f"followup:{family}:{spec.failure_case}",
                source_provenance_hash=f"followup-{seed}-{family_index + 1}-{ordinal + 1}",
                graph_family=family,
                failure_case=spec.failure_case,
                control_intent=ControlIntent(
                    pin=(ids[entry_indices[0]],),
                    boost=(ids[primary],),
                    demote=demote,
                    selected_strategy=SELECTED_STRATEGY_BY_FAILURE[spec.failure_case],
                    raw_numeric_ranks=raw_ranks,
                ),
            )
        )

    memories = tuple(
        MemoryFixture(
            id=ids[index],
            key=ids[index],
            title=titles[index],
            aliases=_dedupe(aliases[index]),
            lifecycle=lifecycle[index],
            references=_dedupe(references[index]),
            provenance=provenance[index],
            body=bodies[index],
        )
        for index in range(500)
    )
    return FrozenCorpus(seed=seed, memories=memories, tasks=tuple(tasks))


def build_followup_corpora(*, seed: int = 5878) -> dict[str, FrozenCorpus]:
    """Build seven independent graph families without inspecting prior outcomes."""

    if seed != 5878:
        raise ValueError("the structural follow-up corpus is frozen at seed 5878")
    return {
        family: _build_family(family, spec, family_index=index, seed=seed)
        for index, (family, spec) in enumerate(GRAPH_FAMILIES.items())
    }


def enrich_followup_corpora(
    corpora: Mapping[str, FrozenCorpus],
    *,
    artifact_repo: Path,
    order_fn: Callable[..., Mapping[str, tuple[str, ...]]] = artifact_structural_orders,
) -> dict[str, FrozenCorpus]:
    return {
        family: materialize_control_ranks(
            enrich_with_ranked_searching(
                corpus,
                artifact_repo=artifact_repo,
                order_fn=order_fn,
            )
        )
        for family, corpus in corpora.items()
    }


def _materialized_order(
    memories: tuple[MemoryFixture, ...], *, corpus_size: int, arm: OrderingArm
) -> tuple[str, ...]:
    if arm is OrderingArm.KEY:
        return tuple(sorted(memory.id for memory in memories))
    if arm is OrderingArm.BM25F or arm.value.startswith("control-"):
        raise ValueError(f"strategy selection requires a query-independent base order: {arm}")
    try:
        return tuple(
            memory.id
            for memory in sorted(
                memories,
                key=lambda memory: (
                    memory.structural_ranks_by_corpus[str(corpus_size)][arm.value],
                    memory.id,
                ),
            )
        )
    except KeyError as exc:
        raise ValueError(f"missing materialized {arm.value} rank at size {corpus_size}") from exc


def materialize_control_ranks(corpus: FrozenCorpus) -> FrozenCorpus:
    """Materialize task-scoped control policies as rebuildable rank fields."""

    ranks_by_id: dict[str, dict[str, dict[str, int]]] = {
        memory.id: {task_id: dict(arms) for task_id, arms in memory.control_ranks_by_task.items()}
        for memory in corpus.memories
    }
    for task in corpus.tasks:
        if task.control_intent is None:
            raise ValueError(f"task has no frozen control intent: {task.task_id}")
        memories = corpus.memories[: task.corpus_size]
        candidates = tuple(memory.id for memory in memories)
        automatic = _materialized_order(
            memories, corpus_size=task.corpus_size, arm=OrderingArm.REVERSE_PAGERANK
        )
        selected = _materialized_order(
            memories,
            corpus_size=task.corpus_size,
            arm=task.control_intent.selected_strategy,
        )
        for policy, arm in CONTROL_ARM_BY_POLICY.items():
            base = selected if policy is ControlPolicy.STRATEGY_SELECTION else automatic
            ordered = apply_control_order(
                candidates=candidates,
                base_order=base,
                intent=task.control_intent,
                policy=policy,
            )
            for position, memory_id in enumerate(ordered, start=1):
                ranks_by_id[memory_id].setdefault(task.task_id, {})[arm.value] = position
    memories = tuple(
        memory.model_copy(update={"control_ranks_by_task": ranks_by_id[memory.id]})
        for memory in corpus.memories
    )
    return corpus.model_copy(update={"memories": memories})


def write_followup_corpora(
    out: Path,
    *,
    artifact_repo: Path,
    seed: int = 5878,
    overwrite: bool = False,
    order_fn: Callable[..., Mapping[str, tuple[str, ...]]] = artifact_structural_orders,
) -> dict[str, Any]:
    """Freeze all independent families and a deterministic checksum inventory."""

    if out.exists() and any(out.iterdir()) and not overwrite:
        raise FileExistsError(f"follow-up fixture directory already exists: {out}")
    out.mkdir(parents=True, exist_ok=True)
    corpora = enrich_followup_corpora(
        build_followup_corpora(seed=seed),
        artifact_repo=artifact_repo,
        order_fn=order_fn,
    )
    families: dict[str, dict[str, object]] = {}
    development_task_count = 0
    heldout_task_count = 0
    for family, corpus in corpora.items():
        path = out / f"{family}.json"
        encoded = (corpus.model_dump_json(indent=2) + "\n").encode()
        path.write_bytes(encoded)
        family_development_count = sum(task.split is TaskSplit.DEVELOPMENT for task in corpus.tasks)
        family_heldout_count = sum(task.split is TaskSplit.HELDOUT for task in corpus.tasks)
        development_task_count += family_development_count
        heldout_task_count += family_heldout_count
        families[family] = {
            "path": path.name,
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "memory_count": len(corpus.memories),
            "development_task_count": family_development_count,
            "heldout_task_count": family_heldout_count,
            "failure_case": GRAPH_FAMILIES[family].failure_case,
            "structural_order_source_git_sha": corpus.structural_order_source_git_sha,
        }
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "status": "frozen-before-followup-agent-outcomes",
        "seed": seed,
        "family_count": len(families),
        "development_task_count": development_task_count,
        "heldout_task_count": heldout_task_count,
        "families": families,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_followup_corpora(root: Path) -> dict[str, FrozenCorpus]:
    """Load a frozen suite fail-closed on inventory or path drift."""

    resolved_root = root.resolve()
    try:
        manifest = json.loads((resolved_root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid follow-up fixture manifest under {root}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("families"), dict):
        raise ValueError("follow-up fixture manifest has no family inventory")
    corpora: dict[str, FrozenCorpus] = {}
    for family, raw_entry in manifest["families"].items():
        if not isinstance(family, str) or not isinstance(raw_entry, dict):
            raise ValueError("follow-up fixture manifest contains an invalid family entry")
        raw_path = raw_entry.get("path")
        expected = raw_entry.get("sha256")
        if not isinstance(raw_path, str) or not isinstance(expected, str):
            raise ValueError(f"follow-up fixture entry is incomplete: {family}")
        path = (resolved_root / raw_path).resolve()
        try:
            path.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(f"follow-up fixture path escapes suite root: {raw_path}") from exc
        try:
            encoded = path.read_bytes()
        except OSError as exc:
            raise ValueError(f"cannot read follow-up fixture: {path}") from exc
        actual = hashlib.sha256(encoded).hexdigest()
        if actual != expected:
            raise ValueError(f"follow-up fixture checksum mismatch: {family}")
        corpus = FrozenCorpus.model_validate_json(encoded)
        if any(task.graph_family != family for task in corpus.tasks):
            raise ValueError(f"follow-up fixture family label mismatch: {family}")
        corpora[family] = corpus
    if set(corpora) != set(GRAPH_FAMILIES):
        raise ValueError("follow-up fixture family inventory is incomplete")
    return corpora


def apply_control_order(
    *,
    candidates: tuple[str, ...],
    base_order: tuple[str, ...],
    intent: ControlIntent | None,
    policy: ControlPolicy,
) -> tuple[str, ...]:
    """Apply frozen query-independent controls without changing candidate membership."""

    if len(base_order) != len(candidates) or set(base_order) != set(candidates):
        raise ValueError("base order must be a permutation of candidates")
    if intent is None:
        raise ValueError("control policy requires frozen operator intent")
    candidate_set = set(candidates)
    controlled = {*intent.pin, *intent.boost, *intent.demote, *intent.raw_numeric_ranks}
    if not controlled <= candidate_set:
        raise ValueError("control intent references a non-candidate Memory")
    positions = {memory_id: index for index, memory_id in enumerate(base_order)}
    if policy in {ControlPolicy.AUTOMATIC, ControlPolicy.STRATEGY_SELECTION}:
        return base_order
    if policy is ControlPolicy.SEMANTIC:
        pins = set(intent.pin)
        boosts = set(intent.boost) - pins
        demotions = set(intent.demote) - pins - boosts

        def semantic_key(memory_id: str) -> tuple[int, int, str]:
            band = (
                0
                if memory_id in pins
                else 1 if memory_id in boosts else 3 if memory_id in demotions else 2
            )
            return band, positions[memory_id], memory_id

        return tuple(sorted(candidates, key=semantic_key))
    if policy is ControlPolicy.RAW_NUMERIC:
        return tuple(
            sorted(
                candidates,
                key=lambda memory_id: (
                    intent.raw_numeric_ranks.get(memory_id, 2**31 - 1),
                    positions[memory_id],
                    memory_id,
                ),
            )
        )
    raise ValueError(f"unsupported control policy: {policy}")
