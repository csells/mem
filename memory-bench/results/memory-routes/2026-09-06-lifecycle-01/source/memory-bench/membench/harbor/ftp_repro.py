"""Graded fail-to-pass repro for ftp-oracle anchor bundles (mem-bxhh.3.3).

`repro_live.LiveReproRunner` scores whole gold-test FILES on the host (npm/vitest);
a codeprobe ftp anchor bundle (mem-bxhh.3.2) instead carries a curated red->green
NODE-ID set on ``verification.ftp_oracle`` that pytest must run IN the rig
container. This runner is the `ReproRunner` the dual verifier / validity gate inject
for those bundles. For one candidate diff it:

1. checks out a detached worktree of the rig clone at the bundle's ``env.base_commit``
   (the ftp oracle's PARENT), cached per (rig, base_commit) and reset between runs;
2. ``git apply`` the candidate diff EXCLUDING the gold test MODULES -- the curated
   tests are the spec, never judged on the candidate's own test edits;
3. overlays the LANDING versions of those gold test modules (``git checkout landing
   -- <modules>``) -- the same parent-source/landing-tests isolation
   ``ftp_curate.curate_commit`` mined the oracle with;
4. runs exactly the curated ftp nodeids in ``bundle.env.base_image`` and counts how
   many pytest reports as ``passed``.

``passed`` = every curated ftp nodeid passes (the ungameable all-or-nothing anchor);
``tests_passed`` / ``tests_total`` are the S1 per-nodeid partial credit underneath it
(mem-g6a). Because the scored run reuses ftp_curate's container-pytest primitive, a
candidate is scored on the same install + junit instrument the oracle was curated
with -- so the validity gate's gold-reproduces / empty-fails invariant holds by
construction for a sound oracle.

An infrastructure failure (the candidate diff will not apply, the landing overlay
failed, the container produced no junit) returns ``ReproOutcome(error=...)`` so
`score_direct` falls back to diff similarity and records WHY -- never a silent 0.

ZFC: pure mechanism -- git IO (injectable `Runner`), container exec, junit set ops.
The one judgement (do the tests pass?) is pytest's, delegated like the curator's.
"""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import Mapping
from pathlib import Path

from membench.grading.dual_verifier import ReproOutcome
from membench.harbor.env_recon import DEFAULT_RIG_REPOS
from membench.harbor.ftp_curate import run_container_pytest, select_pytest_modules
from membench.harbor.probe_gate import _add_worktree, _remove_worktree
from membench.schemas.bundle import TaskBundle
from membench.spawn import Runner

# Distinct from repro's "repro-" and the curator's "ftp-" so an exit-sweep of any
# one prefix never force-removes another runner's live checkouts.
FTP_REPRO_WORKTREE_PREFIX = "ftp-repro-"

# git apply / checkout / clean on a worktree: bounded, never unbounded (an agent
# transcript bounds the patch size, not this code).
GIT_OP_TIMEOUT_SEC = 120.0


class FtpReproRunner:
    """The injectable `ReproRunner` for ftp-oracle anchor bundles. Holds a worktree
    cache across `run` calls (one detached checkout per (rig, base_commit)); `close`
    removes every cached worktree -- use as a context manager so a crashed grid run
    never strands checkouts on the rig clone."""

    def __init__(
        self,
        *,
        rig_repos: Mapping[str, Path] = DEFAULT_RIG_REPOS,
        worktree_root: Path = Path("/tmp"),
        runner: Runner = subprocess.run,
    ) -> None:
        self._rig_repos = rig_repos
        self._worktree_root = worktree_root
        self._runner = runner
        self._worktrees: dict[tuple[str, str], Path] = {}

    def __enter__(self) -> FtpReproRunner:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """Remove every cached worktree. Errors propagate -- a stranded checkout on
        the rig clone is an operator problem, not something to hide."""
        while self._worktrees:
            (rig, _), worktree = self._worktrees.popitem()
            _remove_worktree(self._rig_repos[rig], worktree, self._runner)

    def run(self, *, bundle: TaskBundle, candidate_diff: Mapping[str, str]) -> ReproOutcome:
        oracle = bundle.verification.ftp_oracle
        if oracle is None:
            return ReproOutcome(passed=False, error="bundle carries no ftp_oracle to score against")
        if not oracle.ftp_tests:
            return ReproOutcome(passed=False, error="ftp_oracle carries no ftp tests")
        clone = self._rig_repos.get(bundle.rig)
        if clone is None:
            return ReproOutcome(passed=False, error=f"no local clone for rig {bundle.rig!r}")

        # The spec = the gold diff's pytest MODULES (exactly what ftp_curate overlaid
        # to mine the oracle): excluded from the candidate, overlaid from the landing.
        gold_paths = [path for path, _ in bundle.output.file_diffs]
        spec_modules = frozenset(select_pytest_modules(gold_paths))
        if not spec_modules:
            return ReproOutcome(
                passed=False, error="ftp anchor gold diff carries no pytest modules to overlay"
            )

        try:
            worktree = self._ensure_worktree(bundle, clone)
        except _InfraError as exc:
            return ReproOutcome(passed=False, error=str(exc))

        applied = {
            path: diff
            for path, diff in candidate_diff.items()
            if path not in spec_modules and diff.strip()
        }
        patch = "".join(diff for _, diff in sorted(applied.items()))
        try:
            self._apply(worktree, patch)
            self._overlay(worktree, clone, oracle.commit, sorted(spec_modules))
        except _InfraError as exc:
            return ReproOutcome(passed=False, error=str(exc))

        # Run the spec MODULE FILES (not the curated nodeids): a curated nodeid is in
        # junit ``classname`` form (``tests.test_x::t``), which pytest cannot take as a
        # path arg. ftp_curate ran the files and classified the parsed nodeids -- doing
        # the same here, with the same parser, keeps the scored nodeid form identical
        # to the oracle's, so the lookup below matches by construction.
        try:
            outcomes = run_container_pytest(
                worktree, sorted(spec_modules), bundle.env.base_image, self._runner
            )
        except RuntimeError as exc:
            return ReproOutcome(passed=False, error=str(exc))

        total = len(oracle.ftp_tests)
        passed = sum(1 for node in oracle.ftp_tests if outcomes.get(node) == "passed")
        return ReproOutcome(passed=passed == total, tests_passed=passed, tests_total=total)

    # -- internals -------------------------------------------------------------------

    def _ensure_worktree(self, bundle: TaskBundle, clone: Path) -> Path:
        key = (bundle.rig, bundle.env.base_commit)
        cached = self._worktrees.get(key)
        if cached is not None:
            # Reset between runs: restore tracked files (drops the prior candidate +
            # landing overlay), drop new untracked files (a feature-presence overlay
            # creates files absent at the parent); `-fd` (no -x) keeps ignored deps.
            self._git("-C", str(cached), "checkout", "-q", "--", ".")
            self._git("-C", str(cached), "clean", "-fdq")
            return cached
        worktree = self._worktree_root / (
            f"{FTP_REPRO_WORKTREE_PREFIX}{bundle.rig}-"
            f"{bundle.env.base_commit[:12]}-{uuid.uuid4().hex[:6]}"
        )
        _add_worktree(clone, bundle.env.base_commit, worktree, self._runner)
        self._worktrees[key] = worktree
        return worktree

    def _apply(self, worktree: Path, patch: str) -> None:
        if not patch.strip():
            return
        try:
            completed = self._runner(
                ["git", "-C", str(worktree), "apply", "--whitespace=nowarn", "-"],
                input=patch,
                capture_output=True,
                text=True,
                timeout=GIT_OP_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired as exc:
            raise _InfraError(
                f"candidate diff git apply timed out after {GIT_OP_TIMEOUT_SEC}s"
            ) from exc
        if completed.returncode != 0:
            raise _InfraError(f"candidate diff failed to apply: {completed.stderr.strip()[-500:]}")

    def _overlay(self, worktree: Path, clone: Path, landing: str, modules: list[str]) -> None:
        """Check the LANDING versions of ``modules`` into the parent worktree -- the
        SWE-bench gold-test overlay. A module absent at the parent (a new test file)
        is created; landing must contain every module (the oracle was mined from it),
        so a checkout failure here is a real infra fault, not a silent skip."""
        self._git("-C", str(worktree), "checkout", landing, "--", *modules)

    def _git(self, *args: str) -> None:
        try:
            completed = self._runner(
                ["git", *args], capture_output=True, text=True, timeout=GIT_OP_TIMEOUT_SEC
            )
        except subprocess.TimeoutExpired as exc:
            raise _InfraError(
                f"git {' '.join(args)} timed out after {GIT_OP_TIMEOUT_SEC}s"
            ) from exc
        if completed.returncode != 0:
            raise _InfraError(f"git {' '.join(args)} failed: {completed.stderr.strip()[-300:]}")


class _InfraError(RuntimeError):
    """An infrastructure failure (apply/overlay/timeout) -- becomes
    ``ReproOutcome.error`` so the dual verifier records the fallback reason."""
