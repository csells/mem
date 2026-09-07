"""§9.2 — the multi-session benchmark sequence and its steps.

The eval object is a *sequenced workload* (plan §A, DIV-2): Step1→…→Goal, fresh
context per step, with the persistent memory store the only continuity channel
(except under the oracle condition). Bead replay is one source feeding sequence
construction; this module is the construction target.
"""

from typing import Any

from pydantic import BaseModel, Field


class ExpectedAction(BaseModel):
    """A tool action a step's goal REQUIRES — recalled memory must drive it (mem-31vl).

    ``tool`` must be invoked; every string in ``arg_values`` must appear in that
    call's arguments and none in ``forbidden_values`` may — both word-boundary
    matched (``metrics.scorers.states_value``) over the call's argument VALUES (not
    the dict repr). This carries its OWN ``forbidden_values``, distinct from
    ``OutcomeCheck.forbidden_values`` (which grades the text answer), so a
    tool-requiring shape can make the ACTION the sole reward-bearing channel: the
    stale value fails inside the tool argument, not in the prose. This is what makes
    memory quality load-bearing through a tool call rather than optional text recall.
    """

    tool: str
    arg_values: list[str] = Field(default_factory=list)
    forbidden_values: list[str] = Field(default_factory=list)


class OutcomeCheck(BaseModel):
    """A deterministic check on a step's outcome (§9.3)."""

    check_id: str
    description: str = ""
    # Memory ids whose availability this check depends on. Empty => the check does
    # not require memory (passes statelessly). Non-empty => the step is
    # memory-sensitive: the agent must have the listed memory available to pass.
    requires_memory: list[str] = Field(default_factory=list)
    # Authored values the step's stated answer must NOT contain (mem-z3gi): the
    # superseded (stale) values of the subjects this check requires. Grading is
    # mechanical — a word-boundary match of an authored value
    # (``metrics.scorers.states_value``) — which makes staleness reward-bearing:
    # stating a stale value FAILS the check instead of only ticking the
    # ``stale_memory_retrieval_rate`` diagnostic. Defaults empty so existing
    # fixtures stay valid.
    forbidden_values: list[str] = Field(default_factory=list)
    # Tool actions the step's goal REQUIRES (mem-31vl): recalled memory must drive a
    # specific tool call, not just a text answer. Empty => text-only grade (existing
    # behavior). Graded by ``metrics.scorers.outcome_check_passes`` over the agent's
    # ``tool_calls``. Defaults empty so existing fixtures stay valid.
    requires_action: list[ExpectedAction] = Field(default_factory=list)


class MemoryProbe(BaseModel):
    """A probe asserting a specific memory was used/available (§9.3)."""

    probe_id: str
    expected_memory_id: str
    description: str = ""


class SequenceStep(BaseModel):
    step_id: str
    user_request: str
    available_tools: list[str] = Field(default_factory=list)
    environment_state: dict[str, Any] = Field(default_factory=dict)
    # Memory the step is expected to establish (id → content) and to depend on.
    expected_memory_writes: dict[str, str] = Field(default_factory=dict)
    expected_memory_reads: list[str] = Field(default_factory=list)
    outcome_checks: list[OutcomeCheck] = Field(default_factory=list)
    memory_probes: list[MemoryProbe] = Field(default_factory=list)
    # Distracting-but-irrelevant memories (§10 interference). The runner SEEDS these into
    # the store before the step's retrieve (mem-zt1c), so a query/top-k arm surfaces them
    # as competitors and ``distractor_retrieval_rate`` (Confusion) goes non-zero; an
    # id-exact arm never requests them, so it stays 0. Defaults empty for non-stressor steps.
    distractor_memories: dict[str, str] = Field(default_factory=dict)
    # Staleness/supersession marker (§10.C). Memory ids written by an EARLIER step
    # that this step makes stale by establishing a newer value under a *distinct*
    # id (the runner's oracle pool rejects same-id/different-content rewrites, so
    # supersession is modeled as v1→v2 distinct ids, with later reads depending on
    # v2 only). The runner scores ``stale_memory_retrieval_rate`` (Staleness) against these
    # — a top-k arm that surfaces the still-stored v1 scores non-zero — and asserts every
    # id here is a real prior write (_assert_superseded_written). Defaults empty so existing
    # fixtures stay valid.
    superseded_memory_ids: list[str] = Field(default_factory=list)
    # Whether the READ / WRITE on this step is the AGENT's choice rather than the harness's.
    # Both default False so every existing fixture keeps the forced-loop semantics E3a graded:
    # the harness retrieves, the harness records, and closure measures the LOOP. Flipped True,
    # the harness stops performing that half and the step measures whether the agent chose to do
    # it — which is the only reading under which a 0 is a finding rather than a broken run. They
    # are separate flags because the two choices are separately interesting: an agent that writes
    # but never reads back and one that reads but never records are different failures.
    read_is_endogenous: bool = False
    write_is_endogenous: bool = False
    # Ids this step must NOT write (e.g. re-persisting the superseded v1 it was just
    # told is stale). Scored mechanically as ``RetentionMetrics.forbidden_write_rate``
    # over the ids actually written. Defaults empty so existing fixtures stay valid.
    forbidden_memory_writes: list[str] = Field(default_factory=list)
    # S3 retention-schedule oracle (additive; consumer = the RetentionScheduledMemory
    # arm + its scorer). ``record_class`` is the retention class the step's record is
    # assigned at write (the arm's classify input); ``disposition`` is the schedule's
    # ground-truth disposition for that record at sweep time (the deterministic oracle
    # the wrongful_destruction gate scores against). Both None for non-retention
    # sequences, so existing fixtures stay valid.
    record_class: str | None = None
    disposition: str | None = None
    # E1 discrimination label (mem-9q8dg). True => the step's goal cannot be reached without
    # recalled memory (the value it must carry is stated nowhere in-context); False => the
    # matched UNNECESSARY twin, whose goal states the same value in the request itself, so a
    # no-memory arm can solve it. None => unlabelled (every pre-E1 fixture): the label is a
    # claim about the step's information geometry, and defaulting it to True would assert that
    # claim for steps nothing ever verified. The label is a LABEL — necessity is verified
    # outcome-side by ``runner.e1_necessity_preflight``, never by this field.
    memory_necessary: bool | None = None


class BenchmarkSequence(BaseModel):
    sequence_id: str
    title: str
    domain: str = ""
    goal: str = ""
    steps: list[SequenceStep]
    final_goal_check: dict[str, Any] = Field(default_factory=dict)
    # S2 schema-induction oracle (additive): the abstract rule every episode
    # INSTANTIATES without stating it verbatim — the answer the final probe must
    # induce. None for non-schema sequences, so existing fixtures stay valid. The
    # source-trace set is the written episode ids (expected_memory_writes across
    # steps); it is not duplicated here.
    latent_rule: str | None = None
