"""Deterministic metric assembly for one step trial (§12).

This module owns the trial-level wiring: it pulls the mechanical inputs out of the
agent result + retrieve result + write events and hands them to the pure scorers in
`membench.metrics.scorers`, which do the arithmetic. Privacy/interruption groups and
the judge seams (rubric_score, completion_quality, action-impact, derailment
magnitude) are left at their model defaults — they are populated by the privacy
phase / the LLM judge, not here (ZFC boundary, plan §A DIV-4).
"""

from membench.memory_systems.base import RetrieveResult
from membench.metrics.scorers import (
    RetentionInputs,
    RetrievalInputs,
    SynthesisInputs,
    content_recovered_write_ids,
    score_efficiency,
    score_retention,
    score_retrieval,
    score_synthesis,
)
from membench.runner.agent import AgentStepResult
from membench.runner.tool_surface import (
    MEMORY_TOOL_NAMES,
    assert_recall_is_bounded,
    memory_invocations,
    observed_requested_ids,
    observed_written_content,
    partition_memory_calls,
)
from membench.schemas.memory_event import MemoryEvent
from membench.schemas.metrics import MetricsBundle, TaskMetrics
from membench.schemas.sequence import SequenceStep


def _ratio(num: int, denom: int) -> float:
    return num / denom if denom else 0.0


def _supporting_required_ids(step: SequenceStep) -> list[str]:
    """Memories the step depends on for synthesis = probe targets + check requirements.

    Deduplicated, order-preserving. A step with no probes/required checks reports
    zero supporting memories (synthesis is trivially satisfied)."""
    ids: list[str] = []
    seen: set[str] = set()
    for probe in step.memory_probes:
        if probe.expected_memory_id not in seen:
            seen.add(probe.expected_memory_id)
            ids.append(probe.expected_memory_id)
    for check in step.outcome_checks:
        for mid in check.requires_memory:
            if mid not in seen:
                seen.add(mid)
                ids.append(mid)
    return ids


def compute_metrics(
    step: SequenceStep,
    agent_result: AgentStepResult,
    retrieve: RetrieveResult | None,
    write_events: list[MemoryEvent],
    *,
    reads_enabled: bool,
    context_gated: bool = False,
) -> MetricsBundle:
    checks = agent_result.check_results
    passed = sum(checks.values())
    reward = _ratio(passed, len(checks))
    all_passed = passed == len(checks) and len(checks) > 0
    task = TaskMetrics(
        reward=reward,
        **{"pass": all_passed},
        final_goal_success=all_passed,
        verifier_errors=[cid for cid, ok in checks.items() if not ok],
    )

    memory_events: list[MemoryEvent] = []
    if retrieve is not None:
        memory_events.append(retrieve.event)
    memory_events.extend(write_events)

    # A memory call the AGENT made arrives as a Bash tool_use whose command invokes a bd memory
    # verb (mem-5sht9's tool surface), so it is in `tool_calls` like any other. Counting the raw
    # length here scored every such call as a NON-memory call — the number that answers "how much
    # non-memory tool work did this cost" would have absorbed the endogenous memory calls the
    # moment a grid wired the surface, and the arms that pay for retrieval would look cheaper than
    # the arm that calls the tool itself. The split is mechanical (argv shape) and applies to every
    # arm: for the arms that hand the agent no memory tool it is a no-op, because none of their
    # calls match.
    #
    # Both halves of that split are then COUNTED. Discarding the memory half (the shipped
    # `_, non_memory_calls`) moved the bias rather than removing it: the call left
    # `non_memory_tool_calls` and arrived nowhere, so `tool_calls_total` — a published metric —
    # under-reported by exactly the number of memory calls the agent chose to make, and the arm
    # that uses memory most looked cheapest.
    memory_calls, non_memory_calls = partition_memory_calls(agent_result.tool_calls)
    # What the agent CHOSE to do with the tool, read off observed argv. Counted here rather than
    # taken from the agent's own report for the same reason `available_ids` is below: a step whose
    # measurement is "did it choose to?" cannot let the subject answer. These count INVOCATIONS,
    # not calls — one Bash call can carry two verbs — which is why the cost channel above is
    # counted separately rather than derived from them.
    invocations = memory_invocations(agent_result.tool_calls)
    endogenous_reads = sum(1 for inv in invocations if inv.is_read)
    endogenous_writes = sum(1 for inv in invocations if inv.is_write)
    # A memory call arrives as a structured Bash tool_use, so a step that does not offer Bash
    # cannot receive one and its silence says nothing about the agent.
    memory_tool_offered = any(name in step.available_tools for name in MEMORY_TOOL_NAMES)
    efficiency = score_efficiency(
        input_tokens=agent_result.input_tokens,
        output_tokens=agent_result.output_tokens,
        non_memory_tool_calls=len(non_memory_calls),
        memory_events=memory_events,
        non_memory_tool_latency_ms=sum(tc.latency_ms for tc in non_memory_calls),
        agent_memory_tool_calls=len(memory_calls),
        agent_memory_tool_latency_ms=sum(tc.latency_ms for tc in memory_calls),
        turns=agent_result.turns,
        endogenous_reads=endogenous_reads,
        endogenous_writes=endogenous_writes,
        memory_tool_offered=memory_tool_offered,
    )

    # Ordered retrieved ids carry rank; fall back to payload keys if the event
    # did not record an explicit order (both preserve insertion order).
    retrieved_ids = (
        retrieve.event.retrieved_ids or list(retrieve.payloads) if retrieve is not None else []
    )
    # Confusion/Staleness ground truth is harness-AUTHORED on the step (the generator
    # populates these), never the arm's self-report — so an arm cannot launder its own
    # noise out of the score. score_retrieval counts how many appear in retrieved_ids: 0
    # for an id-exact arm (it only ever returns required ids), non-zero for a top-k arm
    # whose ranking surfaces the seeded distractors / the superseded v1 (mem-zt1c).
    retrieval = score_retrieval(
        RetrievalInputs(
            retrieved_ids=list(retrieved_ids),
            required_ids=list(step.expected_memory_reads),
            distractor_ids=list(step.distractor_memories),
            stale_ids=list(step.superseded_memory_ids),
            read_attempted=reads_enabled and not context_gated,
            context_gated=context_gated,
        )
    )

    if step.write_is_endogenous:
        # The agent chose where to put it, so there is no harness id to compare against: the
        # write is credited when the step's AUTHORED literal is recoverable from what the agent
        # stored, read off observed argv (never off `writes_performed`, which is the subject's own
        # account). Keeping the id-exact path for every other step is what leaves the forced-loop
        # arms — factorial_behavioral, synthetic_arms, memory_necessity_gate — unmoved.
        #
        # Noise is not measurable on this path and is not fabricated: under a self-chosen
        # namespace an unexpected key is indistinguishable from a differently-named required one,
        # so `written_ids` carries only the recovered ids and `over_retention_rate` reads 0.0 —
        # an honest "not measured here", the same convention `RetrievalInputs` uses for an arm
        # that seeds no distractors.
        written_ids = content_recovered_write_ids(
            observed_written_content(memory_calls), step.expected_memory_writes
        )
    else:
        written_ids = [mid for ev in write_events for mid in ev.written_ids]
    retention = score_retention(
        RetentionInputs(
            written_ids=written_ids,
            expected_writes=list(step.expected_memory_writes),
            forbidden_write_ids=list(step.forbidden_memory_writes),
        )
    )

    if step.read_is_endogenous:
        # The harness performs no retrieve on an endogenous-read step, so what was "available" is
        # whatever the agent asked for and the harness OBSERVED it ask for. Reading this off
        # `agent_result` fields the agent populates itself would let the subject grade its own
        # read, and every synthesis number downstream would inherit that self-report.
        assert_recall_is_bounded(memory_calls)
        available_ids = observed_requested_ids(memory_calls)
    else:
        available_ids = list(retrieve.payloads) if retrieve is not None else []
    synthesis = score_synthesis(
        SynthesisInputs(
            supporting_required_ids=_supporting_required_ids(step),
            available_ids=available_ids,
        )
    )

    return MetricsBundle(
        task=task,
        efficiency=efficiency,
        retrieval=retrieval,
        retention=retention,
        synthesis=synthesis,
    )
