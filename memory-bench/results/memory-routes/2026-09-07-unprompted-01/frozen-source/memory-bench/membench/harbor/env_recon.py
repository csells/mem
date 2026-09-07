"""Approximate environment reconstruction for a held-out bead (mem-apg.3.1, D17).

The held-out corpus carries no ``repo``/``base_commit`` (0/76 beads -- see the data
audit), so a faithful checkout is impossible. What IS available: the rig name (which
maps to a local working clone) and the record's ``started_at`` timestamp. This module
reconstructs an APPROXIMATE environment from those two facts:

    rig -> local repo ; commit ~= `git rev-list -1 --before=<started_at> HEAD`

and bakes a snapshot of the repo at that commit into the task's ``environment/`` so
``harbor run`` builds an image with the code at ``/app``. This is deliberately
approximate (D17): the commit is the main-tip-before-timestamp, not the exact branch
state the original run saw (traces ran in worktrees off branch state), and the base
image's toolchain is a per-rig best-effort, not the original CI environment.

Why approximate is still useful: ``path_reached`` (the base-rate gate's denominator)
only needs the held file present at ``/app`` so the agent can navigate to it -- which a
timestamp-approximate checkout provides. Error *recurrence* additionally needs the
build/test toolchain, which is the residual faithfulness risk surfaced here, not hidden.
"""

import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from membench.spawn import Runner

# rig -> local working clone. HOST-SPECIFIC spike configuration (these are the rigs
# present in the held-out corpus that have a local repo on this machine). Injectable
# everywhere it is used; this default is the convenience, not a contract. Paths mirror
# the durable checkouts in the TypeScript `RIG_REPOS` (ingest/rig-repo-map.ts), the
# canonical source of truth -- a rig is added here once its checkout is confirmed on
# this host so the fail-to-pass curator (mem-bxhh.2) can resolve its landing commits.
DEFAULT_RIG_REPOS: Mapping[str, Path] = {
    "gascity": Path("/home/ds/gascity"),
    "gascity_dashboard": Path("/home/ds/gascity-dashboard"),
    "mem": Path("/home/ds/projects/mem"),
    "GEO": Path("/home/ds/projects/GEO"),
    "codeprobe": Path("/home/ds/projects/codeprobe"),
    "scix_experiments": Path("/home/ds/projects/scix_experiments"),
    "gpk": Path("/home/ds/gascity-packs"),
}

# rig -> Docker base image carrying the rig's build/test toolchain. Best-effort, not
# the original CI image (D17). A rig absent here falls back to DEFAULT_BASE_IMAGE, which
# is enough for path_reached but may not reproduce a compile/test failure.
DEFAULT_BASE_IMAGES: Mapping[str, str] = {
    "gascity": "golang:1.23-bookworm",
    "mem": "node:22-bookworm",
    "gascity_dashboard": "node:22-bookworm",
}
DEFAULT_BASE_IMAGE = "ubuntu:24.04"

_ARCHIVE_NAME = "repo.tar"


def resolve_base_commit(
    repo: Path, started_at: str, *, base_ref: str = "HEAD", runner: Runner = subprocess.run
) -> str:
    """The ``base_ref``'s last commit at or before ``started_at`` (the D6 LOO boundary).

    Approximate by construction: the tip-of-``base_ref``-before-timestamp, not the exact
    state the original (worktree) run saw. ``base_ref`` matters: the local ``HEAD`` may
    be an arbitrary stale branch (on this host gascity's HEAD is a months-old PR-check
    ref), so the integration branch (``origin/main``) is the principled base -- callers
    that know the rig pass it (see `reconstruct_env_for_record`). Raises if no commit
    precedes the timestamp -- inventing a fallback (e.g. the current tip) would silently
    reconstruct a LATER environment that may already contain the fix, destroying the
    recurrence signal."""
    completed = runner(
        ["git", "-C", str(repo), "rev-list", "-1", "--before", started_at, base_ref],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"git rev-list in {repo} failed (exit {completed.returncode}): "
            f"{completed.stderr.strip()}"
        )
    commit = completed.stdout.strip()
    if not commit:
        raise RuntimeError(
            f"no commit in {repo} at or before {started_at!r} -- cannot reconstruct an "
            "environment that predates the held-out work"
        )
    return commit


def write_repo_archive(
    repo: Path, commit: str, dest: Path, *, runner: Runner = subprocess.run
) -> None:
    """Snapshot ``repo`` at ``commit`` into a tar at ``dest`` via ``git archive``.

    A tar (not a full ``.git`` clone) keeps the build context small and gives the agent
    a clean tree with no history to mine for the fix."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    completed = runner(
        ["git", "-C", str(repo), "archive", "--format=tar", "-o", str(dest), commit],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"git archive {commit} in {repo} failed (exit {completed.returncode}): "
            f"{completed.stderr.strip()}"
        )


def render_dockerfile(base_image: str, *, install_steps: Sequence[str] = ()) -> str:
    """A Dockerfile that lands the archived repo at ``/app`` (the Harbor workdir).

    The archive is COPYed from the build context (the task's ``environment/`` dir) and
    extracted -- so the agent starts in the reconstructed tree. ``install_steps`` are
    appended as ``RUN`` layers AFTER the extract (so they run in the populated ``/app``);
    a cached base image (mem-bxhh.3.1) uses this to bake a rig's dependency closure into
    site-packages. Empty by default -- the env-reconstruction path stays a pure checkout."""
    lines = [
        f"FROM {base_image}\n",
        "WORKDIR /app\n",
        f"COPY {_ARCHIVE_NAME} /tmp/{_ARCHIVE_NAME}\n",
        f"RUN tar -xf /tmp/{_ARCHIVE_NAME} -C /app && rm /tmp/{_ARCHIVE_NAME}\n",
    ]
    lines.extend(f"RUN {step}\n" for step in install_steps)
    return "".join(lines)


def reconstruct_env(
    task_dir: Path,
    *,
    repo: Path,
    commit: str,
    base_image: str,
    runner: Runner = subprocess.run,
) -> Path:
    """Write ``environment/{Dockerfile,repo.tar}`` into ``task_dir``; return its env dir.

    The repo snapshot at ``commit`` plus a Dockerfile that extracts it to ``/app``. The
    archive lives in ``environment/`` because Harbor's Docker build context is that dir."""
    env_dir = task_dir / "environment"
    env_dir.mkdir(parents=True, exist_ok=True)
    write_repo_archive(repo, commit, env_dir / _ARCHIVE_NAME, runner=runner)
    (env_dir / "Dockerfile").write_text(render_dockerfile(base_image), encoding="utf-8")
    return env_dir


def reconstruct_env_for_record(
    task_dir: Path,
    record: Mapping[str, object],
    *,
    rig_repos: Mapping[str, Path] = DEFAULT_RIG_REPOS,
    base_images: Mapping[str, str] = DEFAULT_BASE_IMAGES,
    base_ref: str = "origin/main",
    runner: Runner = subprocess.run,
) -> Path:
    """Reconstruct a task's environment from a WorkRecord's rig + ``started_at``.

    Resolves the rig's local repo and the timestamp-approximate base commit (against
    ``base_ref`` -- the integration branch, NOT the possibly-stale local HEAD), then
    bakes the snapshot in. Raises (does not guess) when the rig has no local repo or the
    record lacks a ``started_at`` -- a wrong environment is worse than a loud failure."""
    rig = str(record["rig"])
    repo = rig_repos.get(rig)
    if repo is None:
        raise RuntimeError(
            f"no local repo mapped for rig {rig!r} -- cannot reconstruct its environment "
            f"(known rigs: {sorted(rig_repos)})"
        )
    # The LOO boundary is the record's own lifecycle.started (falls back to created,
    # earlier and so strictly leak-safe) -- the SAME boundary `validity.query_from_record`
    # enforces, so the reconstructed env and the query share one timestamp.
    lifecycle = cast(Mapping[str, Any], record.get("lifecycle") or {})
    started_at = lifecycle.get("started") or lifecycle.get("created")
    if not started_at:
        raise RuntimeError(
            f"record {record.get('work_id')!r} has no lifecycle.started/created -- cannot "
            "resolve a base commit"
        )
    commit = resolve_base_commit(repo, str(started_at), base_ref=base_ref, runner=runner)
    base_image = base_images.get(rig, DEFAULT_BASE_IMAGE)
    return reconstruct_env(task_dir, repo=repo, commit=commit, base_image=base_image, runner=runner)
