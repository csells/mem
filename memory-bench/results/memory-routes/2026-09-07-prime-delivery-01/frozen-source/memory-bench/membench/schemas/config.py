"""§3 — the experiment / agent / memory configuration schemas."""

from pydantic import BaseModel, Field

from membench.schemas.conditions import Condition
from membench.schemas.memory_event import MemoryBackend


class AgentConfig(BaseModel):
    """The agent half of the system model (§3).

    Boundary (plan §A, DIV-1): the agent-under-test runs on our Claude account via
    the OAuth subscription — that paid path is approved. The no-paid-API constraint
    applies to the *memory* stack only (see `MemoryConfig`).
    """

    agent_config_id: str
    model: str = "anthropic/claude-opus-4-8"
    runtime: str = "claude_code"
    instructions: str = ""
    connected_tools: list[str] = Field(default_factory=list)
    connected_data_sources: list[str] = Field(default_factory=list)


class MemoryConfig(BaseModel):
    """The memory-system half of the system model (§3).

    `system` selects a reference memory_system. The skeleton ships
    none / oracle / filesystem (§14); `ours` and competitive systems (a-mem / mem0
    / graphiti / nat) plug in later (mem-lvp) behind the same interface.

    no-paid-API (plan §A, DIV-1): backends / embeddings / extractor / judge are
    OSS / self-hosted.
    """

    memory_config_id: str
    system: str = "none"  # none | oracle | filesystem (skeleton reference set)
    instructions: str = ""
    memory_tools: list[str] = Field(default_factory=list)
    storage_backends: list[MemoryBackend] = Field(default_factory=list)
    retrieval_strategy: str = "none"
    # Opt-in context-overflow gate (mem-1m0s): when set, MEMORY_ENABLED skips a step's
    # retrieve once the RUNNING token count accumulated over the condition's prior
    # steps reaches this budget. None (the default) preserves always-on retrieval —
    # zero blast radius to existing runs.
    context_budget_tokens: int | None = None
    # Retrieval width override. ``None`` means "use the arm's own default". Currently
    # only the ``lexical`` arm's construction consumes this (§runner/conditions.py
    # ``_system_for``); other arms ignore it.
    top_k: int | None = Field(default=None, ge=1)


class ExperimentConfig(BaseModel):
    """A full experiment: an agent x a memory system x a dataset, run under the
    requested conditions (§3 / §4)."""

    experiment_id: str
    agent: AgentConfig
    memory: MemoryConfig
    dataset_id: str
    conditions: list[Condition] = Field(
        default_factory=lambda: [
            Condition.NO_MEMORY,
            Condition.ORACLE_MEMORY,
            Condition.MEMORY_ENABLED,
        ]
    )
