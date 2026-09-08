"""``ConsolidatingMemory`` — the two-speed consolidation arm (S1).

The hot path (``write``) is an O(1) wake-append with NO model call; all model cost
is deferred to an offline ``consolidate()`` pass that samples by salience, clusters
near-related episodes, and either recombines them into a schema row or just dedupes
them. The decisive ablation is ``mode``:

* ``recombine`` — synthesise a schema row abstracting each cluster (the latent
  pattern that survives across instances) and tombstone the sources, citing them.
* ``dedupe_only`` — keep one representative per cluster, tombstone the near-dups,
  emit NO schema row. The control: it can retain but never *abstract*.

Subtractive ops are tombstone-only: ``tombstone`` marks an id dead in a side set;
the content is NEVER removed from the store, so it stays re-derivable (the M7
reversibility invariant) and ``is_live`` reports True for a tombstoned-but-present
row, False only once a real GC reaps it. There is no hard-delete primitive in this
module — a source-scan test enforces that.

The cluster summariser is injected behind the ``ClusterSummarizer`` Protocol, so CI
runs a deterministic, model-free fake (``SharedTokenSummarizer``) and the
no-paid-API contract holds; a local model plugs in behind the same seam offline.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from membench.memory_systems.base import MemorySystem, RetrievalRequest, RetrieveResult
from membench.memory_systems.consolidation import ConsolidatedItem, ConsolidationResult
from membench.runtime import StepContext
from membench.schemas.memory_event import MemoryBackend, MemoryEvent, MemoryOperation
from membench.signals import SalienceSignals

_WORD = re.compile(r"\w+")
_MODES = ("recombine", "dedupe_only")


@dataclass(frozen=True)
class SummaryResult:
    """A cluster summariser's output: the recombined text + the offline model cost
    it incurred (``background_tokens`` = 0 for a deterministic fake, > 0 for a real
    model — metered here at the harness boundary, never arm-self-reported)."""

    text: str
    background_tokens: int = 0


@runtime_checkable
class ClusterSummarizer(Protocol):
    """The seam ``consolidate()`` recombines a cluster through. A real summariser is
    a local model; the CI fake is deterministic and makes no call."""

    def summarize(self, *, cluster_contents: Sequence[str]) -> SummaryResult: ...


class SharedTokenSummarizer:
    """Deterministic, model-free recombination: the schema row is the tokens common
    to the whole cluster (in first-seen order) — the latent pattern that survives
    across instances. Every emitted token is present in EVERY source episode, so the
    recombined row is faithful by construction (the deterministic confabulation proxy
    scores it 0). ``background_tokens`` is 0: no model was called."""

    def __init__(self, signals: SalienceSignals | None = None) -> None:
        self._sig = signals or SalienceSignals()

    def summarize(self, *, cluster_contents: Sequence[str]) -> SummaryResult:
        if not cluster_contents:
            return SummaryResult(text="", background_tokens=0)
        token_sets = [self._sig.tokenize(c) for c in cluster_contents]
        common = set(token_sets[0])
        for s in token_sets[1:]:
            common &= s
        ordered: list[str] = []
        seen: set[str] = set()
        for m in _WORD.finditer(cluster_contents[0].lower()):
            tok = m.group(0)
            if tok in common and tok not in seen:
                seen.add(tok)
                ordered.append(tok)
        return SummaryResult(text=" ".join(ordered), background_tokens=0)


class ConsolidatingMemory(MemorySystem):
    """Two-speed consolidation arm. Satisfies ``ConsolidationCapable`` structurally
    (``consolidate`` + ``tombstone``) without widening the ``MemorySystem`` ABC."""

    name = "consolidating"
    backend = MemoryBackend.FILESYSTEM
    supports_write = True

    def __init__(
        self,
        *,
        mode: str = "recombine",
        summarizer: ClusterSummarizer | None = None,
        signals: SalienceSignals | None = None,
        sim_threshold: float = 0.34,
        min_cluster_size: int = 2,
    ) -> None:
        if mode not in _MODES:
            raise ValueError(f"mode must be one of {_MODES}, got {mode!r}")
        if min_cluster_size < 2:
            raise ValueError(f"min_cluster_size must be >= 2, got {min_cluster_size}")
        self.mode = mode
        self._sig = signals or SalienceSignals()
        self._summarizer = summarizer or SharedTokenSummarizer(self._sig)
        self._sim_threshold = sim_threshold
        self._min_cluster_size = min_cluster_size
        self._reset_state()

    def _reset_state(self) -> None:
        # Per-trial reset (the sanctioned clear(scope), M7) — reassigns, never a
        # per-item hard delete. Content lives in _store; _tombstoned is the soft-
        # delete marker; _consolidated/_provenance hold the schema rows.
        self._store: dict[str, str] = {}
        self._order: list[str] = []
        self._tombstoned: set[str] = set()
        self._consolidated: dict[str, str] = {}
        self._provenance: dict[str, tuple[str, ...]] = {}

    def reset(self, trial_id: str) -> None:
        self._reset_state()

    # -- hot path: O(1) wake-append, no model call ------------------------- #
    def write(self, memory_id: str, content: str, ctx: StepContext) -> MemoryEvent:
        if memory_id not in self._store:
            self._order.append(memory_id)
        self._store[memory_id] = content
        return MemoryEvent(
            event_id=ctx.clock.event_id(),
            trial_id=ctx.trial_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            timestamp=ctx.clock.timestamp(),
            concrete_tool=f"{self.name}.wake_append",
            normalized_operation=MemoryOperation.WRITE,
            backend=self.backend,
            written_ids=[memory_id],
            latency_ms=ctx.clock.latency_ms(),
            success=True,
        )

    # -- offline consolidation -------------------------------------------- #
    def _live_episodes(self) -> list[str]:
        return [mid for mid in self._order if mid not in self._tombstoned]

    def _cluster(self) -> list[list[str]]:
        """Greedy salience clustering: each live episode joins the first cluster
        whose representative is near it (Jaccard >= threshold), else starts its own.
        Insertion-order traversal keeps it deterministic."""
        clusters: list[list[str]] = []
        for mid in self._live_episodes():
            content = self._store[mid]
            for cl in clusters:
                if self._sig.jaccard(content, self._store[cl[0]]) >= self._sim_threshold:
                    cl.append(mid)
                    break
            else:
                clusters.append([mid])
        return clusters

    def consolidate(self, ctx: StepContext) -> ConsolidationResult:
        items: list[ConsolidatedItem] = []
        tombstoned: list[str] = []
        background = 0
        eligible = [cl for cl in self._cluster() if len(cl) >= self._min_cluster_size]
        for i, cl in enumerate(eligible):
            if self.mode == "dedupe_only":
                # Keep the representative; tombstone the near-duplicates. No schema row.
                for mid in cl[1:]:
                    self.tombstone(mid)
                    tombstoned.append(mid)
                continue
            summary = self._summarizer.summarize(cluster_contents=[self._store[m] for m in cl])
            background += summary.background_tokens
            sid = f"{self.name}-schema-{i}"
            self._consolidated[sid] = summary.text
            self._provenance[sid] = tuple(cl)
            items.append(
                ConsolidatedItem(memory_id=sid, content=summary.text, source_trace_ids=tuple(cl))
            )
            for mid in cl:
                self.tombstone(mid)
                tombstoned.append(mid)
        return ConsolidationResult(
            items=tuple(items),
            tombstoned_ids=tuple(tombstoned),
            background_tokens=background,
            notes={"mode": self.mode, "clusters": str(len(eligible))},
        )

    def tombstone(self, memory_id: str) -> None:
        # Soft delete: mark dead, never destroy content. The row stays in _store and
        # is_live keeps reporting True until a real GC reaps it.
        self._tombstoned.add(memory_id)

    def is_live(self, trace_id: str) -> bool:
        """Reachability oracle for the provenance gate: a trace is live iff its
        content is still present (tombstoned-but-present counts; GC-reaped does not)."""
        return trace_id in self._store

    # -- retrieval --------------------------------------------------------- #
    def retrieve(self, request: RetrievalRequest, ctx: StepContext) -> RetrieveResult:
        payloads: dict[str, str] = {}
        provenance: dict[str, tuple[str, ...]] = {}
        for rid in request.requested_ids:
            if rid in self._consolidated:  # a schema row asked for directly
                payloads[rid] = self._consolidated[rid]
                provenance[rid] = self._provenance[rid]
            elif rid in self._store and rid not in self._tombstoned:  # live raw episode
                payloads[rid] = self._store[rid]
                provenance[rid] = (rid,)
            elif rid in self._tombstoned:  # subsumed → redirect to the schema row
                for sid, sources in self._provenance.items():
                    if rid in sources:
                        payloads[sid] = self._consolidated[sid]
                        provenance[sid] = sources
        event = MemoryEvent(
            event_id=ctx.clock.event_id(),
            trial_id=ctx.trial_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            timestamp=ctx.clock.timestamp(),
            concrete_tool=f"{self.name}.retrieve",
            normalized_operation=MemoryOperation.SEARCH,
            backend=self.backend,
            query=request.query_text,
            retrieved_ids=list(payloads),
            latency_ms=ctx.clock.latency_ms(),
            success=True,
        )
        return RetrieveResult(payloads=payloads, event=event, source_trace_ids=provenance)
