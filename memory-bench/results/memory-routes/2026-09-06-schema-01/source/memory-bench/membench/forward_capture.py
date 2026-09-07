"""Forward-capture projection — the Phase-0 firewall boundary (PRD §Phase 0).

A runtime `Session`-shaped dict is the OpenRath inversion of mem's field-separated
graph: it bundles label-free join keys, a memory-event payload, AND outcome lineage
(`pr`/`commit_sha`/`base_commit`) into one value that erases field provenance.
This module is the ONLY projecting boundary that re-establishes the separation:

- `project_session_to_record` routes the outcome identifiers ONLY into the
  label-side `record['outcome']` — the leak-side the firewall scans against
  (`grading.leak_guard.outcome_labels`). They never travel anywhere else.
- `project_memory_event` projects ONLY the leak-safe, label-free memory-event
  fields a worker may read, under a STRICT ALLOW-LIST: an unrecognized field
  RAISES (`ForwardCaptureFieldError`) rather than being silently dropped, so a
  producer that grows a novel (possibly outcome-correlated) column is a loud
  failure. It also DEEP-SCANS nested dicts (the free-form `payload`) and RAISES on
  an outcome identifier hiding inside one, then DROPS the label-side `payload`
  from the worker-readable output (mem-ymxp #1). This mirrors the TS
  `MemoryEventSchema.strict()` allow-list (src/schemas/memory-event.ts) — the TS
  schema is the source of truth for the worker-readable shape.
- `worker_readable_text` / `worker_readable_event_text` render exactly what a
  worker could see from a captured record / event, so the caller can run it through
  `assert_no_outcome_leak` — the contract is enforced by the existing guard.
- `assert_capture_firewalled` is the LIVE-path entry point: it runs both scans
  (structural + value) so a runtime write cannot bypass the projector (mem-ymxp #3).
- `rescan_closed_work` is the POST-CLOSE value re-scan (mem-mor1 D-E, Stephanie's
  design B): at in-flight capture the value scan is necessarily empty — the capturing
  work's own outcome SHA does not exist yet — so leak-freeness cannot rest on the
  at-capture value scan alone. Once the work CLOSES and its outcome identifiers are
  known, this re-scans every captured event's worker-readable text against those
  now-known labels and QUARANTINES any whose value carries an outcome label (the
  surface a structural key-scan cannot catch: a raw SHA embedded in `memory_ref`),
  BEFORE that memory is ever served to future work.

ZFC: pure mechanism — key routing, allow-list filtering, substring scanning, no
semantic judgment.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from membench.grading.leak_guard import (
    IDENTIFYING_KEYS,
    assert_no_outcome_leak,
    find_outcome_leaks,
    outcome_labels,
)

# The worker-readable memory-event fields — the leak-safe allow-list, drawn from
# the canonical TS `MemoryEventSchema` (src/schemas/memory-event.ts). Outcome
# identifiers are deliberately absent: a captured memory-event is PRE-OUTCOME and
# carries no label by construction.
_MEMORY_EVENT_FIELDS = frozenset(
    {
        "id",
        "session",
        "work_id",
        "op",
        "backend",
        "memory_ref",
        "used_in",
        "concrete_tool",
        "payload",
        "source",
        "occurred_at",
        "created_at",
    }
)

# `payload` is allow-listed structurally (the TS schema carries it) but is
# LABEL-SIDE per the PRD §Firewall: "ALL memory-event payload is label-side" —
# outcome-correlated low-entropy signal a substring scan structurally cannot catch.
# It is deep-scanned for outcome identifiers (raise) and then DROPPED from the
# worker-readable projection, never surfaced to a worker (mem-ymxp #1).
_LABEL_SIDE_EVENT_FIELDS = frozenset({"payload"})

# The outcome identifiers — imported from `leak_guard` so the projector's routing/
# scan set IS the guard's value-scan set and the two cannot drift (mem-ymxp #5).
# Routed label-side only.
_OUTCOME_KEYS = IDENTIFYING_KEYS

# The Session keys the projector recognizes. A novel top-level Session field is
# also a strict-allow-list violation (same firewall principle as the event fields).
_SESSION_FIELDS = frozenset({"work_id", "rig", "started", "closed", "outcome", "memory_event"})


class ForwardCaptureFieldError(ValueError):
    """Raised when a Session / memory-event payload carries a field outside the
    leak-safe allow-list — a validity failure (the field may be outcome-correlated
    and unscanned), never silently dropped."""

    def __init__(self, where: str, unknown: list[str]) -> None:
        self.where = where
        self.unknown = unknown
        super().__init__(
            f"{where} carries fields outside the forward-capture allow-list: "
            f"{', '.join(sorted(unknown))}"
        )


def _nested_outcome_keys(obj: Any) -> list[str]:
    """Every outcome-identifier key (`pr`/`commit_sha`/`base_commit`) found in a
    NESTED dict reachable from `obj` — the leak a flat top-level allow-list misses
    (e.g. inside the free-form `payload`, or inside a Session's `memory_event`).
    Recurses dicts and list/tuple values. Top-level keys are the caller's concern
    (handled by the allow-list); this scans the values."""
    found: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in _OUTCOME_KEYS:
                found.append(key)
            found.extend(_nested_outcome_keys(value))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            found.extend(_nested_outcome_keys(item))
    return found


def project_session_to_record(session: dict[str, Any]) -> dict[str, Any]:
    """Project a runtime Session dict into a field-separated WorkRecord-shaped dict.

    Outcome identifiers route ONLY into `record['outcome']` (the label-side the
    firewall scans). Label-free join keys (`work_id`/`rig`/`started`/`closed`) stay
    on the record body. A novel top-level Session field RAISES (strict allow-list).
    An unknown key inside the `outcome` dict RAISES rather than being silently
    dropped by the routing comprehension, and an outcome identifier nested anywhere
    OTHER than the routed `outcome` dict RAISES too (mem-ymxp #2) — never a silent
    drop that could let an outcome-correlated value pass unscanned."""
    unknown = [k for k in session if k not in _SESSION_FIELDS]
    if unknown:
        raise ForwardCaptureFieldError("Session", unknown)
    outcome_in = session.get("outcome") or {}
    novel_outcome = [k for k in outcome_in if k not in _OUTCOME_KEYS]
    if novel_outcome:
        raise ForwardCaptureFieldError("Session.outcome", novel_outcome)
    # Outcome identifiers are legitimate ONLY in the routed `outcome` dict; anywhere
    # else (e.g. nested in the dropped `memory_event`) they are an unscanned leak.
    misplaced = [
        key
        for field, value in session.items()
        if field != "outcome"
        for key in _nested_outcome_keys(value)
    ]
    if misplaced:
        raise ForwardCaptureFieldError("Session (nested outside outcome)", misplaced)
    return {
        "work_id": session["work_id"],
        "rig": session["rig"],
        "lifecycle": {
            "started": session.get("started"),
            "closed": session.get("closed"),
        },
        "outcome": {key: outcome_in[key] for key in _OUTCOME_KEYS if key in outcome_in},
    }


def project_memory_event(event: dict[str, Any]) -> dict[str, Any]:
    """Project a memory-event onto the worker-readable allow-list.

    A top-level field outside `_MEMORY_EVENT_FIELDS` RAISES (it could smuggle an
    unscanned, outcome-correlated column past the firewall). Beyond the flat list:
    an outcome identifier nested inside the allow-listed (free-form) `payload` — or
    any other nested dict — RAISES (mem-ymxp #1), so it cannot ride a label-side
    field past the firewall unscanned. The label-side fields (`payload`) are then
    DROPPED from the returned worker-readable event: they are never surfaced to a
    worker (PRD §Firewall — payload is outcome-correlated by default)."""
    unknown = [k for k in event if k not in _MEMORY_EVENT_FIELDS]
    if unknown:
        raise ForwardCaptureFieldError("memory_event", unknown)
    nested = [key for value in event.values() for key in _nested_outcome_keys(value)]
    if nested:
        raise ForwardCaptureFieldError("memory_event (nested)", nested)
    return {k: v for k, v in event.items() if k not in _LABEL_SIDE_EVENT_FIELDS}


def worker_readable_text(record: dict[str, Any]) -> str:
    """The agent-readable text a worker could see from a captured record: the
    label-free join keys only. The outcome block is NEVER rendered — it exists on
    the record solely as the label-side the firewall scans against."""
    lifecycle = record.get("lifecycle") or {}
    parts = [
        f"work_id={record.get('work_id', '')}",
        f"rig={record.get('rig', '')}",
        f"started={lifecycle.get('started', '')}",
    ]
    return "\n".join(parts)


def worker_readable_event_text(event: dict[str, Any]) -> str:
    """The agent-readable text a worker could see from a captured memory-event: the
    string values of its leak-safe (already-projected) fields, joined for scanning.
    The caller passes a `project_memory_event` output, so label-side fields are
    already dropped."""
    return "\n".join(f"{key}={value}" for key, value in sorted(event.items()))


def assert_capture_firewalled(event: dict[str, Any], outcome_labels: Iterable[str]) -> None:
    """The LIVE-path firewall: the SAME boundary the offline projector enforces, so a
    live write is not a firewall bypass (mem-ymxp #3).

    Two complementary scans, both raising:
      1. STRUCTURAL — `project_memory_event` RAISES on a novel field or an outcome
         identifier nested in `payload` (key-based; needs no known label values).
      2. VALUE — `assert_no_outcome_leak` RAISES if any KNOWN outcome label appears
         in the worker-readable text (e.g. a SHA literal embedded in `memory_ref`).
         With no known labels (the pilot, where the in-flight work's outcome does
         not yet exist) this is a no-op and the structural scan stands alone."""
    projected = project_memory_event(event)
    assert_no_outcome_leak(worker_readable_event_text(projected), outcome_labels)


@dataclass(frozen=True)
class QuarantinedCapture:
    """A captured event the POST-CLOSE re-scan blocks from serving: it was
    structurally clean at capture time but its value carries an outcome label that
    only became known once the work closed. `offenders` is the list of
    ``(where, label)`` matches that triggered the quarantine — surfaced, never a
    silent drop."""

    event: dict[str, Any]
    offenders: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class PostCloseRescan:
    """The result of `rescan_closed_work`: the events safe to SERVE (`clean`) and the
    events QUARANTINED because a now-known outcome label appeared in their
    worker-readable text. Only `clean` may be served to future work."""

    clean: tuple[dict[str, Any], ...] = ()
    quarantined: tuple[QuarantinedCapture, ...] = field(default_factory=tuple)

    @property
    def leaked(self) -> bool:
        """True iff the re-scan quarantined at least one event — a post-close leak the
        in-flight structural scan could not catch."""
        return bool(self.quarantined)


def rescan_closed_work(
    events: Iterable[dict[str, Any]], outcome: Mapping[str, Any]
) -> PostCloseRescan:
    """Post-close VALUE re-scan of a work's forward-captured events (mem-mor1 D-E,
    design B).

    At in-flight capture the firewall's value scan is empty — the capturing work's own
    outcome SHA does not exist yet — so a raw outcome value embedded in a non-outcome-
    keyed field (e.g. `memory_ref`) passes the structural scan unguarded. Once the work
    CLOSES, `outcome` (its `pr`/`commit_sha`/`base_commit`) is known; this re-scans each
    captured event's worker-readable text against those labels and partitions the events
    into the ones safe to SERVE and the ones to QUARANTINE — the serve-time gate that
    makes the corpus's "outcome never leaks into input" claim defensible.

    Each event is first run through `project_memory_event` (so the re-scan sees exactly
    the worker-readable projection — label-side `payload` dropped, structural violations
    still RAISING, since a structurally-bad stored event is a producer bug at any time).
    A clean event is returned in `clean`; an event whose value carries an outcome label
    is returned in `quarantined` with its offenders — surfaced, never silently dropped.
    With an empty `outcome` (no identifiers known) every event is clean: the re-scan is
    a no-op until there is a label to scan against.

    ZFC: mechanical substring scan against the now-known labels (shared with the
    `leak_guard` value scan via `find_outcome_leaks`), no semantic judgment."""
    labels = outcome_labels({"outcome": dict(outcome)})
    clean: list[dict[str, Any]] = []
    quarantined: list[QuarantinedCapture] = []
    for event in events:
        projected = project_memory_event(event)
        offenders = find_outcome_leaks(worker_readable_event_text(projected), labels)
        if offenders:
            quarantined.append(QuarantinedCapture(event=event, offenders=tuple(offenders)))
        else:
            clean.append(event)
    return PostCloseRescan(clean=tuple(clean), quarantined=tuple(quarantined))
