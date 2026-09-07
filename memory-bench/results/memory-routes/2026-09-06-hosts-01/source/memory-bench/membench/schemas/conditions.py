"""§4 — the three required evaluation conditions."""

from enum import StrEnum


class Condition(StrEnum):
    """The three conditions every benchmark sequence must support (§4)."""

    NO_MEMORY = "no_memory"
    """A — memory disabled; establishes stateless performance."""

    ORACLE_MEMORY = "oracle_memory"
    """B — harness injects the exact relevant memory; the task-validity ceiling."""

    MEMORY_ENABLED = "memory_enabled"
    """C — the full memory system through its normal read/write/consolidate path."""
