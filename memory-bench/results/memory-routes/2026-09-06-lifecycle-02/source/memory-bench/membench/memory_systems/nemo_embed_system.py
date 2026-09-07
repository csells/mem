"""`nemo-embed` — a plain dense NeMo embedder as a BASELINE retrieval arm (mem-sikg).

A second, architecturally-different neural baseline next to `mem0`: where `mem0`
lets its backend (Ollama) own the embedding and Qdrant own the ANN search, this arm
embeds the agent-readable payload with an NVIDIA NeMo dense embedder *we* drive, then
ranks candidates by **exact cosine** top-k. It is a sibling of the `mem0` arm via the
same ``SemanticMemoryClient`` seam — **not** an `ours` upgrade: embeddings are never
folded into the deterministic, provenance-anchored `ours` retriever (ADR
docs/mem-nemo-retriever-agentic-feasibility.md §4/§6). The agentic LLM-refinement loop
and the ColBERT/vision-language backends are deliberately DEFERRED (ADR §6).

Design choices:

- **Exact in-process cosine, not Qdrant ANN.** We compute the embeddings ourselves,
  so the vector store is just a cosine top-k index over the LOO-bounded candidate set
  the harness already scopes per trial. Exact cosine over that bounded set is fully
  deterministic (no HNSW recall loss, no approximation), which is a *stronger* eval
  guarantee than an approximate index — and needs no extra daemon. `mem0` keeps its
  Qdrant lane; this lane is intentionally simpler.
- **Leak boundary is the harness's, not the arm's.** Like every ``AbstractSemanticArm``,
  this arm embeds exactly the ``content`` the runner hands ``write`` — the
  agent-readable lesson + citation, never an outcome/failure-signature field. The
  runner owns that boundary and ``validity.assert_no_leak`` is the backstop (ADR §3);
  the arm adds no payload logic of its own.
- **Embedder is INJECTED behind a Protocol**, so the arm wiring is testable against a
  deterministic fake with no model and no network — the scix no-paid-API contract holds
  in CI. The real embedder (sentence-transformers loading the pinned NeMo HF model) is
  built LAZILY in ``default_nemo_embedder`` and plugs in behind the same seam.

License (PL default, mem-sikg, countermandable): the pinned default is the
**permissively-licensed** ``nvidia/llama-nemotron-embed-1b-v2`` rather than the
NVIDIA-Non-Commercial agentic-recipe backend (``llama-nv-embed-reasoning-3b``), to keep
the published stack redistribution-clean — consistent with the qwen2.5:14b judge choice.
Swapping to the NC backend for a stronger arm is a one-line ``LocalModelStack`` pin
(``MEMBENCH_LOCAL_NEMO_EMBED_MODEL``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from membench.memory_systems.local_stack import LocalModelStack
from membench.memory_systems.semantic_base import (
    DEFAULT_TOP_K,
    AbstractSemanticArm,
    SemanticHit,
    SemanticMemoryClient,
)
from membench.schemas.memory_event import MemoryBackend


@runtime_checkable
class NemoEmbedder(Protocol):
    """The minimal embedding seam the NeMo arm drives. Two methods, not one, so a
    backend that uses asymmetric query/document instruction prompts (the NVIDIA NeMo
    embedders do) can apply them INSIDE the embedder — that asymmetry is a backend
    concern, never the client's. Each returns plain ``list[float]`` vectors, so the
    cosine index (and the test fake) never depend on numpy/torch."""

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed corpus payloads (the document side). Returns one vector per text,
        in the same order, each of the same dimension."""

    def embed_query(self, text: str) -> list[float]:
        """Embed one query/failure string (the query side)."""


def _unit(vector: Sequence[float]) -> list[float]:
    """L2-normalize so cosine similarity is a plain dot product. A zero or
    non-finite norm means the embedder returned a degenerate (all-zero / NaN) vector;
    normalizing it would divide by zero or propagate NaN through every score, so fail
    loud rather than poison the ranking (mirrors ``l2_distance_to_similarity``)."""
    norm = math.sqrt(sum(x * x for x in vector))
    if not math.isfinite(norm) or norm == 0.0:
        raise ValueError(
            f"embedding has a zero/non-finite L2 norm ({norm!r}); the embedder returned a "
            "degenerate vector, which cannot be cosine-ranked."
        )
    return [x / norm for x in vector]


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


@dataclass(frozen=True)
class _Indexed:
    """One stored memory: the surface content plus its unit-normalized embedding, so
    a query's cosine score is a single dot product against pre-normalized vectors."""

    content: str
    unit: list[float]


class _NemoEmbedClient:
    """Adapts a ``NemoEmbedder`` to ``SemanticMemoryClient`` with an exact per-scope
    cosine index. Unlike mem0/A-MEM (which mint their own ids), this client OWNS the
    store, so it keys memories by the caller's ``memory_id`` and returns it verbatim —
    no id round-trip needed. ``scope`` (the per-trial id) isolates every trial's
    candidate set; ``clear`` drops one scope only."""

    def __init__(self, embedder: NemoEmbedder) -> None:
        self._embedder = embedder
        # scope -> {memory_id: indexed vector+content}
        self._scopes: dict[str, dict[str, _Indexed]] = {}
        # The embedding dimension, fixed on first vector seen; every later vector
        # (doc or query) must match or cosine across them is meaningless.
        self._dim: int | None = None

    def _validated_unit(self, vector: Sequence[float]) -> list[float]:
        if len(vector) == 0:
            raise ValueError("embedder returned an empty (zero-dimension) vector.")
        if self._dim is None:
            self._dim = len(vector)
        elif len(vector) != self._dim:
            raise ValueError(
                f"embedding dimension changed: expected {self._dim}, got {len(vector)}. "
                "Every vector from one embedder must share a dimension."
            )
        return _unit(vector)

    def store(self, *, scope: str, content: str, memory_id: str) -> str:
        vectors = self._embedder.embed_documents([content])
        # One text in, exactly one vector out — anything else means the embedder
        # split/dropped the input, which would silently corrupt the id->vector map.
        if len(vectors) != 1:
            raise ValueError(
                f"embed_documents([1 text]) must return exactly one vector, got {len(vectors)} "
                f"for memory_id {memory_id!r}."
            )
        self._scopes.setdefault(scope, {})[memory_id] = _Indexed(
            content=content, unit=self._validated_unit(vectors[0])
        )
        return memory_id

    def query(self, *, scope: str, query_text: str, top_k: int) -> Sequence[SemanticHit]:
        items = self._scopes.get(scope)
        if not items:
            return []
        query_unit = self._validated_unit(self._embedder.embed_query(query_text))
        hits = [
            SemanticHit(
                memory_id=memory_id, content=indexed.content, score=_dot(query_unit, indexed.unit)
            )
            for memory_id, indexed in items.items()
        ]
        # Best-first cosine; ties broken by memory_id so the ranking is deterministic
        # (the base does no re-ranking — determinism is the client's responsibility).
        hits.sort(key=lambda hit: (-(hit.score or 0.0), hit.memory_id))
        return hits[:top_k]

    def clear(self, *, scope: str) -> None:
        self._scopes.pop(scope, None)


class _SentenceTransformerNemoEmbedder:
    """The real ``NemoEmbedder``: a ``sentence_transformers.SentenceTransformer`` loading
    the pinned NeMo HF model on the local GPU (no paid API). ``query_prompt`` /
    ``doc_prompt`` carry the model's asymmetric instruction prompts when one is needed;
    both default to ``None`` (plain dense, symmetric) so v1 makes no unverified
    assumption about a specific instruction string — tune them per model via the
    factory if retrieval quality calls for it."""

    def __init__(
        self,
        model: Any,
        *,
        query_prompt: str | None = None,
        doc_prompt: str | None = None,
    ) -> None:
        self._model = model
        self._query_prompt = query_prompt
        self._doc_prompt = doc_prompt

    def _encode(self, texts: list[str], prompt: str | None) -> list[list[float]]:
        kwargs: dict[str, Any] = {"convert_to_numpy": True, "normalize_embeddings": False}
        if prompt is not None:
            kwargs["prompt"] = prompt
        encoded = self._model.encode(texts, **kwargs)
        # encode() returns a numpy array (Any to mypy); convert to plain lists at the
        # boundary so the index and tests never touch numpy.
        return [[float(value) for value in row] for row in encoded.tolist()]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode(list(texts), self._doc_prompt)

    def embed_query(self, text: str) -> list[float]:
        return self._encode([text], self._query_prompt)[0]


def default_nemo_embedder(
    stack: LocalModelStack | None = None,
    *,
    query_prompt: str | None = None,
    doc_prompt: str | None = None,
) -> NemoEmbedder:
    """Build the real NeMo embedder over the pinned model. ``sentence_transformers`` is
    imported HERE, lazily, so this module (and the suite) loads without the package and
    a missing one surfaces at run time, not import time — exactly like A-MEM's
    sentence-transformers embedder, which is why ``preflight`` does not check it (it is a
    pip package, not an Ollama-served model)."""
    from sentence_transformers import SentenceTransformer

    resolved = stack or LocalModelStack.from_env()
    # trust_remote_code: the NeMo embedders ship custom modeling code on the Hub.
    model = SentenceTransformer(resolved.nemo_embedding_model, trust_remote_code=True)
    return _SentenceTransformerNemoEmbedder(model, query_prompt=query_prompt, doc_prompt=doc_prompt)


class NemoEmbedMemory(AbstractSemanticArm):
    """Plain dense NeMo embedder baseline arm. Sets identity only; translation is
    inherited from ``AbstractSemanticArm`` and the cosine index lives in
    ``_NemoEmbedClient``."""

    name = "nemo-embed"
    backend = MemoryBackend.VECTOR_DB

    def __init__(
        self,
        client: SemanticMemoryClient | None = None,
        *,
        top_k: int = DEFAULT_TOP_K,
    ) -> None:
        # Build the real embedder-backed client only when none is injected, so tests
        # and the suite never require sentence-transformers / the NeMo weights.
        super().__init__(
            client if client is not None else _NemoEmbedClient(default_nemo_embedder()),
            top_k=top_k,
        )
