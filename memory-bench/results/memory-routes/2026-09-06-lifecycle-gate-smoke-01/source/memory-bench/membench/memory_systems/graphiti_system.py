"""`graphiti` — the Graphiti temporal-knowledge-graph competitive arm (mem-lvp.4).

`GraphitiMemory` is a pure ``name`` + ``backend`` subclass of ``AbstractSemanticArm``;
all the translation lives in ``_GraphitiClient``, which adapts ``graphiti_core.Graphiti``
(async) to the SYNC ``SemanticMemoryClient`` seam through an injected
``AsyncClientBridge`` (mem-lvp.5a) — every Graphiti method is a coroutine, the Protocol
is not, so the bridge holds one persistent loop and the seam (and the fakes) stay sync.

- ``store`` -> ``add_episode(name=memory_id, episode_body=content, source=EpisodeType.text,
  group_id=scope, reference_time=now)``. Graphiti runs LLM extraction over the episode
  body and mints its own ids; the adapter returns the EPISODE uuid
  (``AddEpisodeResults.episode.uuid``) as the backend id, while retrieval keys off the
  extracted EntityEdge uuids — the two differ by design (LLM extraction fans one episode
  into many edges), the same mint-your-own-id trait mem0/A-MEM share.
- ``query`` -> ``search(query=query_text, group_ids=[scope], num_results=k)`` -> a list of
  ``EntityEdge``; map ``.uuid`` -> id and ``.fact`` -> content. ``search`` exposes NO
  per-edge score, so every hit carries ``score=None`` and the base trusts Graphiti's
  hybrid-search list order (the documented Graphiti-path of ``SemanticHit``).
- ``clear`` -> a NO-OP. Per the mem-lvp.4b decision (docs/competitive-arms-integration.md
  §5b) isolation comes from a never-reused ``group_id`` per trial, NOT a destructive
  purge: ``scope`` is ``ctx.trial_id``, which the base asserts globally unique
  (mem-lvp.12), so each trial already writes a brand-new namespace. This keeps the seam
  at ``store``/``query``/``clear`` with no driver-level ``execute_query`` Cypher hook.

The real ``Graphiti`` (FalkorDB/Neo4j graph + local Ollama LLM/embedder + a
sentence-transformers reranker, all self-hosted, no paid API) is built LAZILY in
``default_graphiti_client`` so importing this module — and the whole test suite — needs
neither ``graphiti-core`` nor a live graph DB. Tests inject a deterministic async fake.
This is the heaviest arm (graph DB + LLM extraction at ingest); its CI is still
model-free/network-free via the fake. See docs/competitive-arms-integration.md §5b.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from membench.memory_systems.async_bridge import AsyncClientBridge, trial_timeout
from membench.memory_systems.local_stack import LocalModelStack
from membench.memory_systems.semantic_base import (
    DEFAULT_TOP_K,
    AbstractSemanticArm,
    SemanticHit,
    SemanticMemoryClient,
)
from membench.schemas.memory_event import MemoryBackend


class _GraphitiEpisode(Protocol):
    """The slice of ``graphiti_core``'s ``EpisodicNode`` the adapter reads off an
    ``add_episode`` result — just the minted episode uuid."""

    uuid: str


class _AddEpisodeResult(Protocol):
    """The slice of ``AddEpisodeResults`` the adapter reads: the persisted episode
    node (whose uuid is the backend id ``store`` returns). The extracted ``nodes`` /
    ``edges`` are not read here — retrieval re-derives the edges via ``search``."""

    episode: _GraphitiEpisode


class _GraphitiEdge(Protocol):
    """The slice of an ``EntityEdge`` a search hit exposes: its uuid (the retrieval id)
    and ``fact`` (the human-readable edge text surfaced as content)."""

    uuid: str
    fact: str


class _GraphitiBackend(Protocol):
    """The async slice of ``graphiti_core.Graphiti`` the adapter drives. A Protocol so
    the fake stands in without the SDK; both verbs are coroutines, run through the
    bridge. ``search`` returns ``list[Any]`` (not ``list[_GraphitiEdge]``) so a fake
    returning its own concrete edge type satisfies it — ``list`` is invariant, so a
    ``list[_GraphitiEdge]`` return would reject a structurally-valid fake; the adapter
    reads the ``_GraphitiEdge`` field slice off each hit at the call site."""

    async def add_episode(
        self,
        *,
        name: str,
        episode_body: str,
        source: Any,
        group_id: str,
        reference_time: datetime,
    ) -> _AddEpisodeResult: ...

    async def search(self, query: str, *, group_ids: list[str], num_results: int) -> list[Any]: ...


def _utcnow() -> datetime:
    """The episode's bi-temporal ``reference_time``. Graphiti needs a valid-time on
    every episode; it does not enter our retrieval ranking, so wall-clock now is
    correct. Injected into ``_GraphitiClient`` so a test can pin it."""
    return datetime.now(UTC)


def _default_episode_source() -> Any:
    """Bind ``graphiti_core``'s ``EpisodeType.text`` LAZILY so this module loads without
    the SDK; only the real (no-arg-default) client reaches here. The episode is a plain
    text record, never JSON/message, so ``text`` is the only source we emit."""
    from graphiti_core.nodes import EpisodeType

    return EpisodeType.text


class _GraphitiClient:
    """Adapts ``graphiti_core.Graphiti`` to ``SemanticMemoryClient``. ``scope`` maps to
    Graphiti's ``group_id``. The async backend is driven through ``bridge`` (one
    persistent loop for the client's lifetime); ``bridge``, ``episode_source`` and
    ``now`` are injected so the same seam serves the fake and the real Graphiti."""

    def __init__(
        self,
        backend: _GraphitiBackend,
        bridge: AsyncClientBridge,
        *,
        episode_source: Any,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._backend = backend
        self._bridge = bridge
        self._episode_source = episode_source
        self._now = now

    def store(self, *, scope: str, content: str, memory_id: str) -> str:
        # Graphiti mints its own ids; the EPISODE uuid is the backend id we return.
        # `name=memory_id` round-trips the caller's id into the episode for provenance,
        # but the returned id is Graphiti's episode uuid (what retrieval can re-find).
        result = self._bridge.run(
            self._backend.add_episode(
                name=memory_id,
                episode_body=content,
                source=self._episode_source,
                group_id=scope,
                reference_time=self._now(),
            )
        )
        return result.episode.uuid

    def query(self, *, scope: str, query_text: str, top_k: int) -> Sequence[SemanticHit]:
        edges: list[_GraphitiEdge] = self._bridge.run(
            self._backend.search(query_text, group_ids=[scope], num_results=top_k)
        )
        # search() exposes no per-edge score, so score=None and the base trusts the
        # hybrid-search list order (the Graphiti path of SemanticHit).
        return [SemanticHit(memory_id=edge.uuid, content=edge.fact, score=None) for edge in edges]

    def clear(self, *, scope: str) -> None:
        # No-op by design (mem-lvp.4b, §5b): isolation is a fresh, never-reused group_id
        # per trial (scope == ctx.trial_id, asserted globally unique by the base), so
        # there is nothing to purge and no driver-level Cypher hook leaks onto the seam.
        return

    def close(self) -> None:
        """Tear down the persistent bridge loop + executor (mem-lvp.15). The Graphiti
        graph-driver connection runs through the bridge's loop; closing it releases the
        loop, its self-pipe sockets, and any driver executor threads. Idempotent."""
        self._bridge.close()


def default_graphiti_client(stack: LocalModelStack | None = None) -> SemanticMemoryClient:
    """Build the real Graphiti-backed client over its own persistent bridge, with all
    inference local (no paid API). ``graphiti_core`` is imported HERE, lazily, so the
    module (and the suite) loads without it; the arm depends only on the Protocol.

    Local stack (mem-lvp.5): the LLM and embedder are Ollama, reached through Graphiti's
    OpenAI-compatible clients pointed at Ollama's ``/v1`` endpoint; the reranker is a
    local sentence-transformers cross-encoder. The graph store is a self-hosted
    FalkorDB/Neo4j driver — NEVER a bare ``Graphiti(uri, user, password)`` (that path
    defaults the LLM/embedder to paid OpenAI, breaking the scix constraint)."""
    from graphiti_core import Graphiti
    from graphiti_core.cross_encoder.bge_reranker_client import BGERerankerClient
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

    resolved = stack or LocalModelStack.from_env()
    openai_base_url = f"{resolved.ollama_base_url.rstrip('/')}/v1"
    # api_key is required by the OpenAI client shape but unused by Ollama; "ollama" is
    # the conventional placeholder.
    llm = OpenAIGenericClient(
        config=LLMConfig(api_key="ollama", base_url=openai_base_url, model=resolved.chat_model)
    )
    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            api_key="ollama",
            base_url=openai_base_url,
            embedding_model=resolved.ollama_embedding_model,
        )
    )
    graphiti = Graphiti(
        graph_driver=FalkorDriver(),
        llm_client=llm,
        embedder=embedder,
        cross_encoder=BGERerankerClient(),
    )
    return _GraphitiClient(
        graphiti,
        AsyncClientBridge(timeout=trial_timeout()),
        episode_source=_default_episode_source(),
    )


class GraphitiMemory(AbstractSemanticArm):
    """Graphiti temporal-knowledge-graph arm. Sets identity only; all translation is
    inherited from ``AbstractSemanticArm`` and adaptation lives in ``_GraphitiClient``."""

    name = "graphiti"
    backend = MemoryBackend.KG

    def __init__(
        self,
        client: SemanticMemoryClient | None = None,
        *,
        top_k: int = DEFAULT_TOP_K,
    ) -> None:
        # Build the real Graphiti-backed client only when none is injected, so tests
        # and the suite never require the SDK or a live graph DB.
        super().__init__(client if client is not None else default_graphiti_client(), top_k=top_k)
