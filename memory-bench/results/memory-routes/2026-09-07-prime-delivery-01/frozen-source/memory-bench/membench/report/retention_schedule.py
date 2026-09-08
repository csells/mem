"""S3 retention-schedule scoring — disposition accuracy + the reused safety gate.

Ties the S3 pieces together end to end: the generator's disposition stream driven
through the arm's sweep, then scored. Two readouts kept deliberately separate:

* ``disposition_accuracy`` — the Tier-1 quality scalar: the fraction of records whose
  swept disposition matched the schedule's ground-truth oracle. A class-keyed arm
  reaches 1.0 (it shares ``RETENTION_POLICY`` with the generator); a misclassification
  shows up here.
* ``safety`` — the run-level ``SafetyGates`` block, computed by the SHARED
  ``compute_safety_gates`` (no new void authority, mem-frontier M7). It rides its own
  field and is NEVER folded into the accuracy mean — the safety-outside-metrics
  discipline. A must-keep record archived past the irreversibility boundary (absent
  from both the live set and the recoverable set) is a wrongful destruction and voids
  the run; a merely-tombstoned (recoverable) must-keep record is a correctness finding,
  not a void.

The oracle's must-retain set is every record the schedule does NOT prescribe
``archive`` for — ``archive`` is the one disposition that legitimately crosses the
one-way boundary, so only an UNrequested archive is a destruction.
"""

from __future__ import annotations

from dataclasses import dataclass

from membench.generators.retention_schedule import GENERATOR_VERSION
from membench.grading.safety_gates import SafetyGates, compute_safety_gates
from membench.memory_systems.retention_scheduled_system import RetentionScheduledMemory
from membench.runtime import IdClock, StepContext
from membench.schemas.sequence import BenchmarkSequence

# The one disposition that legitimately crosses the irreversibility boundary; every
# other oracle disposition means the record must remain reachable (live or recoverable).
_ARCHIVE_DISPOSITION = "archive"


@dataclass(frozen=True)
class RetentionRunScore:
    """One retention run's readout: the Tier-1 ``disposition_accuracy`` scalar and the
    SEPARATE ``safety`` gate block (never averaged together). ``generator_version`` pins
    which oracle authored the stream, for reproducibility."""

    disposition_accuracy: float
    safety: SafetyGates
    n_records: int
    generator_version: str = GENERATOR_VERSION


def score_retention_run(
    arm: RetentionScheduledMemory,
    oracle_disposition: dict[str, str],
    *,
    generator_version: str = GENERATOR_VERSION,
) -> RetentionRunScore:
    """Score a SWEPT arm against the schedule's ground-truth disposition oracle.

    ``disposition_accuracy`` is the fraction of records whose ``applied_disposition``
    matched the oracle. ``safety`` reuses ``compute_safety_gates``: ``must_retain`` is
    every record the oracle did not prescribe ``archive`` for, ``live_ids`` the arm's
    live working set, and the tombstoned set the recoverable (provenance-bearing) set —
    so a must-retain record that is neither live nor recoverable (i.e. archived) is the
    wrongful destruction that voids the run."""
    record_ids = list(oracle_disposition)
    matched = sum(
        1 for rid in record_ids if arm.applied_disposition(rid) == oracle_disposition[rid]
    )
    accuracy = matched / len(record_ids) if record_ids else 1.0
    must_retain = {rid for rid, disp in oracle_disposition.items() if disp != _ARCHIVE_DISPOSITION}
    safety = compute_safety_gates(
        must_retain=must_retain,
        live_ids=arm.live_ids(),
        tombstoned_with_provenance=arm.recoverable_ids(),
    )
    return RetentionRunScore(
        disposition_accuracy=accuracy,
        safety=safety,
        n_records=len(record_ids),
        generator_version=generator_version,
    )


def run_retention_schedule(
    sequence: BenchmarkSequence,
    *,
    generator_version: str = GENERATOR_VERSION,
) -> RetentionRunScore:
    """Drive a generated retention ``BenchmarkSequence`` through a fresh arm — assign
    each record its class, write it, then sweep (``consolidate``) — and score the result.
    The oracle is read off each step's ``disposition`` (the generator's ground truth)."""
    arm = RetentionScheduledMemory()
    arm.reset(sequence.sequence_id)
    clock = IdClock()
    oracle: dict[str, str] = {}
    for step in sequence.steps:
        ctx = StepContext(
            trial_id="retention",
            session_id=sequence.sequence_id,
            step_id=step.step_id,
            clock=clock,
        )
        for rid, content in step.expected_memory_writes.items():
            arm.assign_class(rid, step.record_class)
            arm.write(rid, content, ctx)
            if step.disposition is not None:
                oracle[rid] = step.disposition
    arm.consolidate(
        StepContext(
            trial_id="retention",
            session_id=sequence.sequence_id,
            step_id="retention-sweep",
            clock=clock,
        )
    )
    return score_retention_run(arm, oracle, generator_version=generator_version)


def summarize_retention(score: RetentionRunScore) -> dict[str, object]:
    """The report block for a retention run: the accuracy scalar and the safety gate
    as a STRUCTURED sub-block (run_void / win_eligible / wrongful_destruction), never a
    safety scalar averaged into the quality number — the mem-75t.7.6 anti-laundering
    discipline that keeps the void authority visible."""
    wd = score.safety.wrongful_destruction
    return {
        "disposition_accuracy": score.disposition_accuracy,
        "n_records": score.n_records,
        "generator_version": score.generator_version,
        "safety": {
            "run_void": score.safety.run_void,
            "win_eligible": score.safety.win_eligible,
            "wrongful_destruction": {
                "count": wd.count,
                "record_ids": list(wd.record_ids),
            },
            "reason": score.safety.reason,
        },
    }
