"""`none` — the no-memory control (§4 condition A).

Retrieval returns nothing and writes are not supported. The runner does not invoke
memory under the no_memory condition; this system exists so the interface is
uniform and a `none` config is still expressible.
"""

from membench.memory_systems.base import MemorySystem, RetrievalRequest, RetrieveResult
from membench.runtime import StepContext
from membench.schemas.memory_event import MemoryBackend, MemoryEvent, MemoryOperation


class NoneMemory(MemorySystem):
    name = "none"
    backend = MemoryBackend.FILESYSTEM
    supports_write = False

    def reset(self, trial_id: str) -> None:
        return None

    def retrieve(self, request: RetrievalRequest, ctx: StepContext) -> RetrieveResult:
        event = MemoryEvent(
            event_id=ctx.clock.event_id(),
            trial_id=ctx.trial_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            timestamp=ctx.clock.timestamp(),
            concrete_tool="none",
            normalized_operation=MemoryOperation.SEARCH,
            backend=self.backend,
            query=request.query_text,
            success=True,
        )
        return RetrieveResult(payloads={}, event=event)

    def write(self, memory_id: str, content: str, ctx: StepContext) -> MemoryEvent:
        raise NotImplementedError("NoneMemory does not support writes")
