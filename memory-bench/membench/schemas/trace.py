"""§8 — the complete agent-session trace."""

from typing import Any

from pydantic import BaseModel, Field

from membench.schemas.memory_event import MemoryEvent


class TraceMessage(BaseModel):
    role: str
    content: str


class ToolCall(BaseModel):
    name: str
    tool_use_id: str | None = None
    # Positions in the stream's flattened message content blocks. Legacy traces have no
    # ordering evidence; a missing result position also covers an unanswered live call.
    tool_use_index: int | None = Field(default=None, ge=0)
    tool_result_index: int | None = Field(default=None, ge=0)
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: str | None = None
    # The `tool_result` block's own `is_error`. Structural, not a read of the result prose: a
    # reach that the harness answered with an error obtained nothing, and a recognizer that
    # cannot tell the two apart reports "the agent used memory" for 59 reads of a file that did
    # not exist.
    is_error: bool = False
    latency_ms: float = 0.0
    is_memory_tool: bool = False


class Trace(BaseModel):
    """One agent session's complete trace (§8)."""

    trial_id: str
    experiment_id: str
    dataset_id: str
    task_id: str
    step_id: str
    agent_config_id: str
    memory_config_id: str
    start_time: str
    end_time: str
    messages: list[TraceMessage] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    memory_events: list[MemoryEvent] = Field(default_factory=list)
    files_read: list[str] = Field(default_factory=list)
    files_written: list[str] = Field(default_factory=list)
    commands_run: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    final_answer: str = ""
    verifier_result: dict[str, Any] = Field(default_factory=dict)
