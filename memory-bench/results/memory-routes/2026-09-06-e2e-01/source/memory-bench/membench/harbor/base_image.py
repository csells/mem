"""harbor/base_image -- build a cached, dependency-baked base image (mem-bxhh.3.1).

Codeprobe graded/curation runs re-run ``pip install -e . pytest`` on every leg
(ftp_curate ``_container_pytest``); cold, that resolves and builds the whole
dependency closure each time. This builds a ``codeprobe-base`` image once with
that closure baked into the image's ``/usr/local/lib`` site-packages. The image's
deps survive a later ``-v <worktree>:/app`` mount (different path), so the runtime
``pip install -e . pytest`` finds them satisfied -- no downloads -- and does only
the cheap editable re-link for that commit's tree.

This is NOT a Docker build-layer cache trick: the win is deps physically present
in the image filesystem at run time. And it is OPT-IN -- callers pass the tag via
``--base-image``; the default stays the self-bootstrapping public
``python:3.11-bookworm`` so a fresh checkout / CI never fails on a missing local
image.

Known limitation (pilot scope): the closure is baked at one representative commit.
A later commit that adds a dependency self-heals via the network at runtime (the
runtime install is NOT ``--no-deps``), just slower for that leg -- it never
silently runs without the new dep.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from membench.harbor.env_recon import render_dockerfile, write_repo_archive
from membench.spawn import Runner

_log = logging.getLogger(__name__)

# The opt-in codeprobe cached image and the steps that bake its dep closure. Kept
# as named constants so callers (curate-ftp --base-image, the grid materializer)
# reference one source of truth rather than restating the tag/steps.
CODEPROBE_CACHED_IMAGE = "codeprobe-base:py3.11"
CODEPROBE_BASE_IMAGE = "python:3.11-bookworm"
CODEPROBE_INSTALL_STEPS: tuple[str, ...] = ("pip install -e . pytest -q",)


def _context_dirname(tag: str) -> str:
    """A filesystem-safe context dir name from an image tag (``a/b:c`` -> ``a-b-c``).

    Every character outside ``[A-Za-z0-9._-]`` collapses to ``-`` (so spaces, ``/``,
    ``:`` etc. never reach the path); the constant ``base-image-`` prefix keeps the
    result a single component even for a pathological tag."""
    safe = "".join(c if (c.isalnum() or c in "._-") else "-" for c in tag)
    return f"base-image-{safe}"


def build_base_image(
    repo: Path,
    commit: str,
    tag: str,
    *,
    base_image: str,
    install_steps: Sequence[str],
    context_root: Path = Path("/tmp"),
    runner: Runner = subprocess.run,
) -> str:
    """Build and tag a dependency-baked image from ``repo`` at ``commit``.

    Writes a throwaway build context (``Dockerfile`` + ``repo.tar``), runs
    ``docker build -t <tag>``, and returns ``tag``. The context is always removed,
    even on failure. A non-zero ``docker build`` raises rather than returning a
    half-built tag."""
    context = context_root / _context_dirname(tag)
    if context.exists():
        _log.warning("build_base_image: removing stale build context %s", context)
        shutil.rmtree(context)
    context.mkdir(parents=True)
    try:
        write_repo_archive(repo, commit, context / "repo.tar", runner=runner)
        (context / "Dockerfile").write_text(
            render_dockerfile(base_image, install_steps=install_steps), encoding="utf-8"
        )
        completed = runner(
            ["docker", "build", "-t", tag, str(context)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"docker build -t {tag} failed (exit {completed.returncode}): "
                f"{completed.stderr.strip()}"
            )
    finally:
        shutil.rmtree(context, ignore_errors=True)
    return tag


def build_codeprobe_base_image(
    repo: Path,
    commit: str,
    *,
    context_root: Path = Path("/tmp"),
    runner: Runner = subprocess.run,
) -> str:
    """Build ``CODEPROBE_CACHED_IMAGE`` from the codeprobe checkout at ``commit`` --
    the opt-in fast image for curation/grid runs."""
    return build_base_image(
        repo,
        commit,
        CODEPROBE_CACHED_IMAGE,
        base_image=CODEPROBE_BASE_IMAGE,
        install_steps=CODEPROBE_INSTALL_STEPS,
        context_root=context_root,
        runner=runner,
    )
