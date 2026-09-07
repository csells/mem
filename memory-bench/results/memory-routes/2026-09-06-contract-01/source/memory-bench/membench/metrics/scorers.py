"""Deterministic §12 scorers: retrieval / retention / synthesis / efficiency / privacy.

Each scorer is a pure function of explicit inputs (ordered retrieved ids, the
step's required / distractor / stale / superseded id sets, write events, the
trace's token + tool counts, injected-item rig provenance). It returns a populated
metric model with ONLY the mechanical fields set; the judge seams documented in
`schemas.metrics` are left at their defaults. Privacy's `leakage_flags` is mechanical
and computed here; its `privacy_class` is a model-classified seam (DIV-4) passed
THROUGH, never decided here — the ZFC boundary the module enforces.

Ranking math (`mrr`, `nDCG`, `retrieval_rank`) keys on the *ordered* retrieved-id
list — `MemoryEvent.retrieved_ids` carries retrieval order, so a backend that ranks
distractors above a required id is penalised correctly. Set-only fields (precision,
recall, miss counts) are order-independent.
"""

from __future__ import annotations

import math
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field

from membench.schemas.handoff import (
    INTERRUPTION_POINTS,
    VALIDATION,
    VALIDATION_FAIL,
    PredecessorEvent,
)
from membench.schemas.memory_event import MemoryEvent
from membench.schemas.metrics import (
    EfficiencyMetrics,
    InterruptionMetrics,
    PrivacyMetrics,
    RetentionMetrics,
    RetrievalMetrics,
    SynthesisMetrics,
)
from membench.schemas.sequence import OutcomeCheck
from membench.schemas.trace import ToolCall

# DIV-4 frozen vocabulary (phase-2.5-plan §A): the model-classified sensitivity
# buckets, and the cross-rig isolation leak a strict cross_rig run must never produce.
PRIVACY_CLASSES = ("none", "internal", "sensitive")
CROSS_RIG_SCOPE = "cross_rig"
LEAK_CROSS_RIG_SAME_RIG = "cross_rig_same_rig_injection"

# Interruption inject-timing buckets (plan §A DIV-4): whether the takeover landed ON a
# live failure signal or not — the mechanical attribute the derailment proxy conditions on.
ON_FAILURE = "on_failure"
OFF_FAILURE = "off_failure"


def _ratio(num: int, denom: int) -> float:
    return num / denom if denom else 0.0


# --------------------------------------------------------------------------- #
# Outcome-check grading (mem-z3gi — reward-bearing staleness)
# --------------------------------------------------------------------------- #
def states_value(text: str, value: str) -> bool:
    """True when ``text`` states the authored ``value`` as a standalone token run.

    Word-boundary anchored (a value never matches inside a larger identifier, e.g.
    ``v2`` does not match ``checkout_v2``) — a format-anchored mechanical match on an
    authored ground-truth string, not a semantic heuristic (the ZFC boundary)."""
    return re.search(rf"(?<!\w){re.escape(value)}(?!\w)", text) is not None


def content_recovered_write_ids(stored_text: str, expected_writes: Mapping[str, str]) -> list[str]:
    """The expected write ids whose AUTHORED LITERAL is recoverable from ``stored_text``.

    The endogenous-write grade (E3b): an agent that chooses its own key produces an id no
    harness-authored id set can name, so grading the write by id equality measures id-naming
    discipline and scores a correct fact stored under a self-chosen key as a miss. Here the id is
    credited when the step's authored content for it is stated in what the agent actually stored,
    word-boundary matched by ``states_value`` — the same mechanical authored-literal matcher used
    everywhere else in this module, never a fuzzy or semantic one (anything fuzzier belongs to a
    judge outside this file).

    An empty authored literal is never a hit: ``states_value(text, "")`` is true of any text, so
    crediting it would hand every endogenous step a free write.

    Order follows ``expected_writes`` so the returned list is deterministic."""
    return [
        mid
        for mid, literal in expected_writes.items()
        if literal and states_value(stored_text, literal)
    ]


def _call_args_text(call: ToolCall) -> str:
    """One tool call's argument VALUES as a single string — values, never
    ``str(arguments)`` — so the mechanical match does not depend on Python's dict repr
    (quoting/braces)."""
    return "\n".join(str(value) for value in call.arguments.values())


def outcome_check_passes(
    check: OutcomeCheck,
    *,
    available_ids: Collection[str],
    stated_text: str,
    tool_calls: Collection[ToolCall] = (),
) -> bool:
    """Deterministic grade for one ``OutcomeCheck``: every required memory id must be
    available, the answer must not state any forbidden (superseded) value, AND every
    required tool action must have been taken with the recalled value in its args.

    The forbidden-values clause makes staleness reward-bearing on the TEXT answer
    (mem-z3gi). The ``requires_action`` clause (mem-31vl) makes it reward-bearing on
    a TOOL action instead: the goal REQUIRES calling a named tool whose arguments
    contain every ``arg_values`` string and none of the action's own
    ``forbidden_values`` (both matched over the call's argument values with the same
    word-boundary ``states_value``). A tool-requiring shape clears the text
    ``forbidden_values`` so the action is the sole reward-bearing channel — an arm
    that surfaced a stale version drives a stale tool argument and fails HERE, not on
    the prose. Shared by the ``ScriptedAgent`` self-grade and any external scorer of
    a real agent's trace (the values are authored, so the grade is mechanical)."""
    if not set(check.requires_memory).issubset(available_ids):
        return False
    if any(states_value(stated_text, value) for value in check.forbidden_values):
        return False
    for action in check.requires_action:
        calls = [call for call in tool_calls if call.name == action.tool]
        if not calls:
            return False
        # Some SINGLE call must carry every required value (a real application of the
        # recalled fact, not values merged across calls) ...
        if not any(
            all(states_value(_call_args_text(call), value) for value in action.arg_values)
            for call in calls
        ):
            return False
        # ... and NO call to the tool may carry a forbidden (stale) value.
        if any(
            states_value(_call_args_text(call), value)
            for call in calls
            for value in action.forbidden_values
        ):
            return False
    return True


# --------------------------------------------------------------------------- #
# Retrieval (§12.3)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RetrievalInputs:
    """What a retrieval scorer needs for one step.

    `retrieved_ids` is the ranked list the backend returned (order matters for
    rank/mrr/nDCG). `required_ids` are the ids the step depends on. `distractor_ids`
    and `stale_ids` are known-irrelevant / known-superseded ids the backend should
    NOT have surfaced; both default empty, so an arm that seeds neither reports 0.0
    for those rates (an honest "not measured here", not a fabricated number).
    `context_gated` (mem-1m0s) is passed straight through to `RetrievalMetrics` —
    True when the harness skipped the retrieve call because the accumulated token
    count for the condition reached the configured context budget.
    """

    retrieved_ids: list[str]
    required_ids: list[str]
    distractor_ids: list[str] = field(default_factory=list)
    stale_ids: list[str] = field(default_factory=list)
    read_attempted: bool = True
    context_gated: bool = False


def _dcg(relevances: list[int]) -> float:
    return sum(rel / math.log2(i + 2) for i, rel in enumerate(relevances))


def score_retrieval(inp: RetrievalInputs) -> RetrievalMetrics:
    retrieved = inp.retrieved_ids
    required = inp.required_ids
    required_set = set(required)
    distractor_set = set(inp.distractor_ids)
    stale_set = set(inp.stale_ids)

    retrieved_relevant = [m for m in retrieved if m in required_set]

    # First-relevant rank (1-based) drives retrieval_rank + mrr.
    rank: int | None = None
    for i, mid in enumerate(retrieved):
        if mid in required_set:
            rank = i + 1
            break

    # Ideal DCG = every required id retrieved at the top (binary relevance).
    gains = [1 if mid in required_set else 0 for mid in retrieved]
    ideal = [1] * min(len(required_set), len(retrieved))
    idcg = _dcg(ideal)

    n_distractor = sum(1 for m in retrieved if m in distractor_set)
    n_stale = sum(1 for m in retrieved if m in stale_set)

    return RetrievalMetrics(
        read_attempted=inp.read_attempted and bool(required),
        relevant_memory_available=bool(retrieved_relevant),
        relevant_memory_retrieved=bool(required) and required_set.issubset(set(retrieved)),
        retrieval_rank=rank,
        precision_at_k=_ratio(len(retrieved_relevant), len(retrieved)),
        recall_at_k=_ratio(len(retrieved_relevant), len(required_set)),
        mrr=(1.0 / rank) if rank else 0.0,
        nDCG=(_dcg(gains) / idcg) if idcg else 0.0,
        distractor_retrieval_rate=_ratio(n_distractor, len(retrieved)),
        stale_memory_retrieval_rate=_ratio(n_stale, len(retrieved)),
        missed_required_memory_count=len(required_set - set(retrieved)),
        context_gated=inp.context_gated,
    )


# --------------------------------------------------------------------------- #
# Retention (§12.4)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RetentionInputs:
    """What a retention scorer needs for one step.

    `written_ids` are the ids the agent actually persisted. `expected_writes` are
    the ids the step was supposed to establish. `correct_scope_ids` /
    `correct_backend_ids` are the subsets that landed in the right scope / backend —
    defaulting to the expected-and-written intersection means a backend that does
    not distinguish scope reports a clean 1.0 rather than a fabricated penalty.
    `removed_ids` and `superseded_expected_ids` drive the supersession fields.
    """

    written_ids: list[str]
    expected_writes: list[str]
    correct_scope_ids: list[str] | None = None
    correct_backend_ids: list[str] | None = None
    removed_ids: list[str] = field(default_factory=list)
    superseded_expected_ids: list[str] = field(default_factory=list)
    # Ids the step AUTHORED as forbidden to write (``SequenceStep.forbidden_memory_writes``).
    # Scored as its own directed rate; ``over_retention_rate``'s arithmetic is untouched.
    forbidden_write_ids: list[str] = field(default_factory=list)


def score_retention(inp: RetentionInputs) -> RetentionMetrics:
    written = inp.written_ids
    written_set = set(written)
    expected = inp.expected_writes
    expected_set = set(expected)

    written_expected = [m for m in written if m in expected_set]
    hit_rate = _ratio(len(written_expected), len(expected_set))
    n_noise = len(written) - len(written_expected)

    scope_ids = inp.correct_scope_ids if inp.correct_scope_ids is not None else written_expected
    backend_ids = (
        inp.correct_backend_ids if inp.correct_backend_ids is not None else written_expected
    )

    superseded = set(inp.superseded_expected_ids)
    removed = set(inp.removed_ids)
    forbidden = set(inp.forbidden_write_ids)
    n_forbidden = sum(1 for m in written if m in forbidden)

    return RetentionMetrics(
        expected_memory_written=bool(expected) and expected_set.issubset(written_set),
        write_hit_rate=hit_rate,
        write_miss_rate=(1.0 - hit_rate) if expected else 0.0,
        # Over-retention = ids written that were not asked for, relative to writes.
        over_retention_rate=_ratio(n_noise, len(written)),
        noise_write_rate=_ratio(n_noise, len(written)),
        forbidden_write_rate=_ratio(n_forbidden, len(written)),
        correct_scope_rate=_ratio(len(set(scope_ids) & written_set), len(written_expected)),
        correct_backend_rate=_ratio(len(set(backend_ids) & written_set), len(written_expected)),
        # Supersession: a superseded id is correctly handled iff it was removed.
        stale_memory_removed=bool(superseded) and superseded.issubset(removed),
        supersession_correct=(not superseded) or superseded.issubset(removed),
    )


# --------------------------------------------------------------------------- #
# Synthesis (§12.5)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SynthesisInputs:
    """Cross-session synthesis inputs.

    `supporting_required_ids` are the memories the step's probes/checks say it
    depends on; `available_ids` are the ids the harness surfaced this step. Cross-
    session dependency succeeds iff every required supporting memory was available.
    `multi_backend_synthesis_success` and `contradiction_resolution_success` are
    judge seams and are NOT set here.
    """

    supporting_required_ids: list[str]
    available_ids: list[str]


def score_synthesis(inp: SynthesisInputs) -> SynthesisMetrics:
    required = set(inp.supporting_required_ids)
    available = set(inp.available_ids)
    used = required & available
    return SynthesisMetrics(
        supporting_memories_required=len(required),
        supporting_memories_used=len(used),
        cross_session_dependency_success=bool(required) and required.issubset(available),
    )


# --------------------------------------------------------------------------- #
# Efficiency arithmetic (§12.2)
# --------------------------------------------------------------------------- #
def score_efficiency(
    *,
    input_tokens: int,
    output_tokens: int,
    non_memory_tool_calls: int,
    memory_events: list[MemoryEvent],
    non_memory_tool_latency_ms: float = 0.0,
    agent_memory_tool_calls: int = 0,
    agent_memory_tool_latency_ms: float = 0.0,
    turns: int = 0,
    retries: int = 0,
    endogenous_reads: int = 0,
    endogenous_writes: int = 0,
    memory_tool_offered: bool = False,
) -> EfficiencyMetrics:
    """Sum tokens / tool-call counts / latencies over a trial.

    `memory_tool_calls` counts the normalized memory events the HARNESS performed (each
    retrieve/write is one memory tool call); `tool_latency_ms` sums their measured latency plus the
    non-memory tool latency. `endogenous_reads` / `endogenous_writes` are what the AGENT did,
    counted by the caller from observed argv, and are reported alongside rather than added in: an
    arm that retrieves FOR the agent and an agent that reaches for the tool are different facts.
    `memory_tool_offered` says whether "no endogenous call" is an observation at all.

    Note the two units, which is why `agent_memory_tool_calls` is not just their sum:
    `endogenous_reads` / `endogenous_writes` count INVOCATIONS, and one Bash call can carry two
    (`bd recall a; bd remember b c`), while `agent_memory_tool_calls` counts the CALLS a cost
    metric is denominated in. Deriving either from the other would quietly misreport whichever
    question was not being asked.

    `cost_usd` and `model_latency_ms` stay 0.0 in the
    deterministic path — they are populated on the Harbor/model path, not here.

    `agent_memory_tool_calls` is the third channel and it exists because the second one moved.
    Before mem-5sht9's FIX 6, a Bash-wrapped `bd recall` was counted as a non-memory call; FIX 6
    correctly stopped counting it there but routed it NOWHERE, so `tool_calls_total` silently
    dropped it. On a published efficiency metric that is the worst possible direction: the arm
    whose agent actually reaches for memory reports the LOWEST total tool cost, and the cheaper an
    arm looks the more it looks like the one to ship. `tool_calls_total` must equal the number of
    tool calls the agent really made, so it sums all three channels, and the latency follows the
    same rule. Kept as its own parameter rather than folded back into `non_memory_tool_calls`
    because "how much non-memory work did this cost" is still a question worth answering.
    """
    mem_calls = len(memory_events)
    mem_latency = sum(ev.latency_ms for ev in memory_events)
    endogenous = endogenous_reads + endogenous_writes
    return EfficiencyMetrics(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        tool_calls_total=non_memory_tool_calls + mem_calls + agent_memory_tool_calls,
        memory_tool_calls=mem_calls,
        endogenous_memory_tool_calls=endogenous,
        endogenous_memory_reads=endogenous_reads,
        endogenous_memory_writes=endogenous_writes,
        # Only meaningful where a tool was actually offered; elsewhere "did not call" is not an
        # observation about the agent, so it stays False rather than reading as a universal miss.
        tool_not_called=memory_tool_offered and endogenous == 0,
        non_memory_tool_calls=non_memory_tool_calls,
        tool_latency_ms=non_memory_tool_latency_ms + mem_latency + agent_memory_tool_latency_ms,
        turns=turns,
        retries=retries,
    )


# --------------------------------------------------------------------------- #
# Privacy (plan §A DIV-4) — measured, not acted on in v1
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PrivacyInputs:
    """What the privacy scorer needs for one trial.

    `run_scope` is the Decision-7 retrieval track (`cross_rig` / `same_rig_temporal`);
    `task_rig` is the rig the task belongs to; `injected_rigs` maps each injected
    memory id to the rig it came from. All default to the honest "not measured here"
    (no scope, no provenance) so a run that does not thread rig provenance reports an
    empty `leakage_flags` rather than a fabricated clean bill — the same default
    discipline `distractor_ids`/`stale_ids` use.

    `privacy_class` is the DIV-4 model-classified sensitivity bucket
    (`none`/`internal`/`sensitive`), decided by a judge UPSTREAM and passed through
    here; `None` means unclassified. The scorer never calls a model — classification
    is a judge seam, the leak check is the mechanism.
    """

    run_scope: str | None = None
    task_rig: str | None = None
    injected_rigs: dict[str, str] = field(default_factory=dict)
    privacy_class: str | None = None


def score_privacy(inp: PrivacyInputs) -> PrivacyMetrics:
    """Deterministic privacy readout. ``leakage_flags`` carries the cross-rig-in-strict
    check: a ``cross_rig`` run must never inject SAME-rig content (that would defeat the
    cross-rig generalization isolation), so each injected id whose source rig equals the
    task's rig is flagged ``cross_rig_same_rig_injection:<id>``. A ``same_rig_temporal``
    run injecting same-rig content is expected and never flagged. ``privacy_class`` is
    passed through after a vocabulary check (an out-of-bucket class is a producer bug,
    surfaced loudly, not silently kept)."""
    if inp.privacy_class is not None and inp.privacy_class not in PRIVACY_CLASSES:
        raise ValueError(
            f"privacy_class {inp.privacy_class!r} is not one of {PRIVACY_CLASSES} (DIV-4)"
        )
    leakage_flags: list[str] = []
    if inp.run_scope == CROSS_RIG_SCOPE and inp.task_rig is not None:
        offending = sorted(mid for mid, rig in inp.injected_rigs.items() if rig == inp.task_rig)
        leakage_flags.extend(f"{LEAK_CROSS_RIG_SAME_RIG}:{mid}" for mid in offending)
    return PrivacyMetrics(privacy_class=inp.privacy_class, leakage_flags=leakage_flags)


# --------------------------------------------------------------------------- #
# Interruption (plan §A DIV-4) — measured, not acted on in v1
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class InterruptionInputs:
    """What the interruption scorer needs for one mem-dsu handoff task.

    `point` is the interruption point the task was cut at (one of
    `schemas.handoff.INTERRUPTION_POINTS`). `checkpoint_prefix` is the predecessor
    trajectory up to AND INCLUDING the event that triggered the point — the frozen
    state the successor inherits. The caller derives both from the generator:
    `detect_interruption_points(traj.events)[point]` gives the trigger index, and the
    prefix is `traj.events[: index + 1]`. The 4 view arms of one point share this
    prefix, so they share one `inject_timing` (timing is a property of the point, not
    the injected memory view).
    """

    point: str
    checkpoint_prefix: tuple[PredecessorEvent, ...]


def score_interruption(inp: InterruptionInputs) -> InterruptionMetrics:
    """Deterministic interruption readout. `inject_timing` is `on_failure` iff a
    validation FAILED on or before the frozen checkpoint — i.e. the takeover lands on a
    live failure signal (`first_validation_result` of a failing run, or any
    `first_post_failure_edit`) — else `off_failure` (e.g. `first_source_edit`, before
    any validation). It is read from the trajectory's actual outcomes, never hardcoded
    by point name, so a trajectory whose first validation PASSES classifies honestly.

    `derailment_signal` MAGNITUDE is a judge seam, left `None`: the added-iterations /
    abandonment effort proxy rides the efficiency metrics (`handoff_efficiency`), and
    the semantic derailment scalar is the model's call, never decided here (ZFC)."""
    if inp.point not in INTERRUPTION_POINTS:
        raise ValueError(f"point {inp.point!r} is not one of {INTERRUPTION_POINTS}")
    on_failure = any(
        e.kind == VALIDATION and e.outcome == VALIDATION_FAIL for e in inp.checkpoint_prefix
    )
    return InterruptionMetrics(
        inject_timing=ON_FAILURE if on_failure else OFF_FAILURE,
        derailment_signal=None,
    )
