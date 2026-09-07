"""Pure aggregation for the throughput sweep: turn a batch of per-request
``StreamResult``s plus the before/after runtime snapshots into one row of the
latency-throughput-KV frontier. No network, no threads — the script in
``scripts/engine_throughput_sweep.py`` does the IO and concurrency; this is the math.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass

from membench.engines.client import StreamResult
from membench.engines.metrics_scrape import EngineRuntimeStats


def percentile(values: Sequence[float], q: float) -> float | None:
    """The ``q``-th percentile (0..1) by nearest-rank on the sorted values. None for an
    empty input. Nearest-rank (not interpolated) keeps the result a value that actually
    occurred — adequate for the dozens-to-hundreds of samples a sweep collects."""
    if not values:
        return None
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be in [0, 1]")
    ordered = sorted(values)
    return ordered[_ceil_rank(len(ordered), q) - 1]


def _ceil_rank(n: int, q: float) -> int:
    """The 1-based nearest-rank index for the ``q``-th percentile of ``n`` values,
    clamped to [1, n]."""
    rank = int(q * n)
    if rank < q * n:  # round up to the nearest rank
        rank += 1
    return min(max(rank, 1), n)


@dataclass(frozen=True)
class SweepRow:
    """One point on the frontier: an (engine, concurrency) cell with its latency
    percentiles, realized throughput, and the KV / prefix-cache state around the run."""

    engine: str
    concurrency: int
    requests: int
    completed: int
    failed: int
    wall_s: float
    request_throughput: float | None
    output_token_throughput: float | None
    ttft_p50_s: float | None
    ttft_p90_s: float | None
    itl_median_p50_s: float | None
    output_tps_p50: float | None
    kv_cache_usage_before: float | None
    kv_cache_usage_after: float | None
    prefix_cache_hit_rate_before: float | None
    prefix_cache_hit_rate_after: float | None
    # True per-cell hit rate from the raw-counter delta (vLLM). The *_before/_after
    # fields above are cumulative lifetime ratios and are NOT a per-cell rate; this is.
    # None for engines without raw counters (SGLang) → use its windowed gauge instead.
    prefix_cache_hit_rate_delta: float | None
    num_waiting_after: float | None
    preemptions_delta: float | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def aggregate_rows(
    *,
    engine: str,
    concurrency: int,
    requests: int,
    results: Sequence[StreamResult],
    wall_s: float,
    before: EngineRuntimeStats | None,
    after: EngineRuntimeStats | None,
) -> SweepRow:
    """Aggregate one (engine, concurrency) cell. ``results`` holds only the completed
    requests; ``requests`` is the number dispatched, so ``failed`` is the difference.
    The KV / prefix-cache snapshots are recorded before and after the batch so the
    cache warm-up across the batch is visible, not just a single instantaneous read."""
    completed = len(results)
    ttfts = [r.ttft_s for r in results if r.ttft_s is not None]
    itls = [m for r in results if (m := r.median_itl_s()) is not None]
    tps = [t for r in results if (t := r.output_tps()) is not None]
    total_output_tokens = sum(r.output_tokens for r in results)
    return SweepRow(
        engine=engine,
        concurrency=concurrency,
        requests=requests,
        completed=completed,
        failed=requests - completed,
        wall_s=wall_s,
        request_throughput=(completed / wall_s) if wall_s > 0 else None,
        output_token_throughput=(total_output_tokens / wall_s) if wall_s > 0 else None,
        ttft_p50_s=percentile(ttfts, 0.50),
        ttft_p90_s=percentile(ttfts, 0.90),
        itl_median_p50_s=percentile(itls, 0.50),
        output_tps_p50=percentile(tps, 0.50),
        kv_cache_usage_before=_get(before, "kv_cache_usage"),
        kv_cache_usage_after=_get(after, "kv_cache_usage"),
        prefix_cache_hit_rate_before=_get(before, "prefix_cache_hit_rate"),
        prefix_cache_hit_rate_after=_get(after, "prefix_cache_hit_rate"),
        prefix_cache_hit_rate_delta=_delta_hit_rate(before, after),
        num_waiting_after=_get(after, "num_waiting"),
        preemptions_delta=_counter_delta(before, after, "num_preemptions_total"),
    )


def _get(stats: EngineRuntimeStats | None, field: str) -> float | None:
    return getattr(stats, field) if stats is not None else None


def _counter_delta(
    before: EngineRuntimeStats | None, after: EngineRuntimeStats | None, field: str
) -> float | None:
    b, a = _get(before, field), _get(after, field)
    if a is None or b is None:
        return None
    return a - b


def _delta_hit_rate(
    before: EngineRuntimeStats | None, after: EngineRuntimeStats | None
) -> float | None:
    """Per-cell prefix-cache hit rate from the raw-counter delta across the batch:
    (hits_after - hits_before) / (queries_after - queries_before). Returns None when
    the engine exports no raw counters (SGLang) or no new queries arrived (0/0)."""
    hits = _counter_delta(before, after, "prefix_cache_hits_total")
    queries = _counter_delta(before, after, "prefix_cache_queries_total")
    if hits is None or queries is None:  # engine exports no raw counters (SGLang)
        return None
    if queries <= 0 or hits < 0:  # no new queries, or a counter reset (engine restart)
        return None
    return hits / queries


def failed_cells(rows: Sequence[SweepRow]) -> list[SweepRow]:
    """Cells with swallowed request failures. ``run_cell`` counts a failed request but
    still emits a row whose throughput is computed over completed-only — a plausible
    but invalid number. The experiment layer must reject these before they reach a
    headline; this is that gate."""
    return [r for r in rows if r.failed > 0]
