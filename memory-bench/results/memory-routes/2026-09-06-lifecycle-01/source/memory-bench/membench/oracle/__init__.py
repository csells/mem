"""Oracle-context curation for task bundles (mem-75t.7.3, plan §4 P2).

Ports codeprobe's multi-backend consensus + LLM curator onto the mem bundle: the
gold diff seeds the oracle, pluggable `SymbolResolver` backends (grep, Sourcegraph)
resolve reference context, consensus gates it, and an OAuth-`claude -p` curator
keeps/rejects single-backend candidates. `curate_bundle` is the entry point; it
returns a new bundle with ``oracle_context`` populated plus an `OracleBuild` audit.
"""

from membench.oracle.backends import (
    GrepResolver,
    SourcegraphResolver,
    StubResolver,
)
from membench.oracle.build import (
    DEFAULT_MAX_ORACLE_FILES,
    GOLD_DIFF_BACKEND,
    OracleBuild,
    SymbolQuarantine,
    build_oracle_context,
    curate_bundle,
)
from membench.oracle.consensus import (
    DEFAULT_THRESHOLD,
    BackendResult,
    ConsensusDecision,
    SymbolResolver,
    canonicalize_repo_path,
    compute_consensus,
    compute_pair_metrics,
)
from membench.oracle.curator import (
    DEFAULT_MIN_BACKENDS,
    ClaudeOracleCurator,
    CuratedItem,
    CuratedOracleResult,
    CuratorVote,
    OracleCurator,
    OracleCuratorError,
    StubOracleCurator,
    curate_consensus,
    parse_curator_reply,
)

__all__ = [
    "DEFAULT_MAX_ORACLE_FILES",
    "DEFAULT_MIN_BACKENDS",
    "DEFAULT_THRESHOLD",
    "GOLD_DIFF_BACKEND",
    "BackendResult",
    "ClaudeOracleCurator",
    "ConsensusDecision",
    "CuratedItem",
    "CuratedOracleResult",
    "CuratorVote",
    "GrepResolver",
    "OracleBuild",
    "OracleCurator",
    "OracleCuratorError",
    "SourcegraphResolver",
    "StubOracleCurator",
    "StubResolver",
    "SymbolQuarantine",
    "SymbolResolver",
    "build_oracle_context",
    "canonicalize_repo_path",
    "compute_consensus",
    "compute_pair_metrics",
    "curate_bundle",
    "curate_consensus",
    "parse_curator_reply",
]
