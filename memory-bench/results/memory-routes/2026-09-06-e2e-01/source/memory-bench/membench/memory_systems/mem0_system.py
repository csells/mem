"""`mem0` — the mem0ai vector-store competitive arm (mem-lvp.2).

`Mem0Memory` is a pure ``name`` + ``backend`` subclass of ``AbstractSemanticArm``;
all the translation lives in ``_Mem0Client``, which adapts ``mem0.Memory`` to the
``SemanticMemoryClient`` seam:

- ``store`` -> ``add(content, user_id=scope, infer=False, metadata=...)``. ``infer``
  is OFF so one write is exactly one memory (no LLM fact-splitting); mem0 mints the
  id and we return ``results[0]["id"]`` — honest 1-write-1-memory.
- ``query`` -> ``search(query, top_k, filters={"user_id": scope})``; mem0's score is
  already higher-better, so the hits pass through without normalization.
- ``clear`` -> ``delete_all(user_id=scope)``; this scrubs one user only and never
  ``reset()`` (which drops the whole collection across trials).

The real ``mem0.Memory`` (Qdrant embedded + Ollama embedder/LLM, all local) is built
LAZILY in ``default_mem0_client`` so importing this module — and the whole test
suite — needs neither the SDK nor a network. Tests inject a fake instead.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import Sequence
from typing import Any, Protocol

from membench.memory_systems.local_stack import LocalModelStack
from membench.memory_systems.semantic_base import (
    DEFAULT_TOP_K,
    AbstractSemanticArm,
    SemanticHit,
    SemanticMemoryClient,
)
from membench.schemas.memory_event import MemoryBackend


def default_mem0_store_path() -> str:
    """A unique on-disk Qdrant location per call, so no two ``Mem0Memory`` instances —
    and no two membench runs — share a collection (mem-lvp.12). ``mem-lvp.5`` can pin
    the parent directory with ``MEMBENCH_MEM0_STORE_DIR`` or override the whole path by
    passing ``store_path`` explicitly."""
    base = os.environ.get("MEMBENCH_MEM0_STORE_DIR") or tempfile.gettempdir()
    return os.path.join(base, f"membench-mem0-{os.getpid()}-{uuid.uuid4().hex}")


def build_mem0_config(store_path: str, *, stack: LocalModelStack | None = None) -> dict[str, Any]:
    """Compose the full mem0 config for one run: Qdrant embedded as the vector store,
    Ollama for both the embedder and the LLM, so the real arm runs with no paid API
    and no network beyond the local Ollama daemon (mem-lvp.5 owns provisioning it).

    The embedder/LLM model names come from the shared ``LocalModelStack`` — the single
    source of truth across every arm — never hardcoded here, so the V2 confound pin is
    consistent. The vector-store ``store_path`` is injected per run so two arm
    instances (or two runs) never share one Qdrant collection: a shared collection
    separated only by the ``user_id`` filter is a silent cross-trial contamination risk
    (mem-lvp.12 audit)."""
    stack = stack or LocalModelStack.from_env()
    return {
        "vector_store": {
            "provider": "qdrant",
            "config": {"path": store_path, "on_disk": True},
        },
        "embedder": {
            "provider": "ollama",
            "config": {
                "model": stack.ollama_embedding_model,
                "ollama_base_url": stack.ollama_base_url,
            },
        },
        "llm": {
            "provider": "ollama",
            "config": {
                "model": stack.chat_model,
                "ollama_base_url": stack.ollama_base_url,
            },
        },
    }


class _NativeMem0(Protocol):
    """The slice of ``mem0.Memory`` the client touches. Declared as a Protocol so the
    adapter is typed against behaviour, not the SDK class, and the in-test fake stands
    in without importing mem0."""

    def add(
        self,
        content: str,
        *,
        user_id: str,
        infer: bool,
        metadata: dict[str, Any],
    ) -> dict[str, Any]: ...

    def search(
        self,
        query: str,
        *,
        top_k: int,
        filters: dict[str, Any],
    ) -> dict[str, Any]: ...

    def delete_all(self, *, user_id: str) -> None: ...


class _Mem0Client:
    """Adapts ``mem0.Memory`` to ``SemanticMemoryClient``. ``scope`` maps to mem0's
    ``user_id``. ``add`` runs with ``infer=False`` so the write is not LLM-split into
    several facts — exactly one result comes back and its minted id is returned."""

    def __init__(self, native: _NativeMem0) -> None:
        self._native = native

    def store(self, *, scope: str, content: str, memory_id: str) -> str:
        result = self._native.add(
            content,
            user_id=scope,
            infer=False,
            metadata={"memory_id": memory_id},
        )
        results = result["results"]
        # infer=False is a 1-write-1-memory contract; anything else means mem0 split
        # or dropped the write, which would silently corrupt the id mapping.
        if len(results) != 1:
            raise ValueError(
                f"mem0 add(infer=False) must yield exactly one memory, got {len(results)} "
                f"for memory_id {memory_id!r}"
            )
        return str(results[0]["id"])

    def query(self, *, scope: str, query_text: str, top_k: int) -> Sequence[SemanticHit]:
        result = self._native.search(query_text, top_k=top_k, filters={"user_id": scope})
        return [
            SemanticHit(memory_id=str(r["id"]), content=r["memory"], score=r.get("score"))
            for r in result["results"]
        ]

    def clear(self, *, scope: str) -> None:
        self._native.delete_all(user_id=scope)


def default_mem0_client(store_path: str | None = None) -> SemanticMemoryClient:
    """Build the real local mem0 client over a per-run store (``store_path`` or a fresh
    unique path). ``mem0`` is imported HERE, lazily, so the module (and the suite) loads
    without the SDK installed; the arm depends only on the Protocol."""
    from mem0 import Memory

    path = store_path if store_path is not None else default_mem0_store_path()
    return _Mem0Client(Memory.from_config(build_mem0_config(path)))


class Mem0Memory(AbstractSemanticArm):
    """mem0ai vector-store arm. Sets identity only; translation is inherited from
    ``AbstractSemanticArm`` and adaptation lives in ``_Mem0Client``."""

    name = "mem0"
    backend = MemoryBackend.VECTOR_DB

    def __init__(
        self,
        client: SemanticMemoryClient | None = None,
        *,
        top_k: int = DEFAULT_TOP_K,
        store_path: str | None = None,
    ) -> None:
        super().__init__(
            client if client is not None else default_mem0_client(store_path),
            top_k=top_k,
        )
