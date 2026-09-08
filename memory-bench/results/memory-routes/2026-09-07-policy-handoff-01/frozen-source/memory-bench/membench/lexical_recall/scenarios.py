"""The 36 frozen lexical-miss pairs, nine per kind.

Each pair is `(query, surface_form)`: the query an operator would type, and the
wording the gold Memory actually uses. The pairs are chosen so that neither
string is a case-insensitive substring of the other, which is what makes the
literal matcher miss. `corpus.validate_miss_construction` re-checks that
mechanically against the materialized text rather than trusting this table.

Short queries are avoided on purpose. A two-letter query like `CI` is a substring
of `efficiency` and `decision`, so it would match filler prose and the miss would
stop being a property of the pair. Where the abbreviation is the query it is at
least four characters.
"""

from __future__ import annotations

from membench.lexical_recall.models import MissKind

SYNONYM_PAIRS: tuple[tuple[str, str], ...] = (
    ("deployment rollback", "release revert"),
    ("stale cache", "outdated buffer"),
    ("throttling", "rate limiting"),
    ("outage", "service disruption"),
    ("credential rotation", "secret cycling"),
    ("shard rebalance", "partition redistribution"),
    ("backpressure", "flow control"),
    ("cold start", "initial warmup"),
    ("quorum loss", "majority failure"),
)

ABBREVIATION_PAIRS: tuple[tuple[str, str], ...] = (
    ("time to live", "TTL"),
    ("continuous integration", "CI"),
    ("remote procedure call", "RPC"),
    ("write ahead log", "WAL"),
    ("mean time to recovery", "MTTR"),
    ("RBAC", "role based access control"),
    ("OIDC", "open id connect"),
    ("HSTS", "strict transport security"),
    ("CIDR", "classless inter domain routing"),
)

RENAMED_CONCEPT_PAIRS: tuple[tuple[str, str], ...] = (
    ("worker pool", "executor group"),
    ("job queue", "task ledger"),
    ("feature flag", "rollout switch"),
    ("health check", "liveness probe"),
    ("config map", "settings bundle"),
    ("build agent", "pipeline runner"),
    ("access log", "request journal"),
    ("index rebuild", "catalog refresh"),
    ("session token", "auth handle"),
)

# Both members of every morphological pair stem to the same porter tokens, which
# is the capability the FTS arm is supposed to have and the literal matcher does
# not. `expiry` is deliberately absent: porter maps it to `expiri` while
# `expiring` maps to `expir`, so that pair would fail for a tokenizer reason
# rather than a morphological one.
MORPHOLOGICAL_PAIRS: tuple[tuple[str, str], ...] = (
    ("renewing leases", "lease renewal"),
    ("retried connections", "connection retry"),
    ("migrating schemas", "schema migration"),
    ("throttled requests", "request throttle"),
    ("expired tokens", "token expiration"),
    ("replicating shards", "shard replication"),
    ("compacting segments", "segment compaction"),
    ("validating payloads", "payload validation"),
    ("scheduling drains", "drain scheduler"),
)

PAIRS_BY_KIND: dict[MissKind, tuple[tuple[str, str], ...]] = {
    MissKind.SYNONYM: SYNONYM_PAIRS,
    MissKind.ABBREVIATION: ABBREVIATION_PAIRS,
    MissKind.RENAMED_CONCEPT: RENAMED_CONCEPT_PAIRS,
    MissKind.MORPHOLOGICAL: MORPHOLOGICAL_PAIRS,
}

# Filler vocabulary for the background notes. It carries none of the query
# strings above, so a background note never enters a literal candidate set. It is
# deliberately NOT scrubbed of the queries' individual tokens: an FTS arm that
# only works because the filler avoids its vocabulary would be measuring the
# filler, not the tokenizer.
FILLER_SUBJECTS: tuple[str, ...] = (
    "the nightly export",
    "the staging environment",
    "the artifact store",
    "the audit trail",
    "the metrics pipeline",
    "the backup window",
    "the read replica",
    "the ingest queue",
)

FILLER_PREDICATES: tuple[str, ...] = (
    "was reviewed during the maintenance window and needs no further action",
    "carries a retention policy that the platform team owns",
    "is documented in the runbook and has not changed this quarter",
    "reports its own counters and is excluded from the weekly digest",
    "was migrated off the legacy host without incident",
    "has an owner recorded in the service catalog",
    "is exercised by the smoke suite on every merge",
    "remains on the default configuration",
)
