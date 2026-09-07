from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrderingArm(StrEnum):
    KEY = "key"
    NAVIGATION = "navigation"
    INDEGREE = "indegree"
    OUTDEGREE = "outdegree"
    PAGERANK = "pagerank"
    REVERSE_PAGERANK = "reverse-pagerank"
    HITS_AUTHORITY = "hits-authority"
    HITS_HUB = "hits-hub"
    BM25F = "bm25f"
    CONTROL_AUTOMATIC = "control-automatic"
    CONTROL_SEMANTIC = "control-semantic"
    CONTROL_STRATEGY = "control-strategy"
    CONTROL_RAW = "control-raw"


class ControlPolicy(StrEnum):
    AUTOMATIC = "automatic"
    SEMANTIC = "pin-boost-demote"
    STRATEGY_SELECTION = "strategy-selection"
    RAW_NUMERIC = "raw-numeric-rank"


class ExperimentMode(StrEnum):
    SEARCH_ONLY = "search-only"
    NAVIGATION = "navigation"
    DEPTH_FIRST = "depth-first"


class TaskSplit(StrEnum):
    DEVELOPMENT = "development"
    HELDOUT = "heldout"


class TaskSourceKind(StrEnum):
    AUTHORED = "authored"
    SANITIZED_REAL_DERIVED = "sanitized-real-derived"


class BM25FConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    key_weight: float = Field(default=6.0, ge=0)
    alias_weight: float = Field(default=5.0, ge=0)
    title_weight: float = Field(default=3.0, ge=0)
    body_weight: float = Field(default=1.0, ge=0)
    k1: float = Field(default=1.2, gt=0)
    b: float = Field(default=0.75, ge=0, le=1)


class CompactMemory(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    key: str = ""
    title: str
    lifecycle: str
    excerpt: str
    matched_fields: tuple[str, ...] = ()
    rank: int = Field(ge=1)

    @field_validator("matched_fields", mode="before")
    @classmethod
    def normalize_null_matched_fields(cls, value: object) -> object:
        # Empty-search inventory pages have no match provenance. Go encodes a
        # nil slice as JSON null; normalize it to the same empty tuple used when
        # the field is omitted.
        return () if value is None else value


class DiscoveryPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[CompactMemory, ...]
    query: str
    order: OrderingArm
    page_size: int = Field(ge=1)
    unbounded: bool = False
    total_matched: int = Field(ge=0)
    complete: bool
    continuation: str = ""
    candidate_digest: str
    bm25f: BM25FConfig
    candidate_generation_ms: float = Field(default=0, ge=0)
    ordering_ms: float = Field(default=0, ge=0)


class ExhaustedDiscovery(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[CompactMemory, ...]
    pages: tuple[DiscoveryPage, ...]
    candidate_digest: str


class MemoryFixture(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    key: str
    title: str
    aliases: tuple[str, ...] = ()
    lifecycle: str = "active"
    navigation_rank: int | None = None
    references: tuple[str, ...] = ()
    provenance: str = "human"
    structural_ranks_by_corpus: dict[str, dict[str, int]] = Field(default_factory=dict)
    control_ranks_by_task: dict[str, dict[str, int]] = Field(default_factory=dict)
    body: str

    def stored_value(
        self, corpus_size: int | None = None, *, control_task_id: str | None = None
    ) -> str:
        aliases = ", ".join(self.aliases)
        references = ", ".join(self.references)
        rank = "" if self.navigation_rank is None else str(self.navigation_rank)
        structural = self.structural_ranks_by_corpus.get(str(corpus_size), {})
        rank_lines = "".join(
            f"structural_rank_{name.replace('-', '_')}: {position}\n"
            for name, position in sorted(structural.items())
        )
        controls = self.control_ranks_by_task.get(control_task_id or "", {})
        control_lines = "".join(
            f"structural_rank_{name.replace('-', '_')}: {position}\n"
            for name, position in sorted(controls.items())
        )
        return (
            "---\n"
            f"title: {self.title}\n"
            f"aliases: [{aliases}]\n"
            f"lifecycle: {self.lifecycle}\n"
            f"navigation_rank: {rank}\n"
            f"{rank_lines}"
            f"{control_lines}"
            f"references: [{references}]\n"
            f"provenance: {self.provenance}\n"
            "---\n"
            f"{self.body}"
        )


class ControlIntent(BaseModel):
    """Frozen operator intent used to compare query-independent rank controls."""

    model_config = ConfigDict(frozen=True)

    pin: tuple[str, ...] = ()
    boost: tuple[str, ...] = ()
    demote: tuple[str, ...] = ()
    selected_strategy: OrderingArm = OrderingArm.REVERSE_PAGERANK
    raw_numeric_ranks: dict[str, int] = Field(default_factory=dict)


class OrderingTask(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_id: str
    corpus_size: int
    query: str
    instruction: str
    primary_relevant: str
    acceptable_entry_points: tuple[str, ...]
    distractors: tuple[str, ...]
    expected_facts: tuple[str, ...]
    forbidden_facts: tuple[str, ...]
    split: TaskSplit = TaskSplit.DEVELOPMENT
    source_kind: TaskSourceKind = TaskSourceKind.AUTHORED
    source_shape: str = "authored-operational-control"
    source_provenance_hash: str = ""
    graph_family: str = ""
    failure_case: str = ""
    control_intent: ControlIntent | None = None


class FrozenCorpus(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 3
    seed: int
    structural_order_source_git_sha: str = ""
    memories: tuple[MemoryFixture, ...]
    tasks: tuple[OrderingTask, ...]


class ToolLogEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    sequence: int = Field(ge=1)
    operation: str
    started_at: str
    elapsed_ms: float = Field(ge=0)
    since_agent_start_ms: float | None = Field(default=None, ge=0)
    response_bytes: int = Field(ge=0)
    response_tokens_estimate: int = Field(ge=0)
    visible_ids: tuple[str, ...] = ()
    total_matched: int | None = Field(default=None, ge=0)
    continuation: str = ""
    memory_id: str | None = None
    references: tuple[str, ...] = ()
    followed_reference: bool = False
    server_candidate_generation_ms: float = Field(default=0, ge=0)
    server_ordering_ms: float = Field(default=0, ge=0)
    error: str | None = None


class OrderingRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    task_id: str
    query: str = ""
    corpus_size: int
    arm: OrderingArm
    mode: ExperimentMode = ExperimentMode.NAVIGATION
    repeat: int
    page_size: str
    total_matched: int
    primary_rank: int
    primary_page: int
    acceptable_rank: int | None
    acceptable_page: int | None
    pages_requested: int
    pages_to_first_useful: int | None
    page_one_acceptable_visible: bool
    compact_records_visible: int
    compact_result_bytes: int
    compact_result_tokens: int
    compact_bytes_to_first_useful: int = 0
    compact_tokens_to_first_useful: int = 0
    retrieval_tokens_to_first_useful: int = 0
    tool_calls_to_first_useful: int = 0
    retrieval_tool_calls: int
    time_to_first_useful_ms: float | None
    full_recalls: int
    first_recalled_relevant: bool | None
    graph_hops_after_first_useful: int
    graph_hops_total: int = 0
    reference_edges_exposed: int = 0
    branching_factor_mean: float = 0
    branching_factor_max: int = 0
    navigation_reached_primary: bool = False
    retrieval_related_tokens: int
    retrieval_latency_ms: float
    server_candidate_generation_ms: float
    server_ordering_ms: float
    end_to_end_ms: float
    task_success: bool
    abstained: bool
    premature_stop: bool
    agent_input_tokens: int
    agent_output_tokens: int
    mem_git_sha: str = ""
    mem_git_dirty: bool = False
    mem_git_diff_sha256: str = ""
    beads_git_sha: str = ""
    beads_git_dirty: bool = False
    beads_git_diff_sha256: str = ""
    beads_bin_sha256: str = ""
    structural_order_source_git_sha: str = ""
    agent_model: str = ""
    agent_cli_version: str = ""
    final_answer: str = ""
    failure: str | None = None
