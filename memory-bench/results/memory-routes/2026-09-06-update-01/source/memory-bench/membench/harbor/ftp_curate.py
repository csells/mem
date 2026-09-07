"""harbor/ftp_curate -- per-rig fail-to-pass oracle curation (mem-bxhh.1).

Productionizes the codeprobe ftp probe (docs/mem-rig-eval-infra-feasibility.md)
into a reusable per-rig tool. Input: the rig's *linked landing commits* (from the
TS `mem link-outcomes` emitter over `linkRigOutcomes`). For each commit it runs
the SWE-bench fail-to-pass isolation -- run the landing commit's test-touching
files at the PARENT tree and at the LANDING tree, in a container, and take the
set that passes at landing but not at parent. Output: per-rig JSON of
``{commit, parent, ftp_tests[], behavioral|feature_presence, type}``.

Reuses the validated harbor replay primitives rather than reinventing them:
``_add_worktree``/``_remove_worktree`` (worktree lifecycle) and the ``Runner``
subprocess seam -- so the git/worktree plumbing is shared with ``repro_live.py``
and injectable for tests. It does NOT reuse ``is_test_path`` for choosing what to
run: that predicate matches anything under a ``tests/`` tree (conftest, fixtures,
data), but pytest must be handed only runnable modules -- see
:func:`select_pytest_modules`.

Three bugs the ad-hoc probe carried are fixed by construction:

1. multi-file pytest paths are passed as separate argv tokens (never a comma- or
   shell-joined string) -- see :func:`pytest_argv`;
2. the parent/landing comparison is a set difference, not ``comm`` over sorted
   streams (no "not in sorted order" fragility) -- see :func:`classify_ftp`;
3. a collection ERROR at the parent counts as not-pass and is read from a
   machine-readable ``--junitxml`` (``<error>`` vs ``<failure>``), so it
   classifies *feature-presence* distinctly from a behavioral red->green --
   rather than being missed by scraping ``-q`` stdout.

ZFC: pure mechanism -- worktree IO, container exec, structural XML/set ops. No
semantic judgment; "behavioral vs feature-presence" is a structural fact (did the
test nodeid exist at the parent), not a quality call.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from membench.harbor.probe_gate import _add_worktree, _remove_worktree
from membench.harbor.repro_live import TEST_TIMEOUT_SEC
from membench.spawn import Runner

# Worktree basename prefix for ftp curation -- distinct from repro's "repro-" so a
# sweep of either never force-removes the other's checkouts.
FTP_WORKTREE_PREFIX = "ftp-"

# Codeprobe's stock toolchain image: `pip install -e .` resolves with no system
# deps, and running IN-container sidesteps the PEP-668 externally-managed host
# python that keeps the mem Python suite unwired (see repro_live MEM_TEST_CONFIG).
DEFAULT_BASE_IMAGE = "python:3.11-bookworm"

# Env-flaky tests to exclude from both legs so the ftp count is deterministic
# (docs/mem-rig-eval-infra-feasibility.md flags test_validate_ready). Substring
# match against the nodeid -- a node whose id contains one of these is dropped.
FLAKY_TEST_SUBSTRINGS: tuple[str, ...] = ("test_validate_ready",)

# Path of the junit report inside the container (the mounted worktree is /app).
_JUNIT_BASENAME = ".ftp-junit.xml"

# Codeprobe install spec: an editable install plus `pytest` itself -- pytest is a
# test-only dependency the rig does not declare in its runtime deps, so
# `pip install -e .` alone leaves `pytest: command not found` (the probe's own
# reproduce line was `pip install -e . pytest`). junitxml needs no extra plugin.
INSTALL_PACKAGES: tuple[str, ...] = ("-e", ".", "pytest")


# Per-commit headline: behavioral (any red->green present -- the stronger
# discriminator), feature-presence (only new-test collection errors), or none
# (test files changed but no fail-to-pass surfaced).
FtpType = Literal["behavioral", "feature-presence", "none"]


@dataclass(frozen=True)
class FtpResult:
    """The fail-to-pass split for one parent->landing comparison. Tuple fields so
    ``frozen=True`` is a real immutability guarantee, not just a frozen reference
    to a mutable list."""

    ftp_tests: tuple[str, ...]
    behavioral: tuple[str, ...]
    feature_presence: tuple[str, ...]
    type: FtpType


@dataclass(frozen=True)
class CommitFtp:
    """One landing commit's curated oracle."""

    commit: str
    parent: str
    ftp_tests: tuple[str, ...]
    behavioral: tuple[str, ...]
    feature_presence: tuple[str, ...]
    type: FtpType

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


# --- pure logic -------------------------------------------------------------------


def parse_junit_outcomes(xml_text: str) -> dict[str, str]:
    """Map each ``<testcase>`` to its outcome from pytest ``--junitxml`` output.

    nodeid is ``<file>::<name>`` (falling back to ``<classname>::<name>`` when the
    file attribute is absent, as on some collection-error cases). Status is
    ``error`` (``<error>`` child -- a collection or setup failure), ``failed``
    (``<failure>``), ``skipped`` (``<skipped>``), else ``passed``. The error vs
    failure distinction is what separates feature-presence from behavioral.
    """
    # The junit is written by untrusted repo code running as root in the
    # container, so treat it as hostile. pytest junitxml never carries a DTD;
    # reject one rather than let xml.etree's expat expand entities (billion-laughs
    # / entity-injection). A dependency-free guard -- defusedxml is not vendored.
    if "<!DOCTYPE" in xml_text or "<!ENTITY" in xml_text:
        raise RuntimeError("junit report contains a DTD/entity declaration; refusing to parse")
    root = ET.fromstring(xml_text)
    outcomes: dict[str, str] = {}
    for tc in root.iter("testcase"):
        name = tc.get("name", "")
        locus = tc.get("file") or tc.get("classname") or ""
        nodeid = f"{locus}::{name}"
        if tc.find("error") is not None:
            outcomes[nodeid] = "error"
        elif tc.find("failure") is not None:
            outcomes[nodeid] = "failed"
        elif tc.find("skipped") is not None:
            outcomes[nodeid] = "skipped"
        else:
            outcomes[nodeid] = "passed"
    return outcomes


def classify_ftp(parent: Mapping[str, str], landing: Mapping[str, str]) -> FtpResult:
    """Fail-to-pass = passes at landing AND does not pass at parent (a set diff,
    not ``comm``). Each ftp nodeid is *behavioral* if it ran at the parent (its
    nodeid is present, i.e. it failed/errored there) or *feature-presence* if it
    was absent at the parent (a new test/file -- the parent had only a file-level
    collection error, never this per-test nodeid)."""
    landing_pass = {nodeid for nodeid, status in landing.items() if status == "passed"}
    parent_pass = {nodeid for nodeid, status in parent.items() if status == "passed"}
    ftp = tuple(sorted(landing_pass - parent_pass))
    behavioral = tuple(nodeid for nodeid in ftp if nodeid in parent)
    feature_presence = tuple(nodeid for nodeid in ftp if nodeid not in parent)
    if behavioral:
        ftp_type: FtpType = "behavioral"
    elif feature_presence:
        ftp_type = "feature-presence"
    else:
        ftp_type = "none"
    return FtpResult(
        ftp_tests=ftp,
        behavioral=behavioral,
        feature_presence=feature_presence,
        type=ftp_type,
    )


def pytest_argv(test_files: Sequence[str], junit_path: str) -> tuple[str, ...]:
    """The pytest invocation: each test file is its OWN argv token (the bug-1 fix
    -- never comma- or shell-joined), with a machine-readable junit report."""
    return (
        "pytest",
        *test_files,
        "-p",
        "no:cacheprovider",
        "-q",
        f"--junitxml={junit_path}",
    )


def container_command(
    test_files: Sequence[str],
    junit_path: str,
    install_packages: Sequence[str] = INSTALL_PACKAGES,
    *,
    chown_to: str | None = None,
    workdir: str = "/app",
) -> str:
    """The ``bash -lc`` string the container runs: install the rig (plus pytest),
    then run the scoped tests. ``shlex.join`` quotes every token, so the test
    files stay separate argv elements (never re-fused into one comma/space path
    -- the bug-1 guarantee carries through the shell layer too).

    The container runs as root, so ``pip install -e .`` writes a root-owned
    ``*.egg-info`` into the mounted worktree; ``chown_to`` (``uid:gid``) hands the
    tree back to the host user as the final step so host-side worktree cleanup
    does not hit permission errors. It runs after pytest with ``;`` (not ``&&``)
    so a nonzero pytest exit -- the normal case when tests fail -- still restores
    ownership; the junit report is written before pytest exits, so it is intact."""
    install = "pip install " + shlex.join(install_packages) + " -q"
    run = f"{install} && " + shlex.join(pytest_argv(test_files, junit_path))
    if chown_to is not None:
        # Quote both (a future caller could pass non-literal values), and
        # --no-dereference so a symlink the repo planted under the mount can't
        # redirect the chown onto a host file outside the worktree.
        run += f" ; chown -R --no-dereference {shlex.quote(chown_to)} {shlex.quote(workdir)}"
    return run


def single_parent(parents: Sequence[str]) -> str:
    """The sole parent SHA, or a ValueError. The probe's ``parent = commit^`` only
    holds for single-parent (squash/direct) commits; a merge (2 parents) or root
    (0) must fail loudly rather than silently picking the first parent."""
    if len(parents) != 1:
        raise ValueError(
            f"expected a single-parent commit for ftp isolation, got {len(parents)} parents"
        )
    return parents[0]


def select_pytest_modules(paths: Iterable[str]) -> list[str]:
    """The runnable pytest MODULES among ``paths`` -- ``test_*.py`` / ``*_test.py``
    only (order preserved). Both the gold-test overlay and the pytest invocation
    use this set.

    Deliberately stricter than the shared ``is_test_path`` (which matches *anything*
    under a ``tests/`` tree -- conftest, ``*.json`` fixtures, data). Two reasons:
    (1) passing a non-module path like a ``*.json`` fixture to pytest is a
    collection error that derails the whole run (the 6f0c65 false 0-ftp bug); and
    (2) the fail-to-pass anchor (docs/mem-rig-eval-infra-feasibility.md) is the
    modules-only isolation -- overlaying the landing conftest/fixtures onto parent
    source changes the harness and inflates the count (6f0c65: 11 -> 26). The
    parent's own conftest/fixtures are auto-discovered; a genuinely new fixture an
    overlaid gold test needs simply collection-errors at parent, which is the
    correct feature-presence signal."""
    out: list[str] = []
    for path in paths:
        if not path.endswith(".py"):
            continue
        base = Path(path).name
        if base.startswith("test_") or base.endswith("_test.py"):
            out.append(path)
    return out


def drop_flaky(outcomes: Mapping[str, str], substrings: Sequence[str]) -> dict[str, str]:
    """Outcomes minus any nodeid containing a known env-flaky substring."""
    return {
        nodeid: status
        for nodeid, status in outcomes.items()
        if not any(flaky in nodeid for flaky in substrings)
    }


def load_linked_commits(
    payload: Mapping[str, object], *, linkages: frozenset[str] = frozenset({"canonical"})
) -> list[str]:
    """Distinct landing SHAs from a `mem link-outcomes` payload, keeping only the
    requested linkage confidences (default: canonical -- the sound trailer set).
    Order-preserving and de-duplicated (several work ids can land in one commit)."""
    commits = payload.get("commits", [])
    seen: dict[str, None] = {}
    if isinstance(commits, list):
        for entry in commits:
            if not isinstance(entry, Mapping):
                continue
            if entry.get("linkage") not in linkages:
                continue
            sha = entry.get("commit_sha")
            if isinstance(sha, str):
                seen.setdefault(sha, None)
    return list(seen)


# --- IO orchestration -------------------------------------------------------------


def _git_out(clone: Path, args: Sequence[str], runner: Runner) -> str:
    completed = runner(
        ["git", "-C", str(clone), *args], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {clone} failed: {completed.stderr.strip()}")
    return completed.stdout


def _parent_shas(clone: Path, sha: str, runner: Runner) -> list[str]:
    """The parent SHAs of ``sha`` (``rev-list --parents -n1`` lists the commit then
    its parents)."""
    line = _git_out(clone, ["rev-list", "--parents", "-n", "1", sha], runner).split()
    return line[1:]


def _changed_paths(clone: Path, parent: str, landing: str, runner: Runner) -> list[str]:
    out = _git_out(clone, ["diff", "--name-only", f"{parent}..{landing}"], runner)
    return [line for line in out.splitlines() if line]


def run_container_pytest(
    worktree: Path,
    test_files: Sequence[str],
    base_image: str,
    runner: Runner,
) -> dict[str, str]:
    """Run ``test_files`` (file paths OR ``file::node`` ids) in ``base_image`` over
    the mounted worktree and return each collected nodeid's junit outcome. No files
    -> no run (an absent test file at the parent is the feature-presence signal, not
    an error). A missing report after a run is an infra failure (e.g. ``pip install``
    broke) and is raised, never swallowed.

    Shared by the curator (parent/landing legs) and the graded ftp repro runner
    (`harbor.ftp_repro`, which hands the curated nodeids straight in) -- one
    container-pytest primitive, so a scored run installs the rig and reads junit
    exactly as the oracle it is scored against was curated."""
    if not test_files:
        return {}
    junit_host = worktree / _JUNIT_BASENAME
    junit_host.unlink(missing_ok=True)
    # Hand the container-written tree back to the host user on Linux; where
    # getuid is absent (Windows) or the Docker FS already maps ownership (macOS),
    # skip the chown -- container_command treats chown_to=None as "no chown".
    chown_to = f"{os.getuid()}:{os.getgid()}" if hasattr(os, "getuid") else None
    container_cmd = container_command(test_files, f"/app/{_JUNIT_BASENAME}", chown_to=chown_to)
    argv = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{worktree}:/app",
        "-w",
        "/app",
        base_image,
        "bash",
        "-lc",
        container_cmd,
    ]
    try:
        completed = runner(argv, capture_output=True, text=True, timeout=TEST_TIMEOUT_SEC)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"pytest in {base_image} timed out after {TEST_TIMEOUT_SEC}s") from exc
    if not junit_host.exists():
        raise RuntimeError(
            f"pytest produced no junit at {junit_host} "
            f"(install/collection likely failed): {getattr(completed, 'stderr', '')}"
        )
    return parse_junit_outcomes(junit_host.read_text())


def _fresh_worktree(clone: Path, commit: str, dest: Path, runner: Runner) -> None:
    """Add a detached worktree at ``commit``, removing any stale checkout at
    ``dest`` first so the tool is re-run-safe (a prior run that was killed before
    cleanup must not block the next one with 'already exists')."""
    if dest.exists():
        _remove_worktree(clone, dest, runner)
    _add_worktree(clone, commit, dest, runner)


def _overlay_paths(
    worktree: Path, source_commit: str, paths: Sequence[str], runner: Runner
) -> None:
    """Check the ``source_commit`` versions of ``paths`` into ``worktree`` -- the
    SWE-bench "gold test diff" applied to the parent leg. Fail-to-pass isolation
    runs the LANDING test files against the PARENT source, so a behavioral
    red->green (gold test fails on old code) and a new-test-file collection error
    (feature-presence) are both detectable; running the parent's OWN old tests
    against old source would simply pass and surface neither."""
    completed = runner(
        ["git", "-C", str(worktree), "checkout", source_commit, "--", *paths],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"overlaying gold tests from {source_commit[:12]} into {worktree} failed: "
            f"{completed.stderr.strip()}"
        )


def curate_commit(
    rig: str,
    landing_sha: str,
    clone: Path,
    *,
    base_image: str = DEFAULT_BASE_IMAGE,
    runner: Runner = subprocess.run,
    worktree_root: Path = Path("/tmp"),
) -> CommitFtp | None:
    """Curate one landing commit, or None when it touches no test files. Worktrees
    for the parent and landing trees are always cleaned up, even on error."""
    parent_sha = single_parent(_parent_shas(clone, landing_sha, runner))
    changed = _changed_paths(clone, parent_sha, landing_sha, runner)
    run_files = select_pytest_modules(changed)
    if not run_files:
        return None

    wt_parent = worktree_root / f"{FTP_WORKTREE_PREFIX}{rig}-{parent_sha[:12]}-parent"
    wt_landing = worktree_root / f"{FTP_WORKTREE_PREFIX}{rig}-{landing_sha[:12]}-landing"
    _fresh_worktree(clone, parent_sha, wt_parent, runner)
    try:
        _fresh_worktree(clone, landing_sha, wt_landing, runner)
        try:
            # SWE-bench isolation: the GOLD (landing) tests run against BOTH trees.
            # Overlay the landing test modules onto the parent worktree so its leg
            # exercises parent SOURCE with landing TESTS -- a behavioral test fails
            # there (red->green), a new test file collection-errors there
            # (feature-presence). Both legs run the same `run_files`.
            _overlay_paths(wt_parent, landing_sha, run_files, runner)
            parent_out = drop_flaky(
                run_container_pytest(wt_parent, run_files, base_image, runner),
                FLAKY_TEST_SUBSTRINGS,
            )
            landing_out = drop_flaky(
                run_container_pytest(wt_landing, run_files, base_image, runner),
                FLAKY_TEST_SUBSTRINGS,
            )
            result = classify_ftp(parent_out, landing_out)
        finally:
            _remove_worktree(clone, wt_landing, runner)
    finally:
        _remove_worktree(clone, wt_parent, runner)

    return CommitFtp(
        commit=landing_sha,
        parent=parent_sha,
        ftp_tests=result.ftp_tests,
        behavioral=result.behavioral,
        feature_presence=result.feature_presence,
        type=result.type,
    )


Logger = Callable[[str], None]


def curate_rig(
    rig: str,
    landing_shas: Sequence[str],
    clone: Path,
    *,
    base_image: str = DEFAULT_BASE_IMAGE,
    runner: Runner = subprocess.run,
    worktree_root: Path = Path("/tmp"),
    log: Logger = print,
) -> list[CommitFtp]:
    """Curate every linked landing commit for one rig. Commits with no
    test-touching diff are skipped; commits whose tree is uncurate-able (a gold
    test path absent at the landing sha, a non-installable parent) are isolated as
    errored rather than aborting the whole rig -- a single corpus-invalid link must
    not discard the curated results of the other commits. The superset->subset
    shrink (skipped + errored) is logged so the filtering is visible (not a silent
    truncation)."""
    results: list[CommitFtp] = []
    skipped = 0
    errored = 0
    for sha in landing_shas:
        try:
            curated = curate_commit(
                rig,
                sha,
                clone,
                base_image=base_image,
                runner=runner,
                worktree_root=worktree_root,
            )
        except RuntimeError as exc:
            errored += 1
            log(f"{rig} {sha[:12]}: uncurate-able -- {exc}")
            continue
        if curated is None:
            skipped += 1
            log(f"{rig} {sha[:12]}: no test-touching files -- skipped")
            continue
        results.append(curated)
        log(
            f"{rig} {sha[:12]}: {len(curated.ftp_tests)} ftp "
            f"({len(curated.behavioral)} behavioral) [{curated.type}]"
        )
    log(
        f"{rig}: {len(landing_shas)} linked commits -> "
        f"{len(results)} test-touching ({skipped} skipped, {errored} errored)"
    )
    return results


def rig_report(rig: str, results: Sequence[CommitFtp]) -> dict[str, object]:
    """The per-rig ftp-oracle JSON payload."""
    total_ftp = sum(len(r.ftp_tests) for r in results)
    total_behavioral = sum(len(r.behavioral) for r in results)
    return {
        "rig": rig,
        "commits": [r.as_dict() for r in results],
        "summary": {
            "commits": len(results),
            "ftp_tests": total_ftp,
            "behavioral": total_behavioral,
        },
    }
