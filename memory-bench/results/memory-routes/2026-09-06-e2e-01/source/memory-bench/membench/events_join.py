"""gc-events join source (mem-75t.4 — PRIMARY source of the merged join).

`/home/ds/gas-city/.gc/events.jsonl` (live) plus its `*.archive-*-seq-A-B.gz`
siblings are the authoritative claim/dispatch record: every `bead.*` event
carries the bead payload, the acting seat-session (`actor`, e.g.
`polecat-gc-223433`), and a timestamp. This catches silent polecats (sessions
that never type their bead id) and yields the per-bead actor SEQUENCE that
fixes the assignee wrong-conversation mis-attribution found in mem-75t.9.

Two extractions per pass:

- (work_id, gc-session) pairs from work-bead events, via TWO channels: the
  event `actor` (the session ACTED on the bead) and the payload `assignee`
  (the bead was ASSIGNED to that session at event time — symbolic actors like
  `controller`/`cache-reconcile` write events that carry the worker only in
  the assignee field). Session-housekeeping beads (`issue_type=session` /
  `gc:session` label) are excluded as link TARGETS — they track seats, not
  work.
- gc-session -> Claude session UUID from those same housekeeping beads'
  `metadata.session_key` — the transcript filename stem. This is the one-pass
  resolver that replaces per-record `gc session logs` shelling (~11 s/call).

ZFC boundary: structural parsing of an append-only log — no semantic judgment.
Archive/live overlap is deduplicated mechanically via the seq ranges encoded
in the archive filenames.
"""

from __future__ import annotations

import gzip
import json
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

# A gc session id embedded in an event actor (`polecat-gc-223433`,
# `mem-worker-gc-340057`, bare `gc-351468`). Path-shaped or symbolic actors
# (`mayor`, `controller`, `cache-reconcile`, `/home/ds/...`) carry no session
# id and yield no pair — their sessions are covered by the content scan.
_ACTOR_SESSION_RE = re.compile(r"\bgc-\d+\b")

# Cheap line probe: full JSON parse only on lines that can carry a bead.*
# event ('"bead.' matches the quoted type value with or without key spacing).
_BEAD_EVENT_PROBE = '"bead.'

# Archive filename seq range: events.jsonl.archive-<stamp>-seq-<first>-<last>.gz
_ARCHIVE_SEQ_RE = re.compile(r"\.archive-.*-seq-(\d+)-(\d+)\.gz$")


@dataclass(frozen=True)
class EventPair:
    """One (work bead, session) pair aggregated over all its events.

    `n_actor_events` counts events where the session was the ACTOR;
    `n_assignee_events` where it was the payload assignee. A session can be
    implicated through both in one event (counted once in `n_events`)."""

    work_id: str
    session_id: str
    t_first: str
    t_last: str
    n_events: int
    n_actor_events: int = 0
    n_assignee_events: int = 0


@dataclass(frozen=True)
class EventsJoin:
    """The full events extraction: pairs + the session-key resolver map."""

    pairs: tuple[EventPair, ...]
    # gc session id -> Claude session UUID (transcript filename stem).
    session_keys: Mapping[str, str]
    n_events_scanned: int
    n_bead_events: int
    # bead-shaped lines that failed to parse as JSON -- surfaced (not swallowed) so
    # event-log corruption shows up as a coverage gap in the report rather than
    # silently dropping pairs.
    n_malformed_lines: int = 0


def actor_session(actor: str) -> str | None:
    """The gc session id embedded in an event actor, or None."""
    match = _ACTOR_SESSION_RE.search(actor)
    return match.group(0) if match else None


def event_paths(events_dir: str | Path) -> list[Path]:
    """The events files of a .gc dir in replay order: archives (by seq), then
    the live log. Raises FileNotFoundError when the live log is absent — an
    events dir without events.jsonl is a misconfiguration, not an empty join."""
    base = Path(events_dir)
    live = base / "events.jsonl"
    if not live.is_file():
        raise FileNotFoundError(f"no events.jsonl under {base}")
    archives = sorted(
        (p for p in base.glob("events.jsonl.archive-*.gz") if p.is_file()),
        key=_archive_first_seq,
    )
    return [*archives, live]


def _archive_first_seq(path: Path) -> int:
    match = _ARCHIVE_SEQ_RE.search(path.name)
    return int(match.group(1)) if match else 0


def _max_archived_seq(paths: Iterable[Path]) -> int:
    """The highest seq covered by the archive files (0 when none parse)."""
    best = 0
    for path in paths:
        match = _ARCHIVE_SEQ_RE.search(path.name)
        if match:
            best = max(best, int(match.group(2)))
    return best


def _open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open(encoding="utf-8", errors="replace")


def bead_payload(event: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The bead object of a bead.* event — two shapes exist in the log:
    `payload.bead` (nested, bd-originated) and a flat `payload` (gc-originated)."""
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return None
    nested = payload.get("bead")
    if isinstance(nested, Mapping):
        return nested
    return payload


def is_session_bead(payload: Mapping[str, Any]) -> bool:
    """True for gc session-housekeeping beads (seat trackers, not work)."""
    if payload.get("issue_type") == "session":
        return True
    labels = payload.get("labels")
    return isinstance(labels, list) and "gc:session" in labels


@dataclass
class _PairAcc:
    t_first: str = ""
    t_last: str = ""
    n_events: int = 0
    n_actor: int = 0
    n_assignee: int = 0

    def add(self, ts: str, *, as_actor: bool, as_assignee: bool) -> None:
        if ts:
            if not self.t_first or ts < self.t_first:
                self.t_first = ts
            if not self.t_last or ts > self.t_last:
                self.t_last = ts
        self.n_events += 1
        if as_actor:
            self.n_actor += 1
        if as_assignee:
            self.n_assignee += 1


def _iter_bead_events(
    paths: Iterable[Path], skip_live_upto: int, malformed: list[int]
) -> Iterator[Mapping[str, Any]]:
    """Yield parsed bead-shaped events. ``malformed`` is a single-element
    accumulator the caller reads after the generator is drained: a bead-shaped line
    that fails to parse increments it rather than vanishing silently."""
    for path in paths:
        is_live = path.suffix != ".gz"
        with _open_text(path) as handle:
            for line in handle:
                if _BEAD_EVENT_PROBE not in line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    malformed[0] += 1
                    continue
                if not isinstance(event, Mapping):
                    continue
                if is_live:
                    seq = event.get("seq")
                    if isinstance(seq, int) and seq <= skip_live_upto:
                        continue
                yield event


def collect_events_join(paths: Iterable[Path]) -> EventsJoin:
    """One pass over the events files: (bead, session) pairs + session keys.

    Live-log events whose seq is already covered by an archive are skipped, so
    overlapping retention never double-counts a pair's `n_events`."""
    path_list = list(paths)
    skip_live_upto = _max_archived_seq(path_list)

    pair_acc: dict[tuple[str, str], _PairAcc] = {}
    session_keys: dict[str, str] = {}
    n_scanned = 0
    n_bead = 0
    malformed = [0]

    for event in _iter_bead_events(path_list, skip_live_upto, malformed):
        n_scanned += 1
        event_type = event.get("type")
        if not isinstance(event_type, str) or not event_type.startswith("bead."):
            continue
        n_bead += 1
        payload = bead_payload(event)
        if payload is None:
            continue
        ts = event.get("ts")
        ts_str = ts if isinstance(ts, str) else ""

        if is_session_bead(payload):
            # Housekeeping bead: harvest the session-key resolver mapping.
            session_id = payload.get("id") or event.get("subject")
            metadata = payload.get("metadata")
            key = metadata.get("session_key") if isinstance(metadata, Mapping) else None
            if isinstance(session_id, str) and isinstance(key, str) and key:
                session_keys[session_id] = key
            continue

        work_id = payload.get("id") or event.get("subject")
        if not isinstance(work_id, str) or not work_id:
            continue
        actor = event.get("actor")
        from_actor = actor_session(actor) if isinstance(actor, str) else None
        assignee = payload.get("assignee")
        from_assignee = actor_session(assignee) if isinstance(assignee, str) else None
        for session in {s for s in (from_actor, from_assignee) if s is not None}:
            pair_acc.setdefault((work_id, session), _PairAcc()).add(
                ts_str,
                as_actor=session == from_actor,
                as_assignee=session == from_assignee,
            )

    pairs = tuple(
        EventPair(
            work_id=work_id,
            session_id=session,
            t_first=acc.t_first,
            t_last=acc.t_last,
            n_events=acc.n_events,
            n_actor_events=acc.n_actor,
            n_assignee_events=acc.n_assignee,
        )
        for (work_id, session), acc in sorted(pair_acc.items())
    )
    return EventsJoin(
        pairs=pairs,
        session_keys=session_keys,
        n_events_scanned=n_scanned,
        n_bead_events=n_bead,
        n_malformed_lines=malformed[0],
    )
