"""Concrete `SymbolResolver` backends for oracle consensus (mem-75t.7.3).

The mem rigs start grep + Sourcegraph (plan §7.3): grep is always available over a
git checkout; Sourcegraph runs only when the repo + endpoint are configured and
reports ``available=False`` otherwise, so a missing SG config degrades the
candidate to single-backend mode (documented in the curator) rather than crashing.

`StubResolver` is the deterministic, offline backend every consensus/curator test
runs on -- a fixed symbol→files map, no subprocess, no network.

ZFC: pure mechanism -- subprocess IO + structural parsing of tool output. No
semantic judgement lives here; the keep/reject call is the curator's (model's).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from membench.oracle.consensus import BackendResult
from membench.spawn import Runner, redact_secret, sanitised_child_output

logger = logging.getLogger(__name__)

DEFAULT_GREP_TIMEOUT_S = 30.0
DEFAULT_SG_TIMEOUT_S = 60.0


@dataclass(frozen=True)
class StubResolver:
    """A deterministic backend backed by a ``symbol -> files`` map. ``available``
    is fixed; an unknown symbol resolves to the empty set. Tests use two
    StubResolvers with diverging maps to exercise the quarantine path offline."""

    name: str
    files_by_symbol: Mapping[str, frozenset[str]] = field(default_factory=dict)
    available: bool = True
    error: str | None = None

    def resolve(self, symbol: str, *, defining_file: str, repo_root: Path) -> BackendResult:
        if not self.available:
            return BackendResult(backend=self.name, available=False, error=self.error)
        return BackendResult(
            backend=self.name, files=frozenset(self.files_by_symbol.get(symbol, frozenset()))
        )


@dataclass(frozen=True)
class GrepResolver:
    """Mechanical literal symbol match via ``git grep`` over the checkout.

    ``git grep -l -F -w -- <symbol>`` lists the repo-relative files that contain
    the symbol as a whole word. A non-git tree or a git failure other than
    "no matches" (exit 1) is reported as ``available=False`` rather than swallowed,
    so the divergence report shows why grep dropped out."""

    name: str = "grep"
    runner: Runner = subprocess.run
    timeout_s: float = DEFAULT_GREP_TIMEOUT_S

    def resolve(self, symbol: str, *, defining_file: str, repo_root: Path) -> BackendResult:
        try:
            completed = self.runner(
                ["git", "-C", str(repo_root), "grep", "-l", "-F", "-w", "--", symbol],
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_s,
            )
        except FileNotFoundError as exc:
            return BackendResult(backend=self.name, available=False, error=f"git not found: {exc}")
        except subprocess.TimeoutExpired:
            return BackendResult(
                backend=self.name,
                available=False,
                error=f"git grep timed out at {self.timeout_s:.0f}s",
            )
        except OSError as exc:
            # PermissionError / ENOEXEC / EACCES on the spawn -- a non-executable git
            # or an unreadable repo_root. FileNotFoundError (a subclass) is handled
            # above, so this degrades the backend rather than crashing consensus.
            return BackendResult(
                backend=self.name, available=False, error=f"git grep spawn failed: {exc}"
            )
        # git grep: 0 = matches, 1 = no matches (both fine), >=2 = real error.
        if completed.returncode >= 2:
            # Bound the child's stderr: this error flows into the serialized
            # divergence_report (consensus.py) via the public backend_results tuple, so a
            # runaway stderr must not land there unbounded (mem-zls5s). No VALUE redaction
            # here: git inherits the whole process env (SRC_ACCESS_TOKEN included, since the
            # SG backend's default env IS os.environ), but `git grep` has no code path that
            # echoes an unrelated env var -- so there is no specific token to redact by
            # value the way the src child below has. Bounding unrelated inherited env a
            # child MIGHT echo is the general env-surface question (mem-jwp3c), not this
            # site's raise-vs-report contract.
            detail = sanitised_child_output(completed.stderr.strip())
            return BackendResult(
                backend=self.name,
                available=False,
                error=f"git grep failed (exit {completed.returncode}): {detail}",
            )
        files = frozenset(line for line in completed.stdout.splitlines() if line.strip())
        return BackendResult(backend=self.name, files=files)


# Sourcegraph config env vars (the `src` CLI's own conventions). Both must be set,
# plus a per-rig repo identifier, or the backend reports unavailable.
ENV_SG_ENDPOINT = "SRC_ENDPOINT"
ENV_SG_TOKEN = "SRC_ACCESS_TOKEN"


@dataclass(frozen=True)
class SourcegraphResolver:
    """Sourcegraph symbol references via the ``src`` CLI search.

    A LITERAL content search for the symbol (``content:<symbol>`` over the indexed
    repo), the closest ``src search`` analogue to "files referencing the symbol" --
    the codeprobe original used an LSP find_references RPC, which the search surface
    does not expose; a true semantic reference backend is the deferred per-rig AST
    addition (plan §7.3), not this. The value over grep is index-level: SG searches
    a specific indexed revision with its own file filters, so its set diverges from
    a working-tree ``git grep`` -- exactly the independence the consensus gate needs.

    Reports ``available=False`` (never raises) when the repo identifier or the
    ``SRC_ENDPOINT`` / ``SRC_ACCESS_TOKEN`` env is missing -- the common offline
    case, which degrades the candidate to single-backend mode. ``runner`` is
    injected so the parse path is tested without a live Sourcegraph instance."""

    sg_repo: str = ""
    name: str = "sourcegraph"
    runner: Runner = subprocess.run
    timeout_s: float = DEFAULT_SG_TIMEOUT_S
    env: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))

    def resolve(self, symbol: str, *, defining_file: str, repo_root: Path) -> BackendResult:
        # defining_file is intentionally unused: a `src search` content query cannot
        # scope by the symbol's definition site the way codeprobe's LSP
        # find_references RPC did. Disambiguation falls to the consensus gate + the
        # Tier-2 curator; a definition-scoped backend is the deferred AST work.
        del defining_file
        if not self.sg_repo:
            return BackendResult(backend=self.name, available=False, error="sg_repo not configured")
        if not self.env.get(ENV_SG_ENDPOINT) or not self.env.get(ENV_SG_TOKEN):
            return BackendResult(
                backend=self.name,
                available=False,
                error=f"{ENV_SG_ENDPOINT}/{ENV_SG_TOKEN} not set",
            )
        # Quote the symbol: an unquoted ``content:foo bar`` would split into two
        # search terms; a quoted literal keeps a multi-word / punctuated symbol stem
        # as one term (symbol stems carry no embedded double-quote to escape).
        query = f'repo:^{self.sg_repo}$ count:all case:yes select:file content:"{symbol}"'
        try:
            completed = self.runner(
                ["src", "search", "-json", query],
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_s,
                env=dict(self.env),
            )
        except FileNotFoundError as exc:
            return BackendResult(
                backend=self.name, available=False, error=f"src CLI not found: {exc}"
            )
        except subprocess.TimeoutExpired:
            return BackendResult(
                backend=self.name,
                available=False,
                error=f"src search timed out at {self.timeout_s:.0f}s",
            )
        except OSError as exc:
            # PermissionError / ENOEXEC / EACCES on the spawn -- a non-executable src
            # CLI. FileNotFoundError (a subclass) is handled above, so this degrades
            # the backend to single-backend mode rather than raising out of resolve().
            return BackendResult(
                backend=self.name, available=False, error=f"src search spawn failed: {exc}"
            )
        if completed.returncode != 0:
            # The src child is handed SRC_ACCESS_TOKEN via env, so a `src` that echoes its
            # own auth on failure would put the token in this stderr, which flows into the
            # serialized divergence_report (mem-zls5s). Redact by VALUE -- the exact token we
            # passed (see redact_secret) -- BEFORE the bound, on the untruncated string, so a
            # token straddling the truncation cut is already gone; then sanitise for the bound.
            detail = sanitised_child_output(
                redact_secret(completed.stderr.strip(), self.env[ENV_SG_TOKEN])
            )
            return BackendResult(
                backend=self.name,
                available=False,
                error=f"src search failed (exit {completed.returncode}): {detail}",
            )
        try:
            files = _parse_sg_files(completed.stdout)
        except ValueError as exc:
            return BackendResult(backend=self.name, available=False, error=str(exc))
        return BackendResult(backend=self.name, files=files)


def _parse_sg_files(stdout: str) -> frozenset[str]:
    """Repo-relative paths from ``src search -json`` output. Tolerates the two
    documented result shapes (``Results`` list of file matches, or a bare list);
    an unparseable payload raises so the backend reports it as unavailable rather
    than returning a silently empty set."""
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"src search returned non-JSON: {exc}") from exc
    if isinstance(payload, Mapping):
        rows = payload.get("Results") or payload.get("results") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        raise ValueError(f"unexpected src search payload type: {type(payload).__name__}")
    files: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        path = row.get("file") or row.get("path") or (row.get("File") or {}).get("path")
        if isinstance(path, str) and path.strip():
            files.add(path.strip())
    return frozenset(files)
