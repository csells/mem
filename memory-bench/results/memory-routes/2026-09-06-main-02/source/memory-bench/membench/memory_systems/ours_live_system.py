"""`ours-live` — the LIVE analog of the replay-only `ours` arm (mem-mtqi).

`OursMemory` (replay-only, `supports_write=False`) retrieves over a frozen
work-audit graph for a closed query work `B`. `OursLiveMemory` keeps that exact
retrieval path (it subclasses `OursMemory`, so READ is unchanged and failure-
triggered) but adds the forward-capture WRITE leg: at the deterministic capture
points the harness already detects (build / test / lint outcomes + `file:line`
errors, surfaced as a harness `write`), it EMITS a `memory_event` through the
single firewalled writer — the canonical `mem memory-event record` CLI — tagged
`source='forward-capture'`. It NEVER writes the SQLite `memory_events` table from
Python and NEVER ports the TS schema: the CLI is the only path into the store, so
the TS `MemoryEventSchema.strict()` allow-list governs every captured field.

Boundary discipline:

- READ delegates to `OursMemory.retrieve` — same LOO-bounded, replay-only
  retrieval; the harness re-checks its output against the boundary.
- WRITE shells the CLI; a failed emit RAISES (never a silent "no capture").
- `supports_write = True`, so the harness routes captures here. Because the base
  `OursMemory.write` raises, `seed()` is overridden to a no-op — harness distractor
  seeding must never emit a forward-capture event (that is environment state the
  harness owns, not an agent capture; mem-zt1c).

SCOPE (YAGNI): the pilot stays at failure-triggered capture — the same events
replay-only `ours` is scored on. It does NOT broaden to capture every tool call.

CONSTRUCTION CONTRACT: a runnable live arm needs a `mem_bin` (or an injected
`emit_runner`) so it can reach the CLI, plus a `store_path` for the replay READ
leg. A bare factory call (`build_memory_system("ours-live")`) supplies neither and
RAISES on first use — by design, so an unwired arm is never silently selected.
The runnable paths are (a) the conditions-runner `override=` injection seam and
(b) the `MEMBENCH_MEMORY_SYSTEM=ours-live` launch override, which resolves
`mem_bin`/`store_path` from `MEMBENCH_MEM_BIN`/`MEMBENCH_MEM_STORE` and fails fast
at launch if they are absent (mem-ymxp #4) — so a registered agent with that env
does LIVE write-capture, not an arm that raises on first write.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from membench.forward_capture import assert_capture_firewalled
from membench.mem_cli import run_mem_json
from membench.memory_systems.ours_system import OursMemory
from membench.runtime import StepContext
from membench.schemas.memory_event import MemoryBackend, MemoryEvent, MemoryOperation

# The tag every forward-capture write carries — reconciled to the TS literal and
# the Python MemoryEvent.source field (mem-mtqi #3).
FORWARD_CAPTURE_SOURCE = "forward-capture"

# The emit seam: `(argv) -> envelope data`. Injectable so tests exercise the write
# path with no built CLI / real store, mirroring `OursMemory`'s `RetrieveRunner`.
EmitRunner = Callable[[list[str]], dict[str, Any]]


def _default_emit_runner(mem_bin: str) -> EmitRunner:
    """Shell `mem memory-event record ... --json` through the shared seam. A failed
    emit raises `MemCliError` — a dropped capture is surfaced, never silenced."""

    def emit(argv: list[str]) -> dict[str, Any]:
        return run_mem_json([mem_bin, *argv])

    return emit


class OursLiveMemory(OursMemory):
    name = "ours-live"
    # Capture writes flow through this arm; the base OursMemory stays write-free.
    supports_write = True

    def __init__(
        self,
        store_path: str | Path | None = None,
        *,
        runner: Any | None = None,
        mem_bin: str | None = None,
        limit: int | None = None,
        emit_runner: EmitRunner | None = None,
        protected_labels: tuple[str, ...] = (),
    ) -> None:
        super().__init__(store_path, runner=runner, mem_bin=mem_bin, limit=limit)
        self._emit_runner = emit_runner
        self._emit_mem_bin = mem_bin
        # The KNOWN outcome identifiers the live firewall value-scans against. Empty
        # in the pilot (the in-flight work's outcome does not yet exist at capture
        # time), where the STRUCTURAL scan (nested-key/allow-list) stands alone.
        self._protected_labels = protected_labels

    def _resolve_emit_runner(self) -> EmitRunner:
        if self._emit_runner is not None:
            return self._emit_runner
        if self._emit_mem_bin is None:
            raise ValueError(
                "OursLiveMemory needs either an injected `emit_runner` or a `mem_bin` "
                "path to the `mem memory-event record` CLI to emit forward-capture events."
            )
        self._emit_runner = _default_emit_runner(self._emit_mem_bin)
        return self._emit_runner

    def write(
        self,
        memory_id: str,
        content: str,
        ctx: StepContext,
        *,
        payload: dict[str, Any] | None = None,
    ) -> MemoryEvent:
        """Emit one forward-capture `memory_event` through the firewalled CLI.

        `memory_id` is the captured memory reference (which memory) and `ctx` carries
        the session/work identity. The op is `write` (a capture is a write-time
        memory operation); `content` is NOT sent to the store — the CLI captures a
        REFERENCE, never memory content (the firewall scans references, content can
        carry outcome-correlated text). The returned `MemoryEvent` is the harness's
        normalized telemetry; the store's row is whatever the CLI wrote.

        The constructed event is run through `assert_capture_firewalled` BEFORE any
        emit (mem-ymxp #3): a novel field, an outcome identifier nested in `payload`,
        or a known outcome label embedded in `memory_ref` RAISES here, so the live
        write path is leak-scanned end-to-end — not a bypass of the offline projector.
        `payload` (structured, NON-content extras) is firewalled but, being label-side
        (PRD §Firewall), is NOT forwarded to the store — the pilot capture is
        reference-only; a dirty payload aborts the capture loudly."""
        event: dict[str, Any] = {
            "session": ctx.session_id,
            "op": "write",
            "backend": "kg",
            "memory_ref": memory_id,
            "source": FORWARD_CAPTURE_SOURCE,
        }
        if payload is not None:
            event["payload"] = payload
        assert_capture_firewalled(event, self._protected_labels)

        emit = self._resolve_emit_runner()
        argv = [
            "memory-event",
            "record",
            "--session",
            ctx.session_id,
            "--op",
            "write",
            "--backend",
            "kg",
            "--ref",
            memory_id,
            "--source",
            FORWARD_CAPTURE_SOURCE,
        ]
        data = emit(argv)
        return MemoryEvent(
            event_id=str(data.get("event_id") or ctx.clock.event_id()),
            trial_id=ctx.trial_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            timestamp=ctx.clock.timestamp(),
            concrete_tool="mem memory-event record",
            normalized_operation=MemoryOperation.WRITE,
            backend=MemoryBackend.KG,
            written_ids=[memory_id],
            latency_ms=ctx.clock.latency_ms(),
            success=True,
            source=FORWARD_CAPTURE_SOURCE,
        )

    def seed(self, memories: dict[str, str], ctx: StepContext) -> None:
        """No-op: distractor/world seeding is environment state the harness owns, not
        an agent capture, and must never emit a forward-capture event. Overrides the
        base `seed` (which would call `write` and emit) — mirrors the contract in
        `MemorySystem.seed` for a write-bearing arm that must not capture on seed."""
        return None
