"""§8 — extractor output schema.

The extractor *model* (which proposes candidate memories from a trace) is a later
phase; this module defines only the schema so traces and reference systems can be
typed against it now.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class MemoryType(StrEnum):
    """`candidate_memory.type` — the two-level taxonomy's type axis (§8).

    Reconciliation (plan §A, DIV-5): this supersedes the pre-spec flat 4-type list.
    The representation axis (filesystem/vector/kg) lives on `MemoryBackend`.
    """

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    PREFERENCE = "preference"
    ENTITY = "entity"
    RELATIONSHIP = "relationship"
    FAILURE_PATTERN = "failure_pattern"


class RetentionPolicy(StrEnum):
    KEEP = "keep"
    DISCARD = "discard"
    TTL = "ttl"
    SUPERSEDE = "supersede"


class MemoryScope(BaseModel):
    project: str | None = None
    repo: str | None = None
    task_family: str | None = None
    user: str | None = None
    team: str | None = None


class CandidateMemory(BaseModel):
    """A memory proposed from a trace (§8)."""

    memory_id: str
    source_trace_id: str
    type: MemoryType
    content: str
    scope: MemoryScope = Field(default_factory=MemoryScope)
    confidence: float = 1.0
    evidence_spans: list[str] = Field(default_factory=list)
    proposed_backend: str = "filesystem"
    retention_policy: RetentionPolicy = RetentionPolicy.KEEP
    supersedes: list[str] = Field(default_factory=list)
