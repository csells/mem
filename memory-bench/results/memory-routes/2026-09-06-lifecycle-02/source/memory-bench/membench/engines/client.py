"""A streaming, OpenAI-compatible client that measures what you actually tune for.

The harness cares about four per-request signals you cannot get from a blocking
call: time-to-first-token (TTFT), the inter-token latencies (ITL, a.k.a. TPOT), the
realized output-token throughput, and the token-level logprobs (for token-level
prediction / harness control). All four fall out of reading the SSE stream and
stamping each chunk with a clock.

Design mirrors ``grading.judge``: the HTTP/SSE transport and the clock are injected,
so the parsing (``parse_sse_line``) and the metric assembly (``assemble_stream_metrics``)
are pure and unit-tested with no network and no real time, while ``complete`` — the
one method that opens a socket — is never run in tests.
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field

from membench.engines.endpoints import EngineEndpoint

# (url, payload_bytes) -> an iterator of decoded SSE lines ("data: {...}", "", ...).
Transport = Callable[[str, bytes], Iterator[str]]
# A monotonic clock in seconds; injected so timing is deterministic under test.
Clock = Callable[[], float]


@dataclass(frozen=True)
class TokenLogprob:
    """One generated token and its logprob (token-level prediction signal)."""

    token: str
    logprob: float


@dataclass(frozen=True)
class StreamChunk:
    """One parsed SSE delta: the text it added, any token logprobs it carried, and
    whether it is the stream's terminal chunk (``finish_reason`` set)."""

    text: str
    logprobs: tuple[TokenLogprob, ...] = ()
    finished: bool = False


@dataclass(frozen=True)
class StreamResult:
    """The measured outcome of one streamed completion.

    ``ttft_s`` is None only for an empty stream (no text ever arrived). ``itl_s`` holds
    the gaps between successive token-bearing chunks; its length is one less than the
    number of token-bearing chunks. ``output_tokens`` counts token-bearing chunks (a
    server-side ``usage`` count, when present, is recorded separately as it may differ
    from chunk count under multi-token chunks)."""

    text: str
    ttft_s: float | None
    itl_s: tuple[float, ...]
    total_s: float
    output_tokens: int
    logprobs: tuple[TokenLogprob, ...]
    finish_reason_seen: bool

    def median_itl_s(self) -> float | None:
        """Median inter-token latency, or None when fewer than one gap was observed."""
        if not self.itl_s:
            return None
        ordered = sorted(self.itl_s)
        mid = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2

    def output_tps(self) -> float | None:
        """Realized decode throughput in output tokens/sec over the generation phase
        (first token → last token). None when there is no generation phase to measure."""
        if self.ttft_s is None or self.output_tokens < 2:
            return None
        decode_s = self.total_s - self.ttft_s
        if decode_s <= 0:
            return None
        # The first token is attributed to prefill (TTFT); the rest to decode.
        return (self.output_tokens - 1) / decode_s


def parse_sse_line(line: str) -> StreamChunk | None:
    """Parse one SSE line into a ``StreamChunk``.

    Returns None for blank keep-alive lines, comment lines, and the terminal
    ``data: [DONE]`` sentinel. A ``data:`` line whose JSON does not match the
    OpenAI chat-completion chunk shape yields an empty (no-text) chunk rather than
    raising — a single malformed keep-alive must not abort a long generation — but a
    line that is not valid JSON at all is a real protocol error and raises."""
    stripped = line.strip()
    if not stripped or stripped.startswith(":"):
        return None
    if not stripped.startswith("data:"):
        return None
    payload = stripped[len("data:") :].strip()
    if payload == "[DONE]":
        return None
    obj = json.loads(payload)  # malformed JSON is a real protocol error → raise
    choices = obj.get("choices") if isinstance(obj, dict) else None
    if not isinstance(choices, list) or not choices:
        return StreamChunk(text="")
    choice = choices[0]
    delta = choice.get("delta") if isinstance(choice, dict) else None
    text = ""
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, str):
            text = content
    finished = isinstance(choice, dict) and choice.get("finish_reason") is not None
    return StreamChunk(text=text, logprobs=_extract_logprobs(choice), finished=finished)


def _extract_logprobs(choice: object) -> tuple[TokenLogprob, ...]:
    """Lift the ``logprobs.content[]`` entries from a chat-completion chunk choice.
    Tolerant of the field being absent (logprobs not requested) — returns ()."""
    if not isinstance(choice, dict):
        return ()
    lp = choice.get("logprobs")
    if not isinstance(lp, dict):
        return ()
    content = lp.get("content")
    if not isinstance(content, list):
        return ()
    out: list[TokenLogprob] = []
    for entry in content:
        if isinstance(entry, dict) and isinstance(entry.get("token"), str):
            value = entry.get("logprob")
            if isinstance(value, (int, float)):
                out.append(TokenLogprob(token=entry["token"], logprob=float(value)))
    return tuple(out)


def assemble_stream_metrics(
    events: Sequence[tuple[float, StreamChunk]], t_start: float
) -> StreamResult:
    """Compute the per-request metrics from time-stamped chunks. Pure.

    ``events`` is the ordered ``(clock_time, chunk)`` log captured while reading the
    stream; ``t_start`` is the clock reading taken immediately before the request was
    sent. TTFT is ``first_token_time - t_start``; ITL gaps are between successive
    token-bearing chunks; total time runs to the last chunk seen."""
    text_parts: list[str] = []
    logprobs: list[TokenLogprob] = []
    token_times: list[float] = []
    finish_seen = False
    last_time = t_start
    for ts, chunk in events:
        last_time = ts
        if chunk.finished:
            finish_seen = True
        if chunk.text:
            text_parts.append(chunk.text)
            token_times.append(ts)
        logprobs.extend(chunk.logprobs)

    ttft = (token_times[0] - t_start) if token_times else None
    itl = tuple(token_times[i] - token_times[i - 1] for i in range(1, len(token_times)))
    return StreamResult(
        text="".join(text_parts),
        ttft_s=ttft,
        itl_s=itl,
        total_s=last_time - t_start,
        output_tokens=len(token_times),
        logprobs=tuple(logprobs),
        finish_reason_seen=finish_seen,
    )


def _urllib_transport(url: str, payload: bytes, *, timeout: float) -> Iterator[str]:
    """Default transport: POST the payload and yield decoded SSE lines as they arrive.
    A trust-boundary call to the local engine — a real timeout so a hung server
    surfaces as an error rather than an indefinite hang."""
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw in response:
            yield raw.decode("utf-8")


@dataclass(frozen=True)
class StreamingClient:
    """Drives one engine's streaming chat-completions API and returns measured metrics.

    ``transport`` and ``clock`` are injected (defaults bind urllib + perf_counter) so
    the streaming/measurement logic is exercised in tests without a live engine."""

    endpoint: EngineEndpoint
    timeout_s: float = 120.0
    transport: Transport | None = None
    clock: Clock = time.perf_counter
    extra_body: dict[str, object] = field(default_factory=dict)

    def build_payload(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float,
        logprobs: bool,
        top_logprobs: int | None,
    ) -> bytes:
        """Assemble the streaming request body. Pure. ``stream_options.include_usage``
        asks the engine to emit a final ``usage`` chunk; ``extra_body`` carries
        engine-specific knobs (e.g. SGLang sampling params) without a schema change."""
        body: dict[str, object] = {
            "model": self.endpoint.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if logprobs:
            body["logprobs"] = True
            if top_logprobs is not None:
                body["top_logprobs"] = top_logprobs
        body.update(self.extra_body)
        return json.dumps(body).encode()

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 256,
        temperature: float = 0.0,
        logprobs: bool = False,
        top_logprobs: int | None = None,
    ) -> StreamResult:
        """Stream one completion and return its measured metrics. Opens a socket;
        never run in tests."""
        payload = self.build_payload(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            logprobs=logprobs,
            top_logprobs=top_logprobs,
        )
        transport = self.transport or (
            lambda url, body: _urllib_transport(url, body, timeout=self.timeout_s)
        )
        t_start = self.clock()
        events: list[tuple[float, StreamChunk]] = []
        for line in transport(self.endpoint.chat_completions_url(), payload):
            chunk = parse_sse_line(line)
            if chunk is not None:
                events.append((self.clock(), chunk))
        return assemble_stream_metrics(events, t_start)
