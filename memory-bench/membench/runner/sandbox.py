"""mem-rx11w — the neutral-sandbox seam for every paid ``claude -p`` cwd.

A cell's sandbox is minted to be NEUTRAL: native memory (or the arm's surfaced
``available_memory``) is meant to be the sole continuity channel, and
``headless_agent``'s cwd contract says so outright — the cwd "MUST be an isolated, neutral
sandbox, never a mem worktree", or the repo's ``CLAUDE.md`` / project memory "would both
fail the session and confound the none/ours/builtin memory variable".

Emptying the cwd does not establish that. Claude Code auto-loads ``CLAUDE.md`` by WALKING
UP the directory tree from cwd at launch, with NO tool call — so an ``--allowedTools``
clamp cannot close the channel, and neither can ``toolreq_builtin.wipe_cwd_contents``,
which iterates ``cwd.iterdir()`` and by construction never ascends. The sandbox is rooted
at the ambient ``TMPDIR`` (``tempfile`` resolves it), so the OPERATOR'S ENVIRONMENT decides
the whole ancestor chain: point ``TMPDIR`` at a workspace for disk space — routine — and
every "neutral" sandbox silently inherits whatever ``CLAUDE.md`` sits above it. No arm's
accounting can see that, because a scavenged pass is indistinguishable from an earned one:
the mechanism under test reads as WORKING when it did not. (``toolreq_builtin`` states the
builtin arm's form of that blind spot, where it publishes as a fabricated SEPARATES.)

So the guard is FAIL-CLOSED and refuses to spend, rather than recording the chain and
spending anyway. That choice is what keeps the sandbox's location OUT of the cache
identity: a run can only complete with an EMPTY ancestor set, so the auto-loaded context is
pinned to nothing by construction, and ``TMPDIR`` — which reaches no argv
(``invocation_fingerprint``), and which the scored artifact's cwd-relative path ignores —
cannot vary a measurement. An input that cannot vary needs no fingerprint, and hashing the
root PATH would be worse than idle: two CLEAN sweeps under different ``TMPDIR`` measure the
same thing, so it would force a false MISS and re-spend real money on a difference that
moves nothing. What the guard DOES invalidate is every cell measured BEFORE it existed —
those assert nothing about their ancestor chain and record no ``TMPDIR``, so they are
unauditable after the fact. That is ``BaseRunIdentity.protocol``'s job, which names this
exact case ("the engagement check or the sandbox firewall"), and each grid bumps its own
``EXECUTION_PROTOCOL`` for it.

ZFC: filesystem plumbing and a structural path check. No model call, no judgment.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

# What Claude Code auto-loads from a directory on its upward walk, and hence what makes an
# ancestor non-neutral. ``CLAUDE.md`` is the verified vector and the one the docs describe;
# ``CLAUDE.local.md`` is its documented per-developer variant; ``AGENTS.md`` is over-broad
# (the docs do not list it as auto-loaded) but is named by the builtin arm's own threat
# model and costs one stat to refuse — for a fail-closed guard, over-broad is the safe side.
#
# NOT here: ``.claude/``. An ancestor project ``.claude/`` carries settings and SessionStart
# hooks and is a real hazard, but the user config dir is literally ``~/.claude``, so
# including the name would refuse EVERY ``TMPDIR`` under a home directory — including clean
# ones — to defend a vector that is not this one (the user scope is cwd-INDEPENDENT, and the
# builtin arm already relocates it via ``CLAUDE_CONFIG_DIR``). It wants its own guard and
# its own reasoning about the ``$HOME`` boundary; mem-f819h.
AUTO_LOADED_CONTEXT_FILES: tuple[str, ...] = ("CLAUDE.md", "CLAUDE.local.md", "AGENTS.md")


class SandboxContaminationError(RuntimeError):
    """A paid sandbox's ancestor chain carries agent context the harness cannot account for.

    Raised rather than recorded: see this module's docstring for why refusing beats
    fingerprinting. A refused measurement is the cheap end of this failure — at construction
    nothing is spent at all, and after the establish leg the calls are made but NOT written,
    which still beats publishing a number whose provenance the harness cannot describe."""


class CorpusReachableError(SandboxContaminationError):
    """The corpus a paid leg is graded against is reachable from the leg's env or cwd tree.

    The graded values reach the agent through the prompt and nowhere else; a path INTO the
    corpus, one ``cat`` away, would let a leg read the answer it is being measured for reaching
    into memory for. Refused before anything is spent."""


def _under(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    return resolved == root or root in resolved.parents


def _reaches(path: Path, root: Path) -> bool:
    """Under the corpus, the corpus itself, or a directory ABOVE it — one ``ls`` away."""
    resolved = path.resolve()
    return _under(path, root) or resolved in root.parents


def assert_corpus_unreachable(*, env: Mapping[str, str], cwd: Path, corpus_root: Path) -> None:
    """Refuse a leg whose env or cwd tree puts the corpus one command away.

    ``env`` is the whole environment the child will see (the operator's, merged with the
    surface's). Every value is split on ``os.pathsep`` so a ``PATH``-shaped entry is checked
    like a bare path, and a RELATIVE segment is resolved against ``cwd`` — the leg's cwd, the
    directory the child will actually resolve it in — never against the harness process's
    own cwd (which would refuse on the operator's shell). An env value is refused when it
    names the corpus root or anything under it. An env value naming an ANCESTOR of the corpus
    is NOT refused: ``HOME`` and ``TMPDIR`` name an ancestor of every path on the machine, so
    that rule would refuse every leg, and the corpus's location is never disclosed to the
    agent — an ancestor in the env is a starting point for a search, not a path to the answer.

    ``cwd`` is refused if it is itself inside the corpus. Every entry under it is resolved and
    refused when it resolves INTO the corpus or to an ANCESTOR of it: a symlink is the reach
    this catches (a COPY of a file is not a path into the corpus), and unlike the env case a
    sandbox entry pointing above the corpus is a real reach — it sits in the one directory
    the agent is told to work in, and ``ls`` follows it straight down. Resolution sees through
    a symlinked corpus root the same way ``assert_neutral_ancestry`` sees through a symlinked
    ``TMPDIR``.

    mem-zfm0m item 7. Filesystem and string plumbing only: no judgment about what the values
    mean, only where they point."""
    root = corpus_root.resolve()
    for key in sorted(env):
        for segment in env[key].split(os.pathsep):
            if segment and _under(Path(cwd, segment), root):
                raise CorpusReachableError(
                    f"env {key}={env[key]!r} names a path inside the corpus {root}; the corpus "
                    f"reaches the agent through the prompt only. Refusing to spend."
                )
    if _under(cwd, root):
        raise CorpusReachableError(
            f"the leg's cwd {cwd} is inside the corpus {root}. Refusing to spend."
        )
    for entry in cwd.rglob("*"):
        if _reaches(entry, root):
            raise CorpusReachableError(
                f"{entry} in the leg's cwd tree resolves into or above the corpus {root}; a "
                f"task's files may be COPIED into a sandbox, never linked from the corpus. "
                f"Refusing to spend."
            )


def assert_neutral_ancestry(sandbox: Path) -> None:
    """Refuse ``sandbox`` if any directory ABOVE it carries auto-loaded agent context.

    Resolves first: ``tempfile`` hands back a path under whatever ``TMPDIR`` names, but the
    kernel's cwd is an inode, so a symlinked ``TMPDIR`` makes the LEXICAL parents clean while
    the child walks the REAL chain. A guard that skipped this would be green exactly when it
    is wrong.

    Walks to ``/`` INCLUSIVE. Claude Code's stopping boundary is undocumented, and this
    codebase has already learned (``BaseRunIdentity.cli_version``) not to encode an asserted
    CLI behavior it does not observe; the asymmetry decides it, since including ``/`` costs
    one stat and a refusal that is near-impossible to trigger, while excluding it wrongly
    costs a silently contaminated paid sweep. Checks ancestors ONLY — the sandbox itself is
    minted empty, and its contents are the cwd firewall's business, not this one's."""
    for ancestor in sandbox.resolve().parents:
        for name in AUTO_LOADED_CONTEXT_FILES:
            found = ancestor / name
            if found.exists():  # follows symlinks: a CLAUDE.md -> AGENTS.md link is context too
                raise SandboxContaminationError(
                    f"{found} sits above the sandbox {sandbox}, and Claude Code auto-loads it "
                    f"by walking up from the cwd at launch — with no tool call to clamp, so "
                    f"this sandbox is not neutral and its result could not be told apart from "
                    f"a real one. Refusing to spend. Set TMPDIR to a directory with no "
                    f"{', '.join(AUTO_LOADED_CONTEXT_FILES)} in any parent."
                )


@contextmanager
def paid_sandbox(prefix: str) -> Iterator[Path]:
    """A neutral cwd for a paid ``claude -p`` cell, guaranteed clean or not handed out.

    Yields the RESOLVED path: the same chain the guard checked and the kernel reports, so
    nothing downstream re-opens the symlink gap. Why ``TMPDIR`` is still honored, and why
    that costs the measurement nothing: see the module docstring."""
    with tempfile.TemporaryDirectory(prefix=prefix) as raw:
        sandbox = Path(raw).resolve()
        assert_neutral_ancestry(sandbox)
        yield sandbox
