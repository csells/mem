"""HeadlessClaudeAgent — a real `claude -p` agent satisfying the runner Agent protocol.

The §4.4 action-impact run (mem-lvp.19) needs REAL divergent agent trajectories the
§12.6 judge can compare. The lvp.8 fixtures are not Docker rigs, so the Harbor
container path does not apply and `ScriptedAgent` produces no real tool-call stream.
This agent runs a `SequenceStep.user_request` — with the per-arm memory the harness
surfaced (`available_memory`, the none/ours/builtin payload) — through headless
``claude -p --output-format stream-json`` on the OAuth subscription (FREE), and keeps
the raw stream so `bbon.extract.steps_from_stream` can derive the `AttemptStep`
trajectory the harness scores.

It conforms to `runner.agent.Agent`, so it can also replace `ScriptedAgent` in the
conditions runner for a real run. The structured fields (tool_calls, tokens) are
parsed from the same stream; `raw_stream` carries it verbatim. ``check_results`` and
``writes_performed`` are left empty — a real agent does not self-grade its outcome
checks or declare a write policy here; those are scored/decided externally (an honest
absence, not a stub).

**Infra rule.** Heavy execution MUST be wrapped in ``scix-batch`` by the CALLER
(transient cgroup + RAM ceiling) so a runaway agent cannot OOM-kill the
supervisor/mayor. This module is the in-process driver; the scix-batch wrapper is the
entrypoint's responsibility (see ``scripts/smoke_realrun_trajectory.py``).

**MCP boot hang.** Headless ``claude -p`` boots project MCP servers at startup and
hangs the batch; ``--strict-mcp-config`` (default on here) prevents it — ``allowedTools``
forbids *calling* MCP tools but does not stop them *booting*.

ZFC: pure plumbing — prompt assembly, subprocess IO, stream parsing. The agent's
behavior IS the model's; no semantic judgment lives here.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import MISSING, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, NoReturn

from membench.armcompare import _iter_tool_result_blocks, _iter_tool_use_blocks
from membench.runner.agent import AgentStepResult
from membench.runtime import StepContext
from membench.schemas.sequence import SequenceStep
from membench.schemas.trace import ToolCall, TraceMessage
from membench.spawn import Runner, run_checked, sanitised_child_output

# A real agent step (multi-turn tool use) can take minutes; a bound this high means a
# wedged CLI, not slow inference — surfaced as an error, never an indefinite hang.
DEFAULT_TIMEOUT_S = 600.0

ENV_MODEL = "MEMBENCH_AGENT_MODEL"

# The credential a real `claude -p` authenticates with. Here beside ENV_MODEL rather than in each
# driver because a driver both READS it off `os.environ` (to refuse an unauthorized spend) and
# PRINTS it (the `env {ENV_OAUTH}=...` go-command a human copies). A per-driver copy makes those
# two strings agree only by coincidence, so a rename leaves a driver printing a command that does
# not arm the gate it tells you to arm.
ENV_OAUTH = "CLAUDE_CODE_OAUTH_TOKEN"

# The metered-API credential a paid run must NOT carry. Claude Code prefers it over the OAuth token,
# so an operator with it exported (a common dev-shell leftover) reroutes every `claude -p` child off
# the subscription onto the billed API: `run_step` builds the child env as `{**os.environ, ...}`, so
# the key flows straight through. That both spends real money and INVALIDATES the run: it is no
# longer the OAuth configuration the experiment claims to measure, and the env is invisible to the
# cache identity, so the mislabel is silent (harbor keeps this unset for the same reason, per
# harbor_exec.py's D16 note). Held here beside ENV_OAUTH so the paid drivers refuse on one name,
# never a per-driver copy. NOTE (mem-9bh93): this is the one var D16 names; ANTHROPIC_BASE_URL /
# *_AUTH_TOKEN / USE_BEDROCK / USE_VERTEX reroute off OAuth too; broader gate tracked as mem-sfkib.
ENV_API_KEY = "ANTHROPIC_API_KEY"

# `claude --version` prints and exits — a bound this high means a wedged CLI, not a slow one.
# Its own constant, not DEFAULT_TIMEOUT_S: that bound sizes a multi-turn agent step (minutes of
# inference), and reusing it here would let a wedged probe stall a paid sweep for ten minutes
# before saying the one thing it had to say.
VERSION_TIMEOUT_S = 30.0

# What a version IS, for the purpose of naming an instrument: a dotted-numeric token, plus whatever
# suffix the CLI hangs off it (`-rc.1`, `+build.5`, both). Tolerant about the SHAPE — nothing reads
# this field, it only has to differ between binaries, so a suffix grammar would buy a halt on
# `2.1.210_beta` and nothing else. Strict about it BEING one: taking a whitespace token unchecked
# would store "Error:" or "unknown" as the binary a cell was measured on, and a later resume would
# match against it.
_VERSION_TOKEN = re.compile(r"\d+(?:\.\d+)+\S*")


def resolve_model(model: str) -> str:
    """The model a run actually executes under: an explicit pin, else ``MEMBENCH_AGENT_MODEL``,
    else "" meaning the CLI's own default (which this codebase never pins and cannot see).

    THE one rule, called from both the agent that runs under it and the caches that key on it.
    A second copy of this expression is the resume-cache defect family in its purest form: the
    cache would hash a MODEL of the executed input, and any change here — a new fallback, a
    second env var — would leave that copy computing the old rule, so two runs on DIFFERENT
    models hash identically and a resumed paid sweep serves one model's numbers as the other's.
    """
    return model or os.environ.get(ENV_MODEL, "")


def a_paid_run_needs_a_model(model: str, *, dry_run: bool) -> bool:
    """Whether a spend must be REFUSED for naming no model — the ONE place this rule lives, so the
    paid drivers all defer to it rather than hand-copy ``not dry_run and not resolve_model(...)``.

    A paid run whose ``resolve_model`` is empty executes under the CLI's own default, which no cache
    identity records, so a resume across a model change would serve one model's numbers as another's
    (mem-bzv2p; ``resume_cache.BaseRunIdentity._a_paid_run_names_the_model_it_executed_under`` is
    the schema backstop). A dry run spawns nothing and may leave the model to the CLI."""
    return not dry_run and not resolve_model(model)


def a_paid_run_carries_the_metered_api_key(*, dry_run: bool) -> bool:
    """Whether a spend must be REFUSED for a set ``ANTHROPIC_API_KEY``: the ONE place this rule
    lives, so the three paid entrypoints defer to it rather than hand-copy
    ``not dry_run and os.environ.get(ENV_API_KEY)`` (the same per-driver drift the sibling above is
    built to avoid; unlike the OAuth-token gate, this refusal is byte-identical across all three, so
    the whole gate centralizes, not just the message).

    A set key reroutes every ``claude -p`` child off OAuth onto the metered API (``ENV_API_KEY``):
    real money, and a measurement that is no longer the OAuth config it claims. An empty-string key
    is treated as UNSET (bare truthiness), matching how the OAuth-token gate reads ``ENV_OAUTH`` and
    how the CLI itself treats an empty key. A dry run spawns nothing, so it may carry any env."""
    return not dry_run and bool(os.environ.get(ENV_API_KEY))


# The refusal a paid grid prints when ``a_paid_run_needs_a_model`` fires — held here beside the rule
# so the grid drivers defer to one string rather than hand-copy it (mem-bzv2p). The probe keeps its
# own shorter variant: it names no cache identity to serve because it caches nothing.
REFUSE_UNPINNED_MODEL = (
    "REFUSING to spend: no model named. An unpinned paid run executes under the CLI's own\n"
    '  default, which this benchmark never records — its cache identity would key on "" and\n'
    "  serve one model's numbers as another's on a resume across a model change.\n"
    "  Pass --model <id>, or set MEMBENCH_AGENT_MODEL, then re-run (or --dry-run for free)."
)

# The refusal a paid path prints when ``ENV_API_KEY`` is set — held here beside ENV_API_KEY and the
# model refusal so every paid entrypoint refuses on one string, never a per-driver copy (mem-9bh93).
REFUSE_API_KEY_SET = (
    "REFUSING to spend: ANTHROPIC_API_KEY is set. Claude Code would authenticate with the metered\n"
    "  API instead of the OAuth subscription, so the run would bill real money AND stop being the\n"
    "  OAuth configuration this benchmark measures, a swap that leaves no trace in the results.\n"
    "  `unset ANTHROPIC_API_KEY` (or run under `env -u ANTHROPIC_API_KEY`), then re-run\n"
    "  (or --dry-run for free)."
)


@dataclass(frozen=True)
class CellCalls:
    """The ONE cycle of ``claude -p`` invocations a single ``(arm, channel)`` cell makes.

    The unit BOTH halves of a paid grid's cache identity are built from: the grid renders the cycle
    its plan WILL send (a grid's ``planned_calls``, which ``resume_cache.CachePlan.lookup`` hashes
    into ``invocation_fingerprint``), the arm returns the cycle it DID send (recorded off the CLI
    seam by ``RecordingRunner``, never modelled), and ``resume_cache.run_cached_corpus`` refuses to
    publish a measurement whose sent cycles do not hash to the identity it was measured under. That
    is what makes the fingerprint the executed input rather than a hand-written model of it, one
    field short.

    An ARGV, not a prompt: the prompt is only the third element of the command line the agent
    actually spawns (``HeadlessClaudeAgent.argv_for``), and the flags around it move results too —
    ``resume_cache.BaseRunIdentity.invocation_fingerprint`` is where hashing the WHOLE line rather
    than just the prompt is argued.

    ``calls`` is ORDERED and stays that way: a cell's legs share a cwd and a config dir and run in
    sequence, so their order IS a measured input (see ``resume_cache.invocation_digest``)."""

    arm: str
    channel: str
    calls: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Leg:
    """One ``claude -p`` call a cell makes: the step it runs, the memory it surfaces to run it, and
    the label its ``StepContext`` carries.

    A cell's legs are the unit both halves of the identity are built from — ``cell_agent`` renders
    them into the plan (``render_cell_calls``) and the arm executes them — so a cell with one leg
    (the none/oracle/ours grid's goal call) and a cell with two (the builtin arm's establish + goal)
    say so in ONE vocabulary rather than each inventing its own.

    ``step`` (a non-frozen pydantic model) and ``memory`` (a plain dict) are ``hash=False``: both
    are unhashable at runtime, so a frozen dataclass's auto-generated ``__hash__`` over every field
    would raise the moment a ``Leg`` were put in a set or used as a key. Value ``__eq__`` still
    spans all three fields — this mirrors ``HeadlessClaudeAgent.env`` below."""

    name: str
    step: SequenceStep = field(hash=False)
    memory: Mapping[str, str] = field(hash=False)


@dataclass(eq=False)
class RecordingRunner:
    """A ``Runner`` that records the argv of every ``claude -p`` it spawns, then delegates.

    THE SEAM the cache identity is checked against — and it is the wire itself, not a report of the
    wire. A record taken from what an arm *says* it sent (a ``prompt`` field on the step result, a
    list the arm appends to as it goes) is one an author has to remember to update: add a leg to the
    arm, forget both to declare it in the plan and to record it — ONE omission, two symptoms, and by
    far the likeliest edit — and the sent record still equals the plan, so nothing fires. The runner
    sees the call whether or not anyone declared it — PROVIDED the executing agent was built with a
    recorder. ``cell_agent`` makes that non-optional: ``runner`` has no default, so an agent that
    executes a leg without being handed a recorder cannot be built by omission (the reflex that
    would otherwise reopen this hole one construction site over). The render-only path passes an
    explicit non-executing runner instead.

    It keeps two records per spawn, aligned by index: the ``calls`` argv (what went OUT, checked
    against the plan's ``invocation_fingerprint``) and the ``streams`` stdout (what came BACK). The
    stream is the ARTIFACT the write boundary checks the pinned CLI version against — each ``claude
    -p`` prints a ``type=system``/``subtype=init`` event carrying the version the binary that ran it
    actually was (``stream_cli_version``), so a cell's OWN stream catches a CLI upgraded mid-sweep
    that the once-per-sweep ``resolve_cli_version`` pre-flight claim cannot (mem-z32zu). Captured
    here for the same reason the argv is: the runner is the wire, not a report of the wire.

    ``eq=False`` keeps the default identity ``__hash__``, so an instance stays usable as the
    ``runner`` field of the frozen ``HeadlessClaudeAgent``."""

    inner: Runner
    calls: list[list[str]] = field(default_factory=list)
    streams: list[str] = field(default_factory=list)

    def __call__(self, argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append([str(arg) for arg in argv])
        stream = ""
        try:
            completed = self.inner(argv, **kwargs)
            stream = completed.stdout or ""
            return completed
        finally:
            # Append in a ``finally``, so ``len(streams) == len(calls)`` holds by CONSTRUCTION even
            # when ``inner`` raises (a timeout, a missing CLI) — the same structural stance
            # ``calls`` gets, not caller discipline. A raised spawn contributes an EMPTY stream
            # (unverified, like any stream with no init event), so a leg that errored cannot leave a
            # later leg's stream indexed under it, and no executed leg escapes the write boundary's
            # version check by a shortened ``streams`` list (the shape a future per-leg-retry arm
            # would create).
            self.streams.append(stream)


class HeadlessAgentError(RuntimeError):
    """A headless agent invocation failed unrecoverably (CLI missing, timeout, or a
    non-zero exit). Surfaced loudly — a failed run is not a silent empty trajectory."""


def resolve_cli_version(runner: Runner = subprocess.run) -> str:
    """The version of the claude binary installed AT THE MOMENT THIS IS CALLED — read off the
    binary itself (``claude --version`` -> ``2.1.210 (Claude Code)`` -> ``2.1.210``), never
    modelled.

    The mirror of ``resolve_model``, one level down: that rule names the model a run points AT,
    this one names the INSTRUMENT that points. Why a paid identity keys on the result, and the
    mid-sweep residue this does NOT close (mem-z32zu), are argued once where the field lives —
    ``resume_cache.BaseRunIdentity.cli_version``.

    FREE, and that is what makes it affordable at the top of every paid run: ``--version`` prints
    and exits — no agent turn, no token, no account.

    Raises ``HeadlessAgentError`` when the instrument cannot be identified — missing CLI, a
    non-zero exit, a hang, or output that carries no version token. A paid run that cannot name
    what it is measuring on must not spend.

    ``runner`` defaults to a real spawn, unlike ``HeadlessClaudeAgent.runner``, and the asymmetry
    is deliberate: that seam decides whether a MEASUREMENT is recorded, simulated or untracked, so
    "real and unrecorded" must not be what you get by omission. This spawns no agent and measures
    nothing — there is only one honest answer to "which binary is installed", and the parameter
    exists so tests can drive the parse path without one."""
    completed = run_checked(
        ["claude", "--version"],
        what="claude --version",
        not_found_hint="a paid run cannot name the binary it would measure on",
        timeout_s=VERSION_TIMEOUT_S,
        error=HeadlessAgentError,
        runner=runner,
    )
    # ONE line, and the version is its first token — the shape `claude --version` prints
    # ("2.1.210 (Claude Code)"). Anchored to that rather than scanning the output for the first
    # version-shaped thing in it: a preamble (an update nag, a bundled-runtime notice —
    # "18.2.0 required, please upgrade") carries a perfectly well-shaped token of its own, and
    # scanning would stamp THAT on the cell as the claude binary's version. A wrong version is
    # worse here than no version: it names an instrument, so it neither halts nor misses — it
    # just files the measurement under a lie. Unrecognised output is refused for the same reason
    # the rest of this module refuses to model its inputs: guessing which line names the
    # instrument is the modelling, and a halt is recoverable where a silent mislabel is not.
    lines = [line for line in (completed.stdout or "").splitlines() if line.strip()]
    token = lines[0].split(maxsplit=1)[0] if len(lines) == 1 else ""
    if not _VERSION_TOKEN.fullmatch(token):
        # Sanitised even though the child SUCCEEDED: `run_checked` only guards its own
        # non-zero arm, and this branch embeds the whole raw stdout of an exit-0 child into
        # an exception that `run_corpus` resolves up front — so it prints on the drivers'
        # SWEEP HALT arm like any other halt. Unbounded and unredacted, it was the widest
        # of the echo sites while looking like the safest.
        raise HeadlessAgentError(
            f"claude --version printed no recognisable version: "
            f"{sanitised_child_output(completed.stdout or '')!r} "
            "— the binary a paid run would measure on cannot be identified"
        )
    return token


def stream_cli_version(stream: str) -> str | None:
    """The version the binary that PRODUCED ``stream`` reported of itself — read off the
    ``type=system``/``subtype=init`` event Claude Code prints first, which carries
    ``claude_code_version``. The mirror of ``resolve_cli_version`` on the OTHER side of the run:
    that reads a pre-flight ``claude --version`` claim about a DIFFERENT process; this reads the
    version the process that actually ran a paid cell announced, so it catches a CLI upgraded
    mid-sweep (the residue ``resolve_cli_version`` cannot — mem-z32zu). The same init event
    ``harbor.probe_gate.assert_run_pins`` scans — but the two DIVERGE on the missing-init case:
    ``assert_run_pins`` fails closed (raises when a stream carries no init event), this fails open
    (returns ``None``, leaving the stream unverified — see below). The write boundary here wants
    that asymmetry: an in-container probe gate can demand a well-formed stream, but a resume-cache
    pass over local runs must not refuse a version-less-but-otherwise-fine measurement.

    ``None`` when the stream names no instrument: no init event (a stream that carries none — an
    empty run, or output that never reached the init line — is left UNVERIFIED at the write
    boundary, not refused; a drifted REAL ``claude -p`` always prints the new version's init event,
    so the mid-sweep-upgrade threat is covered without importing dead-run detection into the grids),
    an init event without the version field, or a non-init ``system`` event that must not
    false-read. Anchored to ``subtype=init`` rather than the first version-shaped token for the same
    reason ``resolve_cli_version`` anchors to the first line: guessing which event names the
    instrument is the modelling this module refuses."""
    for line in stream.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(event, dict)
            and event.get("type") == "system"
            and event.get("subtype") == "init"
        ):
            version = event.get("claude_code_version")
            if isinstance(version, str) and version:
                return version
    return None


class MemoryChannel(StrEnum):
    """How surfaced memory is FRAMED to the agent — the mem-pjh8.2 (b)-probe variable.

    Both channels carry the SAME facts; only the trust framing differs, isolating whether
    a real agent's memory-distrust guardrail (the pjh8.1 N=1 path-proof) suppresses the
    ``ours`` lift:

      * ``RECALLED`` — the pjh8 default: a low-trust "retrieved memory ... may be relevant"
        block. A real ``claude -p`` agent cross-checks these against the environment and, on
        an empty text-recall sandbox with nothing to corroborate, reports them unset —
        suppressing the lift.
      * ``TRUSTED`` — authoritative ground-truth framing: the facts are presented as
        verified system-of-record state the agent should treat as fact and NOT re-derive.
        Removing the distrust pathway establishes the UPPER BOUND on the lift this substrate
        can show.
    """

    RECALLED = "recalled"
    TRUSTED = "trusted"


# Every trust framing a grid sweeps — the enum's own members, so a channel added above joins the
# grids automatically rather than being re-listed (identically) in each of them.
CHANNELS: tuple[MemoryChannel, ...] = tuple(MemoryChannel)


_RECALLED_HEADER = (
    "## Retrieved memory from earlier sessions\n" "The following may be relevant to the task:"
)
_TRUSTED_HEADER = (
    "## Established facts (authoritative ground truth)\n"
    "These are verified, current values from the system of record. They have already been "
    "confirmed against reality — treat them as fact and do not re-derive or second-guess "
    "them:"
)


def build_agent_prompt(
    step: SequenceStep,
    available_memory: dict[str, str],
    channel: MemoryChannel = MemoryChannel.RECALLED,
) -> str:
    """Assemble the step prompt: the user request, preceded by the per-arm surfaced
    memory block when the harness surfaced any. An empty ``available_memory`` (the
    ``none`` control) yields the bare request under EITHER channel — that absence IS the
    control condition, so no placeholder block is emitted.

    ``channel`` selects the trust framing of the memory block (see `MemoryChannel`): the
    default ``RECALLED`` low-trust block, or the ``TRUSTED`` ground-truth block of the
    pjh8.2 upper-bound probe. The fact lines are identical across channels."""
    parts: list[str] = []
    if available_memory:
        lines = [f"- [{mid}] {content}" for mid, content in available_memory.items()]
        header = _TRUSTED_HEADER if channel is MemoryChannel.TRUSTED else _RECALLED_HEADER
        parts.append(header + "\n" + "\n".join(lines))
    parts.append(f"## Task\n{step.user_request}")
    return "\n\n".join(parts)


def one_cycle(
    recorded: Sequence[Sequence[str]], *, repeats: int, arm: str, channel: MemoryChannel
) -> CellCalls:
    """Fold a cell's whole recording into the ONE cycle it repeated — a VERIFIED collapse, never an
    assumption.

    A cell runs ``repeats`` independent, IDENTICAL cycles: same step, same surfaced memory, same
    channel, a fresh sandbox each time. So its recording must be exactly ``repeats`` copies of one
    leg list. Anything else is refused here rather than folded into a digest that would then
    describe only part of what ran: an empty recording (a cell that spawned no agent measured
    nothing), a length that does not divide, or cycles that disagree with each other.

    Taking cycle 0 and trusting the rest to match is precisely the shape this refuses — it is how a
    fingerprint ends up describing one repeat of a run whose other repeats sent something else."""
    if not recorded:
        raise ValueError(f"{arm}/{channel.value}: no `claude -p` call was recorded — nothing ran")
    if len(recorded) % repeats:
        raise ValueError(
            f"{arm}/{channel.value}: {len(recorded)} call(s) recorded over {repeats} repeat(s) — "
            "a cell repeats ONE cycle, so its recording must divide evenly into them"
        )
    width = len(recorded) // repeats
    cycles = [
        tuple(tuple(argv) for argv in recorded[i * width : (i + 1) * width]) for i in range(repeats)
    ]
    if any(cycle != cycles[0] for cycle in cycles[1:]):
        raise ValueError(
            f"{arm}/{channel.value}: the repeats did not send the same invocations — a cell's "
            "repeats differ only in their sandbox, so a divergence means the executed input is not "
            "the fixed thing the identity claims to fingerprint"
        )
    return CellCalls(arm=arm, channel=channel.value, calls=cycles[0])


@dataclass(eq=False)
class CellRecorder:
    """The seam that OWNS the executed invocations. ``run_cached_corpus`` creates one, hands it to
    ``evaluate``, and reads ``recorded()`` ITSELF — so the argv hashed at the write boundary are the
    ones the CLI seam SAW, never a value ``evaluate`` returned. An arm no longer hands back a
    ``CellCalls`` at all: it opens a per-``(arm, channel)`` ``RecordingRunner`` via ``cell`` and
    drives its ``repeats`` cycles through it. That is what closes the last route by which a caller
    could supply the hashed invocations — the write boundary once trusted ``Evaluation.calls``, an
    ordinary value nothing bound to the wire (mem-9gvej).

    The repeats-fold happens HERE, in ``recorded()``, not the arm: the ``(arm, channel, repeats)``
    labels are captured at ``cell`` time, so ``one_cycle`` collapses each recorder exactly as the
    in-arm fold used to — same divide/agree/non-empty refusals, off a recorder the caller cannot
    detach from."""

    _cells: list[tuple[str, MemoryChannel, int, RecordingRunner]] = field(default_factory=list)

    def cell(
        self, inner: Runner, *, arm: str, channel: MemoryChannel, repeats: int
    ) -> RecordingRunner:
        runner = RecordingRunner(inner)
        self._cells.append((arm, channel, repeats, runner))
        return runner

    def recorded(self) -> list[CellCalls]:
        return [
            one_cycle(runner.calls, repeats=repeats, arm=arm, channel=channel)
            for arm, channel, repeats, runner in self._cells
        ]

    def recorded_streams(self) -> list[str]:
        """Every executed ``claude -p`` stream, flat across cells AND repeats — unlike ``recorded``,
        which FOLDS each cell's argv back to its one repeated cycle. The fold is unsafe here: a CLI
        upgrade can land between two repeats of a single cell, so the write boundary must be able to
        check the stream of every run, not one representative per cell (mem-z32zu)."""
        return [
            stream for _arm, _channel, _repeats, runner in self._cells for stream in runner.streams
        ]


def assistant_event(
    tool_uses: Sequence[
        tuple[str, Mapping[str, object]] | tuple[str, Mapping[str, object], str]
    ] = (),
    *,
    usage: tuple[int, int] | None = (0, 0),
) -> dict[str, object]:
    """One Claude Code ``assistant`` event whose content carries ``tool_uses`` as ``tool_use``
    blocks, in order. A three-tuple ``(name, input, id)`` stamps the block's ``id``, which is
    what a later ``tool_result_event`` joins back to. ``usage=None`` omits the key entirely —
    the shape that exercises the parsers' honest-unmeasured (0, 0) branch, which a hardcoded
    zero would silently skip."""
    content: list[dict[str, object]] = []
    for tool_use in tool_uses:
        block: dict[str, object] = {
            "type": "tool_use",
            "name": tool_use[0],
            "input": dict(tool_use[1]),
        }
        if len(tool_use) == 3:
            block["id"] = tool_use[2]
        content.append(block)
    message: dict[str, object] = {"role": "assistant", "content": content}
    if usage is not None:
        message["usage"] = {"input_tokens": usage[0], "output_tokens": usage[1]}
    return {"type": "assistant", "message": message}


def tool_result_event(
    tool_use_id: str, content: str, *, is_error: bool = False
) -> dict[str, object]:
    """The ``user`` event Claude Code prints when a tool returns: one ``tool_result`` block
    carrying the tool's output under the ``tool_use_id`` of the call it answers.

    ``is_error`` is the CLI's own flag and it is NOT the refusal signal a scorer can rely on: a
    command like ``bd remember list 2>&1 | head`` exits 0 through the pipe, so its refusal arrives
    with ``is_error=false`` (mem-8fv4t). The evidence of acceptance or refusal is the CONTENT."""
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": content,
                    "is_error": is_error,
                }
            ],
        },
    }


def result_event(result: str = "done") -> dict[str, object]:
    """The terminal ``type=result`` event Claude Code prints — the one `_stream_result_text` reads
    the final answer off."""
    return {"type": "result", "result": result}


def serialize_stream(events: Sequence[dict[str, object]]) -> str:
    """Serialize ``events`` as the JSONL `claude -p --output-format stream-json` prints: one JSON
    object per line.

    The INVERSE of this module's three parsers (``_stream_usage_tokens`` / ``_stream_result_text``
    / ``tool_calls_from_stream``), and it lives beside them for that reason: every dry-run
    simulator and test double that fakes a `claude -p` writes this format, and one fitted to its
    own idea of it proves nothing about the real one (that is how a MEMORY.md-only glob survived a
    green dry-run — ``toolreq_builtin.simulated_builtin_runner``). One writer against this module's
    three parsers means a format change moves both, and the round-trip test guards the pair. Other
    parsers of the same format live outside this module (``armcompare`` / ``bbon.extract``) and are
    NOT guarded by that test — mem-4tvkc tracks the rest.

    Not a model of the CLI's output — a writer of the subset the parsers read. The real stream
    carries fields nothing here consumes; inventing them would be modelling."""
    return "".join(json.dumps(event) + "\n" for event in events)


def _stream_usage_tokens(stream_text: str) -> tuple[int, int]:
    """Sum (input, output) token usage across the stream's events. Claude Code stamps
    ``usage`` on assistant message events; an event without one contributes 0. Absent
    usage everywhere yields (0, 0) — an honest unmeasured, not an imputed estimate."""
    input_tokens = 0
    output_tokens = 0
    for line in stream_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = event.get("message") if isinstance(event, dict) else None
        usage = message.get("usage") if isinstance(message, dict) else None
        if isinstance(usage, dict):
            input_tokens += int(usage.get("input_tokens", 0) or 0)
            output_tokens += int(usage.get("output_tokens", 0) or 0)
    return input_tokens, output_tokens


def _stream_result_text(stream_text: str) -> str:
    """The agent's final answer: the ``result`` field of the terminal ``type=result``
    event Claude Code emits. Empty when none is present (e.g. a stream truncated before
    completion) — the trajectory's tool calls still stand on their own."""
    final = ""
    for line in stream_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            result = event.get("result")
            if isinstance(result, str):
                final = result
    return final


def _tool_result_text(block: Mapping[str, Any]) -> str:
    """The text of one ``tool_result`` block. The CLI prints ``content`` either as a string or as
    a list of ``text`` blocks; both are read, and anything else contributes nothing."""
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            part["text"]
            for part in content
            if isinstance(part, Mapping) and isinstance(part.get("text"), str)
        )
    return ""


def tool_calls_from_stream(stream_text: str) -> list[ToolCall]:
    """One `ToolCall` per ``tool_use`` block, in stream order — the same tolerant walk
    `bbon.extract.steps_from_stream` uses, so the structured tool_calls and the derived
    AttemptStep trajectory agree by construction.

    Each call carries the ``tool_result`` the stream answered it with, joined by ``tool_use_id``
    (``ToolCall.result``; ``None`` when the stream carries no answer — a stream truncated before
    the tool returned). The join exists because a verb on the argv is not an operation: the
    160-leg staged fire's only "endogenous write" was a ``bd remember list`` that bd REFUSED, and
    only the result can say so (mem-8fv4t)."""
    results = {
        block["tool_use_id"]: _tool_result_text(block)
        for block in _iter_tool_result_blocks(stream_text)
        if isinstance(block.get("tool_use_id"), str)
    }
    calls: list[ToolCall] = []
    for block in _iter_tool_use_blocks(stream_text):
        name = block.get("name")
        raw_input = block.get("input")
        block_id = block.get("id")
        calls.append(
            ToolCall(
                name=name if isinstance(name, str) and name else "unknown",
                arguments=dict(raw_input) if isinstance(raw_input, dict) else {},
                result=results.get(block_id) if isinstance(block_id, str) else None,
            )
        )
    return calls


@dataclass(frozen=True, kw_only=True)
class HeadlessClaudeAgent:
    """A real `claude -p` agent. ``model`` pins the CLI model (left empty it reads
    ``MEMBENCH_AGENT_MODEL`` then falls back to the CLI default, recorded as
    ``cli-default``). ``strict_mcp`` keeps ``--strict-mcp-config`` on (the boot-hang guard);
    ``constrain_tools`` passes the step's ``available_tools`` as ``--allowedTools``.
    ``memory_channel`` selects how surfaced memory is FRAMED (see `MemoryChannel`): the
    default low-trust ``RECALLED`` block, or the ``TRUSTED`` ground-truth block of the
    pjh8.2 upper-bound probe.

    ``runner`` has NO default and must be passed explicitly. It is THE seam that decides whether a
    ``claude -p`` is recorded (a ``RecordingRunner``, on the paid-grid path), simulated (dry-run),
    or a real unrecorded spawn (``subprocess.run``). A default of ``subprocess.run`` here would make
    "real, unrecorded" the thing you get by omission — the caller-discipline hole the resume-cache
    identity exists to close, one construction site below its ``cell_agent`` wrapper. Requiring it
    forces every construction — wrapper or direct — to name which of the three it wants."""

    agent_config_id: str = "headless-claude"
    model: str = ""
    timeout_s: float = DEFAULT_TIMEOUT_S
    runner: Runner
    strict_mcp: bool = True
    constrain_tools: bool = True
    # Path to the MCP server config `--strict-mcp-config` should restrict the session TO. Without
    # it, strict mode boots NO servers at all, so every `mcp__<server>__<tool>` name in
    # `--allowedTools` is unreachable and an MCP-surfaced tool can never be called — a wiring
    # zero indistinguishable from an agent that chose not to call it (mem-5sht9). `None` is the
    # bd-on-PATH surface's honest value: it declares no MCP server, rather than passing a path to
    # a config that does not exist. It reaches the argv, so `invocation_fingerprint` covers it.
    mcp_config: str | None = None
    # Tool patterns the CLI must REFUSE, emitted as `--disallowedTools`. The paid sandbox bounds
    # the cwd, not the process table: with `--allowedTools Bash` the evaluated agent has a real
    # shell on the operator's host, and a hung memory shim once drove one to a host-wide
    # `pkill -9 bd` (mem-5sht9). `tool_surface.HOST_DENIED_TOOLS` is the list any surface handing
    # out Bash should pass. It is a rule engine and not a kernel boundary — see that module's
    # host-exposure paragraph for what it does not cover. Lands in the argv, so
    # `invocation_fingerprint` covers it.
    disallowed_tools: tuple[str, ...] = ()
    memory_channel: MemoryChannel = MemoryChannel.RECALLED
    # Working dir for the CLI. MUST be an isolated, neutral sandbox — never a mem
    # worktree: the repo's SessionStart hooks / CLAUDE.md / project memory would both
    # fail the session and confound the none/ours/builtin memory variable. The only
    # memory the agent should see is the arm's surfaced ``available_memory``. ``None``
    # inherits the parent cwd (correct only in tests with an injected runner).
    cwd: str | None = None
    # Extra env vars for the CLI subprocess (the builtin arm's ``CLAUDE_CONFIG_DIR``).
    # MERGED over `os.environ`, never a raw replace — a replace would silently drop PATH
    # and the OAuth token, and stay invisible under `--dry-run` (simulated runners swallow
    # `**kwargs`). ``hash=False``: callers pass a plain (unhashable) dict, which would
    # otherwise break this frozen dataclass's auto-generated ``__hash__``.
    env: Mapping[str, str] | None = field(default=None, hash=False)
    # Env var names to REMOVE from the child's environment, applied AFTER the merge above.
    # `env` can only ADD, and a dict merge has no way to express "the child must NOT see this":
    # an inlet exported in the operator's shell reaches the child whatever any startup guard
    # concluded, because the guard reads the parent env and the merge then re-supplies it. The
    # E1 floor rung needs the removal to be real — its `autoMemoryEnabled: false` pin is the
    # LOWEST-precedence of the CLI's five settings scopes and several env vars are consulted
    # before the merge, so an inherited one silently outranks the pin while the rig records it
    # as held. Removal is by `pop`, never by assigning "": the CLI's own truthiness parsers
    # decide what an empty string means and this rig does not observe them, so an unset name is
    # the only value whose meaning it can state. ``hash=False`` for the reason ``env`` has it.
    env_unset: Sequence[str] = field(default=(), hash=False)
    _pass_model: bool = field(default=False, init=False)
    _resolved_model: str = field(default="", init=False)

    def __post_init__(self) -> None:
        runner_field = type(self).__dataclass_fields__["runner"]
        if runner_field.default is not MISSING or runner_field.default_factory is not MISSING:
            raise TypeError(
                f"{type(self).__name__}.runner has a default — every HeadlessClaudeAgent, base or "
                "subclass, must make `runner` mandatory so 'real and unrecorded' is never what you "
                "get by omission. A frozen kw_only subclass that re-adds `runner = <default>` "
                "reopens the resume-cache hole the RecordingRunner seam closes (mem-9gvej). A "
                "`callable(runner)` check does NOT close it: subprocess.run is callable. Declare "
                "`runner` with no default."
            )
        resolved = resolve_model(self.model)
        object.__setattr__(self, "_pass_model", bool(resolved))
        object.__setattr__(self, "_resolved_model", resolved or "cli-default")

    def argv_for(self, step: SequenceStep, available_memory: Mapping[str, str]) -> list[str]:
        """The exact command line this agent will spawn for one step — the prompt is its third
        element, and the flags around it are the rest of the executed input.

        PUBLIC, and ``run_step`` goes through it, because a paid grid's cache identity IS this list:
        the grid renders it from the plan the arm executes and hashes it (``CellCalls``). One method
        for both is what keeps the fingerprinted invocation and the sent one from being two things
        that merely agree today — the whole defect family this seam closes."""
        prompt = build_agent_prompt(step, dict(available_memory), self.memory_channel)
        argv = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose"]
        if self.strict_mcp:
            argv.append("--strict-mcp-config")
        if self.mcp_config:
            # Emitted ALONGSIDE --strict-mcp-config, never instead of it: strict mode is the
            # boot-hang guard, and the config names the one server the session may boot. Passing
            # strict without a config is what made every MCP tool unreachable.
            argv += ["--mcp-config", self.mcp_config]
        if self._pass_model:
            # Use the RESOLVED model: when the model comes from MEMBENCH_AGENT_MODEL
            # (not the `model=` kwarg), `self.model` is "" and would pass an empty
            # `--model`, making the env override a silent no-op.
            argv += ["--model", self._resolved_model]
        if self.constrain_tools and step.available_tools:
            argv += ["--allowedTools", ",".join(step.available_tools)]
        if self.disallowed_tools:
            argv += ["--disallowedTools", ",".join(self.disallowed_tools)]
        return argv

    def child_env(self) -> dict[str, str] | None:
        """The environment the child process actually gets, or ``None`` to inherit the parent's.

        ``None`` is subprocess's own inherit-the-parent-environment sentinel, and it is the right
        answer only when this agent asks for no change at all. The moment ``env_unset`` names
        anything, inheriting is exactly the failure it exists to prevent, so the environment is
        materialized from ``os.environ`` and the named entries are dropped from it — a scrub
        expressed as a sentinel would be no scrub."""
        if self.env is None and not self.env_unset:
            return None
        merged = {**os.environ, **(self.env or {})}
        for name in self.env_unset:
            merged.pop(name, None)
        return merged

    def run_step(
        self,
        step: SequenceStep,
        available_memory: dict[str, str],
        ctx: StepContext,
    ) -> AgentStepResult:
        argv = self.argv_for(step, available_memory)
        env = self.child_env()
        completed = run_checked(
            argv,
            what="claude -p",
            not_found_hint="install it to run the headless agent",
            timeout_s=self.timeout_s,
            error=HeadlessAgentError,
            runner=self.runner,
            cwd=self.cwd,
            env=env,
        )

        stream_text = completed.stdout or ""
        input_tokens, output_tokens = _stream_usage_tokens(stream_text)
        tool_calls = tool_calls_from_stream(stream_text)
        return AgentStepResult(
            final_answer=_stream_result_text(stream_text),
            check_results={},  # a real agent does not self-grade; scored externally
            writes_performed={},  # write policy decided externally, not here
            messages=[TraceMessage(role="user", content=step.user_request)],
            tool_calls=tool_calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            raw_stream=stream_text,
        )


def _render_only_runner(argv: Sequence[str], **kwargs: object) -> NoReturn:
    """The ``runner`` for an agent built only to RENDER argv (``render_cell_calls`` calls
    ``argv_for``, which never executes). If it is ever actually invoked, a plan-rendering agent has
    been made to spawn a real ``claude -p`` — the exact unrecorded call the recorder seam exists to
    make impossible — so it fails loudly instead of running untracked."""
    raise RuntimeError(
        "render_cell_calls built this agent to render argv only; it must never run a claude -p. "
        "An execution path needs a RecordingRunner, not this render sentinel."
    )


def seed_config_dir(config_dir: Path, settings: Mapping[str, object]) -> None:
    """Create ``config_dir`` if needed and write ``settings`` as its ``settings.json``.

    THE shared config-surface seeder, imported by every paid grid that runs a real ``claude -p``
    (the builtin arm, the none/oracle/ours arms). A cell passes the seeded dir as
    ``env={"CLAUDE_CONFIG_DIR": ...}`` to ``cell_agent`` so the agent reads its USER/GLOBAL config
    (``~/.claude``: settings.json, CLAUDE.md, hooks, MCP) from THIS empty dir rather than inheriting
    whichever ambient home launched the sweep — the mem-mv67o vector, where two account homes with
    different ``autoMemoryEnabled`` shared one cache because nothing in the identity disagreed.

    ``settings`` is a MEASURED INPUT the command line cannot carry: it reaches the agent through
    this FILE, not through argv, so a grid must fingerprint it separately
    (``resume_cache.BaseRunIdentity.settings_fingerprint``). Each grid declares the dict it seeds
    (the builtin arm's ``autoMemoryEnabled: True``, the probe's ``autoMemoryEnabled: False``) and
    seeds it through here, so the dict written and the dict hashed are one thing. ``settings`` is
    unwrapped to a plain ``dict`` before ``json.dumps``, which only fast-paths ``isinstance(obj,
    dict)`` and raises ``TypeError`` on the frozen ``MappingProxyType`` the builtin arm passes
    (``toolreq_builtin.BUILTIN_SETTINGS``).

    It scopes ONLY ``~/.claude``: per the Claude Code docs the CLI also walks the cwd's ANCESTORS
    for ``CLAUDE.md`` and reads its own ``TMPDIR``, neither of which a seeded ``CLAUDE_CONFIG_DIR``
    isolates (mem-rx11w). Those are separate inputs, out of scope here."""
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "settings.json").write_text(json.dumps(dict(settings), indent=2) + "\n", "utf-8")


def cell_agent(
    *,
    model: str,
    channel: MemoryChannel,
    runner: Runner,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    mcp_config: str | None = None,
) -> HeadlessClaudeAgent:
    """The agent one ``(arm, channel)`` cell runs ALL its legs through.

    THE definition, and the only one — for every paid grid, not per grid. Each arm executes through
    it and each grid renders its cache identity through it (``render_cell_calls``), so the flags
    that land in the argv cannot be set one way on the wire and another in the hash. A per-grid copy
    of this constructor would keep each grid internally consistent (its own fingerprint and its own
    calls moving together, write boundary green) while letting two grids drift onto DIFFERENT
    command lines — and ours-vs-builtin is a comparison between grids.

    ONE agent drives every leg of a cell, which is what makes "the legs share a sandbox cwd and a
    ``CLAUDE_CONFIG_DIR``" structural rather than a thing to assert. Safe because the per-leg
    differences are carried by the STEP, not the agent: ``--allowedTools`` is derived from
    ``step.available_tools`` (so the builtin arm's establish leg runs unconstrained and its goal leg
    is Write-only), and ``memory_channel`` only frames a surfaced-memory block, which a bare leg
    never has.

    ``runner`` has NO default — an executing caller must hand in its ``RecordingRunner`` explicitly,
    so a leg cannot be run through an unrecorded agent by omission (``render_cell_calls``, which
    never executes, passes ``_render_only_runner``). ``cwd`` and ``env`` are the only things the
    fingerprint path leaves at their defaults: neither appears in the argv, so a rendered invocation
    is byte-identical to the sent one without them.

    ``mcp_config`` is NOT one of those: it lands in the argv, so a rendered plan that omitted it
    would hash a command line the cell does not send, and the write boundary would refuse the
    measurement. It is threaded through ``render_cell_calls`` for that reason."""
    return HeadlessClaudeAgent(
        model=model,
        runner=runner,
        memory_channel=channel,
        constrain_tools=True,
        cwd=cwd,
        env=env,
        mcp_config=mcp_config,
    )


def render_cell_calls(
    *,
    arm: str,
    channel: MemoryChannel,
    legs: Sequence[Leg],
    model: str,
    mcp_config: str | None = None,
) -> CellCalls:
    """The command lines one ``(arm, channel)`` cell WILL spawn — the plan, rendered from the legs
    the arm executes, through the agent that executes them.

    EVERY leg, in order. A fingerprint over the scored leg alone would call two runs identical while
    an earlier leg differed — and for the builtin arm the earlier leg is the one under test."""
    agent = cell_agent(
        model=model, channel=channel, runner=_render_only_runner, mcp_config=mcp_config
    )
    return CellCalls(
        arm=arm,
        channel=channel.value,
        calls=tuple(tuple(agent.argv_for(leg.step, leg.memory)) for leg in legs),
    )
