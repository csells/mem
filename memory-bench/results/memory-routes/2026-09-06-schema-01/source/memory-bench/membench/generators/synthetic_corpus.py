"""§11 Phase-1 — materialize a synthetic ``BenchmarkSequence`` into a corpus WorkRecord.

The synthetic generator (``generators.synthetic_task`` → ``BenchmarkSequence``, gated
by ``generators.memory_necessity_gate``) already exists; this module is the missing
wiring that turns its output into a DURABLE WorkRecord the eval consumes the SAME way
it consumes real work — ``corpus.load_corpus`` → ``validity.work_ref_from_record`` →
the temporal LOO guard. No bespoke synthetic loader, no second firewall, no second
reader.

D-J SHARE (Stephanie, mayor gc-408430): a synthetic record IS a WorkRecord in the
existing JSON projection, distinguished from a real one ONLY by ``origin="synthetic"``
(projected first-class by ``validity.WorkRef.origin``; real records project
``"real"``). One schema, one reader, one LOO path.

Field separation is load-bearing for validity: the ONLY outcome label a synthetic
record carries is the deterministic memory-necessity verdict (oracle-vs-no-memory
rewards), computed offline with no model — never a real bead's ``commit_sha`` / ``pr``
/ resolution. An optional high-entropy ``outcome_sentinel`` (a synthetic outcome
token, never a real SHA) is routed into the firewall-scanned ``outcome.commit_sha``
ONLY, so the EXISTING ``grading.leak_guard`` / ``WorkRecordLadderAdapter`` firewall
catches it mechanically if a mis-projection ever lets it reach agent-readable text.

ZFC: deterministic projection of authored ground truth — no semantic judgment.
"""

from __future__ import annotations

from typing import Any

from membench.generators.memory_necessity_gate import NecessityResult
from membench.schemas.sequence import BenchmarkSequence

# Marks a record as generator-produced, distinguishing it from a city-ingested real
# WorkRecord. The reader (`validity.work_ref_from_record`) projects this as a
# first-class field defaulting to "real", so one corpus carries both provenances. The
# synthetic `rig` namespace coincides with the origin by design — generated work has
# no real repository.
SYNTHETIC_ORIGIN = "synthetic"


def materialize_record(
    seq: BenchmarkSequence,
    necessity: NecessityResult,
    *,
    started: str,
    closed: str,
    outcome_sentinel: str | None = None,
) -> dict[str, Any]:
    """Project a gated synthetic sequence into a WorkRecord — the existing JSON
    projection shape ``work_ref_from_record`` / ``load_corpus`` consume.

    The agent-readable side is built ONLY from the sequence's label-free ``title``;
    the label side carries the offline necessity verdict (and the optional synthetic
    outcome sentinel) confined to ``outcome``, so the existing firewall holds."""
    verdict = necessity.verdict
    outcome: dict[str, Any] = {
        # The synthetic outcome label: the deterministic necessity verdict ONLY —
        # never a real bead outcome. Lives on the label side of field separation.
        "memory_necessity": {
            "accepted": verdict.accepted,
            "oracle_reward": verdict.oracle_reward,
            "no_memory_reward": verdict.no_memory_reward,
            "delta": verdict.delta,
        },
    }
    if outcome_sentinel is not None:
        # A synthetic outcome token routed into a firewall-scanned identifying key, so
        # leak-safety is mechanically checkable end-to-end (never a real SHA/PR).
        outcome["commit_sha"] = outcome_sentinel
    return {
        "work_id": f"synthetic-{seq.sequence_id}",
        "rig": SYNTHETIC_ORIGIN,
        # Label-free task framing — the only synthetic text an agent may read.
        "title": seq.title,
        "lifecycle": {
            "created": started,
            "started": started,
            "closed": closed,
            "status": "closed",
        },
        "links": {"supersedes": []},
        "origin": SYNTHETIC_ORIGIN,
        "outcome": outcome,
    }
