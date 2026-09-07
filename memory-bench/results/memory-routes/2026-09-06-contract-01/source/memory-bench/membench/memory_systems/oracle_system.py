"""`oracle` — the memory-sensitivity ceiling (§4 condition B).

Pre-loaded by the harness with the exact relevant memory for the sequence; a
retrieve call returns precisely the requested ids (perfect retrieval). This is the
task-validity gate: if `oracle ≈ no_memory`, the task does not discriminate memory
benefit and is rejected (plan §A, DIV-3).
"""

from membench.memory_systems.base import MemorySystem, RetrievalRequest, RetrieveResult
from membench.runtime import StepContext
from membench.schemas.memory_event import MemoryBackend, MemoryEvent, MemoryOperation


class OracleMemory(MemorySystem):
    name = "oracle"
    backend = MemoryBackend.FILESYSTEM
    supports_write = False

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def load(self, memories: dict[str, str]) -> None:
        """Inject the exact relevant memory the harness considers ground truth."""
        self._store = dict(memories)

    def reset(self, trial_id: str) -> None:
        # Oracle contents are injected by the harness via load(); reset keeps them
        # (they are ground truth for the whole sequence, not trial-accumulated).
        return None

    def retrieve(self, request: RetrievalRequest, ctx: StepContext) -> RetrieveResult:
        requested_ids = request.requested_ids
        payloads = {mid: self._store[mid] for mid in requested_ids if mid in self._store}
        event = MemoryEvent(
            event_id=ctx.clock.event_id(),
            trial_id=ctx.trial_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            timestamp=ctx.clock.timestamp(),
            concrete_tool="oracle_inject",
            normalized_operation=MemoryOperation.READ,
            backend=self.backend,
            query=request.query_text,
            target_ids=list(requested_ids),
            retrieved_ids=list(payloads),
            latency_ms=ctx.clock.latency_ms(),
            success=True,
        )
        return RetrieveResult(payloads=payloads, event=event)

    def write(self, memory_id: str, content: str, ctx: StepContext) -> MemoryEvent:
        raise NotImplementedError("OracleMemory is injected, not written to")
