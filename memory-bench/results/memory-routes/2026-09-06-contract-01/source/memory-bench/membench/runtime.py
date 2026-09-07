"""Deterministic runtime primitives shared by the runner and memory systems.

The skeleton is deterministic on purpose: a monotonic counter stands in for the
clock and the id generator so a sequence run is byte-reproducible (and tests need
no time/uuid mocking). Real runs under Harbor can inject a wall-clock variant
behind the same interface.
"""

from dataclasses import dataclass, field


class IdClock:
    """A deterministic monotonic source of event ids and timestamps."""

    def __init__(self) -> None:
        self._n = 0

    def _advance(self) -> int:
        self._n += 1
        return self._n

    def event_id(self, prefix: str = "ev") -> str:
        return f"{prefix}-{self._advance():04d}"

    def timestamp(self) -> str:
        # Deterministic, valid ISO-8601 for any counter value (sub-second offset
        # from an arbitrary epoch — avoids an out-of-range seconds field at n>59).
        return f"1970-01-01T00:00:00.{self._n:06d}Z"

    def latency_ms(self) -> float:
        return float(self._n)


@dataclass
class StepContext:
    """Per-step identity passed to the memory system when emitting events."""

    trial_id: str
    session_id: str
    step_id: str
    clock: IdClock = field(default_factory=IdClock)
