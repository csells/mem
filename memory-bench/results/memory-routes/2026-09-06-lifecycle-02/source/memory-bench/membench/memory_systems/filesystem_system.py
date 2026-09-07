"""`filesystem` — human-readable text memory (§7 A; the skeleton's integrated system).

Memories are Markdown files under a per-instance base dir; they persist across the
steps of a trial (the only continuity channel under the memory_enabled condition)
and are cleared on `reset` for a new trial. Retrieval is exact-by-id (deterministic
mechanism); fuzzy/embedding retrieval is a property of later systems (`ours`,
graphiti, …), not of this reference baseline.
"""

from pathlib import Path

from membench.memory_systems.base import MemorySystem, RetrievalRequest, RetrieveResult
from membench.runtime import StepContext
from membench.schemas.memory_event import MemoryBackend, MemoryEvent, MemoryOperation


def _safe_name(memory_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in memory_id)


class FilesystemMemory(MemorySystem):
    name = "filesystem"
    backend = MemoryBackend.FILESYSTEM
    supports_write = True

    def __init__(self, base_dir: str | Path | None = None) -> None:
        # Default to an in-process dict if no dir is given (hermetic); when a dir is
        # supplied, write real .md files (honest to "filesystem memory").
        self._base_dir: Path | None = Path(base_dir) if base_dir is not None else None
        self._store: dict[str, str] = {}
        if self._base_dir is not None:
            self._base_dir.mkdir(parents=True, exist_ok=True)

    def reset(self, trial_id: str) -> None:
        self._store = {}
        if self._base_dir is not None:
            trial_dir = self._base_dir / _safe_name(trial_id)
            trial_dir.mkdir(parents=True, exist_ok=True)
            for md in trial_dir.glob("*.md"):
                md.unlink()
            self._trial_dir: Path | None = trial_dir
        else:
            self._trial_dir = None

    def _read_all(self) -> dict[str, str]:
        if self._trial_dir is not None:
            return {md.stem: md.read_text(encoding="utf-8") for md in self._trial_dir.glob("*.md")}
        return dict(self._store)

    def retrieve(self, request: RetrievalRequest, ctx: StepContext) -> RetrieveResult:
        query = request.query_text
        requested_ids = request.requested_ids
        available = self._read_all()
        payloads = {mid: available[mid] for mid in requested_ids if mid in available}
        event = MemoryEvent(
            event_id=ctx.clock.event_id(),
            trial_id=ctx.trial_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            timestamp=ctx.clock.timestamp(),
            concrete_tool=f'grep("{query or ""}", ~/memory)',
            normalized_operation=MemoryOperation.SEARCH,
            backend=self.backend,
            query=query,
            target_ids=list(requested_ids),
            retrieved_ids=list(payloads),
            latency_ms=ctx.clock.latency_ms(),
            success=True,
        )
        return RetrieveResult(payloads=payloads, event=event)

    def write(self, memory_id: str, content: str, ctx: StepContext) -> MemoryEvent:
        # The id is the file stem, so it must survive _safe_name unchanged or the
        # read-back key (md.stem) won't match the written id. Fail fast rather than
        # silently storing under a mangled key that can never be retrieved.
        if _safe_name(memory_id) != memory_id:
            raise ValueError(
                f"memory_id {memory_id!r} is not filesystem-safe "
                "(use only alphanumerics, '-', '_', '.')"
            )
        if self._trial_dir is not None:
            (self._trial_dir / f"{_safe_name(memory_id)}.md").write_text(content, encoding="utf-8")
        else:
            self._store[memory_id] = content
        return MemoryEvent(
            event_id=ctx.clock.event_id(),
            trial_id=ctx.trial_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            timestamp=ctx.clock.timestamp(),
            concrete_tool=f'Write("~/memory/{_safe_name(memory_id)}.md")',
            normalized_operation=MemoryOperation.WRITE,
            backend=self.backend,
            written_ids=[memory_id],
            latency_ms=ctx.clock.latency_ms(),
            success=True,
        )

    # _trial_dir is set in reset(); declare for type-checkers / pre-reset access.
    _trial_dir: Path | None = None
