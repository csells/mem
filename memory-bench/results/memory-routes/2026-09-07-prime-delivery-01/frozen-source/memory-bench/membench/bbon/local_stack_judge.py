"""LocalModelStack-backed comparative judge — the §4.1 shared OSS-judge backend.

This is the local-model seam the §12.6 action-impact scorer
(`membench.metrics.action_impact.score_action_impact`) and the §4.3 derailment /
§4.5 judges consume in place of headless `claude -p`. It satisfies the SAME
`membench.bbon.comparative_judge.ComparativeJudge` protocol (a `model` property and
`complete(prompt) -> str`), so every consumer accepts it unchanged: where
`ClaudeComparativeJudge` shells out to the local Claude CLI, this judge POSTs to a
self-hosted Ollama daemon serving the pinned `LocalModelStack.chat_model` (an 8B+
instruct model such as ``qwen2.5`` / ``llama3.1``).

Built ONCE for three consumers (the §12.6 fork decision, mayor gc-390342): it is
judge infrastructure, not metric logic, so the scorer stays judge-agnostic.

**No silent paid-API fallback.** A missing or unreachable daemon does not degrade to
a managed API — it raises loudly. `preflight()` delegates to `LocalModelStack.preflight`
so a real run fails fast at the boundary with the actionable `ollama pull`; and
`complete()` itself wraps a daemon-connection failure in `LocalStackUnavailableError`
rather than returning a default verdict.

**§4.5 license gate.** The model identity is whatever `LocalModelStack.chat_model`
is pinned to, so Nemotron (NVIDIA Open Model License) can be the wired default
without any code change here. That license is NOT OSI-approved: a run pinned to a
non-OSI model is publication-gated — keep an OSI-clean fallback (e.g. ``llama3.1``,
``qwen2.5``) benchmarked in parallel. This module records the model in telemetry via
the stack; it does not itself enforce the gate (a publication-time concern, not a
runtime one).

ZFC: the verdict IS the delegated model judgment. This module's own code is pure
plumbing — request assembly, HTTP IO, JSON unwrapping, and structural validation.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

from membench.bbon.comparative_judge import ComparativeJudgeError
from membench.memory_systems.local_stack import (
    HttpFetch,
    LocalModelStack,
    LocalStackUnavailableError,
)

# A local chat completion resolves in seconds on a provisioned GPU box; a minute-plus
# bound means a wedged daemon, not slow inference — same reasoning as the CLI judge.
DEFAULT_TIMEOUT_S = 120.0

# Ollama's non-streaming text-completion endpoint. The reply is a single JSON object
# whose ``response`` field holds the model text.
_GENERATE_PATH = "/api/generate"

# A POST callable: (url, request_body_bytes) -> raw response bytes. Injected in tests
# so the parse path is exercised with no live daemon; the default binds urllib.
ChatPost = Callable[[str, bytes], bytes]


def _urllib_post(url: str, body: bytes, *, timeout: float) -> bytes:
    # Trust-boundary call to the local daemon: a real timeout so a hung/absent Ollama
    # surfaces as an error, never an indefinite hang.
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        data: bytes = resp.read()
    return data


@dataclass(frozen=True)
class LocalStackComparativeJudge:
    """A `ComparativeJudge` backed by a self-hosted Ollama daemon serving the pinned
    `LocalModelStack.chat_model`.

    ``stack`` is the shared pinned model identity, env-resolved by default so an
    operator pins the model (e.g. Nemotron vs an OSI-clean ``llama3.1``) through
    ``MEMBENCH_LOCAL_CHAT_MODEL`` with no code change. ``post`` is injected in tests so
    the parse path runs without a live daemon; left ``None`` the default urllib POST is
    used with ``timeout_s``. Every failure mode is surfaced loudly: a daemon connection
    failure as `LocalStackUnavailableError`, a malformed reply as `ComparativeJudgeError`."""

    stack: LocalModelStack = field(default_factory=LocalModelStack.from_env)
    timeout_s: float = DEFAULT_TIMEOUT_S
    post: ChatPost | None = None

    @property
    def model(self) -> str:
        """The pinned chat model — the identity recorded in cache keys and verdicts."""
        return self.stack.chat_model

    def preflight(self, *, fetch: HttpFetch | None = None) -> None:
        """Verify the daemon is up and the pinned chat model is pulled, raising
        `LocalStackUnavailableError` otherwise. Delegates to `LocalModelStack.preflight`
        with ``require_chat=True`` — this judge runs an instruct model. ``fetch`` is
        forwarded to the stack for test injection."""
        self.stack.preflight(require_chat=True, fetch=fetch)

    def complete(self, prompt: str) -> str:
        """Run the pinned chat model over ``prompt`` and return its raw text reply.

        POSTs a non-streaming `/api/generate` request and returns the ``response``
        field verbatim — the caller (`parse_judgment_reply` /
        `parse_action_impact_verdict`) extracts and validates the JSON verdict from it.
        A daemon connection failure raises `LocalStackUnavailableError` (fail loud, no
        paid-API fallback); a non-JSON or shape-wrong reply raises
        `ComparativeJudgeError`."""
        url = f"{self.stack.ollama_base_url.rstrip('/')}{_GENERATE_PATH}"
        body = json.dumps(
            {"model": self.stack.chat_model, "prompt": prompt, "stream": False}
        ).encode()
        do_post = self.post or (lambda u, b: _urllib_post(u, b, timeout=self.timeout_s))
        try:
            raw = do_post(url, body)
        except (urllib.error.URLError, OSError) as exc:
            raise LocalStackUnavailableError(
                f"Ollama daemon not reachable at {self.stack.ollama_base_url} ({exc}). "
                "Start it with `ollama serve` (or set MEMBENCH_OLLAMA_BASE_URL to its "
                "address); this judge will not fall back to a paid API."
            ) from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ComparativeJudgeError(f"Ollama reply is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("response"), str):
            raise ComparativeJudgeError(
                f"Ollama reply missing a string 'response' field: {payload!r}"
            )
        return str(payload["response"])
