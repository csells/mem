"""§6.2 — map concrete memory-tool invocations into the canonical operation set.

This is pure mechanism (ZFC): a transparent, deterministic lookup keyed on
(backend, concrete_tool). Unknown tools raise rather than silently defaulting to a
no-op — an unmapped memory tool is a benchmark-validity bug we want surfaced, not
swallowed (§17: "Do not treat all memory systems as equivalent without normalized
operation mapping").
"""

from membench.schemas.memory_event import MemoryBackend, MemoryOperation

# (backend, concrete_tool) → canonical operation. Tool keys are matched
# case-insensitively against the bare verb (the leading identifier of the
# invocation, e.g. "Read" from `Read("~/memory/foo.md")`).
_MAPPING: dict[MemoryBackend, dict[str, MemoryOperation]] = {
    MemoryBackend.FILESYSTEM: {
        "read": MemoryOperation.READ,
        "cat": MemoryOperation.READ,
        "write": MemoryOperation.WRITE,
        "edit": MemoryOperation.UPDATE,
        "rm": MemoryOperation.DELETE,
        "grep": MemoryOperation.SEARCH,
        "ls": MemoryOperation.SEARCH,
    },
    MemoryBackend.MCP: {
        "add_memory": MemoryOperation.WRITE,
        "search_memories": MemoryOperation.SEARCH,
        "update_memory": MemoryOperation.UPDATE,
        "delete_memory": MemoryOperation.DELETE,
        "get_memory": MemoryOperation.READ,
    },
    MemoryBackend.VECTOR_DB: {
        "embed": MemoryOperation.CLASSIFY,
        "vector_search": MemoryOperation.SEARCH,
        "upsert": MemoryOperation.WRITE,
        "delete": MemoryOperation.DELETE,
    },
    MemoryBackend.KG: {
        "entity_search": MemoryOperation.SEARCH,
        "relationship_query": MemoryOperation.SEARCH,
        "upsert_entity": MemoryOperation.WRITE,
        "upsert_edge": MemoryOperation.WRITE,
        "delete_entity": MemoryOperation.DELETE,
    },
}


class UnknownMemoryToolError(KeyError):
    """Raised when a concrete tool has no mapping for its backend."""


def _tool_verb(concrete_tool: str) -> str:
    """Extract the bare verb from a concrete-tool string.

    `Read("~/memory/foo.md")` → `read`; `add_memory` → `add_memory`.
    """
    head = concrete_tool.strip().split("(", 1)[0].strip()
    return head.split()[0].lower() if head else ""


def normalize_operation(concrete_tool: str, backend: MemoryBackend) -> MemoryOperation:
    """Map a concrete tool invocation to its canonical `MemoryOperation`."""
    backend_map = _MAPPING.get(backend)
    if backend_map is None:
        raise UnknownMemoryToolError(
            f"No operation mapping registered for backend {backend.value!r}"
        )
    verb = _tool_verb(concrete_tool)
    op = backend_map.get(verb)
    if op is None:
        raise UnknownMemoryToolError(
            f"Concrete tool {concrete_tool!r} (verb {verb!r}) is unmapped for "
            f"backend {backend.value!r}"
        )
    return op
