"""Build a bundle's ``oracle_context`` from its gold diff (mem-75t.7.3, plan §4 P2).

This is the glue between the consensus/curator port and the bundle: codeprobe
mined an oracle for a stated symbol-reference task, but a mem bundle's task is a
bead, so the oracle SEED is the gold diff itself. Two tiers fall out:

- the gold-diff modified files are REQUIRED, unconditionally -- they were edited to
  produce the output, so the agent definitionally needed them (provenance
  ``gold_diff``, the most authoritative source);
- reference CONTEXT (files that reference the modified modules) is expanded per
  modified module and admitted ONLY when consensus ships (≥2 backends agree above
  the F1 threshold). A quarantined or single-backend symbol contributes no context
  -- this is the first-class precision guard the mem-75t.7.6 gate demanded: the
  probe measured unfiltered context REGRESSING a bundle (-0.09 combined, +138
  turns), so context enters the oracle only when a second backend vouches for it.

``max_oracle_files`` is the volume cap. Required files are never dropped (ground
truth); supplementary (Tier-2 LLM-kept) files are truncated first, lowest
provenance first, and the drop is LOGGED and counted, never silent.

ZFC: mechanism only -- the modified-file seed and consensus arithmetic are
deterministic; the sole semantic call is the curator's Tier-2 keep/reject, already
delegated to the model inside ``curator.py``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from membench.oracle.consensus import (
    DEFAULT_THRESHOLD,
    SymbolResolver,
    canonicalize_repo_path,
    compute_consensus,
)
from membench.oracle.curator import (
    DEFAULT_MIN_BACKENDS,
    CuratedItem,
    OracleCurator,
    curate_consensus,
)
from membench.schemas.bundle import CuratedOracle, TaskBundle

logger = logging.getLogger(__name__)

# The gold diff is the authoritative oracle source -- recorded as its own provenance
# backend so ``oracle_backends_consensus`` shows which files came from ground truth
# versus a searchable backend (the anti-tautology surface).
GOLD_DIFF_BACKEND = "gold_diff"

# Volume cap (plan §4 P2 precision guard). Generous enough that real bundles rarely
# hit it; when they do, supplementary context is truncated before required.
DEFAULT_MAX_ORACLE_FILES = 50


@dataclass(frozen=True)
class SymbolQuarantine:
    """A seed symbol whose reference context was NOT admitted, with the reason --
    the audit trail for the empirical quarantine rate (plan §7.3)."""

    symbol: str
    defining_file: str
    reason: str


@dataclass(frozen=True)
class OracleBuild:
    """The full curation product for one bundle: the projected schema
    `CuratedOracle` plus the audit detail (symbol-level quarantines, dropped
    file/quarantine pairs, truncation count) the schema does not carry."""

    oracle: CuratedOracle
    symbol_quarantines: tuple[SymbolQuarantine, ...]
    file_quarantines: tuple[tuple[str, str], ...]
    truncated: int


def _seed_symbol(path: str) -> str:
    """The module identifier a modified file is referenced by: its basename stem
    (``src/store/writer.ts`` → ``writer``). A mechanical, language-agnostic seed --
    consensus + the curator filter the over-broad matches a bare stem invites.
    Dotfiles (``.env`` → stem ``.env``) carry no module identity, so they return
    the empty seed the caller skips."""
    stem = PurePosixPath(path).stem
    return "" if stem.startswith(".") else stem


def build_oracle_context(
    *,
    modified_files: Sequence[str],
    repo_root: Path,
    resolvers: Sequence[SymbolResolver],
    curator: OracleCurator | None = None,
    threshold: float = DEFAULT_THRESHOLD,
    min_backends: int = DEFAULT_MIN_BACKENDS,
    use_llm: bool = True,
    max_oracle_files: int = DEFAULT_MAX_ORACLE_FILES,
) -> OracleBuild:
    """Curate the oracle for one bundle from its gold-diff ``modified_files``.

    Required = the modified files. Context = per-modified-module reference
    expansion, admitted only when consensus ships. Returns the schema
    `CuratedOracle` plus the audit detail. The modified files are excluded from
    their own reference results (a file does not reference itself into the
    oracle)."""
    if max_oracle_files < 1:
        raise ValueError(f"max_oracle_files must be >= 1, got {max_oracle_files!r}")

    # Canonicalize to the same repo-relative space the backends are reduced to in
    # ``compute_consensus``, so the ``item.path in modified_set`` self-exclusion
    # below compares like for like -- a divergent gold-path shape would otherwise
    # let a modified file re-enter as context (oracle leak).
    modified = tuple(
        sorted({canonicalize_repo_path(m, repo_root) for m in modified_files if m.strip()})
    )
    modified_set = set(modified)

    # Tier "required" from ground truth -- the modified files themselves. Consensus
    # backends accumulate the UNION of provenance per path across every symbol that
    # contributed it (a file kept grep-only for one module and sourcegraph-only for
    # another is backed by both), so the surviving set's provenance after the volume
    # guard can be recomputed exactly without under-claiming.
    tiers: dict[str, str] = dict.fromkeys(modified, "required")
    consensus_backends: dict[str, set[str]] = {}

    symbol_quarantines: list[SymbolQuarantine] = []
    file_quarantines: list[tuple[str, str]] = []
    # Whether ANY symbol's curate_consensus call actually invoked the Tier-2 LLM
    # curator -- the gate for capturing curator_isolation below (mem-x5d3): a build
    # with zero LLM votes has no isolation surface to attest.
    llm_used_any = False

    for mod_path in modified:
        symbol = _seed_symbol(mod_path)
        if not symbol:
            continue
        decision = compute_consensus(
            symbol=symbol,
            defining_file=mod_path,
            repo_root=repo_root,
            resolvers=resolvers,
            threshold=threshold,
        )
        if not decision.shipped:
            n_avail = len(decision.available_backends)
            reason = (
                f"single_backend (available={n_avail}, need 2)"
                if n_avail < 2
                else f"backend_disagreement (max_pair_f1={decision.max_pair_f1:.2f} < {threshold})"
            )
            symbol_quarantines.append(SymbolQuarantine(symbol, mod_path, reason))
            continue

        curated = curate_consensus(
            backend_results=decision.backend_results,
            symbol=symbol,
            defining_file=mod_path,
            repo_root=repo_root,
            curator=curator,
            min_backends=min_backends,
            use_llm=use_llm,
        )
        llm_used_any = llm_used_any or curated.llm_used
        for item in curated.items:
            # The modified files are already REQUIRED from ground truth; a backend
            # re-finding them adds no information and must not be downgraded.
            if item.path in modified_set:
                continue
            _merge_item(tiers, consensus_backends, item)
        for path, why in curated.quarantined:
            if path not in modified_set:
                file_quarantines.append((path, f"{symbol}: {why}"))

    oracle_answer, oracle_tiers, dropped = _apply_volume_guard(tiers, max_oracle_files)
    # Truncation is a drop -- record which paths so the audit trail is complete.
    for path in dropped:
        file_quarantines.append((path, f"volume_guard: truncated (cap={max_oracle_files})"))
    # None when the curator never fired this build or has no isolation_marker
    # attribute (e.g. StubOracleCurator).
    curator_isolation = getattr(curator, "isolation_marker", None) if llm_used_any else None
    oracle = CuratedOracle(
        oracle_answer=oracle_answer,
        oracle_tiers=oracle_tiers,
        oracle_backends_consensus=_provenance(set(oracle_answer), modified_set, consensus_backends),
        curator_isolation=curator_isolation,
    )
    return OracleBuild(
        oracle=oracle,
        symbol_quarantines=tuple(symbol_quarantines),
        file_quarantines=tuple(file_quarantines),
        truncated=len(dropped),
    )


def _merge_item(
    tiers: dict[str, str], consensus_backends: dict[str, set[str]], item: CuratedItem
) -> None:
    """Fold one curated item into the running oracle. Backend provenance UNIONS
    across every contributor for the path (a file found grep-only for one module and
    sourcegraph-only for another is backed by both); the tier promotes to
    ``required`` if ANY contributor is Tier-1, and otherwise stays
    ``supplementary``."""
    consensus_backends.setdefault(item.path, set()).update(item.backends)
    if item.tier == "required":
        tiers[item.path] = "required"
    elif tiers.get(item.path) != "required":
        tiers[item.path] = item.tier


def _apply_volume_guard(
    tiers: dict[str, str], max_oracle_files: int
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...], tuple[str, ...]]:
    """Enforce ``max_oracle_files``: required files are kept (ground truth + Tier-1
    consensus); supplementary (Tier-2) files are truncated to fit, sorted for
    determinism. Returns the sorted answer, the (path, tier) pairs, and the sorted
    dropped supplementary paths (so the caller records them, never a silent drop)."""
    required = sorted(p for p, t in tiers.items() if t == "required")
    supplementary = sorted(p for p, t in tiers.items() if t == "supplementary")

    # Required files are ground truth + Tier-1 consensus -- never dropped. When they
    # alone exceed the cap the oracle is legitimately over-cap; warn so the breach is
    # visible rather than reading as "cap respected" (truncated counts supplementary).
    if len(required) > max_oracle_files:
        logger.warning(
            "Oracle volume guard: %d required files exceed cap=%d -- keeping all "
            "(ground truth is non-negotiable); oracle is over-cap by %d",
            len(required),
            max_oracle_files,
            len(required) - max_oracle_files,
        )

    room = max(0, max_oracle_files - len(required))
    kept_supp = supplementary[:room]
    dropped = supplementary[room:]
    if dropped:
        logger.info(
            "Oracle volume guard: kept %d/%d supplementary files (cap=%d, required=%d), "
            "dropped %d",
            len(kept_supp),
            len(supplementary),
            max_oracle_files,
            len(required),
            len(dropped),
        )

    required_set = set(required)
    answer = tuple(sorted(required + kept_supp))
    final_tiers = tuple((p, "required" if p in required_set else "supplementary") for p in answer)
    return answer, final_tiers, tuple(dropped)


def _provenance(
    surviving: set[str], modified_set: set[str], consensus_backends: dict[str, set[str]]
) -> tuple[str, ...]:
    """``oracle_backends_consensus`` over the files that survived the volume guard:
    ``gold_diff`` when a modified file is still in the oracle, plus the UNION of
    backends across every contributor of each surviving file. A backend whose only
    contribution was truncated away no longer appears -- provenance never
    over-claims, and one whose file arrived via several symbols never disappears."""
    backends: set[str] = set()
    if surviving & modified_set:
        backends.add(GOLD_DIFF_BACKEND)
    for path in surviving:
        backends.update(consensus_backends.get(path, set()))
    return tuple(sorted(backends))


def curate_bundle(
    bundle: TaskBundle,
    repo_root: Path,
    *,
    resolvers: Sequence[SymbolResolver],
    curator: OracleCurator | None = None,
    threshold: float = DEFAULT_THRESHOLD,
    min_backends: int = DEFAULT_MIN_BACKENDS,
    use_llm: bool = True,
    max_oracle_files: int = DEFAULT_MAX_ORACLE_FILES,
) -> tuple[TaskBundle, OracleBuild]:
    """Curate ``bundle``'s oracle from its embedded gold diff and return a NEW
    bundle with ``oracle_context`` populated, plus the `OracleBuild` audit detail.
    ``repo_root`` is the checkout at ``bundle.env.base_commit`` (the same tree the
    replay ran against). Immutable: the input bundle is never mutated."""
    modified = [path for path, _diff in bundle.output.file_diffs]
    build = build_oracle_context(
        modified_files=modified,
        repo_root=repo_root,
        resolvers=resolvers,
        curator=curator,
        threshold=threshold,
        min_backends=min_backends,
        use_llm=use_llm,
        max_oracle_files=max_oracle_files,
    )
    return bundle.model_copy(update={"oracle_context": build.oracle}), build
