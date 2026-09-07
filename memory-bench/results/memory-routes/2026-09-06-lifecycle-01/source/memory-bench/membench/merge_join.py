"""Merged session<->bead join (mem-75t.4) — events-primary source hierarchy.

Merges the three join sources into one ordered, source-tagged session list per
store bead:

1. PRIMARY: gc events (`membench.events_join`) — authoritative claim/dispatch
   record at event granularity; its actor sequence orders the sessions.
2. dolt assignee history — cross-check + pre-May fallback.
3. content scan (`membench.session_join`) — cross-validation + non-gc sessions.

Conflict rules (accepted in mem-75t.4 notes):
- event actor-sequence wins: ordering uses event timestamps when present;
- content evidence overrides bare assignee: a store assignee link whose
  transcript was scanned, never mentions its bead, and strongly mentions a
  DIFFERENT bead is flagged `suspect` (the gc-01wm wrong-conversation case)
  instead of being trusted.

Session identity bridges three namespaces: gc session id (`gc-351468`), Claude
session UUID (`session_key`, the transcript filename stem), and transcript
path. The events stream supplies gc-id -> session_key; the transcript corpus
supplies session_key -> path. A respawned seat can resume the same Claude
conversation, so session_key -> gc-id is one-to-many — entries merge through
the gc id when the bead's events already know it, never blindly through the
UUID.

ZFC boundary: deterministic set/ordering logic with explicit tiebreakers — no
semantic judgment.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from membench.session_join import session_uuid

Source = str  # "events" | "dolt-history" | "content-scan" | "assignee"

_FRACTION_TRIM = re.compile(r"\.(\d{6})\d+")


def normalize_ts(raw: str | None) -> str | None:
    """ISO timestamp normalized to UTC (`...+00:00`), or None.

    Event timestamps carry nanosecond fractions and local offsets; transcript
    timestamps are millisecond UTC `Z`. Both must sort together, so everything
    is parsed and re-emitted in one form. Unparseable input returns None —
    ordering treats it as unknown rather than guessing."""
    if not raw:
        return None
    trimmed = _FRACTION_TRIM.sub(r".\1", raw.strip())
    if trimmed.endswith("Z"):
        trimmed = trimmed[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(trimmed)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


@dataclass
class SessionEntry:
    """One session's row in a bead's merged iteration history."""

    gc_session_id: str | None = None
    session_key: str | None = None
    transcript_path: str | None = None
    t_first: str | None = None
    t_last: str | None = None
    sources: list[Source] = field(default_factory=list)
    strength: str = "strong"
    n_events: int = 0
    suspect: bool = False

    def add_source(self, source: Source) -> None:
        if source not in self.sources:
            self.sources.append(source)

    def widen(self, t_first: str | None, t_last: str | None) -> None:
        if t_first and (self.t_first is None or t_first < self.t_first):
            self.t_first = t_first
        if t_last and (self.t_last is None or t_last > self.t_last):
            self.t_last = t_last

    def to_json(self, sequence: int) -> dict[str, Any]:
        return {
            "sequence": sequence,
            "gc_session_id": self.gc_session_id,
            "session_key": self.session_key,
            "transcript_path": self.transcript_path,
            "t_first": self.t_first,
            "t_last": self.t_last,
            "sources": list(self.sources),
            "strength": self.strength,
            "n_events": self.n_events,
            "suspect": self.suspect,
        }


@dataclass(frozen=True)
class MergedBead:
    work_id: str
    entries: tuple[SessionEntry, ...]  # ordered; sequence = index + 1


def _dedupe_content_rows(
    rows: Iterable[Mapping[str, Any]],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    """One content row per (session uuid, work_id): top-level transcript beats
    subagent sidecars (which share the parent sessionId); more strong mentions
    beats fewer. Mechanical tiebreak, mirrors the spike's dedupe."""
    best: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in rows:
        session = str(row.get("session_id") or "")
        work_id = str(row.get("work_id") or "")
        if not session or not work_id:
            continue
        key = (session, work_id)
        current = best.get(key)
        if current is None or _content_rank(row) > _content_rank(current):
            best[key] = row
    return best


def _content_rank(row: Mapping[str, Any]) -> tuple[int, int]:
    path = str(row.get("transcript_path") or "")
    is_top_level = 0 if "/subagents/" in path else 1
    return (is_top_level, int(row.get("n_strong") or 0))


def _sort_key(entry: SessionEntry) -> tuple[int, str, str]:
    """Timestamped entries first (chronological); timeless ones after, ordered
    by source priority (dolt before bare assignee) then id for determinism."""
    if entry.t_first is not None:
        return (0, entry.t_first, entry.gc_session_id or entry.session_key or "")
    priority = "0" if "dolt-history" in entry.sources else "1"
    return (1, priority, entry.gc_session_id or entry.session_key or entry.transcript_path or "")


def _fold_alias(keep: SessionEntry, other: SessionEntry) -> None:
    """Fold `other` into `keep` — they are the same Claude session reached via
    two filesystem namespaces. Union sources, widen the span, keep the richest
    ids. A session confirmed by any non-suspect source is not suspect: an
    assignee-path alias that looked contradicted on its own is cleared when the
    events stream (PRIMARY) places the same uuid on the bead."""
    for source in other.sources:
        keep.add_source(source)
    keep.widen(other.t_first, other.t_last)
    if keep.gc_session_id is None:
        keep.gc_session_id = other.gc_session_id
    if keep.session_key is None:
        keep.session_key = other.session_key
    keep.n_events = max(keep.n_events, other.n_events)
    if other.strength == "strong":
        keep.strength = "strong"
    keep.suspect = keep.suspect and other.suspect


def _collapse_aliases(
    entries: Iterable[SessionEntry], uuid_to_path: Mapping[str, str]
) -> list[SessionEntry]:
    """Collapse entries that are one Claude session reached through different
    namespaces (same UUID stem), guaranteeing one entry per (bead, session
    UUID) — the mem-75t.10 fix. Entries with no derivable UUID (a gc-only seat
    with no resolved transcript) pass through untouched: distinct gc ids are
    distinct sessions. The surviving entry adopts the on-disk corpus path
    (`uuid_to_path`, built from transcripts that exist) so downstream trace
    resolution points at a path that resolves rather than the stale alias."""
    by_uuid: dict[str, SessionEntry] = {}
    passthrough: list[SessionEntry] = []
    for entry in entries:
        uuid = entry.session_key or session_uuid(entry.transcript_path)
        if uuid is None:
            passthrough.append(entry)
            continue
        kept = by_uuid.get(uuid)
        if kept is None:
            by_uuid[uuid] = entry
        else:
            _fold_alias(kept, entry)
    for uuid, entry in by_uuid.items():
        if entry.session_key is None:
            entry.session_key = uuid
        corpus_path = uuid_to_path.get(uuid)
        if corpus_path:
            entry.transcript_path = corpus_path
    return list(by_uuid.values()) + passthrough


def merge_bead_sessions(
    *,
    event_pairs: Iterable[Any],
    session_keys: Mapping[str, str],
    content_rows: Iterable[Mapping[str, Any]],
    dolt_sessions: Mapping[str, Sequence[str]],
    assignee_links: Mapping[str, str],
    uuid_to_path: Mapping[str, str],
    store_ids: frozenset[str],
) -> dict[str, MergedBead]:
    """The merged join: per store bead, its ordered source-tagged sessions.

    `event_pairs` items carry work_id / session_id / t_first / t_last /
    n_events (the `events_join.EventPair` shape). `content_rows` are the corpus
    scan rows (session_id = Claude UUID). Only in-store beads are joined."""
    beads: dict[str, dict[str, SessionEntry]] = {}

    def entry_map(work_id: str) -> dict[str, SessionEntry]:
        return beads.setdefault(work_id, {})

    # --- 1. events (PRIMARY): one entry per (bead, acting session) -----------
    for pair in event_pairs:
        work_id = pair.work_id
        if work_id not in store_ids:
            continue
        key = session_keys.get(pair.session_id)
        entry = SessionEntry(
            gc_session_id=pair.session_id,
            session_key=key,
            transcript_path=uuid_to_path.get(key) if key else None,
            t_first=normalize_ts(pair.t_first),
            t_last=normalize_ts(pair.t_last),
            sources=["events"],
            n_events=pair.n_events,
        )
        entry_map(work_id)[pair.session_id] = entry

    # session_key -> the gc sessions that used it (respawned seats resume the
    # same Claude conversation, so this is one-to-many).
    gc_by_uuid: dict[str, list[str]] = {}
    for gc_id, uuid in session_keys.items():
        gc_by_uuid.setdefault(uuid, []).append(gc_id)

    # --- 2. content scan: merge into event entries via the uuid bridge -------
    # Dedupe ALL rows once; the join POPULATION takes only the in-store subset, but
    # the out-of-store rows are retained for the contradiction test in step 4 (a
    # transcript that strongly belongs to an out-of-store bead must still be able to
    # contradict an in-store assignee link — the gc-01wm wrong-conversation class).
    deduped_all = _dedupe_content_rows(content_rows)
    deduped = {key: row for key, row in deduped_all.items() if key[1] in store_ids}
    for (uuid, work_id), row in sorted(deduped.items()):
        entries = entry_map(work_id)
        t_first = normalize_ts(str(row.get("t_first") or "") or None)
        t_last = normalize_ts(str(row.get("t_last") or "") or None)
        target: SessionEntry | None = None
        for gc_id in gc_by_uuid.get(uuid, []):
            if gc_id in entries:
                target = entries[gc_id]
                break
        if target is None:
            target = entries.get(uuid)
        if target is not None:
            target.add_source("content-scan")
            target.widen(t_first, t_last)
            if target.session_key is None:
                target.session_key = uuid
            if target.transcript_path is None:
                target.transcript_path = str(row.get("transcript_path") or "") or None
            continue
        if str(row.get("strength")) != "strong":
            continue  # weak-only content evidence never creates an entry
        gc_candidates = gc_by_uuid.get(uuid, [])
        entries[uuid] = SessionEntry(
            # A uuid shared by several respawned seats is ambiguous — only an
            # unambiguous single candidate is recorded as the gc identity.
            gc_session_id=gc_candidates[0] if len(gc_candidates) == 1 else None,
            session_key=uuid,
            transcript_path=str(row.get("transcript_path") or "") or None,
            t_first=t_first or normalize_ts(str(row.get("session_start") or "") or None),
            t_last=t_last or normalize_ts(str(row.get("session_end") or "") or None),
            sources=["content-scan"],
        )

    # --- 3. dolt assignee history: cross-check + fallback --------------------
    for work_id, sessions in dolt_sessions.items():
        if work_id not in store_ids:
            continue
        entries = entry_map(work_id)
        for gc_id in sessions:
            if gc_id in entries:
                entries[gc_id].add_source("dolt-history")
                continue
            key = session_keys.get(gc_id)
            bridged = entries.get(key) if key else None
            if bridged is not None:
                # A content entry keyed by this session's uuid is the same
                # session seen from the other namespace.
                bridged.add_source("dolt-history")
                if bridged.gc_session_id is None:
                    bridged.gc_session_id = gc_id
                continue
            entries[gc_id] = SessionEntry(
                gc_session_id=gc_id,
                session_key=key,
                transcript_path=uuid_to_path.get(key) if key else None,
                sources=["dolt-history"],
            )

    # --- 4. store assignee link: annotate or flag (content overrides) --------
    # transcript -> {work_id: strength} view of the scan, for the contradiction
    # test on assignee-only transcripts. Built from `deduped_all` (NOT the in-store
    # population) so a strong link to an out-of-store bead still contradicts.
    scanned: dict[str, dict[str, str]] = {}
    for (_uuid, work_id), row in deduped_all.items():
        path = str(row.get("transcript_path") or "")
        if path:
            scanned.setdefault(path, {})[work_id] = str(row.get("strength"))
    for work_id, trace_path in assignee_links.items():
        if work_id not in store_ids or not trace_path:
            continue
        entries = entry_map(work_id)
        matched = next((e for e in entries.values() if e.transcript_path == trace_path), None)
        if matched is not None:
            matched.add_source("assignee")
            continue
        links_there = scanned.get(trace_path)
        contradicted = (
            links_there is not None
            and work_id not in links_there
            and any(strength == "strong" for strength in links_there.values())
        )
        entries[f"assignee:{trace_path}"] = SessionEntry(
            transcript_path=trace_path,
            sources=["assignee"],
            suspect=contradicted,
        )

    merged: dict[str, MergedBead] = {}
    for work_id, entries in beads.items():
        collapsed = _collapse_aliases(entries.values(), uuid_to_path)
        ordered = tuple(sorted(collapsed, key=_sort_key))
        if ordered:
            merged[work_id] = MergedBead(work_id=work_id, entries=ordered)
    return merged


def merged_stats(merged: Mapping[str, MergedBead]) -> dict[str, Any]:
    """Coverage + source-agreement report over the merged join (arithmetic only)."""
    n_beads = len(merged)
    n_entries = 0
    multi = 0
    multi_non_suspect = 0
    with_path = 0
    with_key = 0
    suspect = 0
    by_source: dict[str, int] = {}
    overlap: dict[str, int] = {}
    iterations: dict[int, int] = {}

    for bead in merged.values():
        live = [e for e in bead.entries if not e.suspect]
        if len(live) >= 2:
            multi_non_suspect += 1
        if len(bead.entries) >= 2:
            multi += 1
        iterations[len(live)] = iterations.get(len(live), 0) + 1
        for entry in bead.entries:
            n_entries += 1
            if entry.transcript_path:
                with_path += 1
            if entry.session_key:
                with_key += 1
            if entry.suspect:
                suspect += 1
            for source in entry.sources:
                by_source[source] = by_source.get(source, 0) + 1
            combo = "+".join(sorted(entry.sources))
            overlap[combo] = overlap.get(combo, 0) + 1

    return {
        "beads": n_beads,
        "session_entries": n_entries,
        "multi_session_beads": multi,
        "multi_session_beads_non_suspect": multi_non_suspect,
        "entries_with_transcript": with_path,
        "entries_with_session_key": with_key,
        "suspect_assignee_entries": suspect,
        "entries_by_source": dict(sorted(by_source.items())),
        "source_overlap": dict(sorted(overlap.items())),
        "iterations_histogram": {str(k): v for k, v in sorted(iterations.items())},
    }
