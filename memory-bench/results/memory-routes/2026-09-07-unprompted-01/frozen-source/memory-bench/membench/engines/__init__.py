"""Local dual-engine (vLLM + SGLang) inference harness for hands-on experimentation.

This subpackage lets the memory harness drive two self-hosted, OpenAI-compatible
inference engines side by side — vLLM (the throughput/observability baseline) and
SGLang (RadixAttention prefix-cache reuse, the lever that matters most when many
retrieval-augmented trials share a memory prefix) — behind the same
paid-host-fenced convention already used by `grading.judge` and
`memory_systems.local_stack`.

Three concerns, three modules:

- ``endpoints`` — config only (no SDK, no network at import). Pins the two engine
  endpoints, env-overridable, fenced against paid managed hosts.
- ``client``    — a streaming OpenAI-compatible client that captures TTFT / inter-token
  latency / output-token throughput and token-level logprobs. Transport and clock are
  injected so the metric assembly is unit-tested with no network.
- ``metrics_scrape`` — a Prometheus text-exposition parser that lifts each engine's
  KV-cache usage, prefix-cache hit rate, and queue depth into one common shape.
"""

from __future__ import annotations

from membench.engines.client import StreamChunk, StreamingClient, StreamResult
from membench.engines.endpoints import (
    DEFAULT_ENGINES,
    EngineEndpoint,
    PaidHostError,
    resolve_engines,
)
from membench.engines.metrics_scrape import EngineRuntimeStats, parse_prometheus

__all__ = [
    "DEFAULT_ENGINES",
    "EngineEndpoint",
    "EngineRuntimeStats",
    "PaidHostError",
    "StreamChunk",
    "StreamResult",
    "StreamingClient",
    "parse_prometheus",
    "resolve_engines",
]
