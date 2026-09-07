"""Consolidation lifecycle: the ``ConsolidationCapable`` Protocol + its result (S1).

``run_sequence`` isinstance-checks this Protocol to decide whether an arm gets an
offline ``consolidate()`` pass after the per-step write loop — the exact
ClosableClient pattern (``semantic_base.py``): a separate runtime-checkable
Protocol, so the core ``MemorySystem`` ABC stays at its method count (the §5b
no-widening rule). Only arms that actually consolidate implement it; everything
else is skipped.

The subtractive primitive is ``tombstone`` — a SOFT delete that keeps the row
re-derivable. There is deliberately no hard-delete on this Protocol: the
reversibility invariant (M7) says every forgetting op is reversible until archived,
and the provenance gate dereferences the citations a consolidated item leaves
behind. ``background_tokens`` is the honest offline LLM cost (M6) — 0 for the
deterministic CI summarizer, ``> 0`` once a real model fills the cluster summary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from membench.runtime import StepContext


@dataclass(frozen=True)
class ConsolidatedItem:
    """One row ``consolidate()`` produced: the merged/recombined content plus the
    source trace ids it derives from (the provenance the M7 gate dereferences). A
    consolidated item with an empty ``source_trace_ids`` is a fabrication and fails
    the gate — there is no such thing as a sourceless schema row."""

    memory_id: str
    content: str
    source_trace_ids: tuple[str, ...]


@dataclass(frozen=True)
class ConsolidationResult:
    """What one offline ``consolidate()`` pass returns.

    ``items`` are the new consolidated/schema rows (empty under ``dedupe_only``
    when nothing recombines); ``tombstoned_ids`` are the raw episodes the pass
    subsumed (soft-deleted, still re-derivable); ``background_tokens`` is the
    offline model cost metered at the harness boundary (M6 honesty clause)."""

    items: tuple[ConsolidatedItem, ...] = ()
    tombstoned_ids: tuple[str, ...] = ()
    background_tokens: int = 0
    # Free-form per-pass provenance the summary/report may surface (mode, sampler
    # selection counts); never consumed by scoring arithmetic.
    notes: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class ConsolidationCapable(Protocol):
    """An arm that supports the offline consolidation lifecycle. ``run_sequence``
    dispatches ``consolidate()`` once after the write loop when an arm satisfies
    this Protocol. ``tombstone`` is the only sanctioned subtractive op (soft)."""

    def consolidate(self, ctx: StepContext) -> ConsolidationResult: ...

    def tombstone(self, memory_id: str) -> None: ...


@runtime_checkable
class Classifiable(Protocol):
    """An arm that accepts a per-record retention CLASS at write (the sweep's input).

    ``run_sequence`` assigns ``step.record_class`` to each id the step writes, on the
    write-bearing condition, when the arm satisfies this Protocol and the step carries
    a class — so the consolidation factor reaches the live sweep instead of being inert.
    A non-classifying arm (filesystem, lexical, oracle, none) does not satisfy this and
    is left untouched, and a sequence with no ``record_class`` never invokes it."""

    def assign_class(self, memory_id: str, record_class: str | None) -> None: ...
