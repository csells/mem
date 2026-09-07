"""AsyncClientBridge — a sync wrapper around a persistent asyncio event loop, so an
async-native backend client (NAT ``MemoryEditor``, Graphiti) can satisfy the SYNC
``SemanticMemoryClient`` Protocol (see semantic_base.py) without making the seam — or
the deterministic fakes — async.

The loop is held across many sequential ``run`` calls so the backend's Redis/graph-
driver connection lifecycle stays warm (``asyncio.run`` per call would tear that down
every time). The loop is created with ``new_event_loop()`` and never installed as the
thread's current loop (no ``set_event_loop``): each bridge owns EXACTLY ONE loop on
its instance, never a shared/global/module-level one. That isolation is load-bearing —
the mem-lvp.12 concurrency audit (failure mode #5) found a shared loop is both a global
serialization point and a shared-connection contamination vector across trials/arms.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine, Mapping
from types import TracebackType
from typing import Any, TypeVar

T = TypeVar("T")

#: Harness per-trial wall-clock budget (seconds) for a single backend coroutine,
#: read by ``trial_timeout`` and threaded into the real-backend client factories'
#: ``AsyncClientBridge``. Unset means unbounded (the default bridge behavior).
ENV_TRIAL_TIMEOUT_SEC = "MEMBENCH_TRIAL_TIMEOUT_SEC"


def trial_timeout(env: Mapping[str, str] | None = None) -> float | None:
    """Resolve the harness per-trial timeout for ``AsyncClientBridge(timeout=...)``
    from the environment (``MEMBENCH_TRIAL_TIMEOUT_SEC``), so the real-backend arms
    bound a hung Redis/Graphiti/NAT call instead of taking it from a hardcoded literal.

    Unset or empty -> ``None`` (unbounded, preserving the default bridge behavior). A
    positive float is the per-call budget. A non-numeric or non-positive value is a
    misconfiguration and raises ``ValueError`` at this boundary rather than silently
    disabling the guard (a ``wait_for`` deadline of 0/negative would trip every trial).
    """
    source = os.environ if env is None else env
    raw = source.get(ENV_TRIAL_TIMEOUT_SEC, "").strip()
    if not raw:
        return None
    try:
        seconds = float(raw)
    except ValueError as exc:
        raise ValueError(f"{ENV_TRIAL_TIMEOUT_SEC}={raw!r} is not a number") from exc
    if seconds <= 0:
        raise ValueError(f"{ENV_TRIAL_TIMEOUT_SEC}={raw!r} must be a positive number of seconds")
    return seconds


class AsyncClientBridge:
    """Holds one persistent event loop and runs coroutines on it synchronously.

    One loop per instance, owned for the instance's lifetime. ``close`` (or exiting
    the context manager) tears the loop down; ``run`` after that raises rather than
    silently spinning up a replacement.

    Not thread-safe: calls must be sequential. ``run_until_complete`` rejects
    re-entrant or concurrent use of the same loop, which matches the harness's
    one-bridge-per-arm, serial-trial execution model.

    We deliberately do NOT delegate to ``asyncio.Runner`` despite the overlap:
    ``Runner`` calls ``events.set_event_loop()`` on init, reintroducing the
    thread-global current-loop mutation the mem-lvp.12 audit (failure mode #5)
    requires us to avoid. ``close`` replicates only its teardown sequence, never
    its global-state side effect.
    """

    def __init__(self, timeout: float | None = None) -> None:
        # new_event_loop (not get_event_loop) guarantees a fresh, instance-private
        # loop — never the thread's shared current loop.
        self._loop = asyncio.new_event_loop()
        self._closed = False
        # Optional per-call wall-clock budget for run(). None (default) preserves the
        # original unbounded behavior; a value bounds a hung backend coroutine
        # (Redis/Graphiti/NAT stall) so it raises instead of blocking the harness
        # thread forever.
        self._timeout = timeout

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """The held loop. Exposed for identity/lifecycle assertions, not for callers
        to drive directly — go through ``run``."""
        return self._loop

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        """Drive ``coro`` to completion on the held loop and return its result.
        Exceptions raised inside the coroutine propagate to the caller unchanged.

        If a ``timeout`` was set at construction, the coroutine is bounded by
        ``asyncio.wait_for``: on expiry it is cancelled and ``asyncio.TimeoutError``
        propagates (never swallowed into a sentinel). The loop stays alive and usable
        for subsequent ``run``/``close`` calls."""
        if self._closed:
            raise RuntimeError("AsyncClientBridge is closed; create a new instance.")
        if self._timeout is not None:
            coro = asyncio.wait_for(coro, self._timeout)
        return self._loop.run_until_complete(coro)

    def close(self) -> None:
        """Stop reusing the loop and release it. Idempotent.

        Drains async generators and the default executor before closing — the same
        teardown ``asyncio.run``/``asyncio.Runner`` perform — so backends that stream
        via ``async for`` or offload work through ``run_in_executor`` don't leak
        pending tasks or daemon threads past the bridge's lifetime."""
        if self._closed:
            return
        self._closed = True
        try:
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.run_until_complete(self._loop.shutdown_default_executor())
        finally:
            self._loop.close()

    def __enter__(self) -> AsyncClientBridge:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
