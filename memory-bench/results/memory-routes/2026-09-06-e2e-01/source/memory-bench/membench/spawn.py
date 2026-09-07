"""The one spawn-and-diagnose choke point for RAISING subprocess sites.

Such a site needs the same four rungs — binary absent, spawn failed, timed out,
non-zero exit — in an order with a subclass trap in it (see ``run_checked``).
Every hand-rolled copy has to re-derive that order, and re-derivation is how it
goes wrong: route new raising spawns here instead.

``error`` is an exception FACTORY rather than a fixed type, which is what lets
one ladder serve callers with different error contracts: it unifies the ORDER
and COMPLETENESS of the rungs while each site keeps its own exception TYPE. Only
``what`` and ``not_found_hint`` are per-site.

A site whose contract is report-and-continue rather than raise
(``oracle/backends.py`` returns ``BackendResult(available=False)`` — a backend
that drops out is reported, not fatal) is NOT a caller: a factory unifies which
exception is raised, not raise-vs-return.
"""

from __future__ import annotations

import contextlib
import os
import re
import signal
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

# A subprocess.run-shaped callable, injectable so tests never spawn a real
# process. The canonical definition -- import it from here rather than restating it.
Runner = Callable[..., "subprocess.CompletedProcess[str]"]

# `sk-` and not `sk-ant-`: the callers carry more than the Anthropic shapes. The paid grid
# hands every child `sk-ant-oat01-...` (OAuth) or `sk-ant-api03-...` (API key), but
# `openwiki_system._openwiki_env` reads OPENAI_COMPATIBLE_API_KEY straight off the operator's
# environment and hands it to a `run_checked` child too -- and an OpenAI key is `sk-proj-...`,
# which `sk-ant-` does not match. Verified end-to-end by review: a stub CLI failing with that
# key on stderr surfaced it in full.
#
# The `\b` is not decoration. `sk-` is a substring of ordinary words this codebase's own
# diagnostics are full of -- taSK-types, diSK-, riSK-, briSK- -- and without the boundary the
# redaction eats them: `no task-types.json found` came out as `no ta<redacted-credential>.json`,
# swallowing the exact filename the operator needed. `--task-types` is a real flag here and
# `task-types.json` a real artifact path, so that was live, not hypothetical. A word boundary
# plus a real shared vendor prefix -- still no entropy scoring, no KEY=VALUE sniffing.
#
# The boundary is a KNOWN-IMPERFECT axis, measured in both directions (mem-wsxpx owns the fix).
# `\b` is a \w-to-non-\w transition, so it MISSES a token glued onto a word char -- including one
# behind an ANSI colour escape, since `\x1b[31m` ends in `m` (reproduced end-to-end: the whole
# credential reached the raised exception). And it still EATS `sk-SK`, the Slovak locale. No `\b`
# variant separates `sk-SK` from `sk-ant-...`; only the vendor shape does. Kept anyway because the
# baseline redacted NOTHING -- this is an incomplete improvement, not a hole it opened. Every
# delimited form (`=`, space, quote, `-`, `:`) redacts today.
#
# It is NOT a general secret scanner. The env is inherited wholesale (`{**os.environ,
# **self.env}`), so a differently-shaped vendor token an operator has exported can still be
# echoed by a child that chooses to. `sgp_` (Sourcegraph) is NOT in this regex, deliberately:
# `oracle/backends.py` used to echo one raw (mem-zls5s) and now redacts it by VALUE
# (`redact_secret` below, where the value-vs-shape rationale lives), which needs no shape
# guess. Bounding the remaining env-surface (other os.environ tokens a child might echo,
# which no caller holds by name) is the env-surface question (mem-jwp3c), still not a
# regex's job. mem never writes a token to these channels itself; this fires when a CLI
# echoes its OWN auth back.
_CREDENTIAL = re.compile(r"\bsk-[A-Za-z0-9_-]+")
_REDACTED = "<redacted-credential>"

# The floor below which `redact_secret` refuses to redact a known value. A real access
# token is far longer; the floor exists only so a misconfigured or test SRC_ACCESS_TOKEN
# like "ab" cannot turn a literal str.replace into a substring shredder ("grab" -> "gr<...>").
# Below it we accept the theoretical miss of an implausibly-short secret to protect the
# diagnosis -- the same both-directions bar the `\b` word boundary holds for the shape pass.
_MIN_REDACTABLE_SECRET_LEN = 8

# How long ``run_in_session`` waits for the pipes to close after it has SIGKILLed the child's
# group. A killed group closes its pipe ends at once, so anything still holding them past this
# bound is a survivor (a kill that did nothing, a process the signal could not reach) and the
# drain reports it rather than blocking the rig on it.
DRAIN_TIMEOUT_S = 5.0


def run_in_session(
    argv: Sequence[str],
    *,
    capture_output: bool,
    text: bool,
    check: bool,
    timeout: float | None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """``subprocess.run`` for a child that may have children of its own.

    ``subprocess.run`` kills the process it spawned on timeout and nothing else: a ``claude -p``
    that outlives its bound leaves its own tool subprocesses running against a sandbox the next
    leg is about to reuse. The child is started as a SESSION LEADER (``start_new_session``), so
    the timeout can signal its whole process group, and the partial stdout is drained after the
    kill and carried on the ``TimeoutExpired`` DECODED, so a scorer reads it the way it reads a
    complete stream.

    The keyword shape is ``run_checked``'s spawn shape and nothing wider: ``capture_output=True``,
    ``text=True``, ``check=False`` are accepted so this drops in as its ``runner``, and any other
    value is refused rather than silently served a different contract.
    """
    if not capture_output:
        raise ValueError("run_in_session serves run_checked's shape: capture_output=True only")
    if not text:
        raise ValueError("run_in_session serves run_checked's shape: text=True only")
    if check:
        raise ValueError(
            "run_in_session serves run_checked's shape: check=False only (the ladder diagnoses a "
            "non-zero exit itself)"
        )
    proc = subprocess.Popen(
        list(argv),
        stdin=subprocess.PIPE if input is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=env,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(input=input, timeout=timeout)
    except subprocess.TimeoutExpired as first:
        _kill_group(proc)
        # The second communicate returns everything buffered before the bound plus whatever the
        # kill flushed. It is bounded too: a pipe still open after the group was SIGKILLed is
        # held by a survivor, and an unbounded drain would block the rig on it for as long as
        # it lives. ``communicate`` only raises ``TimeoutExpired`` from a bounded call, and it
        # raises it with the bound it was given (not a remaining slice), so ``first.timeout`` IS
        # the caller's ``timeout`` and is the one value here that is typed as a bound.
        try:
            stdout, stderr = proc.communicate(timeout=DRAIN_TIMEOUT_S)
        except subprocess.TimeoutExpired as drain:
            reaped = _abandon(proc)
            raise RuntimeError(
                f"process group {proc.pid} survived SIGKILL: its pipes were still held open "
                f"{DRAIN_TIMEOUT_S}s after the kill, so a child of {argv[0]!r} is still "
                "running and the partial output could not be drained"
                + (
                    ""
                    if reaped
                    else (
                        f"; the leader pid {proc.pid} had not exited {DRAIN_TIMEOUT_S}s after "
                        "its own SIGKILL either, so it is left unreaped (a zombie is leaked "
                        "rather than waited on unbounded)"
                    )
                )
            ) from drain
        raise subprocess.TimeoutExpired(
            proc.args, first.timeout, output=stdout, stderr=stderr
        ) from None
    except BaseException:
        _kill_group(proc)
        proc.wait()
        raise
    return subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)


def _abandon(proc: subprocess.Popen[str]) -> bool:
    """Give up on a child whose group outlived its kill: close our pipe ends first so nothing
    waits on the survivor again, SIGKILL the child itself, and wait for the leader for at most
    ``DRAIN_TIMEOUT_S``. Returns whether the leader was reaped in that bound; a leader that is
    not (a kernel-held exit, a stopped process) is LEAKED as a zombie rather than waited on
    unbounded (review G4), and the caller says so."""
    for stream in (proc.stdin, proc.stdout, proc.stderr):
        if stream is not None:
            stream.close()
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    try:
        proc.wait(timeout=DRAIN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return False
    return True


def _kill_group(proc: subprocess.Popen[str]) -> None:
    """SIGKILL the session ``proc`` leads.

    A group already gone is the outcome wanted, not an error. A group that does not exist while
    ``proc`` is still running means ``proc`` was never made a session leader: the child would
    outlive its bound and the drain behind this call would block on it, so that is refused
    loudly rather than waited out."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError as exc:
        if proc.poll() is None:
            raise RuntimeError(
                f"pid {proc.pid} is still running but leads no process group; it was not spawned "
                "as a session leader, so its children cannot be killed with it"
            ) from exc


def timeout_partial_stdout(exc: subprocess.TimeoutExpired) -> str:
    """What the child wrote before the bound fired, as text.

    ``subprocess.run`` hands it over as BYTES even in text mode (it reads the pipes raw when it
    kills); ``run_in_session`` hands it over decoded; a child that wrote nothing hands ``None``.
    All three are the same partial stream to the scorer."""
    partial = exc.stdout
    if partial is None:
        return ""
    if isinstance(partial, bytes):
        return partial.decode("utf-8", errors="replace")
    return str(partial)


# The window the child's own output gets in the diagnosis. HEAD AND TAIL, not head alone:
# `claude -p --output-format stream-json` puts a whole event stream on stdout and the
# operative line lands at the end, while a usage error lands at the start. A head-only
# window would drop exactly the line the operator needs on half the callers.
_HEAD_CHARS = 2_000
_TAIL_CHARS = 2_000


def run_checked(
    argv: Sequence[str],
    *,
    what: str,
    not_found_hint: str,
    timeout_s: float | None = None,
    error: Callable[[str], BaseException] = RuntimeError,
    runner: Runner = subprocess.run,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Spawn ``argv`` and return the completed process, or raise ``error(...)``
    with the root cause attached.

    ``check=False``: a non-zero exit is diagnosed here with the command's own
    stderr rather than as a bare ``CalledProcessError``.

    ``what`` names the command in prose ("harbor run", "claude -p for the
    comparative judge"); ``not_found_hint`` names the fix for a missing binary.
    ``timeout_s`` of None is subprocess's own unbounded sentinel — only pass it
    where no bound is meaningful. ``cwd``/``env``/``input`` are explicit rather
    than ``**kwargs`` so mypy --strict keeps checking the call; ``cwd`` takes
    ``str`` as well as ``Path`` because subprocess does and callers hold it both
    ways.

    The timeout message quotes ``exc.timeout`` rather than ``timeout_s`` so it
    stays accurate where the caller's bound is None.
    """
    try:
        completed = runner(
            list(argv),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
            cwd=cwd,
            env=env,
            input=input,
        )
    except FileNotFoundError as exc:
        # Ordered before OSError -- FileNotFoundError is a subclass, so the
        # reverse order would make this specific wording dead code.
        raise error(f"{argv[0]!r} not found — {not_found_hint}") from exc
    except OSError as exc:
        # The rest of the family -- including EACCES on the cwd, which fails the
        # spawn without the binary itself being at fault.
        raise error(f"could not spawn {what}: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise error(f"{what} did not finish within {exc.timeout}s") from exc
    if completed.returncode != 0:
        # `.strip() or .strip()`, not `(a or b).strip()`: a whitespace-only stderr
        # must still fall through to stdout, or the diagnosis loses the one line
        # that says what went wrong.
        #
        # Select FIRST, then sanitise: redacting or truncating before this line could
        # blank a real stderr into whitespace and silently move the fallback above --
        # the selection is the pinned rung, so nothing may run ahead of it.
        detail = (completed.stderr or "").strip() or (completed.stdout or "").strip()
        raise with_child(
            error(f"{what} failed (exit {completed.returncode}): {sanitised_child_output(detail)}"),
            completed,
        )
    return completed


# The child a non-zero exit came from, carried ON the exception. The message is redacted and
# truncated by design, so a caller that needs to CLASSIFY the failure (a quota refusal is not a
# broken rig; one halts the sweep cleanly, the other is a leg to skip) cannot read the message and
# must not: that is prose matching on a string this module deliberately mangles. The structured
# child travels instead, and the classification reads a field.
_CHILD_ATTR = "spawn_child"


def with_child(exc: BaseException, completed: subprocess.CompletedProcess[str]) -> BaseException:
    """Attach ``completed`` to ``exc`` and return it, so the raise site stays one expression."""
    setattr(exc, _CHILD_ATTR, completed)
    return exc


def child_of(exc: BaseException) -> subprocess.CompletedProcess[str] | None:
    """The child process behind a ``run_checked`` non-zero diagnosis, or ``None``.

    ``None`` for every other failure shape (missing binary, OSError, timeout) — those never had a
    completed child — and for exceptions raised anywhere else. A caller that gets ``None`` has
    learned that it cannot classify structurally, which is the honest answer, not a default."""
    child = getattr(exc, _CHILD_ATTR, None)
    return child if isinstance(child, subprocess.CompletedProcess) else None


def redact_credentials(detail: str) -> str:
    """Replace every credential-shaped run in ``detail``.

    PUBLIC because a caller that imposes its own bound still needs the redaction half
    (``mem_cli.run_mem_json`` slices to 200 chars of its own). Redact BEFORE any slice:
    cutting first leaves a live prefix of the token on the surviving side."""
    return _CREDENTIAL.sub(_REDACTED, detail)


def redact_secret(detail: str, secret: str) -> str:
    """Replace an EXACT known secret value in ``detail`` -- the value-based complement
    to the shape-based ``redact_credentials``.

    For a caller that HOLDS the credential it handed a child (``oracle/backends.py``'s
    SourcegraphResolver passes ``SRC_ACCESS_TOKEN`` via ``env`` and is report-and-continue,
    so it cannot lean on ``run_checked``'s ladder). Redacting the value needs no shape guess,
    so it covers what the regex misses -- a Sourcegraph token has been ``sgp_...`` and a bare
    40-hex string across versions, and only the value catches both.

    ``secret`` is STRIPPED before matching: an env var sourced as ``$(cat token)`` or from
    a k8s/Vault secret file routinely carries a trailing newline, and the child trims it
    before echoing, so matching the raw padded value would find nothing and leak the token
    in full. Stripping is safe both ways -- if the child DID echo the padded form, the bare
    substring still matches. This is EXACT-LITERAL matching, though: a child that echoes a
    transformed rendering (URL-encoded, or the token broken across a line) is not caught --
    the value's honest limit, the mem-jwp3c env-surface question, not this helper's job.

    A short or empty ``secret`` is left in place: ``str.replace('', x)`` injects ``x``
    between every character, and redacting a 2-char value would shred ordinary words
    (``grab`` -> ``gr<redacted>``). See ``_MIN_REDACTABLE_SECRET_LEN``."""
    secret = secret.strip()
    if len(secret) < _MIN_REDACTABLE_SECRET_LEN:
        return detail
    return detail.replace(secret, _REDACTED)


def sanitised_child_output(detail: str) -> str:
    """The child's own output, made fit for the log this diagnosis ends up in.

    PUBLIC, because ``run_checked``'s own non-zero arm was never the only site that builds
    a message out of child output: callers build their own text from a SUCCEEDING child too
    (``resolve_cli_version`` on an unrecognised banner, ``run_mem_json`` on a non-envelope
    stdout), and those messages reach the same printed SWEEP HALT. A choke point that only
    covers the raise-path is not a choke point -- it is the majority case with a name.

    It is NOT yet the choke point for that whole class, so this stops short of saying every
    such site "must" route through it -- that would describe a rule the repo does not follow.
    Five judge sites still slice an exit-0 reply into an exception raw, on a path whose env
    preserves CLAUDE_CODE_OAUTH_TOKEN verbatim (mem-rcm73 names them). Outside this change.

    Both properties live here rather than at the callers, because each of them would
    otherwise have to re-derive both: the output is redacted, and it is bounded. Order is
    fixed -- redact before truncating, so a token straddling the cut cannot survive as a
    fragment on either side of it."""
    detail = redact_credentials(detail)
    if len(detail) <= _HEAD_CHARS + _TAIL_CHARS:
        return detail
    dropped = len(detail) - _HEAD_CHARS - _TAIL_CHARS
    return f"{detail[:_HEAD_CHARS]}\n... <{dropped} chars truncated> ...\n{detail[-_TAIL_CHARS:]}"
