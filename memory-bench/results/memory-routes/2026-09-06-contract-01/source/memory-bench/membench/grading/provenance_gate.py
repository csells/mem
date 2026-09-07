"""M7 — the reversibility/provenance gate (a sibling of ``validity_gate.py``).

Every item a consolidating arm returns claims to be *re-derivable* from the source
traces it cites. This gate proves that claim by DEREFERENCING the chain: each cited
``source_trace_id`` must resolve to a live row. A shape check (is the list
non-empty?) is not enough and is the exact hole premortem lens 4 named —
``consolidate -> tombstone -> GC`` can reap a cited trace, so "re-derivable" is true
at write time and a lie at read time. The negative test is therefore a *reaped*
citation, not a fabricated one.

Two failure shapes, both VOID-worthy for the arm under audit:

* ``no_provenance`` — a returned item cites nothing (a claim with no source);
* ``dangling_citation`` — a cited trace id does not resolve to a live row.

``cited_trace_ids`` is the reference-count keep-set: any GC that runs against the
trace store MUST union it into its retained set, or it reintroduces the dangling
hole the gate exists to catch. The gate is pure mechanism (ZFC): it interprets a
caller-supplied liveness predicate, it does not judge content.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from pydantic import BaseModel, ConfigDict


class ProvenanceItem(BaseModel):
    """One returned/consolidated item and the traces it claims to derive from."""

    model_config = ConfigDict(frozen=True)

    memory_id: str
    source_trace_ids: tuple[str, ...] = ()


class DanglingCitation(BaseModel):
    """Why one item failed the gate. ``missing_trace_ids`` is empty for the
    ``no_provenance`` shape (there was nothing to dereference)."""

    model_config = ConfigDict(frozen=True)

    memory_id: str
    missing_trace_ids: tuple[str, ...]
    reason: str  # "no_provenance" | "dangling_citation"


class ProvenanceResult(BaseModel):
    """The gate readout. ``valid`` is False if ANY item dangles; the offending
    items are named so the failure is never silent."""

    model_config = ConfigDict(frozen=True)

    checked: int
    reachable: int
    dangling: tuple[DanglingCitation, ...]
    valid: bool
    reason: str


def cited_trace_ids(items: Iterable[ProvenanceItem]) -> frozenset[str]:
    """The union of every cited source trace id — the GC reference-count keep-set."""
    out: set[str] = set()
    for item in items:
        out.update(item.source_trace_ids)
    return frozenset(out)


def provenance_gate(
    items: Iterable[ProvenanceItem],
    *,
    is_live: Callable[[str], bool],
) -> ProvenanceResult:
    """Dereference every item's citation chain. ``is_live(trace_id)`` is the
    reachability oracle — it walks a trace id to a live content-bearing row (a
    tombstoned-but-present row is still live; a GC-reaped one is not)."""
    items = list(items)
    dangling: list[DanglingCitation] = []
    reachable = 0
    for item in items:
        if not item.source_trace_ids:
            dangling.append(
                DanglingCitation(
                    memory_id=item.memory_id, missing_trace_ids=(), reason="no_provenance"
                )
            )
            continue
        missing = tuple(t for t in item.source_trace_ids if not is_live(t))
        if missing:
            dangling.append(
                DanglingCitation(
                    memory_id=item.memory_id,
                    missing_trace_ids=missing,
                    reason="dangling_citation",
                )
            )
        else:
            reachable += 1

    if not items:
        return ProvenanceResult(
            checked=0,
            reachable=0,
            dangling=(),
            valid=True,
            reason="no consolidated items to check",
        )
    valid = not dangling
    if valid:
        reason = f"all {len(items)} item(s) re-derivable from live source traces"
    else:
        reason = f"{len(dangling)} of {len(items)} item(s) not re-derivable"
    return ProvenanceResult(
        checked=len(items),
        reachable=reachable,
        dangling=tuple(dangling),
        valid=valid,
        reason=reason,
    )
