"""Multi-backend consensus over symbol-reference file sets (port of codeprobe
``mining/consensus.py``, mem-75t.7.3, plan §4 P2).

A symbol is resolved by several independent backends (grep, sourcegraph, ...);
the candidate ships only when at least two AVAILABLE backends agree above an F1
threshold, otherwise it is quarantined with a divergence report. This is the
structural fix for the single-tool oracle bias (codeprobe-wo7n's gascity rerun):
if grep and Sourcegraph converge on the same files, the oracle is well-defined
regardless of which tool the eval agent later reaches for; if they diverge, the
answer is tool-dependent and the candidate must not silently enter the eval.

Adapted for mem from codeprobe in two ways: (1) backends are PLUGGABLE
`SymbolResolver`s (see ``backends.py``) rather than a hardcoded dispatch -- the
mem rigs are TS + Go and start grep+Sourcegraph-only, so the backend set must be
injectable, not a fixed Literal; (2) backend names are plain strings each
resolver owns, not a closed enum.

ZFC: pure mechanism. Each backend is a deterministic resolver; the consensus
decision is a pairwise F1 calculation followed by an intersection or union -- no
semantic judgement, no hidden thresholds. ``threshold`` is the one explicit
calibration knob.
"""

from __future__ import annotations

import logging
import posixpath
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

logger = logging.getLogger(__name__)

ConsensusMode = Literal["intersection", "union"]

DEFAULT_THRESHOLD: float = 0.8
DEFAULT_MODE: ConsensusMode = "intersection"


def canonicalize_repo_path(path: str, repo_root: Path) -> str:
    """Reduce a backend-emitted path to ONE repo-relative form so every backend
    shares a single path space.

    grep and Sourcegraph both emit repo-relative paths today, but nothing enforces
    it: a future backend (the deferred TS/AST resolver, plan §7.3) or an SG result
    shape emitting ``./src/a`` or an absolute ``/repo/src/a`` would otherwise (a)
    defeat the pairwise agreement count -- the same file counted as two distinct
    paths never reaches the F1 threshold -- and (b) slip past the gold-file
    self-exclusion in ``oracle.build`` (whose ``modified_set`` is repo-relative),
    re-entering the modified file as oracle context = an oracle leak.

    Strips a leading ``./``, collapses ``.``/``..`` segments, and rebases an
    absolute path under ``repo_root`` to repo-relative. An absolute path OUTSIDE the
    repo is left normalized-absolute -- that is a genuine divergence the consensus
    report should show, not one to silently rewrite into a bogus relative path."""
    raw = path.strip()
    if not raw:
        return raw
    candidate = PurePosixPath(raw)
    if candidate.is_absolute():
        try:
            return posixpath.normpath(
                str(candidate.relative_to(PurePosixPath(repo_root.as_posix())))
            )
        except ValueError:
            return posixpath.normpath(raw)
    return posixpath.normpath(raw)


@dataclass(frozen=True)
class BackendResult:
    """One backend's outcome for one symbol. ``available`` is False when the
    backend could not run at all (missing auth/toolchain, repo not on disk) -- the
    caller drops it from the pairwise comparison rather than reading it as an empty
    answer. ``error`` is a short reason carried into the divergence report."""

    backend: str
    files: frozenset[str] = frozenset()
    available: bool = True
    error: str | None = None


class SymbolResolver(Protocol):
    """A backend that resolves a symbol to the repo-relative files referencing it.
    Implementations live in ``backends.py``; ``compute_consensus`` runs them in
    parallel and never assumes any particular set is present."""

    @property
    def name(self) -> str: ...

    def resolve(self, symbol: str, *, defining_file: str, repo_root: Path) -> BackendResult: ...


def _canonicalize_result(result: BackendResult, repo_root: Path) -> BackendResult:
    """A copy of ``result`` with every file path canonicalized to the shared
    repo-relative space (no-op for an unavailable / empty result). The single seam
    where cross-backend path identity is enforced, so the agreement count and the
    downstream oracle self-exclusion compare like for like."""
    if not result.files:
        return result
    return BackendResult(
        backend=result.backend,
        files=frozenset(canonicalize_repo_path(f, repo_root) for f in result.files),
        available=result.available,
        error=result.error,
    )


def compute_pair_metrics(
    files_a: frozenset[str], files_b: frozenset[str]
) -> dict[str, float | int]:
    """Symmetric F1/precision/recall between two file sets (port of codeprobe
    ``cross_validate.compute_pair_metrics``). The pair is unordered: F1 is
    symmetric; precision/recall are reported with ``a`` as reference. Two empty
    sets agree vacuously (F1 = 1.0)."""
    if not files_a and not files_b:
        return {"f1": 1.0, "precision": 1.0, "recall": 1.0, "n_a": 0, "n_b": 0, "n_overlap": 0}
    tp = len(files_a & files_b)
    precision = tp / len(files_b) if files_b else 0.0
    recall = tp / len(files_a) if files_a else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {
        "f1": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "n_a": len(files_a),
        "n_b": len(files_b),
        "n_overlap": tp,
    }


@dataclass(frozen=True)
class ConsensusDecision:
    """Outcome of running every backend for one symbol candidate.

    ``shipped`` is True when at least two AVAILABLE backends agree above
    ``threshold`` (pairwise F1). ``consensus_files`` is the intersection (default,
    high-precision) or union (high-recall) of the available backends' file sets --
    a DIAGNOSTIC summary (also surfaced in ``divergence_report``), NOT the oracle
    answer: with 3+ backends a strict intersection can be empty while two backends
    still agree, so per-file oracle admission is the curator's job
    (``curator.curate_consensus`` over ``backend_results``), never this field.
    ``divergence_report`` is a stable, self-describing dict ready to persist for
    both shipped and quarantined candidates."""

    shipped: bool
    consensus_files: frozenset[str]
    mode: ConsensusMode
    threshold: float
    min_pair_f1: float
    max_pair_f1: float
    available_backends: tuple[str, ...]
    backends_attempted: tuple[str, ...]
    backend_results: tuple[BackendResult, ...]
    divergence_report: dict[str, object] = field(default_factory=dict)


def _pairwise_metrics(
    available: Sequence[BackendResult],
) -> tuple[list[dict[str, object]], float, float]:
    """Symmetric F1 between every pair of available backends. Fewer than two
    available backends → F1 bounds default to 0.0 (full disagreement), so a
    single-backend candidate cannot ship under the consensus gate."""
    pair_metrics: list[dict[str, object]] = []
    f1s: list[float] = []
    for ba, bb in combinations(available, 2):
        metrics = compute_pair_metrics(ba.files, bb.files)
        pair_metrics.append(
            {
                "backend_a": ba.backend,
                "backend_b": bb.backend,
                **metrics,
                f"{ba.backend}_only": sorted(ba.files - bb.files),
                f"{bb.backend}_only": sorted(bb.files - ba.files),
            }
        )
        f1s.append(float(metrics["f1"]))
    if not f1s:
        return pair_metrics, 0.0, 0.0
    return pair_metrics, min(f1s), max(f1s)


def _combine_files(available: Sequence[BackendResult], mode: ConsensusMode) -> frozenset[str]:
    """Intersection (every available backend -- high-precision) or union (any --
    high-recall) of the available file sets. With a single backend both degenerate
    to its set, but ``compute_consensus`` still quarantines (the gate needs two)."""
    if not available:
        return frozenset()
    if mode == "union":
        out: frozenset[str] = frozenset()
        for br in available:
            out = out | br.files
        return out
    iterator = iter(available)
    out = next(iterator).files
    for br in iterator:
        out = out & br.files
    return out


def _build_divergence_report(
    *,
    symbol: str,
    defining_file: str,
    backend_results: Sequence[BackendResult],
    threshold: float,
    mode: ConsensusMode,
    pair_metrics: list[dict[str, object]],
    decision: str,
    consensus_files: Iterable[str],
) -> dict[str, object]:
    """The divergence_report payload -- a stable schema callers read by key. Any
    new field must be additive."""
    return {
        "schema_version": "consensus.v1",
        "symbol": symbol,
        "defining_file": defining_file,
        "threshold": threshold,
        "mode": mode,
        "decision": decision,
        "backend_results": [
            {
                "backend": br.backend,
                "available": br.available,
                "n_files": len(br.files),
                "files": sorted(br.files),
                "error": br.error,
            }
            for br in backend_results
        ],
        "pair_metrics": pair_metrics,
        "consensus_files": sorted(consensus_files),
    }


def compute_consensus(
    *,
    symbol: str,
    defining_file: str,
    repo_root: Path,
    resolvers: Sequence[SymbolResolver],
    threshold: float = DEFAULT_THRESHOLD,
    mode: ConsensusMode = DEFAULT_MODE,
    max_workers: int = 3,
) -> ConsensusDecision:
    """Run every resolver for ``symbol`` and decide whether to ship.

    Ships when ≥2 backends were AVAILABLE and any pair agrees at or above
    ``threshold`` pairwise F1; otherwise the candidate is quarantined and the
    caller must not enter its files into the oracle as consensus-backed. Resolvers
    run in parallel (they share no state). A resolver that raises is recorded as an
    unavailable `BackendResult`, never propagated -- one broken backend must not
    sink the whole candidate."""
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold must be in [0, 1], got {threshold!r}")
    if mode not in ("intersection", "union"):
        raise ValueError(f"mode must be 'intersection' or 'union', got {mode!r}")
    if not resolvers:
        raise ValueError("resolvers must be non-empty")
    if not symbol:
        raise ValueError("symbol must be non-empty")

    backends_attempted = tuple(r.name for r in resolvers)
    if len(set(backends_attempted)) != len(backends_attempted):
        # results are keyed by backend name; a collision would silently drop one
        # resolver's answer and its slot in the report. Fail loud instead.
        raise ValueError(f"resolver names must be unique, got {list(backends_attempted)}")

    def _run(resolver: SymbolResolver) -> BackendResult:
        try:
            return resolver.resolve(symbol, defining_file=defining_file, repo_root=repo_root)
        except Exception as exc:  # one broken backend must not sink the candidate
            return BackendResult(
                backend=resolver.name,
                available=False,
                error=f"{type(exc).__name__}: {exc}",
            )

    results: dict[str, BackendResult] = {}
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        futures = {pool.submit(_run, r): r.name for r in resolvers}
        for fut in as_completed(futures):
            res = fut.result()
            results[res.backend] = res

    ordered_results = tuple(
        _canonicalize_result(results[name], repo_root)
        for name in backends_attempted
        if name in results
    )
    available = tuple(br for br in ordered_results if br.available)
    available_names = tuple(br.backend for br in available)

    pair_metrics, min_f1, max_f1 = _pairwise_metrics(available)
    consensus_files = _combine_files(available, mode)
    shipped = len(available) >= 2 and max_f1 >= threshold
    decision_label = "shipped" if shipped else "quarantined"

    logger.info(
        "Consensus %s for %s: %d/%d backends available, max_pair_f1=%.3f "
        "(threshold=%.2f), n_consensus=%d",
        decision_label,
        symbol,
        len(available),
        len(ordered_results),
        max_f1,
        threshold,
        len(consensus_files),
    )

    return ConsensusDecision(
        shipped=shipped,
        consensus_files=consensus_files,
        mode=mode,
        threshold=threshold,
        min_pair_f1=min_f1,
        max_pair_f1=max_f1,
        available_backends=available_names,
        backends_attempted=backends_attempted,
        backend_results=ordered_results,
        divergence_report=_build_divergence_report(
            symbol=symbol,
            defining_file=defining_file,
            backend_results=ordered_results,
            threshold=threshold,
            mode=mode,
            pair_metrics=pair_metrics,
            decision=decision_label,
            consensus_files=consensus_files,
        ),
    )
