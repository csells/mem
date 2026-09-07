"""Config isolation for every headless ``claude -p`` model callsite (mem-9ld4).

The graded S3 judge shells a headless ``claude -p``. Left to inherit the host
``CLAUDE_CONFIG_DIR`` (an operator account carrying skills / rules / *agents* —
notably a ``code-reviewer`` subagent), a reviewable candidate diff intermittently
hijacks the session into CODE-REVIEW mode: the reply comes back as a
``{"findings": [...], "level": ...}`` object instead of the rubric
``{"criteria": [...]}``. That contaminated every graded number to date
(mem-eacq variance pilot; Stephanie ruled ISOLATE + RE-SCORE, mem-9ld4).

The hijack vector is not specific to the graded judge — it applies to ANY model
call that shells ``claude -p`` with the host config surface, so this module is
the shared isolation seam for all of them: the graded rubric judge, the bbon
comparative judge, the oracle curator, and the task-type classifier (mem-hv9l).
It lives at the package root — like `membench._claude_cli` — so no subpackage
imports another to reach it. ``label`` names the callsite in the retained
isolation dir's prefix, keeping the per-callsite audit trail attributable.
`run_isolated_claude` is the one spawn choke point every callsite goes through
(argv, fresh env, neutral cwd, fail-loud error mapping), and
`IsolatedClaudeCallsite` is the lazy materialize-and-cache contract the judge
dataclasses share — a new callsite gets both for free instead of hand-rolling
the incantation (the drift mem-hv9l existed to close).

The fix is config/mechanism only — the judge MODEL and round count are unchanged
(``claude-sonnet-4-6`` x3). This module materializes a minimal, EMPTY
``CLAUDE_CONFIG_DIR`` (a lone ``settings.json`` — no agents, skills, rules,
commands, or ``CLAUDE.md``) and a neutral working directory outside any project,
then hands back the env + argv + cwd the judge subprocess must run under so it can
NEVER load a host or project agent. Both config surfaces are closed:

- **Host config** — ``CLAUDE_CONFIG_DIR`` is redirected to the clean dir, so the
  operator account's ``agents/skills/rules/CLAUDE.md`` are all bypassed.
- **Project config** — the judge runs with ``cwd`` set to a neutral dir under the
  temp root (not the repo), so ``claude``'s upward walk for ``CLAUDE.md`` /
  ``.claude/`` finds nothing.
- **MCP** — ``--strict-mcp-config`` (with no ``--mcp-config``) disables every MCP
  server, matching the headless-agent boot-hang guard.

Auth is unaffected: headless ``claude -p`` authenticates from the
``CLAUDE_CODE_OAUTH_TOKEN`` env var (the documented headless path), which
`isolated_judge_env` preserves along with ``PATH`` / ``HOME`` — it overrides only
``CLAUDE_CONFIG_DIR``.

ZFC: pure plumbing — directory materialization, env assembly, and a fail-loud
cleanliness assertion. No semantic judgment; the judge model still does all the
grading.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from membench.spawn import Runner, run_checked

# The env var that redirects the entire ``claude`` config surface (skills, rules,
# agents, CLAUDE.md, settings) to a chosen directory.
ENV_CLAUDE_CONFIG_DIR = "CLAUDE_CONFIG_DIR"

# Config-dir entries that would let a host/project agent or instruction back into
# the judge session. If any of these is present in the "clean" dir, isolation has
# failed and we refuse to run rather than silently grade under contamination.
FORBIDDEN_CONFIG_ENTRIES = ("agents", "skills", "rules", "commands", "CLAUDE.md")

# A minimal, valid settings file so the dir is an intentional (not accidentally
# empty) config root. It enables nothing — no hooks, no MCP, no plugins.
_MINIMAL_SETTINGS = "{}\n"

# Disables every MCP server (matches the headless-agent boot-hang guard).
STRICT_MCP_CONFIG_FLAG = "--strict-mcp-config"


def _default_isolation_base(label: str) -> Path:
    """A fresh, unique base dir for one isolated judge config. ``mkdtemp`` guarantees
    the path is exclusive to this call -- concurrent judge invocations (grid runs,
    variance pilots, parallel bundles) never share a base dir, so the
    mkdir -> forbidden-entries-check -> settings.json write below needs no lock.
    ``label`` is the callsite name baked into the prefix, so a retained dir is
    attributable to the judge that produced it, not just "some judge".

    Deliberately never cleaned up: the judge's ``claude -p`` writes its session
    transcripts under ``config/projects/``, and a run's pins reference this dir by
    path (`IsolatedJudgeConfig.marker`) -- together they are the post-hoc audit
    trail that proves what the judge actually did (the mem-eacq contamination was
    diagnosed from exactly this evidence). Retention is bounded by the system
    temp-dir lifecycle."""
    uid = os.getuid() if hasattr(os, "getuid") else os.getpid()
    return Path(tempfile.mkdtemp(prefix=f"membench-{label}-judge-{uid}-"))


@dataclass(frozen=True)
class IsolatedJudgeConfig:
    """The isolation surface for one judge subprocess: the clean ``config_dir``
    (redirected ``CLAUDE_CONFIG_DIR``), a neutral ``cwd`` outside any project, and the
    ``extra_argv`` flags it must carry. ``marker`` is the attributable record echoed
    into a run's pins. There is no cached ``env`` here -- the subprocess env is
    assembled fresh per call (`isolated_judge_env`) so a mid-run credential refresh
    (e.g. ``CLAUDE_CODE_OAUTH_TOKEN``) is never shipped stale."""

    config_dir: Path
    cwd: Path
    extra_argv: tuple[str, ...]

    @property
    def marker(self) -> dict[str, object]:
        """The pins record: isolation is on, and exactly which clean config dir the
        judge ran under. Makes an isolated score attributable and distinguishable
        from a pre-isolation (contaminated) one."""
        return {
            "isolated_config": True,
            "config_dir": str(self.config_dir),
            "strict_mcp_config": STRICT_MCP_CONFIG_FLAG in self.extra_argv,
        }


def _assert_no_forbidden_entries(directory: Path) -> None:
    """Fail-loud cleanliness check shared by every isolation-surface dir (config AND
    cwd): if a forbidden entry (`FORBIDDEN_CONFIG_ENTRIES`) is somehow present, raise
    rather than run a judge that could load it -- isolation fails LOUD, never open."""
    present = [name for name in FORBIDDEN_CONFIG_ENTRIES if (directory / name).exists()]
    if present:
        raise RuntimeError(
            f"isolated judge dir {directory} is not clean: {present} present -- "
            "refusing to run the judge under a config surface that could load a host agent"
        )


def ensure_isolated_config_dir(config_dir: Path) -> Path:
    """Materialize (idempotently) the minimal clean config dir and assert it carries
    NO host/project agent surface. Writes only ``settings.json``."""
    config_dir.mkdir(parents=True, exist_ok=True)
    _assert_no_forbidden_entries(config_dir)
    (config_dir / "settings.json").write_text(_MINIMAL_SETTINGS, encoding="utf-8")
    return config_dir


def isolated_judge_env(
    config_dir: Path, base_env: Mapping[str, str] | None = None
) -> dict[str, str]:
    """A copy of ``base_env`` (default ``os.environ``, read FRESH on every call) with
    ``CLAUDE_CONFIG_DIR`` redirected to ``config_dir``. Everything else is preserved
    verbatim -- notably ``CLAUDE_CODE_OAUTH_TOKEN`` (headless auth), ``PATH``
    (locating ``claude``), and ``HOME`` -- so isolation changes the config surface
    WITHOUT breaking auth. Call this at subprocess-launch time, not once at judge
    construction -- a cached snapshot would ship a stale token if credentials are
    refreshed mid-run."""
    env = dict(os.environ if base_env is None else base_env)
    env[ENV_CLAUDE_CONFIG_DIR] = str(config_dir)
    return env


def prepare_isolated_judge(
    base: Path | None = None, *, label: str | None = None
) -> IsolatedJudgeConfig:
    """Assemble the full isolation surface for one ``claude -p`` subprocess. Creates
    a clean ``config`` dir (redirected ``CLAUDE_CONFIG_DIR``) and a distinct neutral
    ``cwd`` dir (both under ``base``, default `_default_isolation_base` -- a fresh
    unique dir per call, so concurrent invocations never race); the two are separate
    so the judge never treats its own config dir as a project checkout. Both dirs get
    the same fail-loud cleanliness check. Returns the config dir, neutral cwd, and the
    ``--strict-mcp-config`` flag to append to argv. ``label`` names the callsite in
    the retained dir's prefix; it is REQUIRED when ``base`` is None (a retained
    default-base dir must be attributable to the callsite that produced it, never
    silently mislabelled) and unused when ``base`` is supplied."""
    if base is None:
        if label is None:
            raise ValueError(
                "prepare_isolated_judge: label is required when no base is supplied -- "
                "the retained isolation dir must be attributable to its callsite"
            )
        root = _default_isolation_base(label)
    else:
        root = base
    config_dir = ensure_isolated_config_dir(root / "config")
    cwd = root / "cwd"
    cwd.mkdir(parents=True, exist_ok=True)
    _assert_no_forbidden_entries(cwd)
    return IsolatedJudgeConfig(
        config_dir=config_dir,
        cwd=cwd,
        extra_argv=(STRICT_MCP_CONFIG_FLAG,),
    )


def run_isolated_claude(
    prompt: str,
    *,
    isolation: IsolatedJudgeConfig,
    runner: Runner,
    timeout_s: float,
    model: str | None,
    callsite: str,
    error: Callable[[str], BaseException] = RuntimeError,
    output_format_json: bool = True,
) -> str:
    """One headless ``claude -p`` spawn under the isolation surface -- the single
    choke point every ``claude`` callsite shares (mem-hv9l), so an isolation change
    (a new flag, a new env rule) lands everywhere at once instead of drifting per
    copy. The subprocess env is assembled FRESH per call (`isolated_judge_env`) so a
    credential refreshed mid-run is never shipped stale. ``model`` None omits the
    ``--model`` flag (the CLI's own default). Returns raw stdout; callers own reply
    parsing.

    This choke point is drawn around THE CLAUDE BINARY -- the isolation surface and
    the argv are what it owns. The spawn-and-diagnose ladder underneath it is a
    WIDER seam than that (every shelling site needs it, claude or not), so it lives
    in ``spawn.run_checked``; drawing both circles at this radius is what let the
    ladder drift per copy in the first place (mem-o9plh). ``error`` is this
    function's own contribution to that helper: the factory that keeps each
    caller's exception type while sharing one ladder."""
    argv = ["claude", "-p", prompt]
    if output_format_json:
        argv += ["--output-format", "json"]
    if model is not None:
        argv += ["--model", model]
    argv += list(isolation.extra_argv)
    return run_checked(
        argv,
        what=f"claude -p for the {callsite}",
        not_found_hint=f"install it to run the {callsite}",
        timeout_s=timeout_s,
        error=error,
        runner=runner,
        env=isolated_judge_env(isolation.config_dir),
        cwd=isolation.cwd,
    ).stdout


class IsolatedClaudeCallsite:
    """The lazy-isolation contract shared by every frozen-dataclass ``claude -p``
    callsite (graded rubric judge, comparative judge, oracle curator). A subclass
    declares the ``isolation: IsolatedJudgeConfig | None = None`` field and names
    itself via ``_isolation_label`` -- the audit label baked into the retained
    dir's prefix, so the trail stays attributable per callsite.

    ``isolation`` left ``None`` is materialized on first use and cached, so mere
    construction touches no disk; tests inject a ``tmp_path``-scoped one. The
    check-then-set is NOT thread-safe: an instance is sequential-use only (every
    current driver runs calls in a plain ``for`` loop); parallel use needs one
    instance per thread."""

    _isolation_label: ClassVar[str]
    isolation: IsolatedJudgeConfig | None

    def _resolved_isolation(self) -> IsolatedJudgeConfig:
        isolation = self.isolation
        if isolation is None:
            isolation = prepare_isolated_judge(label=self._isolation_label)
            object.__setattr__(self, "isolation", isolation)
        return isolation

    @property
    def isolation_marker(self) -> dict[str, object] | None:
        """The attributable isolation record echoed into a run's artifact -- proves
        an isolated (clean-config) result is distinguishable from a pre-isolation
        one. None until an isolation surface exists (injected, or materialized by
        the first call): the marker attests a surface a call actually ran under,
        never one minted just to satisfy a report -- a dir with no session
        transcripts proves nothing and would litter the retained audit trail
        (mem-hv9l review)."""
        return None if self.isolation is None else self.isolation.marker
