"""Shared self-hosted model stack for the competitive arms (mem-lvp.5).

Single source of truth for the local embedder + local chat/instruct model that the
semantic arms (mem0 / A-MEM / NAT / Graphiti) run against, so every arm honors the
scix **no-paid-API** constraint off one shared Ollama daemon plus bundled
sentence-transformers — and so the *pinned* model identity is recorded in telemetry
to control the V2 local-LLM-quality confound (``.gc/docs/phase-2.5-plan.md``
§Validity V2: "We pin the model + version, record it in telemetry").

The design verdict (phase-2.5-plan §"Shared self-hosted stack") is one shared local
stack, now three embedder modalities:

- an **Ollama-served** embedding model (mem0's embedder is the Ollama daemon),
- an **in-process sentence-transformers** model (A-MEM and NAT embed locally), and
- an **in-process NeMo dense embedder** (the `nemo-embed` baseline arm, mem-sikg) —
  also a sentence-transformers load, but pinned separately so the NeMo baseline's
  model identity is recorded independently of A-MEM/NAT's lighter embedder.

plus one **chat/instruct** model for the arms that run an LLM at ingest (mem0,
A-MEM). Every embedder and the chat model are named here once; each arm's
real-client factory maps the stack onto its backend's native config.

This module is **config only**: it imports no SDK and touches no network at
construction, so importing it — and the whole test suite — stays model-free. The
mapping is done by small pure functions (``mem0_system.build_mem0_config`` /
``amem_system.build_amem_kwargs``) that are unit-tested with no SDK installed.
``preflight`` is the one method that reaches the network; it is called explicitly
before a real run and **fails loud** (raises ``LocalStackUnavailableError``) rather than
letting a backend silently fall back to a paid API.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

# Bumped when the pinned default models change, so a telemetry row's stack identity
# is unambiguous across runs (V2 confound control). The model names below ARE the
# identity; this version disambiguates two runs that pin different defaults.
# v2 (mem-sikg): added the pinned NeMo dense embedder for the `nemo-embed` arm.
STACK_VERSION = "2"

# Defaults match the phase-2.5-plan recommendation: one Ollama embedding model
# (``nomic-embed-text``), the lightest bundled sentence-transformer
# (``all-MiniLM-L6-v2``), and one local instruct model (``llama3``). Every field is
# env-overridable so a run can pin a stronger/weaker model without code change.
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_CHAT_MODEL = "llama3"
DEFAULT_OLLAMA_EMBEDDING_MODEL = "nomic-embed-text"
DEFAULT_SENTENCE_TRANSFORMER_MODEL = "all-MiniLM-L6-v2"
# PL default (mem-sikg, countermandable): the PERMISSIVELY-licensed NVIDIA embedder,
# not the NVIDIA-Non-Commercial agentic-recipe backend (llama-nv-embed-reasoning-3b),
# to keep the published stack redistribution-clean. Swap via the env override below.
DEFAULT_NEMO_EMBEDDING_MODEL = "nvidia/llama-nemotron-embed-1b-v2"

ENV_OLLAMA_BASE_URL = "MEMBENCH_OLLAMA_BASE_URL"
ENV_CHAT_MODEL = "MEMBENCH_LOCAL_CHAT_MODEL"
ENV_OLLAMA_EMBEDDING_MODEL = "MEMBENCH_LOCAL_EMBED_MODEL"
ENV_SENTENCE_TRANSFORMER_MODEL = "MEMBENCH_LOCAL_ST_MODEL"
ENV_NEMO_EMBEDDING_MODEL = "MEMBENCH_LOCAL_NEMO_EMBED_MODEL"


class LocalStackUnavailableError(RuntimeError):
    """Raised by ``preflight`` when the local stack is not provisioned — the Ollama
    daemon is unreachable or a pinned model is not pulled. It carries an actionable
    message (the ``ollama pull`` to run) so a real run fails fast at the boundary
    instead of a backend silently degrading to a paid API."""


# Fetches the raw bytes of an Ollama endpoint; injected into ``preflight`` so the
# readiness check is unit-testable with no live daemon. The default binds urllib.
HttpFetch = Callable[[str], bytes]


def _urllib_fetch(url: str, *, timeout: float) -> bytes:
    # Trust-boundary call to the local daemon: a real timeout so a hung/absent
    # Ollama surfaces as LocalStackUnavailableError, never an indefinite hang.
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        data: bytes = resp.read()
    return data


def _model_present(available: list[str], wanted: str) -> bool:
    """Ollama tags carry a ``:tag`` suffix (``llama3:latest``) while configs name the
    bare model (``llama3``); treat a bare name as present if any tag shares its base."""
    return any(tag == wanted or tag.split(":", 1)[0] == wanted for tag in available)


@dataclass(frozen=True)
class LocalModelStack:
    """The pinned local model identity shared by every competitive arm. Immutable so
    one resolved stack can be passed to several arm factories without any of them
    mutating the shared pin."""

    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    chat_model: str = DEFAULT_CHAT_MODEL
    ollama_embedding_model: str = DEFAULT_OLLAMA_EMBEDDING_MODEL
    sentence_transformer_model: str = DEFAULT_SENTENCE_TRANSFORMER_MODEL
    nemo_embedding_model: str = DEFAULT_NEMO_EMBEDDING_MODEL

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> LocalModelStack:
        """Resolve the stack from environment, falling back to the pinned defaults.
        ``env`` is injectable so the resolution is testable without touching
        ``os.environ``."""
        source = os.environ if env is None else env
        return cls(
            ollama_base_url=source.get(ENV_OLLAMA_BASE_URL, DEFAULT_OLLAMA_BASE_URL),
            chat_model=source.get(ENV_CHAT_MODEL, DEFAULT_CHAT_MODEL),
            ollama_embedding_model=source.get(
                ENV_OLLAMA_EMBEDDING_MODEL, DEFAULT_OLLAMA_EMBEDDING_MODEL
            ),
            sentence_transformer_model=source.get(
                ENV_SENTENCE_TRANSFORMER_MODEL, DEFAULT_SENTENCE_TRANSFORMER_MODEL
            ),
            nemo_embedding_model=source.get(ENV_NEMO_EMBEDDING_MODEL, DEFAULT_NEMO_EMBEDDING_MODEL),
        )

    def telemetry_dict(self) -> dict[str, str]:
        """The pinned identity to record per run (V2 confound control). Excludes
        ``ollama_base_url`` — that is a deployment detail, not part of *which* models
        produced the result."""
        return {
            "stack_version": STACK_VERSION,
            "chat_model": self.chat_model,
            "ollama_embedding_model": self.ollama_embedding_model,
            "sentence_transformer_model": self.sentence_transformer_model,
            "nemo_embedding_model": self.nemo_embedding_model,
        }

    def preflight(
        self,
        *,
        require_chat: bool = True,
        fetch: HttpFetch | None = None,
        timeout: float = 5.0,
    ) -> None:
        """Verify the Ollama daemon is reachable and the pinned models are pulled.
        Raises ``LocalStackUnavailableError`` with the fix to run otherwise. ``require_chat``
        is ``False`` for an arm that only embeds (no ingest LLM). ``fetch`` is injected
        in tests; the default queries ``{base_url}/api/tags`` over urllib.

        The sentence-transformers model AND the NeMo embedder are intentionally NOT
        checked here: both are HF/pip models pulled lazily by their arm on first use,
        not Ollama-served, so a missing one surfaces at install time, not as a
        daemon-readiness failure."""
        tags_url = f"{self.ollama_base_url.rstrip('/')}/api/tags"
        do_fetch = fetch if fetch is not None else (lambda url: _urllib_fetch(url, timeout=timeout))
        try:
            raw = do_fetch(tags_url)
        except (urllib.error.URLError, OSError) as exc:
            raise LocalStackUnavailableError(
                f"Ollama daemon not reachable at {self.ollama_base_url} ({exc}). "
                "Start it with `ollama serve` (or set "
                f"{ENV_OLLAMA_BASE_URL} to its address)."
            ) from exc

        available = [m.get("name", "") for m in json.loads(raw).get("models", [])]
        required = [self.ollama_embedding_model]
        if require_chat:
            required.append(self.chat_model)
        missing = [m for m in required if not _model_present(available, m)]
        if missing:
            pulls = "; ".join(f"ollama pull {m}" for m in missing)
            raise LocalStackUnavailableError(f"Ollama models not pulled: {missing}. Run: {pulls}")
