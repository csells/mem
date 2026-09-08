from __future__ import annotations

from dataclasses import dataclass

from membench.beads_ordering.models import (
    FrozenCorpus,
    MemoryFixture,
    OrderingTask,
    TaskSourceKind,
    TaskSplit,
)


@dataclass(frozen=True)
class _Scenario:
    slug: str
    corpus_size: int
    query: str
    expected: str
    forbidden: str
    match_count: int
    primary_index: int
    entry_index: int
    instruction: str
    split: TaskSplit = TaskSplit.DEVELOPMENT
    source_kind: TaskSourceKind = TaskSourceKind.AUTHORED
    source_shape: str = "authored-operational-control"
    source_provenance_hash: str = ""


_DEVELOPMENT_SCENARIOS = (
    _Scenario(
        "lease-renewal",
        50,
        "lease renewal",
        "LEASE_TTL=90s",
        "LEASE_TTL=30s",
        12,
        47,
        31,
        "Choose the safe worker lease configuration for the scheduler rollout.",
    ),
    _Scenario(
        "schema-shadow",
        50,
        "schema shadow",
        "SHADOW_TABLE_SUFFIX=_next",
        "SHADOW_TABLE_SUFFIX=_tmp",
        20,
        44,
        28,
        "Plan the online schema cutover without colliding with cleanup tables.",
    ),
    _Scenario(
        "snapshot-restore",
        50,
        "snapshot restore",
        "RESTORE_VERIFY=manifest-first",
        "RESTORE_VERIFY=checksum-last",
        30,
        49,
        35,
        "State the required verification order before restoring the production snapshot.",
    ),
    _Scenario(
        "worker-drain",
        50,
        "worker drain",
        "DRAIN_GRACE=45s",
        "DRAIN_GRACE=kill-immediate",
        40,
        46,
        38,
        "Select the drain behavior for replacing a saturated worker pool.",
    ),
    _Scenario(
        "migration-freeze",
        100,
        "migration freeze",
        "FREEZE_SENTINEL=MIGRATION-FREEZE",
        "FREEZE_SENTINEL=.freeze",
        20,
        98,
        62,
        "Name the repository sentinel that must gate all write commands during migration.",
    ),
    _Scenario(
        "cache-stampede",
        100,
        "cache stampede",
        "CACHE_LOCK_TTL=12s",
        "CACHE_LOCK_TTL=60s",
        35,
        91,
        55,
        "Choose the lock TTL for the cache stampede guard in the API gateway.",
    ),
    _Scenario(
        "outbox-replay",
        100,
        "outbox replay",
        "OUTBOX_CURSOR=commit_lsn",
        "OUTBOX_CURSOR=created_at",
        55,
        96,
        70,
        "Specify the durable cursor for replaying the PostgreSQL outbox after failover.",
    ),
    _Scenario(
        "hook-isolation",
        100,
        "hook isolation",
        "HOOKS_PATH=.git/hooks",
        "HOOKS_PATH=global",
        70,
        88,
        60,
        "State how temporary git repositories must isolate hooks in tests.",
    ),
    _Scenario(
        "index-backfill",
        500,
        "index backfill",
        "BACKFILL_BATCH=750",
        "BACKFILL_BATCH=10000",
        50,
        488,
        210,
        "Choose the production-safe batch size for the search-index backfill.",
    ),
    _Scenario(
        "replica-failover",
        500,
        "replica failover",
        "FAILOVER_FENCE=epoch",
        "FAILOVER_FENCE=timestamp",
        100,
        470,
        180,
        "Identify the fencing token required when promoting a replica.",
    ),
    _Scenario(
        "artifact-quarantine",
        500,
        "artifact quarantine",
        "QUARANTINE_RETENTION=14d",
        "QUARANTINE_RETENTION=forever",
        160,
        499,
        320,
        "Set the retention rule for artifacts rejected by the provenance verifier.",
    ),
    _Scenario(
        "session-provenance",
        500,
        "session provenance",
        "PROVENANCE_BASE=commit-by-date",
        "PROVENANCE_BASE=branch-tip",
        220,
        450,
        250,
        "Choose the base-commit rule for reconstructing an agent session.",
    ),
)


_HELDOUT_SCENARIOS = (
    _Scenario(
        "sandbox-environment",
        50,
        "sandbox environment",
        "CHILD_ENV=inherit-required",
        "CHILD_ENV=empty",
        8,
        48,
        2,
        "Choose how a sandboxed dispatcher must pass the database endpoint to its child process.",
        TaskSplit.HELDOUT,
        TaskSourceKind.SANITIZED_REAL_DERIVED,
        "subprocess-environment-propagation-failure",
        "add1e0a43208fda7",
    ),
    _Scenario(
        "bounded-safe-read",
        50,
        "bounded safe read",
        "SAFE_READ_CAP=1MiB",
        "SAFE_READ_CAP=unbounded",
        12,
        45,
        5,
        "Set the maximum accepted diagnostic-file read before content is rejected.",
        TaskSplit.HELDOUT,
        TaskSourceKind.SANITIZED_REAL_DERIVED,
        "bounded-file-read-and-race-hardening",
        "a9a2750f55fd844a",
    ),
    _Scenario(
        "mechanism-smoke",
        50,
        "mechanism smoke",
        "FIRE_GATE=pre-run-smoke",
        "FIRE_GATE=post-hoc-only",
        18,
        43,
        8,
        "Choose when an evaluation must prove that its tested mechanism actually fires.",
        TaskSplit.HELDOUT,
        TaskSourceKind.SANITIZED_REAL_DERIVED,
        "pre-run-mechanism-validity-gate",
        "8921aa903fa1909f",
    ),
    _Scenario(
        "partial-total",
        50,
        "partial total",
        "TOTAL_COUNT=successful-rows",
        "TOTAL_COUNT=requested-rows",
        24,
        42,
        11,
        "Define the total count returned when one shard fails during a bounded aggregate read.",
        TaskSplit.HELDOUT,
        TaskSourceKind.SANITIZED_REAL_DERIVED,
        "partial-failure-count-accounting",
        "c0999d7fdc65f8b7",
    ),
    _Scenario(
        "token-refresh",
        50,
        "token refresh",
        "REFRESH_LOCK=single-flight",
        "REFRESH_LOCK=per-request",
        28,
        41,
        14,
        "Choose the concurrency rule for refreshing an expiring service token.",
        TaskSplit.HELDOUT,
        TaskSourceKind.AUTHORED,
        "concurrent-credential-refresh",
        "7255778897ad564b",
    ),
    _Scenario(
        "webhook-dedup",
        50,
        "webhook dedup",
        "DEDUP_KEY=provider-event-id",
        "DEDUP_KEY=delivery-time",
        32,
        40,
        17,
        "Select the durable idempotency key for retried webhook deliveries.",
        TaskSplit.HELDOUT,
        TaskSourceKind.AUTHORED,
        "idempotent-webhook-processing",
        "7225d4b40c5c8eef",
    ),
    _Scenario(
        "temp-cleanup",
        50,
        "temp cleanup",
        "CLEANUP_SCOPE=owned-prefix",
        "CLEANUP_SCOPE=entire-temp-root",
        36,
        39,
        20,
        "Choose the deletion boundary for test-created temporary artifacts.",
        TaskSplit.HELDOUT,
        TaskSourceKind.AUTHORED,
        "safe-temporary-resource-cleanup",
        "fe01491b5a2bc6e0",
    ),
    _Scenario(
        "config-precedence",
        50,
        "config precedence",
        "CONFIG_ORDER=flag-env-file",
        "CONFIG_ORDER=file-env-flag",
        40,
        37,
        23,
        "State the precedence order used to resolve one runtime setting.",
        TaskSplit.HELDOUT,
        TaskSourceKind.AUTHORED,
        "layered-runtime-configuration",
        "30a33d4460f263cc",
    ),
    _Scenario(
        "stable-cursor",
        100,
        "stable cursor",
        "CURSOR_KEY=sort-key-plus-id",
        "CURSOR_KEY=offset-only",
        16,
        99,
        51,
        "Choose the continuation identity for a deterministic bounded list.",
        TaskSplit.HELDOUT,
        TaskSourceKind.SANITIZED_REAL_DERIVED,
        "stable-order-and-cursor-pagination",
        "c763004cb86da3a8",
    ),
    _Scenario(
        "failure-scope",
        100,
        "failure scope",
        "ON_FAIL=abort-scope",
        "ON_FAIL=continue-siblings",
        24,
        97,
        54,
        "Select the runtime action for a workflow step configured to abort its scope.",
        TaskSplit.HELDOUT,
        TaskSourceKind.SANITIZED_REAL_DERIVED,
        "declared-failure-policy-consumption",
        "ad6dbcaada4200bd",
    ),
    _Scenario(
        "field-alias",
        100,
        "field alias",
        "FIELD_MIGRATION=canonical-write-read-alias",
        "FIELD_MIGRATION=dual-write-forever",
        32,
        95,
        58,
        "Choose the compatibility rule for renaming a persisted graph field.",
        TaskSplit.HELDOUT,
        TaskSourceKind.SANITIZED_REAL_DERIVED,
        "persisted-field-compatibility-migration",
        "341d4671af0ff112",
    ),
    _Scenario(
        "relative-check-path",
        100,
        "relative check path",
        "CHECK_PATH_ROOT=work-dir",
        "CHECK_PATH_ROOT=process-cwd",
        40,
        94,
        64,
        "Choose the base directory for resolving a pack-relative validation path.",
        TaskSplit.HELDOUT,
        TaskSourceKind.SANITIZED_REAL_DERIVED,
        "relative-path-resolution-with-workdir",
        "f83b65cbce7e1846",
    ),
    _Scenario(
        "secret-redaction",
        100,
        "secret redaction",
        "REDACT_STAGE=before-persist",
        "REDACT_STAGE=display-only",
        48,
        93,
        67,
        "Choose when request credentials must be removed from diagnostic events.",
        TaskSplit.HELDOUT,
        TaskSourceKind.AUTHORED,
        "diagnostic-secret-redaction",
        "0909e224c2032a87",
    ),
    _Scenario(
        "queue-backpressure",
        100,
        "queue backpressure",
        "OVERFLOW_POLICY=reject-new",
        "OVERFLOW_POLICY=unbounded-buffer",
        56,
        92,
        72,
        "Set the overload behavior for a saturated background-work queue.",
        TaskSplit.HELDOUT,
        TaskSourceKind.AUTHORED,
        "bounded-work-queue-overload",
        "01c39a5118ba5df2",
    ),
    _Scenario(
        "retry-jitter",
        100,
        "retry jitter",
        "RETRY_JITTER=full",
        "RETRY_JITTER=none",
        64,
        90,
        76,
        "Choose the jitter policy for concurrent clients retrying a failed dependency.",
        TaskSplit.HELDOUT,
        TaskSourceKind.AUTHORED,
        "distributed-retry-backoff",
        "7a5076d195a37bdf",
    ),
    _Scenario(
        "lockfile-recovery",
        100,
        "lockfile recovery",
        "STALE_LOCK=verify-owner-then-remove",
        "STALE_LOCK=remove-on-age-only",
        72,
        89,
        80,
        "Select the safe recovery rule for a possibly stale process lock.",
        TaskSplit.HELDOUT,
        TaskSourceKind.AUTHORED,
        "stale-process-lock-recovery",
        "58508c21435762dd",
    ),
    _Scenario(
        "version-probe",
        500,
        "version probe",
        "VERSION_PROBE=server-cached",
        "VERSION_PROBE=observer-shell",
        40,
        497,
        110,
        "Choose where component versions are probed for a status response.",
        TaskSplit.HELDOUT,
        TaskSourceKind.SANITIZED_REAL_DERIVED,
        "server-owned-version-probe-and-cache",
        "cd3d613ae60f1e6a",
    ),
    _Scenario(
        "transcript-join",
        500,
        "transcript join",
        "TRANSCRIPT_JOIN=audio-url",
        "TRANSCRIPT_JOIN=list-position",
        70,
        495,
        130,
        "Choose the stable join key between published audio and its transcript.",
        TaskSplit.HELDOUT,
        TaskSourceKind.SANITIZED_REAL_DERIVED,
        "cross-collection-media-join",
        "1421989a3408e5ad",
    ),
    _Scenario(
        "bonus-round-flow",
        500,
        "bonus round flow",
        "BONUS_TRIGGER=after-tossup",
        "BONUS_TRIGGER=before-tossup",
        100,
        493,
        150,
        "State when the bonus round begins in the corrected game state machine.",
        TaskSplit.HELDOUT,
        TaskSourceKind.SANITIZED_REAL_DERIVED,
        "multi-stage-client-state-machine-fix",
        "3aad5155daa38328",
    ),
    _Scenario(
        "synthesis-shape",
        500,
        "synthesis shape",
        "SYNTHESIS_SCOPE=per-item-four-part",
        "SYNTHESIS_SCOPE=collection-summary-only",
        130,
        491,
        170,
        "Choose the required output granularity for an item explorer synthesis.",
        TaskSplit.HELDOUT,
        TaskSourceKind.SANITIZED_REAL_DERIVED,
        "per-record-structured-content-expansion",
        "a2f5fc4424b1d079",
    ),
    _Scenario(
        "tenancy-fence",
        500,
        "tenancy fence",
        "TENANT_FILTER=storage-boundary",
        "TENANT_FILTER=ui-only",
        160,
        489,
        190,
        "Choose where tenant isolation must be enforced for a shared query path.",
        TaskSplit.HELDOUT,
        TaskSourceKind.AUTHORED,
        "multi-tenant-storage-isolation",
        "43a46bb70074b25a",
    ),
    _Scenario(
        "canary-rollback",
        500,
        "canary rollback",
        "ROLLBACK_SIGNAL=error-budget-breach",
        "ROLLBACK_SIGNAL=elapsed-time-only",
        190,
        487,
        230,
        "Select the automatic rollback trigger for a canary deployment.",
        TaskSplit.HELDOUT,
        TaskSourceKind.AUTHORED,
        "canary-release-rollback-policy",
        "289709f8ec452aa1",
    ),
    _Scenario(
        "manifest-signing",
        500,
        "manifest signing",
        "SIGN_TARGET=canonical-manifest-bytes",
        "SIGN_TARGET=archive-mtime",
        230,
        485,
        270,
        "Choose the exact artifact representation covered by a release signature.",
        TaskSplit.HELDOUT,
        TaskSourceKind.AUTHORED,
        "reproducible-artifact-signature",
        "f425e30937554796",
    ),
    _Scenario(
        "shard-rebalance",
        500,
        "shard rebalance",
        "REBALANCE_LIMIT=one-replica-per-zone",
        "REBALANCE_LIMIT=all-replicas-at-once",
        280,
        483,
        300,
        "Set the movement limit for rebalancing replicas during a zone evacuation.",
        TaskSplit.HELDOUT,
        TaskSourceKind.AUTHORED,
        "failure-domain-aware-rebalancing",
        "0b5f208231359b9c",
    ),
)


_SCENARIOS = (*_DEVELOPMENT_SCENARIOS, *_HELDOUT_SCENARIOS)


def _candidate_indices(
    scenario: _Scenario,
    reserved: set[int],
    *,
    tier_start: int,
    allow_reserved_fallback: bool,
) -> list[int]:
    candidates = [scenario.primary_index, scenario.entry_index]
    ordered_indices = (*range(tier_start, scenario.corpus_size), *range(tier_start))
    for index in ordered_indices:
        if index in reserved or index in candidates:
            continue
        candidates.append(index)
        if len(candidates) == scenario.match_count:
            break
    if allow_reserved_fallback and len(candidates) < scenario.match_count:
        for index in ordered_indices:
            if index in candidates:
                continue
            candidates.append(index)
            if len(candidates) == scenario.match_count:
                break
    if len(candidates) != scenario.match_count:
        raise ValueError(
            f"scenario {scenario.slug} requested {scenario.match_count} candidates "
            f"but only {len(candidates)} are available"
        )
    return candidates


def build_frozen_corpus(*, seed: int = 5877) -> FrozenCorpus:
    if seed != 5877:
        raise ValueError("the authored Beads ordering corpus is frozen at seed 5877")
    titles = [f"Software factory operating note {index + 1:03d}" for index in range(500)]
    aliases: list[list[str]] = [[] for _ in range(500)]
    bodies = [
        f"Operational note {index + 1}. Applies to routine CI, deployment, storage, "
        "or agent maintenance work."
        for index in range(500)
    ]
    references: list[list[str]] = [[] for _ in range(500)]
    lifecycle = ["active"] * 500
    navigation_ranks = [1000 + index for index in range(500)]
    provenance = ["human" if index % 2 == 0 else "agent" for index in range(500)]
    development_reserved = {scenario.primary_index for scenario in _DEVELOPMENT_SCENARIOS} | {
        scenario.entry_index for scenario in _DEVELOPMENT_SCENARIOS
    }
    all_reserved = {scenario.primary_index for scenario in _SCENARIOS} | {
        scenario.entry_index for scenario in _SCENARIOS
    }
    tasks: list[OrderingTask] = []

    for ordinal, scenario in enumerate(_SCENARIOS):
        tier_start = {50: 0, 100: 50, 500: 100}[scenario.corpus_size]
        tier_width = scenario.corpus_size - tier_start
        is_heldout = scenario.split is TaskSplit.HELDOUT
        candidates = _candidate_indices(
            scenario,
            all_reserved if is_heldout else development_reserved,
            tier_start=tier_start,
            allow_reserved_fallback=is_heldout,
        )
        primary_id = f"mem-{scenario.primary_index + 1:04d}"
        entry_id = f"mem-{scenario.entry_index + 1:04d}"
        if ordinal % 3 == 0:
            titles[scenario.primary_index] = "Corrected production safeguard"
            query_repetitions = scenario.query
        else:
            titles[scenario.primary_index] = (
                f"Corrected production rule for {scenario.slug.replace('-', ' ')}"
            )
            query_repetitions = (
                scenario.query if ordinal % 3 == 1 else f"{scenario.query} {scenario.query}"
            )
        bodies[scenario.primary_index] += (
            f" {query_repetitions}. The accepted correction is "
            f"{scenario.expected}. Do not use {scenario.forbidden}; that value came from the "
            "retired rollout."
        )
        navigation_ranks[scenario.primary_index] = 100 + ordinal

        titles[scenario.entry_index] = f"{scenario.query.title()} navigation map"
        aliases[scenario.entry_index].append(scenario.query)
        bodies[scenario.entry_index] += (
            f" Start here for {scenario.query}. Follow the correction reference before changing "
            "production configuration."
        )
        navigation_ranks[scenario.entry_index] = ordinal + 1

        candidate_remainder = list(candidates[2:])
        entry_indices = [scenario.entry_index]
        if ordinal % 2 == 1 and candidate_remainder:
            second_entry_index = candidate_remainder.pop(0)
            entry_indices.append(second_entry_index)
            titles[second_entry_index] = f"{scenario.query.title()} incident index"
            bodies[second_entry_index] += (
                f" Use this {scenario.query} index as an alternate route to the accepted "
                "correction."
            )
            references[second_entry_index].append(primary_id)
            navigation_ranks[second_entry_index] = 50 + ordinal

        distractors: list[str] = []
        for position, index in enumerate(candidate_remainder):
            memory_id = f"mem-{index + 1:04d}"
            distractors.append(memory_id)
            if position % 3 == 0:
                titles[index] += f" — {scenario.query} rollout note"
            elif position % 3 == 1:
                aliases[index].append(scenario.query)
            bodies[index] += (
                f" Historical {scenario.query} discussion used {scenario.forbidden}; "
                "this note is contextual evidence, not the accepted production rule."
            )

        # The graph intentionally contains both helpful authorities and misleading hubs.
        # These edges never change lexical candidate membership.
        entry_targets = [primary_id]
        if ordinal % 4 == 2:
            entry_targets = [*distractors[:5], primary_id]
            bodies[scenario.entry_index] += (
                " Several neighboring investigations are linked; inspect the correction after "
                "ruling out the historical branches."
            )
        references[scenario.entry_index].extend(entry_targets)

        if distractors:
            structural_distractor = distractors[0]
            structural_index = int(structural_distractor.split("-")[1]) - 1
            references[structural_index].extend(distractors[1:9])
            for offset in range(12):
                supporter = tier_start + ((ordinal * 41 + offset * 17 + 7) % tier_width)
                if supporter not in entry_indices and supporter != scenario.primary_index:
                    references[supporter].append(structural_distractor)

        if ordinal % 4 == 1:
            for offset in range(18):
                supporter = tier_start + ((ordinal * 29 + offset * 13 + 11) % tier_width)
                if supporter not in entry_indices and supporter != scenario.primary_index:
                    references[supporter].append(entry_id)

        if distractors:
            archived_index = int(distractors[0].split("-")[1]) - 1
            lifecycle[archived_index] = "archived"

        tasks.append(
            OrderingTask(
                task_id=f"ordering-{scenario.corpus_size}-{scenario.slug}",
                corpus_size=scenario.corpus_size,
                query=scenario.query,
                instruction=(
                    f"{scenario.instruction} Search project Memory using the supplied tool, recall "
                    "what you judge useful, and return a concise decision with the exact "
                    "configuration token."
                ),
                primary_relevant=primary_id,
                acceptable_entry_points=tuple(f"mem-{index + 1:04d}" for index in entry_indices),
                distractors=tuple(distractors),
                expected_facts=(scenario.expected,),
                forbidden_facts=(scenario.forbidden,),
                split=scenario.split,
                source_kind=scenario.source_kind,
                source_shape=scenario.source_shape,
                source_provenance_hash=scenario.source_provenance_hash,
            )
        )

    memories = tuple(
        MemoryFixture(
            id=f"mem-{index + 1:04d}",
            key=f"mem-{index + 1:04d}",
            title=titles[index],
            aliases=tuple(dict.fromkeys(aliases[index])),
            lifecycle=lifecycle[index],
            navigation_rank=navigation_ranks[index],
            references=tuple(dict.fromkeys(references[index])),
            provenance=provenance[index],
            body=bodies[index],
        )
        for index in range(500)
    )
    return FrozenCorpus(seed=seed, memories=memories, tasks=tuple(tasks))
