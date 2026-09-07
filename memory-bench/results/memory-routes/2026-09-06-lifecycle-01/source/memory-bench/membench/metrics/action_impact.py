"""§12.6 action-impact metric: did memory change what the agent *did*?

The metric answers five counterfactual questions about a memory-on run versus its
memory-off twin (the already-produced on/off paired runs of one step). It is the
"Path 1 + Path 3" design ratified for the §12.6 fork (mayor gc-390342):

* **Path 1 — mechanical (ZFC, this module's own code).** ``diff_trajectories``
  index-aligns the two tool-call streams and reports, per behavioral axis
  (tool_choice / plan / output), whether they STRUCTURALLY differ. That is a
  deterministic fact about the traces — never the claim that *memory caused* the
  difference (that is the model's call).

* **Path 3 — judge seam.** ``score_action_impact`` runs a comparative judge over
  the paired runs to emit the five §12.6 booleans + a rationale. The judge is the
  SAME ``complete(prompt) -> str`` seam the bbon comparative judge exposes
  (`membench.bbon.comparative_judge.ComparativeJudge`): reuse
  ``ClaudeComparativeJudge`` for the headless-claude path, the future
  LocalModelStack-backed OSS judge for the §4.1 local path, or
  ``StubComparativeJudge(fn=...)`` to drive the parse path offline in tests.

The mechanical diff is used two ways, exactly as the fork decision specifies:

* **Pre-filter.** A behavioral axis the streams prove IDENTICAL could not have been
  changed by memory, so its boolean is a sound ``False`` set without a judge call.
  When every axis is identical on its OBSERVED data and the terminal statuses agree,
  the whole verdict is ``False`` and no judge is spawned. Unrecorded output is not
  treated as proof of no change — that pair still goes to the judge.
* **Cross-check.** The judge is never allowed to claim memory changed an axis the
  streams prove identical — such a verdict is overridden to ``False``.

ZFC boundary: the structural diff is mechanism; the counterfactual "did *memory*
cause this, and did it prevent a known failure / improve verification" is the
delegated model judgment. Without a judge the semantic axes stay at their ``None``
seam, never guessed.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from membench._claude_cli import first_json_object
from membench.bbon.comparative_judge import ComparativeJudge
from membench.bbon.models import AttemptStep
from membench.schemas.metrics import ActionImpactMetrics

# The five §12.6 verdict keys, in schema order — the judge must return every one.
_VERDICT_KEYS = (
    "memory_changed_tool_choice",
    "memory_changed_plan",
    "memory_changed_output",
    "memory_prevented_known_failure",
    "memory_improved_verification",
)


class ActionImpactJudgeError(RuntimeError):
    """An action-impact judge invocation produced an unusable verdict (no JSON, a
    missing/!boolean axis, or an empty rationale). A malformed verdict is a real
    failure, surfaced loudly — never coerced to a default verdict."""


# --------------------------------------------------------------------------- #
# Path 1 — mechanical trajectory diff (pure ZFC mechanism)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TrajectoryDiff:
    """Structural on/off comparison of two tool-call streams. Each ``*_differs`` flag
    is a deterministic fact (the streams differ on this axis), NOT the claim that
    memory caused it. ``output_observable`` records whether the steps carried any
    output/observation data to compare — membench tool-use steps usually do not, so
    an "identical" output axis is only informative when this is True."""

    tool_choice_differs: bool
    plan_differs: bool
    output_differs: bool
    output_observable: bool

    @property
    def any_behavioral_diff(self) -> bool:
        return self.tool_choice_differs or self.plan_differs or self.output_differs


def _kind_seq(steps: Sequence[AttemptStep]) -> tuple[str, ...]:
    """The ordered tool-name sequence — the 'tool_choice' axis."""
    return tuple(s.kind for s in steps)


def _plan_seq(steps: Sequence[AttemptStep]) -> tuple[tuple[str, Any], ...]:
    """The ordered (tool, input) sequence — the 'plan' axis (what the agent chose to
    do, with what arguments)."""
    return tuple((s.kind, s.input) for s in steps)


def _output_seq(steps: Sequence[AttemptStep]) -> tuple[tuple[Any, Any], ...]:
    """The ordered (output, observation) sequence — the 'output' axis."""
    return tuple((s.output, s.observation) for s in steps)


def diff_trajectories(
    on_steps: Sequence[AttemptStep], off_steps: Sequence[AttemptStep]
) -> TrajectoryDiff:
    """Index-aligned structural diff of the memory-on vs memory-off step streams.

    Tool-choice and plan are always observable (every step carries a ``kind`` and an
    ``input``); the output axis is observable only when some step carries non-empty
    ``output``/``observation`` data. Comparison is by value over the full ordered
    sequences, so a difference in length, order, tool, or arguments all register."""
    on = tuple(on_steps)
    off = tuple(off_steps)
    output_observable = any(bool(s.output) or bool(s.observation) for s in (*on, *off))
    return TrajectoryDiff(
        tool_choice_differs=_kind_seq(on) != _kind_seq(off),
        plan_differs=_plan_seq(on) != _plan_seq(off),
        output_differs=_output_seq(on) != _output_seq(off),
        output_observable=output_observable,
    )


# --------------------------------------------------------------------------- #
# Path 3 — judge verdict (parse + validate)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ActionImpactInputs:
    """One paired step's worth of action-impact evidence.

    ``on_steps`` is the memory-enabled arm's tool-call stream, ``off_steps`` the
    no-memory twin's. ``on_status``/``off_status`` are the terminal outcomes
    (``completed``/``failed``/``unknown``) when known — used to decide whether a
    no-diff pair can skip the judge, and shown to the judge for the outcome axes.
    ``work_id`` and ``known_failure`` are optional context the judge sees: the bead
    under test and, when this pair targets a specific known failure, its description.
    """

    on_steps: tuple[AttemptStep, ...] = ()
    off_steps: tuple[AttemptStep, ...] = ()
    on_status: str | None = None
    off_status: str | None = None
    work_id: str | None = None
    known_failure: str | None = None


@dataclass(frozen=True)
class ActionImpactVerdict:
    """A parsed, validated judge verdict: the five §12.6 booleans + a rationale."""

    memory_changed_tool_choice: bool
    memory_changed_plan: bool
    memory_changed_output: bool
    memory_prevented_known_failure: bool
    memory_improved_verification: bool
    rationale: str


def parse_action_impact_verdict(reply: str) -> ActionImpactVerdict:
    """Parse a raw judge reply into a validated `ActionImpactVerdict`. A reply with no
    JSON object, a missing or non-boolean axis, or an empty rationale raises
    `ActionImpactJudgeError` — never silently defaulted."""
    block = first_json_object(reply)
    if block is None:
        raise ActionImpactJudgeError(f"verdict reply has no JSON object: {reply[:200]!r}")
    try:
        parsed: Any = json.loads(block)
    except json.JSONDecodeError as exc:
        raise ActionImpactJudgeError(f"verdict reply is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ActionImpactJudgeError(f"verdict reply is not a JSON object: {parsed!r}")

    values: dict[str, bool] = {}
    for key in _VERDICT_KEYS:
        value = parsed.get(key)
        # bool first: bool is an int subclass, so an int would otherwise slip through.
        if not isinstance(value, bool):
            raise ActionImpactJudgeError(f"verdict {key!r} must be a boolean, got {value!r}")
        values[key] = value
    rationale = parsed.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ActionImpactJudgeError(f"verdict rationale missing or empty: {rationale!r}")

    return ActionImpactVerdict(rationale=rationale, **values)


def _render_steps(steps: Sequence[AttemptStep]) -> str:
    """A compact, deterministic stream rendering for the prompt: one line per step,
    ``i. KIND {input json}`` (input truncated so a giant arg block can't blow the
    prompt). Pure formatting — no judgment."""
    if not steps:
        return "  (no tool calls)"
    lines = []
    for i, step in enumerate(steps):
        arg = json.dumps(step.input, sort_keys=True, ensure_ascii=False)
        if len(arg) > 240:
            arg = arg[:237] + "..."
        lines.append(f"  {i}. {step.kind} {arg}")
    return "\n".join(lines)


def build_action_impact_prompt(inp: ActionImpactInputs, mechanical: TrajectoryDiff) -> str:
    """Assemble the §12.6 judge prompt from the paired streams and the mechanical
    diff. Pure plumbing: template substitution, no semantic decision here."""
    work_line = f"Task: {inp.work_id}\n" if inp.work_id else ""
    failure_line = (
        f"Known failure this pair targets: {inp.known_failure}\n" if inp.known_failure else ""
    )
    mech_facts = (
        f"  tool_choice streams differ: {mechanical.tool_choice_differs}\n"
        f"  plan (tool+args) streams differ: {mechanical.plan_differs}\n"
        f"  output streams differ: {mechanical.output_differs} "
        f"(observable: {mechanical.output_observable})"
    )
    return f"""You are judging whether MEMORY changed what an agent did on one task step.

You are shown two runs of the SAME step: ON (memory enabled) and OFF (no memory).
{work_line}{failure_line}
ON run (status: {inp.on_status or "unknown"}):
{_render_steps(inp.on_steps)}

OFF run (status: {inp.off_status or "unknown"}):
{_render_steps(inp.off_steps)}

Mechanical trajectory diff (ground truth on whether the streams differ):
{mech_facts}

Decide each question. Attribute a difference to MEMORY only when the memory content
plausibly caused it — incidental nondeterminism is not memory impact. If the
streams are identical on an axis, memory did not change that axis.

Respond with JSON only, no prose:

{{"memory_changed_tool_choice": true|false, "memory_changed_plan": true|false,
"memory_changed_output": true|false, "memory_prevented_known_failure": true|false,
"memory_improved_verification": true|false, "rationale": "2-3 sentence explanation"}}"""


# --------------------------------------------------------------------------- #
# Orchestration — pre-filter, judge, cross-check
# --------------------------------------------------------------------------- #
def _statuses_known_equal(inp: ActionImpactInputs) -> bool:
    """True only when both terminal statuses are present and equal. Unknown statuses
    are treated as 'not provably equal' so the judge is consulted rather than the
    pair being skipped on an assumption."""
    return inp.on_status is not None and inp.on_status == inp.off_status


def score_action_impact(
    inp: ActionImpactInputs, judge: ComparativeJudge | None = None
) -> ActionImpactMetrics:
    """Score §12.6 action-impact for one paired step.

    Path 1 first: the behavioral axes the streams prove identical are sound ``False``
    set without a judge. With no judge, the remaining behavioral axes (a real
    difference whose *cause* needs a model) and both outcome axes stay at their
    ``None`` seam. With a judge, a pair that is identical on EVERY OBSERVED axis with
    equal statuses skips the call as zero-impact; otherwise the judge emits all five
    booleans and the mechanical diff cross-checks the three behavioral ones — the
    judge cannot claim memory changed an axis the streams prove identical."""
    mech = diff_trajectories(inp.on_steps, inp.off_steps)
    # Sound negatives: identical (and, for output, observed) => memory changed nothing here.
    tool_choice_is_false = not mech.tool_choice_differs
    plan_is_false = not mech.plan_differs
    output_is_false = mech.output_observable and not mech.output_differs

    if judge is None:
        return ActionImpactMetrics(
            memory_changed_tool_choice=False if tool_choice_is_false else None,
            memory_changed_plan=False if plan_is_false else None,
            memory_changed_output=False if output_is_false else None,
            memory_prevented_known_failure=None,
            memory_improved_verification=None,
        )

    # Skip the judge only when zero impact is PROVABLE: every behavioral axis is
    # identical AND the output axis was actually observed (unrecorded output could
    # still hide a memory-caused change in the final artifact) AND the statuses agree.
    if not mech.any_behavioral_diff and mech.output_observable and _statuses_known_equal(inp):
        return ActionImpactMetrics(
            memory_changed_tool_choice=False,
            memory_changed_plan=False,
            memory_changed_output=False,
            memory_prevented_known_failure=False,
            memory_improved_verification=False,
        )

    verdict = parse_action_impact_verdict(judge.complete(build_action_impact_prompt(inp, mech)))
    return ActionImpactMetrics(
        memory_changed_tool_choice=(
            False if tool_choice_is_false else verdict.memory_changed_tool_choice
        ),
        memory_changed_plan=False if plan_is_false else verdict.memory_changed_plan,
        memory_changed_output=False if output_is_false else verdict.memory_changed_output,
        memory_prevented_known_failure=verdict.memory_prevented_known_failure,
        memory_improved_verification=verdict.memory_improved_verification,
    )
