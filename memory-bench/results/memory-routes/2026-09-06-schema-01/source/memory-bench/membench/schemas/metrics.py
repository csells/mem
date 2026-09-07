"""§12 — metric groups (full field sets).

Every group in spec §12.1-§12.6 is modeled here. Fields split into two kinds:

* **Mechanical** — computed deterministically by `membench.metrics.scorers` from a
  trace + memory events + the step's expected reads/writes/probes (set arithmetic,
  ranking math, counting). These carry real values on a run.
* **Judge seams** — fields that require semantic judgment (`rubric_score`,
  `completion_quality`, the action-impact booleans, `derailment_signal` magnitude).
  They stay at Optional/None defaults here; an LLM judge populates them later. We do
  NOT fake them with heuristics (ZFC boundary, plan §A / patterns.md §ZFC).

Privacy + interruption groups (plan §A, DIV-4) remain *measured, not acted on*.
"""

from pydantic import BaseModel, Field


class TaskMetrics(BaseModel):
    """§12.1 — task outcome."""

    reward: float = 0.0  # 0-1
    pass_: bool = Field(default=False, alias="pass")
    # Judge seams — LLM-as-judge populates these; None until then (do not compute here).
    rubric_score: float | None = None
    completion_quality: float | None = None
    final_goal_success: bool = False
    verifier_errors: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class EfficiencyMetrics(BaseModel):
    """§12.2 — efficiency."""

    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    # SCORED METRIC WITH A DEFINITION HISTORY — a number from one SHA is not comparable to a
    # number from another across these two boundaries, and a cross-SHA table must say so:
    #   * before d9809a2/5e45493, an agent-made Bash `bd recall` counted as NON-memory work, so
    #     `non_memory_tool_calls` was inflated by the memory calls the agent chose to make;
    #   * at 5e45493 (FIX 6) it stopped counting there and was routed nowhere, so `tool_calls_total`
    #     and `tool_latency_ms` UNDER-reported by that same quantity;
    #   * from this commit all three channels are summed, and total means total.
    # The change is a no-op for any arm that hands the agent no memory tool (none of its calls
    # match), so only the memory-surface arms move — which is exactly why the drift was invisible
    # until the surface shipped.
    tool_calls_total: int = 0
    # Memory calls the HARNESS performed on the arm's behalf (one per normalized MemoryEvent).
    memory_tool_calls: int = 0
    # Memory calls the AGENT chose to make, parsed from observed tool_use argv by
    # ``runner.tool_surface``. Deliberately a SEPARATE counter from ``memory_tool_calls``: summing
    # them would make an arm that retrieves for the agent indistinguishable from an agent that
    # reached for the tool itself, which is the one distinction E3b exists to measure.
    endogenous_memory_tool_calls: int = 0
    # Of those, the ones that read and the ones that wrote. An agent that only ever writes and an
    # agent that only ever reads both show up as non-zero above; only this split separates them.
    endogenous_memory_reads: int = 0
    endogenous_memory_writes: int = 0
    # True when the step handed the agent a memory tool and the agent made no memory call at all.
    # This is NOT a memory failure and must not be scored as one: it records that the measured
    # behaviour did not occur, which on an endogenous step is the primary observation. False on a
    # step that offers no memory tool, where "did not call" carries no information.
    tool_not_called: bool = False
    non_memory_tool_calls: int = 0
    wall_clock_latency_ms: float = 0.0
    model_latency_ms: float = 0.0
    tool_latency_ms: float = 0.0
    cost_usd: float = 0.0
    retries: int = 0
    turns: int = 0


class RetrievalMetrics(BaseModel):
    """§12.3 — retrieval."""

    read_attempted: bool = False
    relevant_memory_available: bool = False
    relevant_memory_retrieved: bool = False
    retrieval_rank: int | None = None  # 1-based rank of first relevant id; None if absent
    precision_at_k: float = 0.0
    recall_at_k: float = 0.0
    mrr: float = 0.0
    nDCG: float = 0.0  # noqa: N815 — spec §12.3 field name (mixedCase is intentional)
    distractor_retrieval_rate: float = 0.0
    stale_memory_retrieval_rate: float = 0.0
    missed_required_memory_count: int = 0
    # Observability for the context-overflow gate (mem-1m0s): True when the retrieve
    # call was SKIPPED because the RUNNING token count accumulated over the
    # condition's prior steps reached `context_budget_tokens` (threaded through
    # RetrievalInputs -> score_retrieval's constructor call in runner/metrics.py; no
    # scorer signature change).
    context_gated: bool = False


class RetentionMetrics(BaseModel):
    """§12.4 — retention."""

    expected_memory_written: bool = False
    write_hit_rate: float = 0.0
    write_miss_rate: float = 0.0
    over_retention_rate: float = 0.0
    noise_write_rate: float = 0.0
    # Fraction of the agent's writes that landed on an id the step AUTHORED as
    # forbidden (``SequenceStep.forbidden_memory_writes`` — e.g. re-persisting a
    # superseded v1). Distinct from ``over_retention_rate``, which is "wrote an id
    # nobody asked for": a forbidden id is one the harness explicitly named as
    # wrong-to-write, so this is a directed channel rather than a volume proxy.
    # 0.0 when no forbidden ids are authored (an honest "not measured here").
    forbidden_write_rate: float = 0.0
    correct_scope_rate: float = 0.0
    correct_backend_rate: float = 0.0
    stale_memory_removed: bool = False
    supersession_correct: bool = False


class SynthesisMetrics(BaseModel):
    """§12.5 — synthesis / cross-session dependency.

    Counts of supporting memories and cross-session success are mechanical (set
    arithmetic over probes/required ids). `multi_backend_synthesis_success` and
    `contradiction_resolution_success` need a judge to confirm the agent actually
    *combined* sources / resolved a conflict — left as judge seams (None).
    """

    supporting_memories_required: int = 0
    supporting_memories_used: int = 0
    multi_backend_synthesis_success: bool | None = None
    cross_session_dependency_success: bool = False
    contradiction_resolution_success: bool | None = None


class ActionImpactMetrics(BaseModel):
    """§12.6 — did memory change what the agent did?

    Every field is a counterfactual judgment ("would the agent have chosen
    differently without this memory?") — pure judge seams. None until populated.
    """

    memory_changed_tool_choice: bool | None = None
    memory_changed_plan: bool | None = None
    memory_changed_output: bool | None = None
    memory_prevented_known_failure: bool | None = None
    memory_improved_verification: bool | None = None


class PrivacyMetrics(BaseModel):
    """Privacy axis — plan §A DIV-4. Measured, not acted on."""

    privacy_class: str | None = None  # none | internal | sensitive
    leakage_flags: list[str] = Field(default_factory=list)


class InterruptionMetrics(BaseModel):
    """Interruption axis — plan §A DIV-4. Measured, not acted on.

    `derailment_signal` magnitude is a judge seam (None until scored); `inject_timing`
    is a mechanical attribute of where the interruption was injected.
    """

    derailment_signal: float | None = None
    inject_timing: str | None = None  # on_failure | off_failure


class MetricsBundle(BaseModel):
    """All metric groups for one trial (one step under one condition)."""

    task: TaskMetrics = Field(default_factory=TaskMetrics)
    efficiency: EfficiencyMetrics = Field(default_factory=EfficiencyMetrics)
    retrieval: RetrievalMetrics = Field(default_factory=RetrievalMetrics)
    retention: RetentionMetrics = Field(default_factory=RetentionMetrics)
    synthesis: SynthesisMetrics = Field(default_factory=SynthesisMetrics)
    action_impact: ActionImpactMetrics = Field(default_factory=ActionImpactMetrics)
    privacy: PrivacyMetrics = Field(default_factory=PrivacyMetrics)
    interruption: InterruptionMetrics = Field(default_factory=InterruptionMetrics)
