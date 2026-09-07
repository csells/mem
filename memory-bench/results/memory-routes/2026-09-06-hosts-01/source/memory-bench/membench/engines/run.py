"""Execute a sweep: the IO + concurrency that ``sweep.py`` (pure math) deliberately
does not do. Both ``scripts/engine_throughput_sweep.py`` and the autotune trial
runner call into here, so the threaded load-gen + before/after scrape lives in one
place.

The client factory and the scrape function are injectable, so a cell can be driven
end-to-end in tests with a fake transport and no live engine.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor

from membench.engines.client import StreamingClient, StreamResult
from membench.engines.endpoints import EngineEndpoint
from membench.engines.metrics_scrape import EngineRuntimeStats, scrape_engine_stats
from membench.engines.sweep import SweepRow, aggregate_rows

Messages = list[dict[str, str]]
ClientFactory = Callable[[EngineEndpoint], StreamingClient]
Scraper = Callable[[EngineEndpoint], EngineRuntimeStats | None]


def default_client_factory(endpoint: EngineEndpoint) -> StreamingClient:
    return StreamingClient(endpoint=endpoint)


def default_scraper(endpoint: EngineEndpoint) -> EngineRuntimeStats | None:
    """Scrape runtime stats, returning None if the metrics endpoint is unreachable —
    a sweep still records latency even when Prometheus scraping is misconfigured. The
    failure is surfaced on stderr, never silently dropped."""
    try:
        return scrape_engine_stats(endpoint.metrics_url, endpoint.metric_prefix)
    except OSError as exc:
        print(f"  ! metrics scrape failed for {endpoint.name}: {exc}", file=sys.stderr)
        return None


def sweep_cell(
    endpoint: EngineEndpoint,
    concurrency: int,
    workload: Sequence[Messages],
    *,
    max_tokens: int,
    temperature: float,
    logprobs: bool,
    client_factory: ClientFactory = default_client_factory,
    scraper: Scraper = default_scraper,
    clock: Callable[[], float] = time.perf_counter,
) -> SweepRow:
    """Drive ``len(workload)`` requests through a thread pool of width ``concurrency``
    against one engine, scraping KV/prefix-cache state before and after, and aggregate
    the cell. A single failed request is logged and counted as a failure (``completed``
    < ``requests``), never aborting the cell."""
    client = client_factory(endpoint)
    before = scraper(endpoint)
    wall_start = clock()
    results: list[StreamResult] = []
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = [
            pool.submit(
                client.complete,
                list(msgs),
                max_tokens=max_tokens,
                temperature=temperature,
                logprobs=logprobs,
            )
            for msgs in workload
        ]
        for fut in futures:
            try:
                results.append(fut.result())
            except Exception as exc:
                # One bad request must not abort the cell — count it as a failure.
                print(f"  ! request failed on {endpoint.name}: {exc}", file=sys.stderr)
    wall_s = clock() - wall_start
    after = scraper(endpoint)
    return aggregate_rows(
        engine=endpoint.name,
        concurrency=concurrency,
        requests=len(workload),
        results=results,
        wall_s=wall_s,
        before=before,
        after=after,
    )


def sweep_engine(
    endpoint: EngineEndpoint,
    concurrencies: Sequence[int],
    workload: Sequence[Messages],
    *,
    max_tokens: int,
    temperature: float,
    logprobs: bool,
    client_factory: ClientFactory = default_client_factory,
    scraper: Scraper = default_scraper,
    on_row: Callable[[SweepRow], None] | None = None,
) -> list[SweepRow]:
    """Sweep one engine across every concurrency level. ``on_row`` is called as each
    cell finishes (for streaming progress / incremental persistence)."""
    rows: list[SweepRow] = []
    for concurrency in concurrencies:
        row = sweep_cell(
            endpoint,
            concurrency,
            workload,
            max_tokens=max_tokens,
            temperature=temperature,
            logprobs=logprobs,
            client_factory=client_factory,
            scraper=scraper,
        )
        rows.append(row)
        if on_row is not None:
            on_row(row)
    return rows
