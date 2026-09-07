"""§6.2 — normalized memory operations + the memory_event record."""

from enum import StrEnum

from pydantic import BaseModel, Field


class MemoryOperation(StrEnum):
    """The canonical operation set every concrete memory tool maps into (§6.2)."""

    READ = "read"
    WRITE = "write"
    UPDATE = "update"
    DELETE = "delete"
    SEARCH = "search"
    CONSOLIDATE = "consolidate"
    PROMOTE = "promote"
    FORGET = "forget"
    CLASSIFY = "classify"
    DISCARD = "discard"


class MemoryBackend(StrEnum):
    """Backend representation a memory event acted on (§6.2 / §7)."""

    FILESYSTEM = "filesystem"
    VECTOR_DB = "vector_db"
    KG = "kg"
    MCP = "mcp"
    HYBRID = "hybrid"


class MemoryEvent(BaseModel):
    """One normalized memory operation, captured per the §6.2 schema."""

    event_id: str
    trial_id: str
    session_id: str
    step_id: str
    timestamp: str
    concrete_tool: str
    normalized_operation: MemoryOperation
    backend: MemoryBackend
    query: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    retrieved_ids: list[str] = Field(default_factory=list)
    written_ids: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    token_count_in: int | None = None
    token_count_out: int | None = None
    success: bool = True
    error: str | None = None
    # WHO captured this event — reconciled to the canonical TS literal
    # `source: z.string().min(1)` (src/schemas/memory-event.ts:85; TS is the source
    # of truth, so no competing TS field is added). Required there, but defaulted
    # OPTIONAL here so the existing in-harness construction sites (oracle /
    # filesystem / ours / lexical / consolidating / semantic / retention) keep
    # working unchanged. The default `"harness"` marks an event produced by the
    # in-process eval harness; the forward-capture path sets `"forward-capture"`.
    source: str = "harness"
