"""`builtin` — the agent's OWN native memory as a comparison arm (mem-mor1 D-F).

The forward-capture pool differentiates three arms: `none` (no memory anywhere),
`ours-live` (mem's work-audit graph + forward-capture), and `builtin` — the agent's
native Claude/Codex memory as the baseline-to-beat (mem-whi). Stephanie's 2026-06-23
decision (AM ledger gc-408361): build it on the FREE/OAuth path, alongside none +
ours-live, not the paid Harbor grid.

From mem's STORE perspective this arm is uninvolved: it surfaces nothing
(`retrieve` returns no payloads) and persists nothing (`supports_write = False`).
That is NOT the `none` control: the difference between the two arms is realized at
agent launch — under `builtin` the agent's native memory is the continuity channel
(opaque to mem), under `none` no memory exists at all. Enabling the agent's native
memory is the RUN's job (`gc agent add`, the pool launch config); this arm is the
in-store half — it carries an honest empty store interaction and a distinct
`builtin` telemetry label so the pool attributes results to the right condition.

It is deliberately a no-store arm rather than a relabelled `none`: the two encode
different conditions (the no-memory control vs the native-memory baseline) that
change for different reasons, so coupling them would be a false abstraction.
"""

from membench.memory_systems.base import MemorySystem, RetrievalRequest, RetrieveResult
from membench.runtime import StepContext
from membench.schemas.memory_event import MemoryBackend, MemoryEvent, MemoryOperation


class BuiltinMemory(MemorySystem):
    name = "builtin"
    backend = MemoryBackend.FILESYSTEM
    # mem neither reads from nor writes to its store for this arm: the agent's native
    # memory is the continuity channel, opaque to mem and enabled at launch.
    supports_write = False

    def reset(self, trial_id: str) -> None:
        return None

    def retrieve(self, request: RetrievalRequest, ctx: StepContext) -> RetrieveResult:
        # No mem-store payload: the agent's native memory does the recall, off-store.
        # The event is labelled `builtin` so telemetry distinguishes this arm from the
        # `none` control even though both surface no mem payload.
        event = MemoryEvent(
            event_id=ctx.clock.event_id(),
            trial_id=ctx.trial_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            timestamp=ctx.clock.timestamp(),
            concrete_tool="builtin",
            normalized_operation=MemoryOperation.SEARCH,
            backend=self.backend,
            query=request.query_text,
            success=True,
        )
        return RetrieveResult(payloads={}, event=event)

    def write(self, memory_id: str, content: str, ctx: StepContext) -> MemoryEvent:
        raise NotImplementedError(
            "BuiltinMemory does not write to mem's store — the agent's native memory "
            "captures off-store, opaque to mem"
        )
