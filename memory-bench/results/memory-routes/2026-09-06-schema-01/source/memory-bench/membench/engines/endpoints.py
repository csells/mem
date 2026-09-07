"""Pinned, env-overridable endpoints for the two local inference engines.

Config only: imports no SDK and touches no network at construction (same discipline
as ``memory_systems.local_stack``), so importing it — and the whole test suite —
stays model-free.

Both engines speak the OpenAI-compatible API (``/v1/chat/completions``,
``/v1/completions``) and expose a Prometheus ``/metrics`` endpoint, so one shape
covers both. The docker-compose stack in ``infra/local-inference`` serves vLLM on
:8001 and SGLang on :8002 by default; every field is env-overridable so a run can
re-point at a different host/model without a code change.

The paid-host fence mirrors ``grading.judge`` (D4/D16, the no-paid-API constraint):
an engine endpoint MUST be self-hosted. The check is hostname-based (urlparse +
suffix match), not a bare substring blocklist, so ``openai.com`` and host trickery
like ``api.openai.com.evil.test`` are both rejected. This is a second enforcement
point for the same invariant the judge enforces — duplicated deliberately to avoid
a cross-subpackage import of a security boundary.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

# A managed-host marker matches a hostname iff the host equals it or ends with
# ``.<marker>`` — so ``openai.com`` and ``api.openai.com`` match, but a self-hosted
# ``openai.com.local`` host used as a decoy does NOT (it does not end with the marker).
_PAID_HOST_MARKERS = ("openai.com", "anthropic.com", "api.mistral.ai", "googleapis.com")


class PaidHostError(ValueError):
    """Raised when an engine endpoint resolves to a paid managed host. The local
    inference harness is self-hosted by construction (D4/D16); a paid base_url is a
    configuration error that must fail loud, never silently bill a managed API."""


def _is_paid_host(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").lower()
    return any(host == m or host.endswith(f".{m}") for m in _PAID_HOST_MARKERS)


# vLLM and SGLang both serve the OpenAI API under a ``/v1`` prefix and Prometheus
# text under ``/metrics`` at the server root. Defaults match the compose stack.
ENV_VLLM_BASE_URL = "MEMBENCH_VLLM_BASE_URL"
ENV_VLLM_METRICS_URL = "MEMBENCH_VLLM_METRICS_URL"
ENV_VLLM_MODEL = "MEMBENCH_VLLM_MODEL"
ENV_SGLANG_BASE_URL = "MEMBENCH_SGLANG_BASE_URL"
ENV_SGLANG_METRICS_URL = "MEMBENCH_SGLANG_METRICS_URL"
ENV_SGLANG_MODEL = "MEMBENCH_SGLANG_MODEL"
ENV_TOKENSPEED_BASE_URL = "MEMBENCH_TOKENSPEED_BASE_URL"
ENV_TOKENSPEED_METRICS_URL = "MEMBENCH_TOKENSPEED_METRICS_URL"
ENV_TOKENSPEED_MODEL = "MEMBENCH_TOKENSPEED_MODEL"

DEFAULT_VLLM_BASE_URL = "http://localhost:8001/v1"
DEFAULT_VLLM_METRICS_URL = "http://localhost:8001/metrics"
DEFAULT_SGLANG_BASE_URL = "http://localhost:8002/v1"
DEFAULT_SGLANG_METRICS_URL = "http://localhost:8002/metrics"
DEFAULT_TOKENSPEED_BASE_URL = "http://localhost:8003/v1"
DEFAULT_TOKENSPEED_METRICS_URL = "http://localhost:8003/metrics"
# Same checkpoint on both engines so a side-by-side A/B isolates the engine, not the
# model. Overridable per engine; an 8B at bf16 fits the 32 GB 5090 comfortably.
DEFAULT_MODEL = "meta-llama/Meta-Llama-3.1-8B-Instruct"


@dataclass(frozen=True)
class EngineEndpoint:
    """One self-hosted, OpenAI-compatible engine: where to send completions, where to
    scrape runtime metrics, and which model is pinned. Immutable so a resolved
    endpoint can be shared without any caller re-pointing it at a paid host.

    The ``metric_prefix`` names the engine's Prometheus namespace (``vllm`` / ``sglang``)
    so ``metrics_scrape`` can read each engine's gauges without a per-call mapping.
    """

    name: str
    base_url: str
    metrics_url: str
    model: str
    metric_prefix: str

    def __post_init__(self) -> None:
        if _is_paid_host(self.base_url):
            raise PaidHostError(
                f"engine {self.name!r} base_url {self.base_url!r} is a paid managed host; "
                "the local inference harness is self-hosted (D4/D16) — point it at a "
                "loopback vLLM/SGLang endpoint"
            )
        if _is_paid_host(self.metrics_url):
            raise PaidHostError(
                f"engine {self.name!r} metrics_url {self.metrics_url!r} is a paid managed host"
            )

    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    def completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/completions"


def resolve_engines(env: dict[str, str] | None = None) -> dict[str, EngineEndpoint]:
    """Resolve both engine endpoints from the environment, falling back to the pinned
    compose defaults. ``env`` is injectable so resolution is testable without touching
    ``os.environ``. Returns a name→endpoint map (``{"vllm": ..., "sglang": ...}``)."""
    source = os.environ if env is None else env
    vllm = EngineEndpoint(
        name="vllm",
        base_url=source.get(ENV_VLLM_BASE_URL, DEFAULT_VLLM_BASE_URL),
        metrics_url=source.get(ENV_VLLM_METRICS_URL, DEFAULT_VLLM_METRICS_URL),
        model=source.get(ENV_VLLM_MODEL, DEFAULT_MODEL),
        metric_prefix="vllm",
    )
    sglang = EngineEndpoint(
        name="sglang",
        base_url=source.get(ENV_SGLANG_BASE_URL, DEFAULT_SGLANG_BASE_URL),
        metrics_url=source.get(ENV_SGLANG_METRICS_URL, DEFAULT_SGLANG_METRICS_URL),
        model=source.get(ENV_SGLANG_MODEL, DEFAULT_MODEL),
        metric_prefix="sglang",
    )
    # TokenSpeed (lightseekorg/tokenspeed) ships AS a vLLM runner — the
    # ``vllm/vllm-openai:*-tokenspeed`` image with ``VLLM_USE_TOKENSPEED_RUNNER=1``.
    # The HTTP + /metrics surface is byte-identical to vLLM, so it reuses the "vllm"
    # metric prefix and needs no new client/scraper code. Datacenter-GPU only
    # (B200 SXM6 / H200 / H100); it will NOT run on a consumer RTX 5090 — see
    # infra/local-inference/README.md.
    tokenspeed = EngineEndpoint(
        name="tokenspeed",
        base_url=source.get(ENV_TOKENSPEED_BASE_URL, DEFAULT_TOKENSPEED_BASE_URL),
        metrics_url=source.get(ENV_TOKENSPEED_METRICS_URL, DEFAULT_TOKENSPEED_METRICS_URL),
        model=source.get(ENV_TOKENSPEED_MODEL, DEFAULT_MODEL),
        metric_prefix="vllm",
    )
    return {vllm.name: vllm, sglang.name: sglang, tokenspeed.name: tokenspeed}


# Convenience snapshot of the default (un-overridden) endpoints for docs/tests. A
# real run should call ``resolve_engines()`` so env overrides are honored.
DEFAULT_ENGINES: dict[str, EngineEndpoint] = resolve_engines(env={})
