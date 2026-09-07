"""Read each engine's KV-cache and prefix-cache pressure from its ``/metrics`` endpoint.

vLLM and SGLang both export Prometheus text, but under different metric names. This
module parses the exposition format (pure) and maps each engine's gauges onto one
common ``EngineRuntimeStats`` shape, so the sweep can compare KV pressure, prefix-cache
hit rate, and queue depth across engines without per-call-site name juggling.

The boundary fetch is injected; the parser and the name-mapping are pure and tested.

Metric-name references (stable as of vLLM 0.6.x / SGLang 0.4.x):
  vLLM  : vllm:gpu_cache_usage_perc, vllm:num_requests_running,
          vllm:num_requests_waiting, vllm:num_preemptions_total,
          vllm:prefix_cache_hits_total, vllm:prefix_cache_queries_total
  SGLang: sglang:token_usage, sglang:num_running_reqs, sglang:num_queue_reqs,
          sglang:cache_hit_rate
"""

from __future__ import annotations

import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass

# (url) -> the raw Prometheus exposition text. Injected so scraping is testable.
MetricsFetch = Callable[[str], str]


@dataclass(frozen=True)
class Sample:
    """One Prometheus sample: metric name, its label set, and the float value."""

    name: str
    labels: dict[str, str]
    value: float


def parse_prometheus(text: str) -> list[Sample]:
    """Parse Prometheus text-exposition format into samples. Pure.

    Skips ``# HELP`` / ``# TYPE`` comment lines and blanks. Tolerates the optional
    trailing timestamp column. A line whose value is not a float (``NaN`` aside) is
    skipped rather than raising — a single odd line must not blind the whole scrape."""
    samples: list[Sample] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, labels, value = _parse_line(line)
        if value is None:
            continue
        samples.append(Sample(name=name, labels=labels, value=value))
    return samples


def _parse_line(line: str) -> tuple[str, dict[str, str], float | None]:
    if "{" in line:
        name, rest = line.split("{", 1)
        label_str, _, value_str = rest.partition("}")
        labels = _parse_labels(label_str)
    else:
        name, _, value_str = line.partition(" ")
        labels = {}
    fields = value_str.split()
    if not fields:
        return name.strip(), labels, None
    try:
        return name.strip(), labels, float(fields[0])
    except ValueError:
        return name.strip(), labels, None


def _parse_labels(label_str: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for pair in label_str.split(","):
        key, sep, val = pair.partition("=")
        if sep:
            labels[key.strip()] = val.strip().strip('"')
    return labels


def _first(samples: Iterable[Sample], *names: str) -> float | None:
    """The value of the first sample matching any of ``names``, in name order then
    sample order (engine runtime gauges are single-valued or repeated per model — the
    first is representative). Multiple names tolerate vLLM metric renames across
    versions (e.g. ``gpu_cache_usage_perc`` → ``kv_cache_usage_perc``)."""
    sample_list = list(samples)
    for name in names:
        for s in sample_list:
            if s.name == name:
                return s.value
    return None


def _sum(samples: Iterable[Sample], name: str) -> float | None:
    """Sum every sample named ``name`` (counters split across label sets). None when
    no such sample exists, so an absent counter is distinguishable from a zero one."""
    values = [s.value for s in samples if s.name == name]
    return sum(values) if values else None


@dataclass(frozen=True)
class EngineRuntimeStats:
    """The common cross-engine runtime snapshot. Fields are None when the engine does
    not export the corresponding metric, never silently zero — absence and zero load
    are different states."""

    kv_cache_usage: float | None
    prefix_cache_hit_rate: float | None
    num_running: float | None
    num_waiting: float | None
    num_preemptions_total: float | None
    # Raw prefix-cache counters (vLLM only). ``prefix_cache_hit_rate`` above is a
    # CUMULATIVE lifetime ratio; the per-cell rate must be reconstructed from the delta
    # of these counters across a batch. SGLang exports only a windowed gauge, so these
    # stay None for it and the per-cell delta is undefined.
    prefix_cache_hits_total: float | None = None
    prefix_cache_queries_total: float | None = None

    @classmethod
    def from_samples(cls, samples: list[Sample], metric_prefix: str) -> EngineRuntimeStats:
        """Map one engine's samples onto the common shape, dispatching on the engine's
        Prometheus namespace (``vllm`` / ``sglang``)."""
        if metric_prefix == "vllm":
            return cls._from_vllm(samples)
        if metric_prefix == "sglang":
            return cls._from_sglang(samples)
        raise ValueError(f"unknown engine metric prefix {metric_prefix!r}")

    @staticmethod
    def _from_vllm(samples: list[Sample]) -> EngineRuntimeStats:
        hits = _sum(samples, "vllm:prefix_cache_hits_total")
        queries = _sum(samples, "vllm:prefix_cache_queries_total")
        hit_rate = (hits / queries) if (hits is not None and queries) else None
        return EngineRuntimeStats(
            # Newer vLLM (and the NIM build) expose ``kv_cache_usage_perc``; older
            # releases used ``gpu_cache_usage_perc``. Try the new name first, fall back.
            kv_cache_usage=_first(samples, "vllm:kv_cache_usage_perc", "vllm:gpu_cache_usage_perc"),
            prefix_cache_hit_rate=hit_rate,
            num_running=_first(samples, "vllm:num_requests_running"),
            num_waiting=_first(samples, "vllm:num_requests_waiting"),
            num_preemptions_total=_sum(samples, "vllm:num_preemptions_total"),
            prefix_cache_hits_total=hits,
            prefix_cache_queries_total=queries,
        )

    @staticmethod
    def _from_sglang(samples: list[Sample]) -> EngineRuntimeStats:
        return EngineRuntimeStats(
            kv_cache_usage=_first(samples, "sglang:token_usage"),
            prefix_cache_hit_rate=_first(samples, "sglang:cache_hit_rate"),
            num_running=_first(samples, "sglang:num_running_reqs"),
            num_waiting=_first(samples, "sglang:num_queue_reqs"),
            num_preemptions_total=_sum(samples, "sglang:num_preemptions_total"),
        )


def scrape_engine_stats(
    metrics_url: str, metric_prefix: str, *, fetch: MetricsFetch | None = None, timeout: float = 5.0
) -> EngineRuntimeStats:
    """Fetch and parse one engine's runtime stats. ``fetch`` is injected in tests; the
    default reads the URL over urllib with a real timeout (trust-boundary call)."""
    do_fetch = fetch if fetch is not None else (lambda url: _urllib_fetch(url, timeout=timeout))
    text = do_fetch(metrics_url)
    return EngineRuntimeStats.from_samples(parse_prometheus(text), metric_prefix)


def _urllib_fetch(url: str, *, timeout: float) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        data: bytes = resp.read()
    return data.decode("utf-8")
