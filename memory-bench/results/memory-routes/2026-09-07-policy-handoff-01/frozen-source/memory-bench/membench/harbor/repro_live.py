"""Live gold-test reproduction runner (mem-apg.3) -- the dual-verifier's primary
direct leg made executable.

`membench.grading.dual_verifier` defines the `ReproRunner` seam and ships only the
stub; this module is the integration-time implementation it deferred. The protocol
is SWE-bench fail-to-pass, validated end-to-end on gascity-dashboard-4lf62 before
this was written (gold tests against the full gold diff: 58/58 pass; gold tests
against the bare base: 5/5 files fail):

1. detached worktree of the rig clone at the bundle's exact ``env.base_commit``,
   cached per (rig, base_commit) with dependencies installed ONCE -- later runs on
   the same base reset the tree (``git checkout -- . && git clean -fd``, which
   keeps the ignored ``node_modules``/build dirs) instead of reinstalling;
2. ``git apply`` the candidate diff EXCLUDING gold test paths -- the gold tests are
   the spec, so the candidate is never judged on its own test edits;
3. ``git apply`` the gold diff's TEST files on top;
4. re-run the install when an applied path touched a dependency manifest;
5. run the workspace's test command on EACH gold test file on its own (mem-g6a S1),
   with no short-circuit, recording how many of the files passed.

``passed`` = every gold test file (each run on its own) and the rig's setup commands
exit 0 -- the ungameable all-or-nothing anchor, unchanged in meaning from the
batch era (each file is independent fail-to-pass). ``tests_passed``/``tests_total``
are the S1 partial-credit counts UNDER that anchor: a candidate that fixes some but
not all gold tests lands strictly between 0 and 1 on the ratio while the binary
anchor still FAILS. A nonzero test or setup exit is a legitimate FAIL (the candidate
did not satisfy the gold tests / broke the build), never an error. Infrastructure
failures -- a diff that does not apply, an install failure, a timeout, an unmapped
rig or workspace -- return ``ReproOutcome(error=...)`` so `score_direct` falls back
to diff similarity and records why (the dual verifier's designed degradation, never
a silent 0).

ZFC: pure mechanism -- worktree IO, ``git apply``, subprocess fan-out, exit-code
interpretation. The only judgement (do the tests pass?) is the test runner's.
"""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from membench.grading.dual_verifier import ReproOutcome, is_test_path
from membench.harbor.env_recon import DEFAULT_RIG_REPOS
from membench.harbor.probe_gate import _add_worktree, _remove_worktree
from membench.schemas.bundle import TaskBundle
from membench.spawn import Runner

# Dependency-manifest basenames: an applied diff touching one of these invalidates
# the cached install (step 4 above).
_MANIFEST_NAMES = frozenset({"package.json", "package-lock.json"})

# Wide enough for a cold `npm ci` on the dashboard repo (~2 s warm, minutes cold)
# and a scoped vitest run; propagated as an error outcome on expiry, never hidden.
INSTALL_TIMEOUT_SEC = 900.0
TEST_TIMEOUT_SEC = 900.0
# git apply / checkout / clean on a worktree: fast in practice, but an agent
# transcript bounds the patch size, not this code -- so bounded, never unbounded.
GIT_OP_TIMEOUT_SEC = 120.0

# Public: run_grid exit-sweeps stranded checkouts (a SIGKILL'd run never reaches
# `close`) via probe_gate's sweep with this prefix.
WORKTREE_PREFIX = "repro-"


@dataclass(frozen=True)
class WorkspaceTests:
    """One workspace's scoped test invocation: gold test files under ``prefix`` run
    as ``argv_prefix + <paths relative to cwd>`` from ``<worktree>/<cwd>``."""

    prefix: str
    cwd: str
    argv_prefix: tuple[str, ...]


@dataclass(frozen=True)
class RigTestConfig:
    """How one rig runs its tests: ``install`` once per cached worktree, ``setup``
    after every apply (build steps tests depend on), then per-workspace commands."""

    install: tuple[tuple[str, ...], ...]
    setup: tuple[tuple[str, ...], ...]
    workspaces: tuple[WorkspaceTests, ...]


# gascity-dashboard: npm workspaces (shared/backend/frontend); frontend vitest
# normally rebuilds `shared` via its pretest hook, which a direct `npx vitest`
# invocation skips -- hence the explicit build:shared setup step.
DASHBOARD_TEST_CONFIG = RigTestConfig(
    install=(("npm", "ci", "--no-audit", "--no-fund"),),
    setup=(("npm", "run", "build:shared"),),
    workspaces=(
        WorkspaceTests(prefix="frontend/", cwd="frontend", argv_prefix=("npx", "vitest", "run")),
        WorkspaceTests(
            prefix="backend/", cwd="backend", argv_prefix=("node", "--import", "tsx", "--test")
        ),
        WorkspaceTests(prefix="shared/", cwd="shared", argv_prefix=("npx", "tsx", "--test")),
    ),
)

# mem: the rig is THIS repo. The gold tests it carries in the corpus are the root
# TypeScript suite (vitest, tests/*.test.ts) -- mem-us6j, the only assembled mem bundle,
# is TS-only. `npm ci` seeds a local, isolated node_modules; the workspace runs from the
# worktree root (cwd ".") so vitest resolves its config + aliases, and the stripped bare
# filename is the path-substring filter `vitest run` takes.
#
# Deliberately TS-only: the Python memory-bench suite is NOT wired here. It would need
# `pip install -e memory-bench[dev]`, which fails on a PEP-668 externally-managed host
# python (the gate's direct leg runs on the host, not in a container) -- and no mem
# bundle in the pool has a Python gold test, so wiring it would be unvalidated,
# host-fragile generality. A future Python-gold-test mem bundle needs a venv-scoped,
# per-workspace install (RigTestConfig.install is shared across workspaces today), which
# is the change to make THEN -- see docs/mem-7q6e-replay-engine-null.md.
MEM_TEST_CONFIG = RigTestConfig(
    install=(("npm", "ci", "--no-audit", "--no-fund"),),
    setup=(),
    workspaces=(WorkspaceTests(prefix="tests/", cwd=".", argv_prefix=("npx", "vitest", "run")),),
)

RIG_TEST_CONFIGS: dict[str, RigTestConfig] = {
    "gascity_dashboard": DASHBOARD_TEST_CONFIG,
    "mem": MEM_TEST_CONFIG,
}


class LiveReproRunner:
    """The injectable `ReproRunner` that actually applies diffs and runs tests.

    Holds a worktree cache across `run` calls (one installed checkout per
    (rig, base_commit)); `close` removes every cached worktree -- use as a context
    manager so a crashed grid run never strands checkouts on the rig clone.
    """

    def __init__(
        self,
        *,
        rig_repos: Mapping[str, Path] = DEFAULT_RIG_REPOS,
        configs: Mapping[str, RigTestConfig] = RIG_TEST_CONFIGS,
        worktree_root: Path = Path("/tmp"),
        runner: Runner = subprocess.run,
    ) -> None:
        self._rig_repos = rig_repos
        self._configs = configs
        self._worktree_root = worktree_root
        self._runner = runner
        self._worktrees: dict[tuple[str, str], Path] = {}

    def __enter__(self) -> LiveReproRunner:
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
        config = self._configs.get(bundle.rig)
        if config is None:
            return ReproOutcome(passed=False, error=f"no test config for rig {bundle.rig!r}")
        clone = self._rig_repos.get(bundle.rig)
        if clone is None:
            return ReproOutcome(passed=False, error=f"no local clone for rig {bundle.rig!r}")

        gold_tests = {path: diff for path, diff in bundle.output.file_diffs if is_test_path(path)}
        if not gold_tests:
            return ReproOutcome(passed=False, error="gold diff carries no test files")
        unmapped = [
            path
            for path in gold_tests
            if not any(path.startswith(w.prefix) for w in config.workspaces)
        ]
        if unmapped:
            return ReproOutcome(
                passed=False, error=f"gold test paths outside known workspaces: {unmapped}"
            )

        try:
            worktree = self._ensure_worktree(bundle, clone, config)
        except _InfraError as exc:
            return ReproOutcome(passed=False, error=str(exc))

        applied_candidate = {
            path: diff
            for path, diff in candidate_diff.items()
            if path not in gold_tests and diff.strip()
        }
        candidate_patch = "".join(diff for _, diff in sorted(applied_candidate.items()))
        gold_tests_patch = "".join(diff for _, diff in sorted(gold_tests.items()))
        try:
            self._apply(worktree, candidate_patch, label="candidate diff")
            self._apply(worktree, gold_tests_patch, label="gold test diff")
            # Reinstall trigger over exactly the APPLIED paths -- an excluded or
            # blank-diff manifest entry must not cost a multi-minute cold install.
            if any(Path(p).name in _MANIFEST_NAMES for p in (*applied_candidate, *gold_tests)):
                self._install(worktree, config)
        except _InfraError as exc:
            return ReproOutcome(passed=False, error=str(exc))

        # S1 (mem-g6a): score each gold-test FILE on its own, NO short-circuit, so a
        # candidate that fixes some-but-not-all gold tests lands strictly between the
        # binary anchor's 0 and 1. ``passed`` stays the ungameable all-or-nothing
        # floor: every file (and every setup step) must exit 0. A setup failure is a
        # binary FAIL with zero files credited -- the tests never ran.
        total = len(gold_tests)
        try:
            for argv in config.setup:
                if self._exec(worktree, argv, TEST_TIMEOUT_SEC).returncode != 0:
                    return ReproOutcome(passed=False, tests_passed=0, tests_total=total)
            tests_passed = 0
            for workspace in config.workspaces:
                for path in sorted(p for p in gold_tests if p.startswith(workspace.prefix)):
                    relative = path[len(workspace.prefix) :]
                    completed = self._exec(
                        worktree / workspace.cwd,
                        (*workspace.argv_prefix, relative),
                        TEST_TIMEOUT_SEC,
                    )
                    if completed.returncode == 0:
                        tests_passed += 1
        except _InfraError as exc:
            return ReproOutcome(passed=False, error=str(exc))
        return ReproOutcome(
            passed=tests_passed == total, tests_passed=tests_passed, tests_total=total
        )

    # -- internals -------------------------------------------------------------------

    def _ensure_worktree(self, bundle: TaskBundle, clone: Path, config: RigTestConfig) -> Path:
        key = (bundle.rig, bundle.env.base_commit)
        cached = self._worktrees.get(key)
        if cached is not None:
            # Reset between runs: restore tracked files, drop the previous run's new
            # files; `git clean -fd` (no -x) keeps ignored node_modules / build dirs.
            self._git("-C", str(cached), "checkout", "-q", "--", ".")
            self._git("-C", str(cached), "clean", "-fdq")
            return cached
        worktree = self._worktree_root / (
            f"{WORKTREE_PREFIX}{bundle.rig}-{bundle.env.base_commit[:12]}-{uuid.uuid4().hex[:6]}"
        )
        _add_worktree(clone, bundle.env.base_commit, worktree, self._runner)
        try:
            self._install(worktree, config)
        except _InfraError:
            _remove_worktree(clone, worktree, self._runner)
            raise
        self._worktrees[key] = worktree
        return worktree

    def _install(self, worktree: Path, config: RigTestConfig) -> None:
        for argv in config.install:
            completed = self._exec(worktree, argv, INSTALL_TIMEOUT_SEC)
            if completed.returncode != 0:
                raise _InfraError(
                    f"install {argv!r} failed (exit {completed.returncode}): "
                    f"{completed.stderr.strip()[-500:]}"
                )

    def _apply(self, worktree: Path, patch: str, *, label: str) -> None:
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
            raise _InfraError(f"{label} git apply timed out after {GIT_OP_TIMEOUT_SEC}s") from exc
        if completed.returncode != 0:
            raise _InfraError(f"{label} failed to apply: {completed.stderr.strip()[-500:]}")

    def _exec(
        self, cwd: Path, argv: tuple[str, ...], timeout: float
    ) -> subprocess.CompletedProcess[str]:
        try:
            return self._runner(
                list(argv), cwd=str(cwd), capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired as exc:
            raise _InfraError(f"{argv!r} timed out after {timeout}s") from exc

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
    """An infrastructure failure (apply/install/timeout) -- becomes
    ``ReproOutcome.error`` so the dual verifier records the fallback reason."""
