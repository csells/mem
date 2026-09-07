"""Per-file oracle curator (port of codeprobe ``mining/oracle_curator.py``,
mem-75t.7.3, plan §4 P2).

Builds a per-file curated ground-truth set from the raw `BackendResult`s of one
shipped consensus candidate. Tier-1 keeps any file ≥``min_backends`` distinct
backends agreed on (arithmetic, no model). Tier-2 (a single backend) routes
through an LLM curator that reads the actual code and votes keep/reject -- the
structural mitigation for single-tool oracle bias. A reject is QUARANTINED with a
rationale, never silently dropped: the quarantine rate is the empirical signal for
whether a rig needs a third backend (plan §7.3).

The model seam is headless ``claude -p`` (`ClaudeOracleCurator`) -- the local
Claude CLI is the OAuth runtime, NOT the paid managed API, so it honours the
memory stack's no-paid-API stance (same seam as `bbon.comparative_judge`).
`StubOracleCurator` is the deterministic, offline curator every test and the whole
pipeline run on.

ZFC: Tier-1 selection is arithmetic; the Tier-2 keep/reject judgement is the
model's (correct delegation); the surrounding code does IO (read snippet) and
structural validation (parse JSON, check ``keep`` is a bool).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from membench._claude_cli import unwrap_cli_json
from membench.judge_config import (
    IsolatedClaudeCallsite,
    IsolatedJudgeConfig,
    run_isolated_claude,
)
from membench.oracle.consensus import BackendResult
from membench.spawn import Runner

logger = logging.getLogger(__name__)

DEFAULT_MIN_BACKENDS = 2

# Snippet bounds for the curator prompt -- a bounded head keeps the call small and
# deterministic regardless of file size.
_MAX_SNIPPET_LINES = 80
_MAX_SNIPPET_BYTES = 8000

DEFAULT_CURATOR_TIMEOUT_S = 60.0
CLI_DEFAULT_MODEL = "cli-default"
ENV_CURATOR_MODEL = "MEMBENCH_ORACLE_CURATOR_MODEL"


@dataclass(frozen=True)
class CuratorVote:
    """One curator verdict for a Tier-2 candidate. ``keep`` is the model's call;
    ``error`` is set when the call failed (unavailable, parse failure, timeout) and
    in that case ``keep`` is forced False so quarantining is the conservative
    default."""

    keep: bool
    rationale: str = ""
    error: str | None = None


@dataclass(frozen=True)
class CuratedItem:
    """A curated ground-truth file with provenance. ``backends`` is the sorted
    tuple of backends that found it; ``tier`` is ``"required"`` (Tier-1) or
    ``"supplementary"`` (Tier-2, LLM-kept); ``via_llm_review`` marks the Tier-2
    path and carries the model's rationale."""

    path: str
    backends: tuple[str, ...]
    tier: str
    via_llm_review: bool
    llm_rationale: str = ""


@dataclass(frozen=True)
class CuratedOracleResult:
    """Curated ground truth for one symbol. ``items`` are the kept files;
    ``backends_consensus`` is the sorted set of backends that contributed ≥1 kept
    file (the anti-tautology provenance); ``quarantined`` is ``(path, reason)``
    pairs the curator dropped, audit-visible, never silent."""

    items: tuple[CuratedItem, ...]
    backends_consensus: tuple[str, ...]
    quarantined: tuple[tuple[str, str], ...]
    min_backends: int
    llm_used: bool


class OracleCurator(Protocol):
    """Returns a raw model reply for a built curator prompt. ``model`` is the
    recorded identity. Implementations: `StubOracleCurator` (offline) and
    `ClaudeOracleCurator` (headless ``claude -p``)."""

    @property
    def model(self) -> str: ...

    def complete(self, prompt: str) -> str: ...


class OracleCuratorError(RuntimeError):
    """A curator invocation failed (missing binary, timeout, non-zero exit, or an
    unusable reply). Surfaced loudly, never degraded to a default verdict."""


@dataclass(frozen=True)
class StubOracleCurator:
    """A deterministic, offline curator -- NO model, NO network. Supply exactly one
    of: a fixed ``keep`` verdict (with ``rationale``), or ``fn`` (a pure function
    from prompt to a raw reply string, so the full parse path is exercised)."""

    keep: bool | None = None
    rationale: str = "stub verdict"
    fn: Callable[[str], str] | None = None
    model: str = "stub"

    def __post_init__(self) -> None:
        if (self.keep is None) == (self.fn is None):
            raise ValueError("StubOracleCurator needs exactly one of keep or fn")

    def complete(self, prompt: str) -> str:
        if self.fn is not None:
            return self.fn(prompt)
        return json.dumps({"keep": self.keep, "rationale": self.rationale})


@dataclass(frozen=True)
class ClaudeOracleCurator(IsolatedClaudeCallsite):
    """A curator backed by headless ``claude -p ... --output-format json`` -- the
    OAuth seam, not a paid API. ``model`` pins the CLI model; left empty it reads
    ``MEMBENCH_ORACLE_CURATOR_MODEL`` and otherwise uses the CLI default. ``runner``
    is injected so tests drive the parse path without spawning a real claude.

    ``isolation`` (mem-9ld4 / mem-hv9l) is the clean-config surface the subprocess
    runs under, so no host/project agent can hijack the keep/reject vote; lazy
    semantics and the marker contract live on `IsolatedClaudeCallsite`."""

    _isolation_label = "curator"

    model: str = ""
    timeout_s: float = DEFAULT_CURATOR_TIMEOUT_S
    runner: Runner = subprocess.run
    isolation: IsolatedJudgeConfig | None = None
    _pass_model: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        resolved = self.model or os.environ.get(ENV_CURATOR_MODEL, "")
        object.__setattr__(self, "_pass_model", bool(resolved))
        object.__setattr__(self, "model", resolved or CLI_DEFAULT_MODEL)

    def complete(self, prompt: str) -> str:
        reply = run_isolated_claude(
            prompt,
            isolation=self._resolved_isolation(),
            runner=self.runner,
            timeout_s=self.timeout_s,
            model=self.model if self._pass_model else None,
            callsite="oracle curator",
            error=OracleCuratorError,
        )
        return unwrap_cli_json(reply)


def curate_consensus(
    *,
    backend_results: Sequence[BackendResult],
    symbol: str,
    defining_file: str,
    repo_root: Path,
    curator: OracleCurator | None = None,
    min_backends: int = DEFAULT_MIN_BACKENDS,
    use_llm: bool = True,
) -> CuratedOracleResult:
    """Curate per-file ground truth from N backend results.

    Tier-1: files ≥``min_backends`` distinct backends reported are kept
    ``"required"`` with no model call. Tier-2: single-backend files route through
    ``curator`` (keep → ``"supplementary"``, reject → quarantined with rationale).
    Single-backend fallback: when only one backend ran, every file is kept
    ``"required"`` -- there is nothing to consensus-filter against (the
    SG-unconfigured / grep-only mem path). When ``use_llm=False`` or no curator is
    supplied, Tier-2 candidates are QUARANTINED (never silently dropped) so the
    loss is countable."""
    if min_backends < 1:
        raise ValueError(f"min_backends must be >= 1, got {min_backends!r}")

    available = [br for br in backend_results if br.available]
    if not available:
        logger.warning("Oracle curator: no available backends for %s -- empty oracle", symbol)
        return CuratedOracleResult((), (), (), min_backends, False)

    per_path: dict[str, set[str]] = {}
    for br in available:
        for path in br.files:
            per_path.setdefault(path, set()).add(br.backend)

    if len(available) == 1:
        only = available[0].backend
        fallback = tuple(
            CuratedItem(path=p, backends=(only,), tier="required", via_llm_review=False)
            for p in sorted(per_path)
        )
        return CuratedOracleResult(fallback, (only,) if fallback else (), (), min_backends, False)

    items: list[CuratedItem] = []
    quarantined: list[tuple[str, str]] = []
    llm_called = False
    llm_ok = use_llm and curator is not None

    for path in sorted(per_path):
        backends = tuple(sorted(per_path[path]))
        if len(backends) >= min_backends:
            items.append(CuratedItem(path, backends, "required", via_llm_review=False))
            continue
        if not llm_ok:
            quarantined.append((path, "single-backend, LLM curator unavailable"))
            continue
        llm_called = True
        assert curator is not None  # llm_ok already guarantees this; fail loud on regression
        vote = _curate_with_llm(
            curator=curator,
            symbol=symbol,
            defining_file=defining_file,
            candidate_path=path,
            found_by=backends[0],
            repo_root=repo_root,
        )
        if vote.error:
            quarantined.append((path, f"curator error: {vote.error}"))
        elif vote.keep:
            items.append(
                CuratedItem(
                    path,
                    backends,
                    "supplementary",
                    via_llm_review=True,
                    llm_rationale=vote.rationale,
                )
            )
        else:
            quarantined.append((path, f"LLM rejected: {vote.rationale}"))

    consensus_set: set[str] = set()
    for it in items:
        consensus_set.update(it.backends)
    return CuratedOracleResult(
        items=tuple(items),
        backends_consensus=tuple(sorted(consensus_set)),
        quarantined=tuple(quarantined),
        min_backends=min_backends,
        llm_used=llm_called,
    )


def _read_snippet(repo_root: Path, rel_path: str) -> str:
    """A bounded text head of ``rel_path`` under ``repo_root`` (line- and
    byte-capped). Empty string when the file is absent, unreadable, or escapes
    ``repo_root`` -- backend file lists are repo-relative by contract, but a
    ``..`` escape from a malformed bundle or a hostile Sourcegraph response must
    never read outside the checkout (the `replay._rebase_path` boundary rule)."""
    try:
        root = repo_root.resolve()
        full = (root / rel_path).resolve()
        if not full.is_relative_to(root) or not full.is_file():
            return ""
        data = full.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(data) > _MAX_SNIPPET_BYTES:
        data = data[:_MAX_SNIPPET_BYTES]
    lines = data.splitlines()
    if len(lines) > _MAX_SNIPPET_LINES:
        lines = lines[:_MAX_SNIPPET_LINES]
    return "\n".join(lines)


def build_curator_prompt(
    *, symbol: str, defining_file: str, candidate_path: str, found_by: str, snippet: str
) -> str:
    """The keep/reject prompt for one Tier-2 candidate. The model decides whether
    the single-backend file genuinely references the symbol (directly, via alias,
    re-export, or wildcard import)."""
    return (
        "You are an oracle curator for a code-search benchmark. A symbol-reference "
        "search ran multiple backends; this candidate file was reported by exactly "
        "one of them. Decide whether it actually references the symbol -- directly, "
        "via alias, via re-export, or through a wildcard import.\n\n"
        f"**Symbol:** {symbol}\n"
        f"**Defining file:** {defining_file}\n"
        f"**Candidate file:** {candidate_path}\n"
        f"**Found by backend:** {found_by}\n\n"
        "**Candidate snippet (truncated):**\n```\n"
        f"{snippet}\n```\n\n"
        "Respond with JSON only, exactly of the form:\n"
        '{"keep": true|false, "rationale": "<one short sentence>"}\n'
        "No markdown fences, no extra commentary."
    )


def _curate_with_llm(
    *,
    curator: OracleCurator,
    symbol: str,
    defining_file: str,
    candidate_path: str,
    found_by: str,
    repo_root: Path,
) -> CuratorVote:
    """Ask ``curator`` whether ``candidate_path`` truly references ``symbol``. Any
    deviation (unreadable candidate, call failure, non-JSON, missing/invalid
    ``keep``) forces ``keep=False`` with an ``error`` so quarantining is the
    conservative default."""
    snippet = _read_snippet(repo_root, candidate_path)
    if not snippet:
        # No readable evidence (file missing, unreadable, or an out-of-root path):
        # there is nothing for the curator to judge, so quarantine rather than ask
        # the model to keep a file it cannot see.
        return CuratorVote(keep=False, error="candidate file unreadable or outside repo")
    prompt = build_curator_prompt(
        symbol=symbol,
        defining_file=defining_file,
        candidate_path=candidate_path,
        found_by=found_by,
        snippet=snippet,
    )
    try:
        reply = curator.complete(prompt)
    except OracleCuratorError as exc:
        logger.warning("Oracle curator call failed for %s: %s", candidate_path, exc)
        return CuratorVote(keep=False, error=str(exc))
    return parse_curator_reply(reply)


def parse_curator_reply(reply: str) -> CuratorVote:
    """Parse a raw curator reply into a `CuratorVote`. Tolerates a single
    ```-fenced block; a non-JSON reply, a non-object, or a missing/non-bool
    ``keep`` is a forced ``keep=False`` with the reason in ``error``."""
    text = reply.strip()
    if text.startswith("```"):
        text = "\n".join(line for line in text.splitlines() if not line.strip().startswith("```"))
    try:
        parsed: Any = json.loads(text)
    except json.JSONDecodeError:
        return CuratorVote(keep=False, error="non-JSON response")
    if not isinstance(parsed, dict):
        return CuratorVote(keep=False, error="response not a JSON object")
    keep = parsed.get("keep")
    if not isinstance(keep, bool):
        return CuratorVote(keep=False, error="missing or invalid 'keep' field")
    rationale = parsed.get("rationale", "")
    if not isinstance(rationale, str):
        rationale = ""
    return CuratorVote(keep=keep, rationale=rationale[:500])
