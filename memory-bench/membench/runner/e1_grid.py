"""mem-eg850 — E1: the guidance-strength ladder as the call-rate dial.

Five NESTED guidance rungs, ``R0`` (silent) through ``R4`` (recall + capture), are the
harness-level surrogate for residual steering: each rung's text CONTAINS its predecessor's,
so a rung difference is an ADDED clause and nothing else. That containment is the whole
design — it is asserted on the TABLE (``RUNG_TEXT``), not on rendered prose, so a rung
cannot drift into being a rewrite that happens to read stronger.

What this module decides, and what it deliberately does not:

* **The channel axis is DROPPED here.** ``build_agent_prompt`` emits no block at all when
  ``available_memory`` is empty, so on a bare E1 arm ``RECALLED`` and ``TRUSTED`` produce
  BYTE-IDENTICAL argv — sweeping them would buy two cells of one measurement and a doubled
  bill. ``MemoryChannel`` stays on the oracle-ceiling control (``realagent_probe``), which
  actually surfaces a block. E1 pins ``CHANNEL``.
* **The primary endpoint is the discrimination margin ``d(rung)``**, P(call | necessary) -
  P(call | unnecessary), NOT the raw call rate. A rung that lifts the call rate with ``d``
  flat bought nothing (the arXiv 2605.09252 bluntness result); BOTH are emitted, and the
  gate block says which is which.
* **The guidance block's own token count is a REPORTED adjustment, never a correction.**
  R4's block is longer than R0's BY CONSTRUCTION, so the cost axis is contaminated by the
  treatment. ``guidance_words`` per rung rides in the gate block so a cost comparison can
  subtract it explicitly rather than silently reading treatment length as agent behaviour.
* **The tool-name confound is reported, not fixed.** If R0 already calls at ~100% because
  the model reaches for an allowlisted memory tool, the tool's NAME is the treatment and R0
  is the TOOL-AFFORDANCE FLOOR, which the gate block labels. The tool is NOT renamed: a
  rename moves the argv and invalidates every cached cell.

**Nothing in this module spends money by itself.** ``main`` refuses to spend unless the
operator passes ``--preflight`` or ``--staged`` with a pinned model and an OAuth token. The
preflight is a REAL paid cycle at the TOP rung, deliberately not simulated — the same stance
as ``toolreq_builtin_grid.preflight`` — because a simulated mechanism check proves only that
the simulator cooperates. As of this commit BOTH paid paths are UNRUN.

ZFC: rung text is authored data, the counter is ``tool_surface``'s mechanical argv scan, and
the gates are arithmetic over counts. No semantic judgment anywhere in here.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import types
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal

from membench.runner.headless_agent import (
    ENV_OAUTH,
    REFUSE_API_KEY_SET,
    REFUSE_UNPINNED_MODEL,
    HeadlessAgentError,
    HeadlessClaudeAgent,
    MemoryChannel,
    a_paid_run_carries_the_metered_api_key,
    a_paid_run_needs_a_model,
    resolve_cli_version,
    resolve_model,
    result_event,
    seed_config_dir,
    serialize_stream,
    stream_cli_version,
    tool_calls_from_stream,
)
from membench.runner.resume_cache import digest
from membench.runner.sandbox import assert_corpus_unreachable, paid_sandbox
from membench.runner.tool_surface import (
    HOST_DENIED_TOOLS,
    MEMORY_ALLOWED_TOOLS,
    endogenous_memory_verbs,
    memory_invocations,
    memory_reaching_calls,
    native_memory_accesses,
    provision_memory_tool,
    surface_fingerprint,
)
from membench.runner.toolreq_corpus import load_twin_corpus
from membench.runner.toolreq_realagent import (
    DEFAULT_CORPUS,
    VARIANT_NECESSARY,
    VARIANT_UNNECESSARY,
    ToolReqRealAgentTask,
    task_fingerprint,
)
from membench.runtime import StepContext
from membench.schemas.sequence import SequenceStep
from membench.schemas.trace import ToolCall
from membench.spawn import (
    Runner,
    child_of,
    redact_credentials,
    run_in_session,
    timeout_partial_stdout,
)

__all__ = [
    "CHANNEL",
    "DEFAULT_STAGE",
    "EXECUTION_PROTOCOL_VERSION",
    "GATE_KEY",
    "HALT_NO_CALL",
    "HALT_UNMEASURED",
    "NATIVE_MEMORY_SETTING",
    "OK_FIRED",
    "RUNG_IDS",
    "RUNG_SETTINGS",
    "RUNG_TEXT",
    "STAGED_REPEATS",
    "STAGED_RUNGS",
    "STAGED_SLICES",
    "STAGED_TASKS",
    "SUMMARY_NAME",
    "LegRecord",
    "LegScore",
    "MonotonicityViolation",
    "PreflightHaltError",
    "QuotaHaltError",
    "RigHaltError",
    "RungCell",
    "UnmeasuredStreak",
    "assert_gates_ride_outside_metrics",
    "call_rate_gates",
    "corpus_fingerprint",
    "discrimination_margins",
    "grid_keys",
    "guidance_block",
    "guidance_words",
    "monotonicity_violations",
    "native_memory_pinned_off",
    "per_variant_task_count",
    "planned_call_count",
    "preflight",
    "preflight_verdict",
    "priced_plan",
    "rung_settings",
    "rung_settings_fingerprint",
    "rung_step",
    "score_leg",
    "staged_plan",
    "staged_rungs",
    "stream_is_error",
    "summarize",
    "write_json_new",
]

# The summary E1 emits. Named for the file the acceptance criterion reads with
# `jq '.call_rate_gates' .../summary-e1.json`.
SUMMARY_NAME = "summary-e1.json"

# The version of everything that changes what a leg MEASURES without moving the tool surface, the
# CLI binary or the corpus: the sandbox guard (`assert_corpus_unreachable` — what a leg is allowed
# to reach), the PWD pin (the cwd the agent is spawned in and what a relative path resolves
# against), the session runner (`run_in_session` — how a leg is spawned, timed out, killed and
# drained), and the timeout scoring (what a leg that timed out contributes to its cell). It is one
# number in the resume identity: bump it when any of those changes semantics, and a partial
# artifact bought under the old number is refused rather than pooled with the new one.
EXECUTION_PROTOCOL_VERSION = 1

# The one trust framing E1 runs under. NOT a swept axis here — see the module docstring: a bare
# arm surfaces no memory block, so both channels render the same bytes and a channel sweep would
# bill two cells for one measurement.
CHANNEL = MemoryChannel.RECALLED

RUNG_IDS: tuple[str, ...] = ("R0", "R1", "R2", "R3", "R4")

# The `$CLAUDE_CONFIG_DIR/settings.json` each rung SEEDS into its freshly-minted config dir.
#
# R0 pins the CLI's OWN memory system OFF (`autoMemoryEnabled: false`, RULED 2026-09-03). The
# floor rung was minted with an EMPTY config dir, which is the CLI's default — auto-memory ON —
# so the rung that carries no guidance block still ran under a standing native instruction about
# memory, and the first paid R4 cycle proved the reach is real: the agent read the native memory
# file directly (mem-gj0pc). An unprompted reach at R0 was therefore being scored as the agent's
# own disposition while the harness was still prompting it, which is the one reading this rung
# exists to supply (mem-zfm0m item 5).
#
# R1..R4 stay EMPTY on purpose. They measure guidance ON TOP OF native memory, and pinning them
# would change what they measure rather than clean it: the contrast the ladder publishes is
# guidance strength, so only the zero-guidance end has to be actually zero.
#
# Frozen at both levels (`MappingProxyType`), the same discipline as
# `toolreq_builtin.BUILTIN_SETTINGS` and for the same reason: an in-place edit would silently
# diverge the settings WRITTEN from the settings the resume identity HASHES.
NATIVE_MEMORY_SETTING = "autoMemoryEnabled"
RUNG_SETTINGS: Mapping[str, Mapping[str, object]] = types.MappingProxyType(
    {
        "R0": types.MappingProxyType({NATIVE_MEMORY_SETTING: False}),
        "R1": types.MappingProxyType({}),
        "R2": types.MappingProxyType({}),
        "R3": types.MappingProxyType({}),
        "R4": types.MappingProxyType({}),
    }
)


def rung_settings(rung: str) -> Mapping[str, object]:
    """What ``rung`` seeds into its config dir — empty for every rung but the floor."""
    if rung not in RUNG_SETTINGS:
        raise ValueError(f"unknown rung {rung!r}: the ladder is {', '.join(RUNG_IDS)}")
    return RUNG_SETTINGS[rung]


def rung_settings_fingerprint() -> str:
    """Digest of the WHOLE seeding table, read at call time.

    Part of the resume identity for the reason the corpus and the tool surface are: an R0 bought
    before the pin measured the agent under the CLI's own memory prompt, and pooling those legs
    with pinned ones publishes two floors as one rate. Nothing else in the identity could see it
    — ``surface_fingerprint`` digests the recognizer policy and the config-dir PIN, not the
    dir's CONTENTS, and ``EXECUTION_PROTOCOL_VERSION`` is a hand-bumped integer — so before this
    field the two artifacts hashed identical."""
    return digest({rung: dict(settings) for rung, settings in RUNG_SETTINGS.items()})


def native_memory_pinned_off(config_dir: Path) -> bool:
    """Whether the minted ``config_dir`` on disk pins the CLI's own memory system OFF.

    A READ of the artifact, never a restatement of the intent: an absent file, the key set true,
    and the key set false are three different answers and only the last is the pin. Malformed
    JSON in a dir this rig just wrote is a fault and propagates."""
    settings_file = Path(config_dir) / "settings.json"
    if not settings_file.exists():
        return False
    settings = json.loads(settings_file.read_text(encoding="utf-8"))
    return isinstance(settings, dict) and settings.get(NATIVE_MEMORY_SETTING) is False


# The ladder, as ADDED CLAUSES. Each rung's text is its predecessor's plus one clause, so the
# nesting `RUNG_TEXT[n] in RUNG_TEXT[n+1]` is structural rather than a property of prose someone
# has to keep true by hand. R0 is EMPTY — the silent rung, whose prompt carries no guidance block
# at all — and it is the TOOL-AFFORDANCE FLOOR, not a zero: the agent still sees an allowlisted
# memory tool, and reaching for it unprompted is the floor this ladder is measured above.
#
# Silent means silent on BOTH surfaces. R0 also pins `autoMemoryEnabled: false` into its minted
# config dir (`RUNG_SETTINGS`), because the agent's OWN native memory is a second, unprompted
# guidance channel: left on, an R0 leg can reach memory the ladder never offered it, and the
# floor it measures is the harness's default rather than the affordance under test.
_RUNG_CLAUSES: tuple[str, ...] = (
    "",
    "You have a persistent memory tool available in this session.",
    "Consult it when the task may depend on facts established in earlier sessions.",
    "If something you need is not stated in this task, recall it before you answer.",
    "After you act, record any durable fact you established so a later session can recall it.",
)


def _ladder(clauses: Sequence[str]) -> tuple[str, ...]:
    """Accumulate the clauses into the nested rung table.

    Built by accumulation rather than written out five times, which is what makes containment a
    property of the CONSTRUCTION: no edit to one rung's wording can break the nesting without
    breaking it for every rung above, and `test_ladder_is_nested` still checks the table it
    produced (a construction is not a proof that the table shipped is the one it built)."""
    texts: list[str] = []
    parts: list[str] = []
    for clause in clauses:
        if clause:
            parts.append(clause)
        texts.append(" ".join(parts))
    return tuple(texts)


RUNG_TEXT: tuple[str, ...] = _ladder(_RUNG_CLAUSES)

_GUIDANCE_HEADER = "## Memory guidance"


def guidance_block(rung: str) -> str:
    """The rendered guidance block for ``rung`` — EMPTY for R0.

    R0 emits no header either. A "## Memory guidance\\n(none)" placeholder would make the silent
    rung a instruction about memory, which is the one thing the floor must not be."""
    text = RUNG_TEXT[_rung_index(rung)]
    return f"{_GUIDANCE_HEADER}\n{text}" if text else ""


def guidance_words(rung: str) -> int:
    """Whitespace-word count of the rung's guidance text — the REPORTED cost adjustment.

    A word count, not a tokenizer's count, and named ``words`` so no consumer reads it as one.
    What it is for: R4's block is longer than R0's by construction, so any per-rung token
    comparison has the treatment baked into its cost axis. Reporting the treatment's own length
    beside the cost is what lets a reader subtract it; this module never subtracts it silently."""
    return len(RUNG_TEXT[_rung_index(rung)].split())


def _rung_index(rung: str) -> int:
    try:
        return RUNG_IDS.index(rung)
    except ValueError:
        raise ValueError(f"unknown rung {rung!r}; the ladder is {list(RUNG_IDS)}") from None


def rung_step(task: ToolReqRealAgentTask, rung: str) -> SequenceStep:
    """The goal step as run at ``rung``: the task's own goal request, preceded by the rung's
    guidance block, with the memory tool surface allowlisted.

    The guidance rides in ``user_request`` because that is the only channel that reaches the argv
    for a bare arm (``build_agent_prompt`` emits a memory block only when the harness surfaced
    memory, and E1 surfaces none). So a rung difference IS an argv difference, which is what keeps
    the resume cache from serving one rung's measurement for its neighbour's."""
    block = guidance_block(rung)
    step = task.goal_step
    request = f"{block}\n\n{step.user_request}" if block else step.user_request
    return step.model_copy(
        update={
            "step_id": f"{step.step_id}-{rung}",
            "user_request": request,
            "available_tools": list(MEMORY_ALLOWED_TOOLS),
        }
    )


# --------------------------------------------------------------------------------------
# the measured cell
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RungCell:
    """One ``(rung, variant)`` cell: how often the agent CHOSE to call memory across ``runs``.

    ``calling_runs`` is the numerator of the call rate (repeats with at least one memory call);
    ``memory_calls`` is the raw call total, which can exceed ``runs``. Both are kept: a rung that
    doubles the calls per run without moving the fraction of runs that call at all is a different
    finding from one that recruits new runs.

    ``reading_runs`` / ``writing_runs`` are the same split by DIRECTION: legs with at least one
    read, legs with at least one acknowledged write. The discrimination margin is computed on
    ``reading_runs`` (mem-zfm0m item 2) — a read is what the twin corpus manipulates, while a
    write is the same act on both halves and only dilutes an any-call margin — and the write
    rate is reported on its own."""

    rung: str
    variant: str
    runs: int
    calling_runs: int
    memory_calls: int
    read_calls: int
    write_calls: int
    reading_runs: int
    writing_runs: int
    paid: bool
    verbs: tuple[str, ...] = ()
    # Which task this cell ran. Cells are keyed ``(rung, variant, work_id)``: with eight tasks per
    # variant, a ``(rung, variant)`` key names eight cells, and the first staged fire's gate block
    # read the LAST of them as the rung's rate (a 0.8 that was one task's 4/5).
    work_id: str = ""
    # Legs that hit the spawn timeout. They are ATTEMPTED (they were paid for and ``runs`` counts
    # them) but NOT MEASURED: an unmeasured leg is not a non-calling leg, and scoring it as one
    # biases the call rate down, in the direction that manufactures this series' null.
    timed_out_runs: int = 0
    # Legs the CLI failed outright (a non-zero exit that is neither a timeout nor the quota
    # refusal, which halts). Unmeasured for the same reason and kept SEPARATE from the timeouts:
    # the two have different diagnoses and folding them loses which one a cell hit.
    errored_runs: int = 0
    # Whether the legs of this cell ran with the CLI's own memory system pinned OFF, read back
    # off each minted config dir (`native_memory_pinned_off`). Recorded per cell rather than
    # derived from the rung so an artifact says what it RAN under, not what today's table would
    # have given it. Defaults false: a cell built without it claims no pin.
    native_memory_pinned_off: bool = False

    def __post_init__(self) -> None:
        if self.runs <= 0:
            raise ValueError(
                f"{self.rung}/{self.variant}: a cell with {self.runs} run(s) measured nothing"
            )
        if not 0 <= self.timed_out_runs <= self.runs:
            raise ValueError(
                f"{self.rung}/{self.variant}: timed_out_runs {self.timed_out_runs} "
                f"outside 0..{self.runs}"
            )
        if not 0 <= self.errored_runs <= self.runs:
            raise ValueError(
                f"{self.rung}/{self.variant}: errored_runs {self.errored_runs} "
                f"outside 0..{self.runs}"
            )
        if self.timed_out_runs + self.errored_runs > self.runs:
            raise ValueError(
                f"{self.rung}/{self.variant}: {self.timed_out_runs} timed out + "
                f"{self.errored_runs} errored exceeds {self.runs} run(s)"
            )
        if self.calling_runs > self.measured_runs:
            raise ValueError(
                f"{self.rung}/{self.variant}: calling_runs {self.calling_runs} > measured "
                f"{self.measured_runs}"
            )
        if self.memory_calls < self.calling_runs:
            raise ValueError(
                f"{self.rung}/{self.variant}: {self.memory_calls} memory call(s) cannot cover "
                f"{self.calling_runs} run(s) that each made at least one"
            )
        for legs_name, calls_name, legs, calls in (
            ("reading_runs", "read_calls", self.reading_runs, self.read_calls),
            ("writing_runs", "write_calls", self.writing_runs, self.write_calls),
        ):
            if not 0 <= legs <= self.calling_runs:
                raise ValueError(
                    f"{self.rung}/{self.variant}: {legs_name} {legs} > calling_runs "
                    f"{self.calling_runs}"
                )
            if legs > calls:
                raise ValueError(
                    f"{self.rung}/{self.variant}: {legs_name} {legs} > {calls_name} {calls}"
                )
            if calls and not legs:
                raise ValueError(
                    f"{self.rung}/{self.variant}: {calls_name} {calls} with {legs_name} 0 — "
                    "a call was counted that no leg made"
                )

    @property
    def measured_runs(self) -> int:
        """The call-rate DENOMINATOR: legs that returned a stream."""
        return self.runs - self.timed_out_runs - self.errored_runs

    @property
    def call_rate(self) -> float:
        """Over MEASURED legs. Raises on a cell that measured nothing rather than reporting a rate
        of zero for it; ``pooled_rates`` sums numerators and denominators across cells and never
        needs this on an unmeasured cell."""
        if self.measured_runs == 0:
            raise ValueError(f"{self.rung}/{self.variant}/{self.work_id}: no leg returned a stream")
        return self.calling_runs / self.measured_runs

    @property
    def read_rate(self) -> float:
        """P(read | measured leg) — the numerator of the discrimination margin."""
        if self.measured_runs == 0:
            raise ValueError(f"{self.rung}/{self.variant}/{self.work_id}: no leg returned a stream")
        return self.reading_runs / self.measured_runs

    @property
    def write_rate(self) -> float:
        """P(acknowledged write | measured leg) — reported beside the margin, never inside it."""
        if self.measured_runs == 0:
            raise ValueError(f"{self.rung}/{self.variant}/{self.work_id}: no leg returned a stream")
        return self.writing_runs / self.measured_runs

    def metrics(self) -> dict[str, Any]:
        """The per-cell metric vector. The GATE BLOCK IS NOT IN HERE, and that is load-bearing:
        a validity verdict flattened into a per-cell metric vector gets averaged with the cells it
        was meant to judge (the ``safety_gates`` / ``mechanism_gate`` precedent). It rides on the
        SUMMARY instead, and ``assert_gates_ride_outside_metrics`` enforces the separation."""
        return {
            "runs": self.runs,
            "timed_out_runs": self.timed_out_runs,
            "errored_runs": self.errored_runs,
            "measured_runs": self.measured_runs,
            "calling_runs": self.calling_runs,
            "reading_runs": self.reading_runs,
            "writing_runs": self.writing_runs,
            "memory_calls": self.memory_calls,
            "read_calls": self.read_calls,
            "write_calls": self.write_calls,
            "call_rate": self.call_rate if self.measured_runs else None,
            "read_rate": self.read_rate if self.measured_runs else None,
            "write_rate": self.write_rate if self.measured_runs else None,
            "paid": self.paid,
        }

    def row(self) -> dict[str, Any]:
        return {
            "rung": self.rung,
            "variant": self.variant,
            "work_id": self.work_id,
            "guidance_words": guidance_words(self.rung),
            # OUTSIDE `metrics`: the pin is a condition the cell ran under, not something
            # measured about the agent, and `assert_gates_ride_outside_metrics` keeps that
            # boundary meaningful in both directions.
            "native_memory_pinned_off": self.native_memory_pinned_off,
            "verbs": list(self.verbs),
            "metrics": self.metrics(),
        }

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.rung, self.variant, self.work_id)

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> RungCell:
        """The inverse of ``row`` — what a resume reads back from a partial artifact."""
        m = row["metrics"]
        for key in ("reading_runs", "writing_runs"):
            # No default: a row written before the margin moved to reads (mem-zfm0m item 2)
            # would otherwise resume with a fabricated read rate of 0.0.
            if key not in m:
                raise ValueError(
                    f"cell {row.get('rung')}/{row.get('variant')}/{row.get('work_id')} carries "
                    f"no {key!r}: it was counted before per-direction leg counts existed and "
                    "cannot be pooled into a read margin"
                )
        if "native_memory_pinned_off" not in row:
            # No default, for the reason the read counts have none: a row written before the
            # floor was pinned (mem-2vyej) ran under the CLI's own memory prompt, and resuming
            # it as an unpinned-by-choice cell pools two different floors into one rate.
            raise ValueError(
                f"cell {row.get('rung')}/{row.get('variant')}/{row.get('work_id')} carries no "
                "'native_memory_pinned_off': it was counted before the floor rung pinned the "
                "CLI's own memory system and cannot be pooled with cells that did"
            )
        return cls(
            rung=str(row["rung"]),
            variant=str(row["variant"]),
            runs=int(m["runs"]),
            calling_runs=int(m["calling_runs"]),
            memory_calls=int(m["memory_calls"]),
            read_calls=int(m["read_calls"]),
            write_calls=int(m["write_calls"]),
            reading_runs=int(m["reading_runs"]),
            writing_runs=int(m["writing_runs"]),
            paid=bool(m["paid"]),
            verbs=tuple(str(v) for v in row.get("verbs", ())),
            work_id=str(row.get("work_id", "")),
            timed_out_runs=int(m.get("timed_out_runs", 0)),
            errored_runs=int(m.get("errored_runs", 0)),
            native_memory_pinned_off=bool(row["native_memory_pinned_off"]),
        )


# --------------------------------------------------------------------------------------
# the per-leg evidence
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LegRecord:
    """One paid ``claude -p`` leg, WITH THE STREAM IT PRODUCED.

    The cell is a count; this is the evidence under it. Kept because every counter this rig has
    changed so far changed what a leg SCORES (the native-path reach that read as a zero, mem-gj0pc;
    the Bash-mediated reach that still does, mem-zfm0m), and a scoring fix with no stream to
    re-score against costs the whole grid again in real money. A leg persisted here can be
    re-counted for free; a leg that was only counted cannot.

    ``stream`` is REDACTED before it is ever written -- the env this runs under carries an OAuth
    token, and an evidence file is exactly the artifact that outlives the reason it was kept -- but
    deliberately NOT truncated. ``sanitised_child_output`` bounds a diagnosis to a 4000-char head
    and tail, which is right for an exception message and wrong for the one artifact whose whole
    purpose is to be re-counted: a 15k-char stream lands with its middle excised, and the memory
    call that lived there re-counts as a zero. The re-score that costs nothing is the reason this
    record exists, so the evidence is stored whole and the truncation stays where it belongs.

    ``cli_version`` is the instrument THIS leg ran on, read off the stream's own init event rather
    than a pre-flight ``claude --version`` on a different process -- a binary that upgrades
    mid-sweep is invisible to the latter.

    ``truncated`` marks a stream the bound cut short. Its counts are scored by the same arithmetic
    as a complete stream's and are a LOWER BOUND on what the leg did, which is why a truncated leg
    is persisted with them and still kept out of the cell: the cell pools rates over legs whose
    streams ended, and this one did not."""

    rung: str
    variant: str
    work_id: str
    leg: int
    # "ok" (a stream came back and was counted), "timeout", or "error". A quota refusal never
    # lands here as a status: it halts the fire.
    status: str
    memory_calls: int = 0
    read_calls: int = 0
    write_calls: int = 0
    verbs: tuple[str, ...] = ()
    stream: str = ""
    detail: str = ""
    cli_version: str = ""
    truncated: bool = False
    # The condition the leg ran under, read off its own minted config dir. On the leg as well as
    # the cell because the leg is the re-scorable evidence: a stream re-counted later has to say
    # whether the CLI's own memory system was prompting the agent while it was recorded.
    native_memory_pinned_off: bool = False

    def row(self) -> dict[str, Any]:
        return {
            "rung": self.rung,
            "variant": self.variant,
            "work_id": self.work_id,
            "leg": self.leg,
            "status": self.status,
            "memory_calls": self.memory_calls,
            "read_calls": self.read_calls,
            "write_calls": self.write_calls,
            "verbs": list(self.verbs),
            "stream": self.stream,
            "detail": self.detail,
            "cli_version": self.cli_version,
            "truncated": self.truncated,
            "native_memory_pinned_off": self.native_memory_pinned_off,
        }

    @property
    def filename(self) -> str:
        return f"{self.rung}__{self.variant}__{self.work_id}__{self.leg}.json"


# --------------------------------------------------------------------------------------
# the gates
# --------------------------------------------------------------------------------------

GATE_KEY = "call_rate_gates"


@dataclass(frozen=True)
class MonotonicityViolation:
    """One adjacent-rung pair whose call rate went DOWN as the guidance got stronger.

    Carries the pair by NAME. A boolean "monotone: false" cannot be acted on — the point of the
    ladder is which added clause failed, and a violation that does not name its pair reports that
    something is wrong somewhere on a five-rung ladder."""

    lower: str
    upper: str
    lower_rate: float
    upper_rate: float

    @property
    def drop(self) -> float:
        return self.lower_rate - self.upper_rate

    def describe(self) -> str:
        return (
            f"{self.lower}->{self.upper}: call rate FELL {self.lower_rate:.3f} -> "
            f"{self.upper_rate:.3f} (drop {self.drop:.3f}) as the guidance got strictly stronger"
        )


def monotonicity_violations(
    rates: Mapping[str, float], *, tolerance: float = 0.0
) -> list[MonotonicityViolation]:
    """Every adjacent pair of MEASURED rungs whose call rate INVERTED.

    Adjacency is over the rungs actually present, in ladder order — the staged fire measures only
    R0 and R4, and those two are adjacent in that run. ``tolerance`` is a dead band a caller may
    widen for sampling noise; it defaults to 0.0 so the detector reports the raw inversion and any
    softening is an explicit, visible choice.

    Ordered comparison, never a sort or a max: the ladder's order is the treatment's order, so a
    detector that asked "is the maximum at the top" would stay green on a curve that rose, fell,
    and rose again — the exact shape a mid-ladder clause that BACKFIRES produces."""
    measured = [rung for rung in RUNG_IDS if rung in rates]
    return [
        MonotonicityViolation(
            lower=lower, upper=upper, lower_rate=rates[lower], upper_rate=rates[upper]
        )
        for lower, upper in pairwise(measured)
        if rates[upper] < rates[lower] - tolerance
    ]


RateKind = Literal["call", "read", "write"]


def _numerator(cell: RungCell, kind: RateKind) -> int:
    if kind == "call":
        return cell.calling_runs
    if kind == "read":
        return cell.reading_runs
    if kind == "write":
        return cell.writing_runs
    raise ValueError(f"unknown rate kind {kind!r}")


def pooled_rates(
    cells: Sequence[RungCell], variant: str, *, kind: RateKind = "call"
) -> dict[str, float]:
    """P(``kind`` | variant) per rung, POOLED over every task cell of that ``(rung, variant)``:
    the sum of legs that called / read / wrote over the sum of measured legs.

    Pooled, not last-wins and not a mean of per-cell rates. The first staged fire's gate block
    built ``{rung: cell.call_rate}`` over eight task cells per rung and reported the eighth
    cell's 4/5 as "R0 = 0.8" while the pooled rate was 16/40. A mean of cell rates would weight a
    cell with one measured leg the same as one with five. Rungs whose measured denominator is zero
    are omitted, never reported as 0.0."""
    numerator: dict[str, int] = {}
    measured: dict[str, int] = {}
    for cell in cells:
        if cell.variant != variant:
            continue
        numerator[cell.rung] = numerator.get(cell.rung, 0) + _numerator(cell, kind)
        measured[cell.rung] = measured.get(cell.rung, 0) + cell.measured_runs
    return {rung: numerator[rung] / measured[rung] for rung in measured if measured[rung]}


def discrimination_margins(
    cells: Sequence[RungCell], *, kind: RateKind = "read"
) -> dict[str, float]:
    """``d(rung) = P(read | necessary) - P(read | unnecessary)`` per rung — E1's PRIMARY endpoint.

    On READS by default (mem-zfm0m item 2). The twin corpus manipulates whether a recall is
    needed; a write is the agent storing what it just learned, the same act on both halves, so
    a write on each side moves both rates together and drags an any-call margin toward zero
    without saying anything about discrimination. The any-call margin is still computed
    (``kind="call"``) and reported beside the endpoint, never as it.

    Only rungs with BOTH halves measured get a margin: a margin computed against a missing half
    would be a rate wearing the endpoint's name, and E1's whole point is that those two numbers
    can move independently."""
    necessary = pooled_rates(cells, VARIANT_NECESSARY, kind=kind)
    unnecessary = pooled_rates(cells, VARIANT_UNNECESSARY, kind=kind)
    return {rung: necessary[rung] - unnecessary[rung] for rung in necessary if rung in unnecessary}


def _rates_by_variant(cells: Sequence[RungCell], kind: RateKind) -> dict[str, dict[str, float]]:
    return {
        VARIANT_NECESSARY: pooled_rates(cells, VARIANT_NECESSARY, kind=kind),
        VARIANT_UNNECESSARY: pooled_rates(cells, VARIANT_UNNECESSARY, kind=kind),
    }


def call_rate_gates(cells: Sequence[RungCell], *, tolerance: float = 0.0) -> dict[str, Any]:
    """The gate block E1's summary carries — ALWAYS non-empty, including on a run that measured
    nothing, because "no gate block" and "the gates passed" must not look alike to a reader."""
    necessary = pooled_rates(cells, VARIANT_NECESSARY)
    violations = monotonicity_violations(necessary, tolerance=tolerance)
    margins = discrimination_margins(cells)
    floor = necessary.get(RUNG_IDS[0])
    return {
        "endpoint": "discrimination_margin",
        "monotonicity": {
            "rungs_measured": sorted(necessary, key=_rung_index),
            "call_rate_by_rung": necessary,
            "tolerance": tolerance,
            "violations": [asdict(v) | {"drop": v.drop} for v in violations],
            "violation_pairs": [f"{v.lower}->{v.upper}" for v in violations],
            "monotone": not violations,
            # A grid whose every leg went unmeasured has no rungs, hence no adjacent pairs, hence
            # no violations — and would otherwise publish `monotone: true` under a reason that
            # reads as a passing gate. Untested is not passed.
            "comparable": len(necessary) >= 2,
            "reason": (
                "; ".join(v.describe() for v in violations)
                if violations
                else (
                    "call rate is non-decreasing across every adjacent measured rung"
                    if len(necessary) >= 2
                    else f"monotonicity is UNTESTED: {len(necessary)} rung(s) measured, so there "
                    "is no adjacent pair to compare. Not a pass"
                )
            ),
        },
        "discrimination": {
            # The PRIMARY endpoint, reported beside the raw rate precisely so a rate lift with a
            # flat margin cannot be read as the ladder working.
            "counts": "reads",
            "margin_by_rung": margins,
            "read_rate_by_rung": _rates_by_variant(cells, "read"),
            "any_call_margin_by_rung": discrimination_margins(cells, kind="call"),
            "note": (
                "d(rung) = P(read | necessary) - P(read | unnecessary). A rung that lifts the raw "
                "call rate while d stays flat bought nothing. Writes are excluded from d: the "
                "agent storing what it learned is the same act on both halves, so it moves both "
                "rates together (any_call_margin_by_rung shows the diluted number)."
            ),
        },
        "write_rate": {
            "by_rung": _rates_by_variant(cells, "write"),
            "note": (
                "P(acknowledged write | measured leg) per half, REPORTED beside the margin and "
                "never inside it. A write counts only on bd's acknowledgement or a native "
                "memory-file write (mem-8fv4t)."
            ),
        },
        "guidance_token_adjustment": {
            "guidance_words_by_rung": {rung: guidance_words(rung) for rung in RUNG_IDS},
            "note": (
                "REPORTED, never subtracted here: the guidance block is longer at every higher "
                "rung by construction, so a per-rung token cost carries the treatment's own "
                "length. Subtract these words explicitly before comparing cost across rungs."
            ),
        },
        "tool_affordance_floor": {
            "rung": RUNG_IDS[0],
            "call_rate": floor,
            "note": (
                "R0 carries NO guidance text; the agent still sees an allowlisted memory tool. A "
                "high R0 rate means the tool's NAME is the treatment, so R0 is the affordance "
                "FLOOR and not a zero. The tool is deliberately not renamed: a rename moves the "
                "argv and invalidates every cached cell."
            ),
        },
    }


def assert_gates_ride_outside_metrics(summary: Mapping[str, Any]) -> None:
    """Refuse a summary that smuggled the gate block into a per-cell metric vector.

    The acceptance criterion is exactly this shape (``.call_rate_gates`` non-empty AND
    ``.cells[0].metrics.call_rate_gates`` null), and it is a criterion because a validity verdict
    inside ``metrics()`` gets averaged with the cells it judges. Checked at the WRITE boundary so
    a summary that violates it cannot be published, not merely noticed in review."""
    if not summary.get(GATE_KEY):
        raise ValueError(f"summary carries no {GATE_KEY!r} block — a run without gates is unread")
    for row in summary.get("cells", []):
        metrics = row.get("metrics") or {}
        if GATE_KEY in metrics:
            raise ValueError(
                f"cell {row.get('rung')}/{row.get('variant')} carries {GATE_KEY!r} INSIDE its "
                "metrics — the gate block rides on the summary, never in a metric vector where it "
                "would be averaged with the cells it judges"
            )


def corpus_fingerprint(tasks: Sequence[ToolReqRealAgentTask]) -> str:
    """The digest of the TASKS a grid measured on, in a stable order.

    Part of the resume identity for the reason the model and the surface are: a corpus edit
    (rewording an unnecessary twin so it stops withholding its subjects, mem-zfm0m) changes what a
    cell means, and a resume that carried the old cells forward would land two different
    measurements in one grid and report them as one.

    Built on ``task_fingerprint``, which already hashes the whole goal step — the prompt sent and
    the checks it is graded against — so a corpus edit this rig cannot see in the authored values
    still moves it. Sorted: the corpus is a SET of tasks here, and the order ``load_twin_corpus``
    happens to return them in is not a measured input."""
    return digest(sorted(task_fingerprint(task) for task in tasks))


def summarize(
    cells: Sequence[RungCell],
    *,
    model: str,
    dry_run: bool,
    repeats: int,
    tolerance: float = 0.0,
    cli_version: str = "",
    corpus: str = "",
) -> dict[str, Any]:
    """The E1 summary: the cells, and the gate block BESIDE them.

    ``cli_version`` and ``corpus`` are the other two halves of the resume identity. They default
    to empty rather than being computed here: ``resolve_cli_version`` spawns, and a summary
    function that spawns makes every free path pay for a binary it is not measuring on. The PAID
    caller supplies them, and ``resume_cells`` refuses an artifact whose identity is blank."""
    summary = {
        "experiment": "e1-guidance-ladder",
        "channel": CHANNEL.value,
        "model": resolve_model(model) or "cli-default",
        "surface_fingerprint": surface_fingerprint(),
        # The R0 pin is NOT inside `surface_fingerprint`: that hashes the recognizer policy
        # and the fact that a config dir is pinned, never the dir's CONTENTS. A grid counted
        # with R0 unpinned measured a different floor, so the pin table gets its own field.
        "settings_fingerprint": rung_settings_fingerprint(),
        "execution_protocol": EXECUTION_PROTOCOL_VERSION,
        "cli_version": cli_version,
        "corpus_fingerprint": corpus,
        "dry_run": dry_run,
        "repeats": repeats,
        "paid": all(cell.paid for cell in cells) if cells else False,
        # sorted(set(...)), not one entry per cell: with eight tasks per variant this field
        # repeated "R0" thirty-two times and named itself the rungs of the grid.
        "rungs": sorted({cell.rung for cell in cells}),
        "cells": [cell.row() for cell in cells],
        GATE_KEY: call_rate_gates(cells, tolerance=tolerance),
    }
    assert_gates_ride_outside_metrics(summary)
    return summary


# --------------------------------------------------------------------------------------
# execution
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LegScore:
    """What one leg's tool calls count for: memory calls (blocks), reads, acknowledged writes,
    and the verbs reached for, in stream order."""

    memory_calls: int = 0
    read_calls: int = 0
    write_calls: int = 0
    verbs: tuple[str, ...] = ()


# The score of a leg that produced no stream to count -- an errored leg's record.
_NO_SCORE = LegScore()


def score_leg(calls: Sequence[ToolCall], *, config_dir: Path | None) -> LegScore:
    """Score one leg's tool calls — the pure half of ``run_rung_cell``, so a truncated leg's
    partial stream is scored by the same arithmetic as a complete one.

    BOTH affordances count. The bd shim is the one this rig provisions; the native memory file is
    the one the model reaches for first (mem-gj0pc), and scoring only the former reported an agent
    that said "let me check memory" and did as a ZERO. The question the rung ladder asks is
    whether the agent reaches for memory AT ALL, not whether it picks the harness's preferred door.

    A WRITE is counted only on bd's own acknowledgement (``MemoryInvocation.is_accepted_write``),
    never on the verb: the 160-leg fire's single "endogenous write" was a REFUSED
    ``bd remember list`` (mem-8fv4t). A ``bd remember <bare-existing-key>`` bd answered as a recall
    counts as the READ it was. The refused call is still a memory CALL — the agent reached for
    the tool, and that choice is the ladder's endpoint — it just stored nothing.

    A memory CALL is a tool call that reached memory through EITHER door, counted once
    (``memory_reaching_calls``): a Bash block that runs ``bd recall`` and then ``cat``s MEMORY.md
    is one reach (mem-zfm0m item 3), while its reads and writes count per door."""
    native = native_memory_accesses(calls, config_dir=config_dir)
    invocations = memory_invocations(calls)
    reads = sum(1 for inv in invocations if inv.is_read or inv.is_recall_by_result) + sum(
        1 for access in native if access.is_read
    )
    writes = sum(1 for inv in invocations if inv.is_accepted_write) + sum(
        1 for access in native if access.is_write
    )
    return LegScore(
        memory_calls=memory_reaching_calls(calls, config_dir=config_dir),
        read_calls=reads,
        write_calls=writes,
        verbs=(*endogenous_memory_verbs(calls), *(access.verb for access in native)),
    )


def _silent_runner(argv: Sequence[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
    """The dry-run stand-in: an agent that makes NO tool call.

    Deliberately not a cooperating agent. A simulator that "recalls when the guidance says to"
    would reproduce E1's entire finding by construction, which is how a wiring check gets read as
    a result. So the free path measures a call rate of 0.0 at every rung and proves only the
    plumbing — the argv, the surface, the counter, the gates — exactly what ``--dry-run`` claims."""
    return subprocess.CompletedProcess(list(argv), 0, serialize_stream([result_event()]), "")


def _bought(leg: int) -> str:
    return (
        f"{leg} leg(s) of this cell were already paid for; the cell is incomplete, so a resume "
        "re-buys it and those legs are spent"
    )


LegStatus = Literal["ok", "timeout", "error"]


@dataclass(frozen=True)
class _LegOutcome:
    """What ONE leg produced, before the cell decides what it means.

    ``status`` is what the leg record will say; ``score`` and ``stream`` are the evidence (a
    timed-out leg keeps what it wrote before the bound, ``truncated``); ``quota_refusal`` is
    set when the account refused the call — an ``error`` the cell must HALT on rather than
    tolerate, phrased as the reason the halt will quote — and ``cause`` is the exception the
    refusal was read off, so the halt is raised FROM it and a reader of the halt's cause chain
    reaches the CLI's own result event (review G6)."""

    status: LegStatus
    detail: str = ""
    stream: str = ""
    score: LegScore = _NO_SCORE
    cli_version: str = ""
    truncated: bool = False
    quota_refusal: str = ""
    cause: HeadlessAgentError | None = None
    native_memory_pinned_off: bool = False


def _run_leg(
    task: ToolReqRealAgentTask,
    step: SequenceStep,
    *,
    rung: str,
    leg: int,
    model: str,
    dry_run: bool,
    timeout_s: float,
    runner: Runner | None,
    expect_cli_version: str,
    corpus_dir: Path | None,
) -> _LegOutcome:
    """Spend one leg: mint the sandbox and the store, refuse a reachable corpus, run the agent,
    and classify what came back. Nothing here counts toward the cell or writes a record; the
    caller owns accumulation and emission. Raises ``RigHaltError`` when the leg ran on a CLI
    other than the one the fire is pinned to."""
    with (
        tempfile.TemporaryDirectory(prefix="membench-memory-") as root,
        paid_sandbox(f"e1-{rung.lower()}-") as sandbox,
    ):
        surface = provision_memory_tool(Path(root), sandbox=sandbox)
        # The rung's own settings.json, written into the config dir the surface just minted and
        # BEFORE the agent is spawned -- `provision_memory_tool` mints it empty for every arm, so
        # the pin belongs to the rung, not to the surface. Read straight back off disk: what the
        # leg reports having run under is the file the agent would have read.
        config_dir = surface.config_dir
        if config_dir is None:
            # `provision_memory_tool` always pins one; a surface without it is a rig fault, not a
            # leg to run unpinned. Silently skipping the seed would report R0 as silent while the
            # CLI's own memory prompt was still on -- the exact reading the pin exists to fix.
            raise RigHaltError(
                f"{rung}/{task.variant}/{task.work_id}: the provisioned surface pins no config "
                "dir, so the rung's settings cannot be seeded and this leg cannot say what the "
                "agent's own memory system was doing while it ran."
            )
        settings = rung_settings(rung)
        if settings:
            seed_config_dir(config_dir, settings)
        pinned_off = native_memory_pinned_off(config_dir)

        def outcome(**fields: Any) -> _LegOutcome:
            """Every exit from this leg carries the pin it ran under. One factory rather than the
            field repeated at six returns, so a seventh cannot forget it."""
            return _LegOutcome(native_memory_pinned_off=pinned_off, **fields)

        # PWD pinned to the sandbox: the agent merges this over the operator's environment,
        # whose PWD is the shell's cwd -- the checkout the corpus lives in. The kernel's cwd
        # is the sandbox regardless; the variable is what a child shell reports and what
        # this guard would otherwise refuse on every operator run.
        env = {**surface.env(), "PWD": str(sandbox)}
        if corpus_dir is not None:
            assert_corpus_unreachable(
                env={**os.environ, **env}, cwd=sandbox, corpus_root=corpus_dir
            )
        spawn = runner if runner is not None else (_silent_runner if dry_run else None)
        agent = HeadlessClaudeAgent(
            model=model,
            runner=spawn if spawn is not None else run_in_session,
            cwd=str(sandbox),
            env=env,
            memory_channel=CHANNEL,
            disallowed_tools=HOST_DENIED_TOOLS,
            timeout_s=timeout_s,
        )
        ctx = StepContext(
            trial_id=f"e1-{rung}-{task.result_id}-{leg}",
            session_id=f"e1-{rung}-{task.result_id}",
            step_id=step.step_id,
        )
        try:
            result = agent.run_step(step, {}, ctx)
        except HeadlessAgentError as exc:
            # THREE outcomes, and which one this is decides whether the fire continues:
            #   quota   -> the account is out, every further leg would fail the same way and
            #              be billed as nothing. Halt CLEANLY so the caller persists what it
            #              bought (the second staged fire lost cell 21's legs to this).
            #   timeout -> the leg is UNMEASURED, not silent. Scoring it as a non-calling run
            #              biases the rate toward the null this series exists to refuse.
            #   other   -> also unmeasured, tolerated per leg, but a rig that is simply broken
            #              fails EVERY leg, so a run of them halts rather than filling the
            #              grid with "errors" that read as measured zeros.
            if is_quota_halt(exc):
                return outcome(
                    status="error",
                    detail=str(exc),
                    quota_refusal=f"the account refused the call ({exc})",
                    cause=exc,
                )
            timeout = spawn_timeout_of(exc)
            if timeout is None:
                return outcome(status="error", detail=str(exc))
            # The bound cut the stream, it did not erase it. What the agent did BEFORE the
            # bound is scored and persisted (the first fire threw it away and a leg that had
            # reached for memory twice was persisted as an empty stream, mem-zfm0m); the leg
            # still stays out of the cell, whose rates pool only streams that ended.
            partial = timeout_partial_stdout(timeout)
            return outcome(
                status="timeout",
                detail=str(exc),
                stream=partial,
                score=score_leg(tool_calls_from_stream(partial), config_dir=surface.config_dir),
                truncated=True,
            )
        # EXIT 0 IS NOT PROOF THE RUN HAPPENED. `run_checked` raises on a non-zero exit and
        # nothing else, so a CLI that reports its own failure on the result event and still
        # exits 0 arrives HERE, with an empty tool-call list, and counts as a measured leg on
        # which the agent chose not to touch memory. That is the one reading this series
        # exists to refuse, and it would be manufactured by the rig rather than the agent.
        # Same structural field the raising path is classified on, read one line earlier.
        stream = result.raw_stream or ""
        if stream_api_error_status(stream) in QUOTA_STATUSES:
            return outcome(
                status="error",
                detail=f"exit 0 with api_error_status={stream_api_error_status(stream)}",
                stream=stream,
                quota_refusal=(
                    f"the account refused the call (api_error_status="
                    f"{stream_api_error_status(stream)}) and the CLI still exited 0"
                ),
            )
        if stream_is_error(stream):
            return outcome(
                status="error",
                detail="the CLI exited 0 but declared its own run failed (is_error)",
            )
        # The instrument that ran THIS leg, not the one a pre-flight probe asked about. A
        # binary upgraded mid-sweep measures the later cells on a different tool surface and
        # pools both into one rate; the resume identity catches it BETWEEN fires and cannot
        # see it within one.
        leg_cli = stream_cli_version(stream) or ""
        if expect_cli_version and leg_cli and leg_cli != expect_cli_version:
            raise RigHaltError(
                f"{rung}/{task.variant}/{task.work_id} leg {leg}: this leg ran on CLI "
                f"{leg_cli!r}, the fire is pinned to {expect_cli_version!r}. The binary "
                f"changed mid-sweep, so the cells bought and the cells still to buy are not "
                f"the same measurement. {_bought(leg)}."
            )
        return outcome(
            status="ok",
            stream=stream,
            score=score_leg(result.tool_calls, config_dir=surface.config_dir),
            cli_version=leg_cli,
        )


def _one_pin(pinned: set[bool], *, rung: str, task: ToolReqRealAgentTask) -> bool:
    """The single pin state the cell's legs ran under, or a REFUSAL if they disagree."""
    if len(pinned) > 1:
        raise RigHaltError(
            f"{rung}/{task.variant}/{task.work_id}: legs of one cell ran with the CLI's own "
            "memory system both pinned off and left on. That is two different floors in one "
            "rate; the cell is not a measurement."
        )
    return pinned.pop() if pinned else False


def run_rung_cell(
    task: ToolReqRealAgentTask,
    *,
    rung: str,
    repeats: int,
    model: str,
    dry_run: bool,
    timeout_s: float = 600.0,
    runner: Runner | None = None,
    on_leg: Callable[[LegRecord], None] | None = None,
    streak: UnmeasuredStreak | None = None,
    expect_cli_version: str = "",
    corpus_dir: Path | None = None,
) -> RungCell:
    """Run one ``(rung, task-variant)`` cell and count the memory calls the agent CHOSE to make.

    Each repeat gets a fresh neutral sandbox and a fresh memory store OUTSIDE it (the store the
    cwd wipe cannot reach, ``tool_surface.provision_memory_tool``). Nothing is seeded into the
    store and no memory is surfaced in the prompt: this measures DISPOSITION, so the arm must not
    hand the agent a reason to call that the rung did not give it.

    The sandbox is minted EMPTY and stays that way: the task reaches the agent through the prompt
    (``rung_step``), never through files, so nothing from the corpus is copied or linked into
    the cwd. ``corpus_dir`` is the corpus the task was loaded from; when it is given, every leg
    is checked BEFORE the spawn for a path into it in the child's env or cwd tree
    (``sandbox.assert_corpus_unreachable``, mem-zfm0m item 7) and refused with nothing spent.
    None means the caller has no corpus on disk (the harness-side fixtures that build tasks in
    memory); the paid entry points require it.

    ``paid`` is false whenever a runner was substituted or ``dry_run`` is set — the same rule
    ``e1_smoke`` publishes rows under, and for the same reason: an injected runner's call rate is
    the fixture's, not an agent's."""
    calling = 0
    reading = 0
    writing = 0
    total = 0
    reads = 0
    writes = 0
    timed_out = 0
    errored = 0
    # What the legs actually ran under, read off each minted config dir. A SET, so legs that
    # disagree are a refusal rather than a coin flip: every leg of a cell seeds the same rung
    # table, so a split means the seeding stopped being deterministic and the cell would
    # publish one pin for legs that had two.
    pinned: set[bool] = set()
    streak = UnmeasuredStreak() if streak is None else streak
    verbs: list[str] = []
    step = rung_step(task, rung)

    def _emit(record: LegRecord) -> None:
        if on_leg is not None:
            on_leg(record)

    def _unmeasured(leg: int, outcome: _LegOutcome) -> None:
        """Record one leg the CELL cannot count, and halt if the rig has stopped working.

        A timed-out leg arrives with the stream it wrote before the bound and that stream's
        score: the evidence is kept whole and counted on the record, and the leg stays out of
        the cell, whose rates pool only legs whose streams ended."""
        print(
            f"[{outcome.status}] {rung}/{task.variant}/{task.work_id} leg {leg}: {outcome.detail}",
            file=sys.stderr,
            flush=True,
        )
        _emit(
            LegRecord(
                rung=rung,
                variant=task.variant,
                work_id=task.work_id,
                leg=leg,
                status=outcome.status,
                memory_calls=outcome.score.memory_calls,
                read_calls=outcome.score.read_calls,
                write_calls=outcome.score.write_calls,
                verbs=outcome.score.verbs,
                stream=redact_credentials(outcome.stream),
                detail=outcome.detail,
                truncated=outcome.truncated,
                native_memory_pinned_off=outcome.native_memory_pinned_off,
            )
        )
        if streak.unmeasured():
            raise RigHaltError(
                f"{rung}/{task.variant}/{task.work_id}: {streak.count} consecutive legs measured "
                f"NOTHING — this is a broken rig, not a flaky one, and tolerating it leg by leg "
                f"buys a grid of unmeasured cells. {_bought(leg)}. Last: {outcome.detail}"
            )

    for i in range(repeats):
        outcome = _run_leg(
            task,
            step,
            rung=rung,
            leg=i,
            model=model,
            dry_run=dry_run,
            timeout_s=timeout_s,
            runner=runner,
            expect_cli_version=expect_cli_version,
            corpus_dir=corpus_dir,
        )
        pinned.add(outcome.native_memory_pinned_off)
        if outcome.quota_refusal:
            _emit(
                LegRecord(
                    rung=rung,
                    variant=task.variant,
                    work_id=task.work_id,
                    leg=i,
                    status=outcome.status,
                    detail=outcome.detail,
                    stream=redact_credentials(outcome.stream),
                    native_memory_pinned_off=outcome.native_memory_pinned_off,
                )
            )
            raise QuotaHaltError(
                f"{rung}/{task.variant}/{task.work_id} leg {i}: {outcome.quota_refusal}. "
                f"Nothing further can be measured; resume when it resets. {_bought(i)}."
            ) from outcome.cause
        if outcome.status != "ok":
            if outcome.status == "timeout":
                timed_out += 1
            else:
                errored += 1
            _unmeasured(i, outcome)
            continue
        streak.measured()
        score = outcome.score
        total += score.memory_calls
        calling += 1 if score.memory_calls else 0
        reading += 1 if score.read_calls else 0
        writing += 1 if score.write_calls else 0
        reads += score.read_calls
        writes += score.write_calls
        verbs.extend(score.verbs)
        _emit(
            LegRecord(
                rung=rung,
                variant=task.variant,
                work_id=task.work_id,
                leg=i,
                status="ok",
                memory_calls=score.memory_calls,
                read_calls=score.read_calls,
                write_calls=score.write_calls,
                verbs=score.verbs,
                stream=redact_credentials(outcome.stream),
                cli_version=outcome.cli_version,
                native_memory_pinned_off=outcome.native_memory_pinned_off,
            )
        )
    return RungCell(
        rung=rung,
        variant=task.variant,
        runs=repeats,
        calling_runs=calling,
        memory_calls=total,
        read_calls=reads,
        write_calls=writes,
        reading_runs=reading,
        writing_runs=writing,
        paid=not dry_run and runner is None,
        verbs=tuple(verbs),
        work_id=task.work_id,
        timed_out_runs=timed_out,
        errored_runs=errored,
        native_memory_pinned_off=_one_pin(pinned, rung=rung, task=task),
    )


class QuotaHaltError(RuntimeError):
    """The account refused the call. Distinct from every other failure because it is not a defect
    and not a measurement: nothing can be bought until it resets, so the fire persists what it has
    and stops, rather than burning the remaining cells into unmeasured legs."""


class RigHaltError(RuntimeError):
    """Consecutive legs went UNMEASURED — the rig is broken, not flaky. A halt, for the reason the
    per-leg tolerance exists at all: a failure tolerated everywhere is a grid of cells that
    measured nothing while reporting a rate."""


@dataclass
class UnmeasuredStreak:
    """Consecutive legs that returned no measurement, counted ACROSS cell boundaries.

    Mutable and shared on purpose, and it counts TIMEOUTS TOO. Both properties are fixes for the
    same hole: a per-cell counter that resets on a timeout cannot see the two rigs that actually
    burn a budget. An account whose every spawn times out fills every cell with five unmeasured
    legs and never trips a limit that only counts errors; a rig that fails on alternating causes,
    or across a cell boundary, never reaches three of either kind in one place. Both spend the
    whole authorization at up to ``timeout_s`` a leg and leave a grid of cells the next resume
    drops and re-buys.

    The distinction the counters keep (``timed_out_runs`` vs ``errored_runs``) is about what a leg
    MEANS and stays. This is about whether the rig is still worth spending on, and for that
    question the two are the same answer: nothing was measured."""

    limit: int = 3
    count: int = 0

    def measured(self) -> None:
        self.count = 0

    def unmeasured(self) -> bool:
        """Record an unmeasured leg; True once the rig has failed ``limit`` times in a row."""
        self.count += 1
        return self.count >= self.limit


# The api_error_status values that mean "the account will not serve this call": rate limit /
# session limit (429), unauthenticated or revoked token (401), forbidden (403), overloaded (529).
# Read off the STREAM'S OWN FIELD, never off the message: `run_checked` redacts and truncates its
# diagnosis by design, so matching prose there is both fragile and exactly the keyword heuristic
# this repo's ZFC line forbids in the deterministic layer.
QUOTA_STATUSES: frozenset[int] = frozenset({401, 403, 429, 529})


def stream_result_events(stream: str) -> list[dict[str, Any]]:
    """The ``type=result`` events in a stream, in order.

    ONE scanner, because both things read off a result event -- the api status and the error flag
    -- must agree about which events count. Scanning every event instead would pick up a tool
    result that happens to carry an HTTP status and halt a fire on a web fetch."""
    events: list[dict[str, Any]] = []
    for line in stream.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            events.append(event)
    return events


def stream_api_error_status(stream: str) -> int | None:
    """The ``api_error_status`` the CLI stamped on its own result event, or ``None``."""
    for event in stream_result_events(stream):
        status = event.get("api_error_status")
        if isinstance(status, int):
            return status
    return None


def stream_is_error(stream: str) -> bool:
    """Whether the CLI declared its OWN run failed, on the stream's result event.

    The field, not the prose. It exists because ``is_error`` and the process exit code are
    SEPARATE claims: every refusal observed so far (429 session limit, 401 bad token) also exits
    non-zero, so ``run_checked`` raises and the caller classifies it on the way past -- but nothing
    in the contract makes that so, and the arm that reads a stream for memory calls is reached by
    a leg that exited 0. A dead run counted as a measured silent one is scored as evidence the
    agent chose not to call memory, which is the exact reading this experiment exists to refuse."""
    return any(event.get("is_error") is True for event in stream_result_events(stream))


def is_quota_halt(exc: HeadlessAgentError) -> bool:
    """Whether the CLI failed because the ACCOUNT refused, not because the rig is broken.

    Decided on the child's stream, which ``run_checked`` attaches to its non-zero diagnosis. A
    failure with no child attached (missing binary, OSError, timeout) is not a quota refusal, and
    saying so is the honest answer: this returns False and the caller treats it as what it is."""
    child = child_of(exc)
    if child is None:
        return False
    return stream_api_error_status(child.stdout or "") in QUOTA_STATUSES


def spawn_timeout_of(exc: HeadlessAgentError) -> subprocess.TimeoutExpired | None:
    """The spawn timeout under a ``HeadlessAgentError``, or None when it is anything else.

    Decided on the CAUSE CHAIN (``spawn.run_checked`` raises ``from subprocess.TimeoutExpired``),
    not on the message. Only the timeout is tolerated per leg: a missing CLI, a refused token, or
    a non-zero exit is a broken rig, and a broken rig tolerated leg by leg is a cell full of
    "timeouts" that reads as a measured zero. The cause itself is returned, not a bool, because
    it carries the partial stdout the leg is scored from."""
    cause = exc.__cause__
    return cause if isinstance(cause, subprocess.TimeoutExpired) else None


def is_spawn_timeout(exc: HeadlessAgentError) -> bool:
    """Whether a ``HeadlessAgentError`` is the spawn timeout and nothing else."""
    return spawn_timeout_of(exc) is not None


# --------------------------------------------------------------------------------------
# the paid preflight (mechanism-fires at the TOP rung) and the staged spend
# --------------------------------------------------------------------------------------

OK_FIRED = "FIRED"
HALT_NO_CALL = "NO-MEMORY-CALL"
HALT_UNPAID = "UNPAID"
HALT_UNMEASURED = "UNMEASURED"

# The rung the preflight runs at. The TOP one, on purpose: if the STRONGEST guidance cannot get a
# single memory call out of the agent, no interior rung can, and every interior cell would buy an
# uninterpretable zero (the mem-lvp.24 null this gate family exists to refuse).
PREFLIGHT_RUNG = RUNG_IDS[-1]

# The staged fire the bead authorizes FIRST: the two ENDS of the ladder only, at T=8 tasks and
# R=5 repeats over both corpus halves — 2 x 8 x 5 x 2 = 160 real calls. If R4 shows zero memory
# calls there, the interior rungs are NOT run and the null IS the result.
STAGED_RUNGS: tuple[str, ...] = (RUNG_IDS[0], RUNG_IDS[-1])
STAGED_TASKS = 8
STAGED_REPEATS = 5

# The ladder slices a fire may be authorized to buy. R1-R3 exist in RUNG_TEXT and in RUNG_SETTINGS
# and every function under the fire path already takes a `rungs` argument, but the fire itself only
# ever passed STAGED_RUNGS: reaching the interior meant editing a module constant on the one path
# in this package that spends money. A NAMED table rather than a free-form `--rungs` keeps what a
# fire may buy something a bead authorizes, not something a caller composes at the prompt.
# `ends` and `interior` partition `full`, so no rung is unreachable and none is bought twice.
STAGED_SLICES: Mapping[str, tuple[str, ...]] = types.MappingProxyType(
    {
        "ends": STAGED_RUNGS,
        "interior": tuple(RUNG_IDS[1:-1]),
        "full": RUNG_IDS,
    }
)
DEFAULT_STAGE = "ends"


def staged_rungs(stage: str) -> tuple[str, ...]:
    """The rungs named by an authorized slice. Unknown names are an error, never a default: a
    typo that silently fell back to `ends` would spend the wrong grid's money."""
    if stage not in STAGED_SLICES:
        raise ValueError(
            f"unknown stage {stage!r}: the authorized slices are {list(STAGED_SLICES)}"
        )
    return STAGED_SLICES[stage]


class PreflightHaltError(RuntimeError):
    """The preflight's refusal to authorize the interior sweep, carrying its diagnosis.

    A distinct type for ``toolreq_builtin_grid.PreflightHaltError``'s reason: a preflight halt has
    measured nothing and spent one cycle, so it wants halt counsel, not resume counsel."""

    def __init__(self, kind: str, line: str) -> None:
        super().__init__(line)
        self.kind = kind
        self.line = line


def planned_call_count(*, rungs: Sequence[str], n_tasks: int, repeats: int, n_variants: int) -> int:
    """The real ``claude -p`` calls a fire makes — one leg per repeat, so the product. This is the
    number a human authorizes money against, so it is computed, not quoted.

    ``n_variants`` is not defaulted to the twin design. ``staged_cells`` iterates whatever variant
    labels the corpus carries, and a price that assumed two of them quoted half the bill for three
    and twice the bill for one."""
    return len(rungs) * n_tasks * repeats * n_variants


def per_variant_task_count(tasks: Sequence[ToolReqRealAgentTask]) -> int:
    """The tasks the staged slice takes FROM EACH VARIANT — the smaller half, when they differ.

    ``staged_cells`` slices ``[:n_tasks]`` per variant, so a plan priced off the combined list
    over-counts whenever a variant is short: 6 twin tasks is 3 per variant, and a plan that read
    ``min(6, 8) = 6`` would promise twice the grid it runs."""
    by_variant: dict[str, int] = {}
    for task in tasks:
        by_variant[task.variant] = by_variant.get(task.variant, 0) + 1
    return min(by_variant.values()) if by_variant else 0


def _halt_rule(rungs: Sequence[str]) -> str:
    """What a fire over ``rungs`` may state about the zero-call halt without overpromising."""
    rule = (
        f"if {RUNG_IDS[-1]} shows ZERO memory calls, the interior rungs are NOT run and the "
        "null is the result"
    )
    if not set(rungs) & set(STAGED_SLICES["interior"]):
        return rule
    return (
        f"{rule}; this slice buys interior rungs BEFORE it observes {RUNG_IDS[-1]}, so that "
        f"evidence must ALREADY exist (the {RUNG_IDS[-1]} preflight, or a landed ends fire) -- "
        "this fire does not enforce it"
    )


def staged_plan(
    *, n_tasks_per_variant: int, n_variants: int, stage: str = DEFAULT_STAGE
) -> dict[str, Any]:
    """What the staged fire WOULD spend, priced before anything runs.

    Both counts are keyword-only and named for what they are. ``staged_cells`` slices
    ``[:n_tasks]`` PER VARIANT and iterates every variant label present, so a bare positional int
    that turned out to be a corpus total (or a variant count that turned out to be an assumption)
    prices a different grid than the one that runs. This function is exported, and being unable to
    spell the wrong call is worth more here than brevity.

    The halt rule is NOT the same sentence for every slice. ``staged_cells`` runs the rungs in
    order and there is no mid-fire zero-call halt, so a slice holding an interior rung buys it
    before this fire has any R4 result to read: ``interior`` never sees one, and ``full`` sees its
    own last. For those the rule is a PREREQUISITE on evidence that already exists, and it says so
    rather than promising a halt the fire cannot perform."""
    rungs = staged_rungs(stage)
    tasks = min(n_tasks_per_variant, STAGED_TASKS)
    return {
        "stage": stage,
        "rungs": list(rungs),
        "n_tasks": tasks,
        "repeats": STAGED_REPEATS,
        "n_variants": n_variants,
        "calls": planned_call_count(
            rungs=rungs, n_tasks=tasks, repeats=STAGED_REPEATS, n_variants=n_variants
        ),
        "halt_rule": _halt_rule(rungs),
    }


def priced_plan(
    tasks: Sequence[ToolReqRealAgentTask], *, stage: str = DEFAULT_STAGE
) -> dict[str, Any]:
    """``staged_plan`` for a real corpus, priced off the PER-VARIANT count the fire slices to.

    ``--staged`` priced off ``len(tasks)`` while ``--fire-staged`` priced off
    ``per_variant_task_count``. They agree only where BOTH cap at STAGED_TASKS, which the 16-task
    production corpus does — that is why it survived; below the cap they diverge by the variant
    count (4x on a 3+1 corpus), and the number a human authorized money against was the wrong one.
    Priced and spent go through here now, over the variant labels the corpus carries rather than
    the two the twin design assumes."""
    return staged_plan(
        n_tasks_per_variant=per_variant_task_count(tasks),
        n_variants=len({task.variant for task in tasks}),
        stage=stage,
    )


def grid_keys(
    tasks: Sequence[ToolReqRealAgentTask],
    *,
    rungs: Sequence[str] = STAGED_RUNGS,
    n_tasks: int = STAGED_TASKS,
) -> list[tuple[str, str, str]]:
    """Every ``(rung, variant, work_id)`` cell a fire over ``tasks`` will run.

    Built by the same per-variant slice ``staged_cells`` executes, so the set a resume is checked
    against is the set that will actually be bought — not a second derivation of it that can drift
    from the first."""
    by_variant: dict[str, list[ToolReqRealAgentTask]] = {}
    for task in tasks:
        by_variant.setdefault(task.variant, []).append(task)
    return [
        (rung, variant, task.work_id)
        for rung in rungs
        for variant in sorted(by_variant)
        for task in by_variant[variant][:n_tasks]
    ]


def staged_cells(
    tasks: Sequence[ToolReqRealAgentTask],
    *,
    model: str,
    corpus_dir: Path,
    rungs: Sequence[str] = STAGED_RUNGS,
    n_tasks: int = STAGED_TASKS,
    repeats: int = STAGED_REPEATS,
    timeout_s: float = 600.0,
    runner: Runner | None = None,
    on_cell: Callable[[RungCell], None] | None = None,
    on_leg: Callable[[LegRecord], None] | None = None,
    landed: Sequence[RungCell] = (),
    expect_cli_version: str = "",
) -> list[RungCell]:
    """Execute the staged fire: every ``(rung, variant, task)`` cell, ``repeats`` legs each.

    ``n_tasks`` is applied PER VARIANT, which is what makes the bill the priced one.
    ``staged_plan`` counts ``len(rungs) * n_tasks * repeats * 2``, so capping the flat list would
    spend half of it and report a whole grid. The variant split is done here for that reason.

    ``on_cell`` is called with each completed cell as it lands; ``landed`` is the resume cache
    (mem-78gwf): cells already paid for, keyed ``(rung, variant, work_id)``, are returned in
    place and not re-run. The caller decides whether a prior artifact is admissible against the
    current rig (``resume_cells``); this function only honours the keys it is handed.

    ONE ``UnmeasuredStreak`` spans the whole fire. A rig that fails every leg fails them across
    cell boundaries too, and a per-cell counter restarted at each cell never reaches its limit —
    it buys the entire grid one unmeasured cell at a time.

    ``corpus_dir`` is required, not defaulted: this is a paid path, and the corpus-reach guard
    it feeds (``run_rung_cell``) must not be skippable by omission."""
    streak = UnmeasuredStreak()
    by_variant: dict[str, list[ToolReqRealAgentTask]] = {}
    for task in tasks:
        by_variant.setdefault(task.variant, []).append(task)
    done = {cell.key: cell for cell in landed}
    cells: list[RungCell] = []
    for rung in rungs:
        for variant in sorted(by_variant):
            for task in by_variant[variant][:n_tasks]:
                prior = done.get((rung, variant, task.work_id))
                if prior is not None:
                    cells.append(prior)
                    continue
                cell = run_rung_cell(
                    task,
                    rung=rung,
                    repeats=repeats,
                    model=model,
                    dry_run=False,
                    timeout_s=timeout_s,
                    runner=runner,
                    on_leg=on_leg,
                    streak=streak,
                    expect_cli_version=expect_cli_version,
                    corpus_dir=corpus_dir,
                )
                cells.append(cell)
                if on_cell is not None:
                    on_cell(cell)
    return cells


def preflight_verdict(result: Mapping[str, Any]) -> tuple[str, str]:
    """Classify ONE preflight cycle's result row into its ``(kind, line)`` — the halt logic, as a
    pure function over a row, so it is testable against a FIXTURE without spending anything.

    Same shape and priority argument as ``toolreq_builtin_grid.preflight_kind``: kind and line come
    out of ONE ladder so the kind the gate ACTS on and the line the human READS cannot desync.

    An UNPAID row halts too, however many calls it shows: the mechanism claim is only ever about a
    real ``claude -p``, and a fixture runner's calls are the fixture's
    (``e1_smoke.halt_reason``).

    The UNMEASURED test runs FIRST, and it is the whole reason this gate is not just a
    ``memory_calls`` test. The preflight is one leg: a single spawn timeout returns a row with
    zero calls because nothing ran, and read as NO-MEMORY-CALL that row terminates the experiment
    on the strongest verdict it can reach. A row that measured nothing supports NO verdict."""
    measured = result.get("measured_runs")
    if measured is not None and int(measured) <= 0:
        return HALT_UNMEASURED, (
            f"the preflight leg at {result.get('rung')} measured NOTHING "
            f"({int(result.get('timed_out_runs') or 0)} timed out, "
            f"{int(result.get('errored_runs') or 0)} errored) — no stream came back, so this row "
            "is not evidence the mechanism failed to fire. Re-run it; do not read it as a null"
        )
    calls = int(result.get("memory_calls") or 0)
    if not calls:
        return HALT_NO_CALL, (
            f"the agent made ZERO memory calls at the TOP rung {result.get('rung')} — the "
            "strongest guidance on the ladder did not move it, so no interior rung can, and every "
            "interior cell would buy an uninterpretable zero"
        )
    if not result.get("paid"):
        return HALT_UNPAID, (
            f"{calls} memory call(s) recorded, but this row is not a paid run (paid=false): the "
            "stream came from a simulator or an injected runner, so the mechanism is UNPROVEN"
        )
    return OK_FIRED, f"the memory mechanism fired at {result.get('rung')}: {calls} call(s)"


def preflight(
    task: ToolReqRealAgentTask,
    *,
    model: str,
    corpus_dir: Path,
    rung: str = PREFLIGHT_RUNG,
    timeout_s: float = 600.0,
) -> dict[str, Any]:
    """ONE REAL ``claude -p`` cycle at the top rung, before any interior rung is paid for.

    Deliberately NOT simulated, mirroring ``toolreq_builtin_grid.preflight``: a mechanism check a
    simulator can satisfy checks the simulator. It takes no ``dry_run`` and no ``runner`` for that
    reason — there is no free path through this function, and a caller that wants one is asking for
    a different (and worthless) measurement."""
    cell = run_rung_cell(
        task,
        rung=rung,
        repeats=1,
        model=model,
        dry_run=False,
        timeout_s=timeout_s,
        corpus_dir=corpus_dir,
    )
    return {
        "rung": rung,
        "work_id": task.work_id,
        "variant": task.variant,
        "paid": cell.paid,
        # Carried so `preflight_verdict` can tell "the agent did not call" from "nothing ran".
        # Without them a timed-out leg is a zero-call row, and a zero-call row at the TOP rung is
        # the verdict that ends the experiment.
        "runs": cell.runs,
        "measured_runs": cell.measured_runs,
        "timed_out_runs": cell.timed_out_runs,
        "errored_runs": cell.errored_runs,
        "memory_calls": cell.memory_calls,
        "verbs": list(cell.verbs),
        "native_memory_pinned_off": cell.native_memory_pinned_off,
        "model": resolve_model(model) or "cli-default",
    }


def preflight_gate(result: Mapping[str, Any]) -> dict[str, Any]:
    """Apply ``preflight_verdict`` and RAISE on anything but a fired mechanism."""
    kind, line = preflight_verdict(result)
    if kind != OK_FIRED:
        raise PreflightHaltError(kind, line)
    return {"kind": kind, "line": line, **dict(result)}


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

EXIT_OK = 0
EXIT_HALT = 1
EXIT_REFUSED = 2
EXIT_NO_CORPUS = 4

_PLAN_ONLY = (
    "No fire requested. This printed the PLAN and spent nothing.\n"
    "  paid mechanism check : python -m membench.runner.e1_grid --preflight --rung R4 "
    "--model <id>\n"
    "  staged spend         : python -m membench.runner.e1_grid --staged --model <id>\n"
    "  a named ladder slice : python -m membench.runner.e1_grid --staged "
    "--stage {ends|interior|full}\n"
    "Both need CLAUDE_CODE_OAUTH_TOKEN and a pinned --model, and both spend real money."
)


def _refusal(*, dry_run: bool, model: str) -> str | None:
    """Why a paid path must not run, or ``None``. Checked BEFORE the corpus loads, so a refused
    run costs nothing and reports the reason it was actually refused."""
    if a_paid_run_carries_the_metered_api_key(dry_run=dry_run):
        return REFUSE_API_KEY_SET
    if a_paid_run_needs_a_model(model, dry_run=dry_run):
        return REFUSE_UNPINNED_MODEL
    if not dry_run and not os.environ.get(ENV_OAUTH):
        return (
            f"REFUSING to spend: {ENV_OAUTH} is unset. Source it from an account home and re-run, "
            "or drop the paid flag."
        )
    return None


class ResumeMismatchError(RuntimeError):
    """A partial artifact was produced by a different rig than the one about to resume it."""


def resume_cells(
    summary: Mapping[str, Any],
    *,
    model: str,
    cli_version: str,
    corpus: str,
    repeats: int,
    grid: Sequence[tuple[str, str, str]] | None = None,
) -> list[RungCell]:
    """The cells a partial ``--out`` artifact contributes to a resumed fire.

    Admissible only when EVERY identity field matches the rig now running — the model, the tool
    surface, the per-rung settings pin, the execution protocol, the CLI binary, the corpus, and
    the repeat count. Each of them changes what a leg measures, so a mismatch on any one would
    land two measurements in one grid and report them as one. A blank field is a mismatch, not a
    pass: an artifact that cannot say what produced it cannot be shown to have been produced by
    this.

    Rows are then filtered to what is admissible AS EVIDENCE:

    * unmeasured cells (no leg returned a stream) are dropped — a resume is the chance to buy them
    * unpaid rows are dropped: a dry-run or injected-runner cell is the FIXTURE's call rate, and
      carrying one into a paid grid publishes a simulation as a measurement
    * rows with no ``work_id`` are dropped — they key to ``(rung, variant, "")``, which matches no
      task, so they would be kept forever and their real cells bought every time
    * duplicate keys are a REFUSAL, not a filter: two rows for one cell means two fires wrote the
      same artifact, and silently picking one publishes half of each
    * rows outside ``grid`` (when given) are a refusal for the same reason — a cell the current
      fire will not run cannot be pooled into its rates"""
    want: dict[str, object] = {
        "model": resolve_model(model) or "cli-default",
        "surface_fingerprint": surface_fingerprint(),
        "settings_fingerprint": rung_settings_fingerprint(),
        "execution_protocol": EXECUTION_PROTOCOL_VERSION,
        "cli_version": cli_version,
        "corpus_fingerprint": corpus,
    }
    got = {field: summary.get(field) for field in want}
    blank = [field for field, value in want.items() if not value]
    if blank:
        raise ResumeMismatchError(
            f"this rig cannot state its own {', '.join(blank)}; refusing to match an artifact "
            "against an identity it does not have"
        )
    if got != want:
        differing = {f: (got[f], want[f]) for f in want if got[f] != want[f]}
        detail = "; ".join(f"{f}: artifact={a!r} rig={b!r}" for f, (a, b) in differing.items())
        raise ResumeMismatchError(
            f"partial artifact was produced by a different rig ({detail}). "
            "Not resuming into a different rig's grid."
        )
    got_repeats = summary.get("repeats")
    if got_repeats != repeats:
        raise ResumeMismatchError(
            f"partial artifact ran {got_repeats} repeat(s) per cell, this fire runs {repeats}. "
            "Pooling cells of different leg counts weights them wrong."
        )
    admissible: list[RungCell] = []
    seen: set[tuple[str, str, str]] = set()
    allowed = set(grid) if grid is not None else None
    for row in summary.get("cells", ()):
        cell = RungCell.from_row(row)
        if cell.key in seen:
            raise ResumeMismatchError(
                f"partial artifact carries {cell.key} twice; two fires wrote it and neither "
                "row can be shown to be the one this grid should keep"
            )
        seen.add(cell.key)
        if allowed is not None and cell.key not in allowed:
            raise ResumeMismatchError(
                f"partial artifact carries {cell.key}, which is not a cell of the grid this fire "
                "runs; it cannot be pooled into these rates"
            )
        if cell.runs != repeats:
            # Not poolable and not completable: a cell of 3 legs weights differently from one of
            # 5, and a fire halted mid-cell writes no cell at all, so a row like this came from a
            # different fire or a hand edit. Dropped, which re-buys it — the legs it did pay for
            # survive as leg evidence.
            continue
        if not cell.paid or not cell.work_id or cell.measured_runs <= 0:
            continue
        admissible.append(cell)
    return admissible


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write ``payload`` so a reader never sees a half-written artifact.

    The resume artifact is rewritten after EVERY paid cell, so the window where a truncate-then-
    write is a partial file is a window where a kill costs every cell bought so far — the file the
    next fire reads to avoid re-buying them is the file that got truncated."""
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def write_json_new(path: Path, payload: Mapping[str, Any]) -> Path:
    """Write ``payload`` to ``path``, or to the next free ``.attemptN`` beside it. Never over it.

    A leg file is keyed ``(rung, variant, work_id, leg)``, and a fire halted MID-CELL re-runs that
    cell from leg 0 on resume — same key, different paid leg. An overwrite there destroys the
    evidence for a leg that was bought with real money, which is precisely the artifact this
    directory exists to keep. Mode 0600: the stream is redacted, but an evidence file written into
    a shared /tmp should not also be world-readable."""
    candidate = path
    attempt = 1
    while True:
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            candidate = path.with_name(f"{path.stem}.attempt{attempt}{path.suffix}")
            attempt += 1
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2))
        return candidate


@contextmanager
def out_lock(path: Path) -> Iterator[None]:
    """Hold an exclusive lock beside ``path`` for the life of a fire.

    Two fires on one ``--out`` both resume from it, both re-buy the cells the other is buying, and
    the last writer publishes its own half as the grid. ``O_EXCL`` is the whole mechanism: the
    second fire fails to create the lock and refuses instead of spending."""
    lock = path.with_name(f"{path.name}.lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        # The pid it was written with, so a lock left behind by a killed fire is distinguishable
        # from one a live fire holds. A stale lock and a real collision refuse identically
        # otherwise, and the operator's only move is to delete a lock they cannot check.
        try:
            holder = lock.read_text(encoding="utf-8").strip() or "unknown"
        except OSError:
            holder = "unreadable"
        raise ResumeMismatchError(
            f"{lock} exists: another fire holds {path} (written by pid {holder}). Check whether "
            f"that process is alive (`ps -p {holder}`); if it is not, the lock is stale and safe "
            "to remove."
        ) from exc
    try:
        os.write(fd, f"{os.getpid()}\n".encode())
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


def _fire_staged(args: argparse.Namespace, tasks: Sequence[ToolReqRealAgentTask]) -> int:
    """Execute the staged spend, persisting every leg and every cell as it is paid for.

    Split out of ``main`` because it is the only path in this module that spends money and it is
    the only one with a resume, a lock, an evidence directory and three distinct halts. Reading
    the refusal ladder of a paid path should not mean reading an argument parser first.

    ``--out`` is REQUIRED. Without it this path spends the whole authorization and persists
    nothing: no resume, no leg evidence, no lock, and a summary that exists only on a terminal
    someone has to keep open. A paid run whose result cannot outlive the shell is not a cheaper
    run, it is the same money for no artifact."""
    if args.out is None:
        print(
            "REFUSING to spend: --fire-staged requires --out. It is the resume artifact, the "
            "lock, and the parent of the leg evidence directory; without it a halt loses every "
            "cell bought so far and a re-run re-buys the whole grid.",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    out = args.out
    plan = priced_plan(tasks, stage=args.stage)
    rungs = staged_rungs(args.stage)
    repeats = int(plan["repeats"])
    corpus = corpus_fingerprint(tasks)
    try:
        cli_version = resolve_cli_version()
    except HeadlessAgentError as exc:
        print(f"REFUSING to spend: {exc}", file=sys.stderr)
        return EXIT_REFUSED

    landed: list[RungCell] = []
    # Anything the prior artifact carries that `summarize` does not produce — the identity
    # backfill block that documents WHY a pre-hardening artifact is admissible, most of all.
    # `_persist` rewrites the file from `landed`, so without this the first resumed cell erases
    # the provenance the resume itself depends on.
    carried: dict[str, Any] = {}
    if out.exists():
        try:
            prior = json.loads(out.read_text(encoding="utf-8"))
            produced = set(summarize([], model=args.model, dry_run=False, repeats=repeats))
            carried = {k: v for k, v in prior.items() if k not in produced}
            landed.extend(
                resume_cells(
                    prior,
                    model=args.model,
                    cli_version=cli_version,
                    corpus=corpus,
                    repeats=repeats,
                    grid=grid_keys(tasks, rungs=rungs, n_tasks=int(plan["n_tasks"])),
                )
            )
        except ResumeMismatchError as exc:
            print(f"REFUSED: {exc} (this fire is --stage {args.stage})", file=sys.stderr)
            return EXIT_REFUSED
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            print(f"{out}: not a readable partial artifact: {exc}", file=sys.stderr)
            return EXIT_REFUSED
    print(
        json.dumps(
            {
                "firing": plan,
                "resumed_cells": len(landed),
                "cli_version": cli_version,
                "corpus_fingerprint": corpus,
            },
            indent=2,
        ),
        file=sys.stderr,
    )

    legs_dir = out.with_name(f"{out.name}.legs")
    legs_dir.mkdir(parents=True, exist_ok=True)

    def _summary(cells: Sequence[RungCell]) -> dict[str, Any]:
        return (
            carried
            | summarize(
                cells,
                model=args.model,
                dry_run=False,
                repeats=repeats,
                cli_version=cli_version,
                corpus=corpus,
            )
            # Which slice bought this artifact, so a reader of the file does not have to infer the
            # design from the rungs that happen to be present in it.
            | {"stage": args.stage}
        )

    def _persist() -> None:
        # Partial evidence, written as it is paid for: a fire that dies at cell 21 leaves the
        # 20 cells it bought, and the next --fire-staged with the same --out resumes from them
        # (mem-78gwf). Atomic, because the file that makes the resume possible is the file a
        # kill mid-write would truncate.
        atomic_write_json(out, _summary(landed))

    def _record(cell: RungCell) -> None:
        landed.append(cell)
        print(
            f"[{len(landed)}] {cell.rung}/{cell.variant}/{cell.work_id} "
            f"{cell.calling_runs}/{cell.measured_runs} calling "
            f"({cell.timed_out_runs} timed out, {cell.errored_runs} errored), "
            f"{cell.memory_calls} call(s)",
            file=sys.stderr,
            flush=True,
        )
        _persist()

    def _record_leg(leg: LegRecord) -> None:
        write_json_new(legs_dir / leg.filename, leg.row())

    def _run() -> int:
        try:
            cells = staged_cells(
                tasks,
                model=args.model,
                corpus_dir=args.corpus_dir,
                rungs=rungs,
                n_tasks=int(plan["n_tasks"]),
                repeats=repeats,
                on_cell=_record,
                on_leg=_record_leg,
                landed=list(landed),
                expect_cli_version=cli_version,
            )
        except (QuotaHaltError, RigHaltError) as exc:
            _persist()
            print(f"HALT: {exc}", file=sys.stderr)
            print(
                f"{len(landed)} cell(s) kept in {out}; re-run the same command to resume.",
                file=sys.stderr,
            )
            return EXIT_HALT
        # The final artifact is the GRID, not the accumulator: the two diverge whenever a resume
        # reorders cells, and a caller reading --out must get what stdout printed.
        summary = _summary(cells)
        atomic_write_json(out, summary)
        print(json.dumps(summary, indent=2))
        return EXIT_OK

    try:
        with out_lock(out):
            return _run()
    except ResumeMismatchError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS)
    ap.add_argument("--model", default="")
    ap.add_argument("--rung", default=PREFLIGHT_RUNG, choices=list(RUNG_IDS))
    ap.add_argument(
        "--preflight",
        action="store_true",
        help="ONE real paid cycle at --rung; asserts >=1 memory tool call. Zero is a HALT.",
    )
    ap.add_argument(
        "--stage",
        default=DEFAULT_STAGE,
        choices=list(STAGED_SLICES),
        help=(
            "which authorized slice of the ladder to price or fire: "
            f"{ {name: list(rungs) for name, rungs in STAGED_SLICES.items()} }"
        ),
    )
    ap.add_argument(
        "--staged",
        action="store_true",
        help=(
            f"price the staged spend for --stage at T={STAGED_TASKS}, R={STAGED_REPEATS} over "
            "both corpus halves; spends nothing"
        ),
    )
    ap.add_argument(
        "--fire-staged",
        action="store_true",
        help=(
            "EXECUTE the staged spend priced by --staged. Separate from --staged on purpose: "
            "pricing and spending must not be the same keystroke."
        ),
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "where to write the summary; cells are written as they land, and an existing file "
            "here is RESUMED (its landed cells are kept, not re-bought) when it matches this rig"
        ),
    )
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    paid = args.preflight or args.fire_staged
    refusal = _refusal(dry_run=not paid, model=args.model)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return EXIT_REFUSED

    _, tasks = load_twin_corpus(args.corpus_dir)
    if not tasks:
        print(
            f"no tool-requiring tasks under {args.corpus_dir}: the corpus is missing or empty, so "
            "there is nothing to measure (this is NOT a result)",
            file=sys.stderr,
        )
        return EXIT_NO_CORPUS

    if args.preflight:
        anchor = next((t for t in tasks if t.variant == VARIANT_NECESSARY), tasks[0])
        result = preflight(anchor, model=args.model, corpus_dir=args.corpus_dir, rung=args.rung)
        try:
            gated = preflight_gate(result)
        except PreflightHaltError as exc:
            print(json.dumps({"kind": exc.kind, "line": exc.line, **result}, indent=2))
            print(f"HALT: {exc.line}. Do NOT pay for the interior rungs.", file=sys.stderr)
            return EXIT_HALT
        print(json.dumps(gated, indent=2))
        return EXIT_OK

    if args.fire_staged:
        return _fire_staged(args, tasks)

    if args.staged:
        # Reachable, and deliberately not run here: the staged fire is the orchestrator's to
        # trigger after the preflight clears. Wiring it to run off the same flag that prices it
        # would make an authorization and an execution the same keystroke.
        print(json.dumps({"staged_plan": priced_plan(tasks, stage=args.stage)}, indent=2))
        print(
            "STAGED PLAN PRICED, NOT FIRED: run the preflight first; the staged fire is "
            "authorized separately.",
            file=sys.stderr,
        )
        return EXIT_OK

    plan = {
        "n_tasks": len(tasks),
        "rungs": list(RUNG_IDS),
        "guidance_words_by_rung": {rung: guidance_words(rung) for rung in RUNG_IDS},
        "staged_plan": priced_plan(tasks, stage=args.stage),
        "staged_plans": {name: priced_plan(tasks, stage=name) for name in STAGED_SLICES},
    }
    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        print(json.dumps(plan, indent=2))
        print(_PLAN_ONLY, file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    raise SystemExit(main())
