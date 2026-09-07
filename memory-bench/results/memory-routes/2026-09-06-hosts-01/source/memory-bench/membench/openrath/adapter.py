"""Pure projecting adapter: an OpenRath `Session` -> mem's existing field-separated
types (a provenance `cut` event, typed `MemoryEvent` records, and a `WorkRecord`
with named join keys).

OpenRath (arXiv 2606.19409) makes agent runtime state a first-class composable
`Session`. mem adopts it at EXACTLY ONE boundary — this one-direction projector —
and never persists or carries a Session forward (PRD
`docs/prd-openrath-incorporation.md`, Phase 1). The design rule is an
ALLOW-LIST, not a deny-list: every output is built from an enumerated set of input
fields, and an unrecognized top-level Session field RAISES — a silently dropped
field is an unaudited exfiltration channel the firewall was never told about
(PRD Risk #2 / firewall #5).

Field routing is the load-bearing validity invariant. The held-out outcome label
(`lineage.commit_sha`) is routed into `outcome.commit_sha` ONLY — never into the
agent-readable `title` or any other column — so the EXISTING
`grading.leak_guard` / `WorkRecordLadderAdapter` firewall (not a parallel one)
catches it mechanically if a mis-projection lets it escape. The runtime
`fork_point` is legitimate provenance and rides into a `cut` event; the
memory-event payload is field-separated out into typed `MemoryEvent`s and is
never folded into the WorkRecord.

ZFC: deterministic projection + structural (allow-list / charset / length) checks
only — no semantic judgment in code.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from membench.schemas.memory_event import MemoryBackend, MemoryEvent, MemoryOperation

# Allow-list of recognized top-level Session fields. An unrecognized field is an
# unaudited channel and must RAISE — never be silently dropped, which would let a
# future producer smuggle a field past the firewall (PRD Risk #2 / firewall #5).
_SESSION_FIELDS = frozenset(
    {"session_id", "title", "lineage", "memory_events", "tokens", "rig", "started"}
)

# A runtime fork-point ref: a 40-char lowercase git object id. We accept the full
# lowercase-alphanumeric charset (not strict hex) at this projecting boundary so the
# runtime lineage value rides through verbatim; the strict-hex narrowing
# (`GIT_SHA_RE` / `ProvenanceSchema` in src/schemas/provenance-event.ts) is the
# store's write-boundary job. The 40-length-plus-lowercase requirement already
# rejects the high-entropy outcome labels the firewall guards against.
_FORK_SHA_RE = re.compile(r"^[0-9a-z]{40}$")

# Stamped on every cut this adapter emits — distinguishes runtime-authoritative
# OpenRath lineage from the date-heuristic ingest backfill (src/ingest/provenance.ts)
# at the store boundary (PRD Phase 1.5 dual-source gate).
_OPENRATH_SOURCE = "openrath-runtime"


def _require_known_fields(session: Mapping[str, Any]) -> None:
    """Allow-list gate: every top-level Session field must be enumerated. Raises
    `ValueError` on the first unrecognized field rather than dropping it silently."""
    unknown = sorted(set(session) - _SESSION_FIELDS)
    if unknown:
        raise ValueError(
            f"unrecognized OpenRath Session field(s) {unknown}: the projector is an "
            "allow-list — an unaudited field must fail loudly, never be dropped"
        )


def project_session_to_record(session: Mapping[str, Any]) -> dict[str, Any]:
    """Project a Session into a leak-safe WorkRecord with named join keys.

    The record is built field-by-field from the allow-list — the Session is never
    spread in — so the held-out `lineage.commit_sha` reaches `outcome.commit_sha`
    and nothing else, and the memory-event payload is not folded in."""
    _require_known_fields(session)
    lineage = session.get("lineage") or {}
    record: dict[str, Any] = {
        "work_id": session["session_id"],
        "rig": session["rig"],
        # Label-free task framing — the ONLY Session text an agent may read.
        "title": session["title"],
        "lifecycle": {
            # The D6 LOO boundary the ladder reads; a timestamp, not an outcome.
            "started": session["started"],
            "created": session["started"],
            # A projected Session is always a completed, held-out replay (like a
            # synthetic record) — there is no in-progress OpenRath Session concept.
            "status": "closed",
        },
    }
    commit_sha = lineage.get("commit_sha")
    if commit_sha:
        # The held-out outcome label — routed to the firewall-side column ONLY.
        record["outcome"] = {"commit_sha": commit_sha}
    return record


def project_cut_events(session: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Project the runtime `fork_point` into a provenance `cut` event.

    Returns at most one cut. The fork point is legitimate provenance, so it rides
    into the event verbatim — but only after a structural git-object-id check, so a
    mis-shaped (or outcome-label-shaped) ref fails loudly instead of being recorded."""
    lineage = session.get("lineage") or {}
    fork_point = lineage.get("fork_point")
    if not fork_point:
        return []
    ref = fork_point.get("commit")
    ref_kind = fork_point.get("ref_kind")
    if ref_kind != "git-sha":
        raise ValueError(
            f"unsupported fork_point ref_kind {ref_kind!r}: only 'git-sha' is projected"
        )
    if not (isinstance(ref, str) and _FORK_SHA_RE.match(ref)):
        raise ValueError(f"fork_point commit {ref!r} is not a 40-char git object id")
    return [
        {
            "kind": "cut",
            "ref": ref,
            "ref_kind": "git-sha",
            "source": _OPENRATH_SOURCE,
            "history_state": "recorded",
        }
    ]


def project_memory_events(session: Mapping[str, Any]) -> list[MemoryEvent]:
    """Project the Session's memory-event records into typed `MemoryEvent`s.

    Field-separated from the WorkRecord. Unknown operations/backends fail closed via
    the enums. The Phase-2 `used`/`replay` keys are deliberately not projected yet."""
    session_id = session["session_id"]
    events: list[MemoryEvent] = []
    for index, raw in enumerate(session.get("memory_events") or []):
        events.append(
            MemoryEvent(
                event_id=f"{session_id}-mev-{index}",
                trial_id=session_id,
                session_id=session_id,
                step_id=str(index),
                timestamp=raw["timestamp"],
                concrete_tool=raw["concrete_tool"],
                normalized_operation=MemoryOperation(raw["operation"]),
                backend=MemoryBackend(raw["backend"]),
                query=raw.get("query"),
                retrieved_ids=list(raw.get("retrieved_ids") or []),
            )
        )
    return events
