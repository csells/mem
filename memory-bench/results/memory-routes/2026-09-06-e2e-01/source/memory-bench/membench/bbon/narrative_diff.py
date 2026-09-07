"""Deterministic narrative diff between two attempts (port of engram's
`src/agents/judge/narrativeDiff.ts`).

The diff is the mechanical artifact that shows WHAT a warm-forked run did
differently from a cold one: an index-aligned walk of the two tool-call
sequences, the attempt-level deltas, and the pros/cons each side earns from those
deltas. Engram aligned steps and pulled `status`/error/`learn_complete` signals;
this keeps the alignment verbatim but sources the attempt-level deltas from
membench's real axes — terminal status, tool-call count, iterations-to-green, and
total tokens — since `learn_complete` has no membench analog.

ZFC: pure mechanism. Every delta and pros/cons bullet is deterministic arithmetic
over the attempt records and step lists; the *semantic* judgment over this diff is
the comparative judge's job (`comparative_judge.py`), not this module's.
"""

from __future__ import annotations

from collections.abc import Sequence

from membench.bbon.models import (
    AlignedStep,
    Attempt,
    AttemptStep,
    Delta,
    NarrativeDiff,
    ProsCons,
)

# result-vector keys (from `armcompare.BeadMetrics`) the attempt-level deltas read,
# each as (result_key, delta_label, pros_cons_phrase). Every axis is lower-is-better,
# so a smaller value is the advantage; the label and phrase name the same axis so the
# delta description and its pros/cons bullet never disagree.
_LOWER_IS_BETTER = (
    ("iterations_to_green", "iterations to green", "iterations to green"),
    ("total_tokens", "tokens", "tokens"),
)


def generate_narrative_diff(
    left: Attempt,
    right: Attempt,
    left_steps: Sequence[AttemptStep],
    right_steps: Sequence[AttemptStep],
) -> NarrativeDiff:
    """The full deterministic diff of ``left`` vs ``right``."""
    aligned = _align_steps(left_steps, right_steps)
    deltas = _compute_deltas(left, right, left_steps, right_steps)
    pros_cons = _extract_pros_cons(left, right, deltas)
    summary = _summary(left, right, deltas, pros_cons)
    return NarrativeDiff(
        left_attempt_id=left.id,
        right_attempt_id=right.id,
        aligned_steps=aligned,
        deltas=deltas,
        pros_cons=pros_cons,
        summary=summary,
    )


def _align_steps(
    left_steps: Sequence[AttemptStep], right_steps: Sequence[AttemptStep]
) -> list[AlignedStep]:
    """Index-align the two step lists (engram's `alignSteps`): pair by position,
    flag kind/output mismatches and one-sided overruns."""
    aligned: list[AlignedStep] = []
    for i in range(max(len(left_steps), len(right_steps))):
        left = left_steps[i] if i < len(left_steps) else None
        right = right_steps[i] if i < len(right_steps) else None
        delta: str | None = None
        if left is not None and right is not None:
            if left.kind != right.kind:
                delta = f"Step {i}: kind differs ({left.kind} vs {right.kind})"
            elif left.output != right.output or left.observation != right.observation:
                delta = f"Step {i}: output or observation differs"
        elif left is not None:
            delta = f"Step {i}: only in left attempt ({left.kind})"
        elif right is not None:
            delta = f"Step {i}: only in right attempt ({right.kind})"
        aligned.append(AlignedStep(index=i, left_step=left, right_step=right, delta=delta))
    return aligned


def _result_number(attempt: Attempt, key: str) -> float | None:
    """A numeric metric from ``attempt.result``, or ``None`` for a typed absence /
    non-numeric value (so a missing axis omits its delta rather than imputing 0)."""
    value = attempt.result.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _compute_deltas(
    left: Attempt,
    right: Attempt,
    left_steps: Sequence[AttemptStep],
    right_steps: Sequence[AttemptStep],
) -> list[Delta]:
    """Attempt-level differences: status, step count, and the lower-is-better
    result axes — each emitted only when both sides carry a value."""
    deltas: list[Delta] = []
    if left.status != right.status:
        deltas.append(
            Delta(
                type="modified",
                path="status",
                left_value=left.status,
                right_value=right.status,
                description=f"Status: {left.status} → {right.status}",
            )
        )
    if len(left_steps) != len(right_steps):
        deltas.append(
            Delta(
                type="modified",
                path="steps.length",
                left_value=len(left_steps),
                right_value=len(right_steps),
                description=f"Step count: {len(left_steps)} → {len(right_steps)}",
            )
        )
    for key, label, _ in _LOWER_IS_BETTER:
        left_val, right_val = _result_number(left, key), _result_number(right, key)
        if left_val is None or right_val is None or left_val == right_val:
            continue
        deltas.append(
            Delta(
                type="modified",
                path=key,
                left_value=left_val,
                right_value=right_val,
                description=f"{label}: {left_val:g} → {right_val:g}",
            )
        )
    return deltas


def _extract_pros_cons(left: Attempt, right: Attempt, deltas: Sequence[Delta]) -> ProsCons:
    """The advantages each side earns from the deltas (engram's `extractProsCons`):
    completion, then each lower-is-better axis, then step-count conciseness."""
    left_pros: list[str] = []
    left_cons: list[str] = []
    right_pros: list[str] = []
    right_cons: list[str] = []

    for attempt, pros, cons in ((left, left_pros, left_cons), (right, right_pros, right_cons)):
        if attempt.status == "completed":
            pros.append("Completed successfully")
        else:
            cons.append(f"Did not complete (status: {attempt.status})")

    lower_is_better_labels = {key: phrase for key, _, phrase in _LOWER_IS_BETTER}
    for delta in deltas:
        if delta.path in lower_is_better_labels:
            phrase = lower_is_better_labels[delta.path]
            left_val, right_val = delta.left_value, delta.right_value
            if left_val is None or right_val is None:
                # _compute_deltas never emits a None-valued lower-is-better delta, but
                # Delta.left/right_value are typed Any — guard the comparison so a
                # hand-built Delta can't trip an opaque TypeError here.
                continue
            if left_val < right_val:
                left_pros.append(f"Fewer {phrase} ({left_val:g} vs {right_val:g})")
                right_cons.append(f"More {phrase} ({right_val:g} vs {left_val:g})")
            else:
                right_pros.append(f"Fewer {phrase} ({right_val:g} vs {left_val:g})")
                left_cons.append(f"More {phrase} ({left_val:g} vs {right_val:g})")
        elif delta.path == "steps.length":
            left_n, right_n = delta.left_value, delta.right_value
            if left_n < right_n:
                left_pros.append(f"More concise ({left_n} steps vs {right_n})")
            elif right_n < left_n:
                right_pros.append(f"More concise ({right_n} steps vs {left_n})")

    return ProsCons(
        left_pros=left_pros,
        left_cons=left_cons,
        right_pros=right_pros,
        right_cons=right_cons,
    )


def _summary(left: Attempt, right: Attempt, deltas: Sequence[Delta], pros_cons: ProsCons) -> str:
    """The human-readable rollup (engram's `generateSummary`): identity line, the
    top deltas, and which side the mechanical pros/cons tally favors."""
    parts = [
        f"Comparing {left.arm} {left.id[:8]} ({left.status}) "
        f"vs {right.arm} {right.id[:8]} ({right.status})"
    ]
    if deltas:
        parts.append(f"Found {len(deltas)} differences:")
        parts.extend(f"  - {delta.description}" for delta in deltas[:3])
        if len(deltas) > 3:
            parts.append(f"  ... and {len(deltas) - 3} more")
    else:
        parts.append("Attempts are structurally similar")

    left_score = len(pros_cons.left_pros) - len(pros_cons.left_cons)
    right_score = len(pros_cons.right_pros) - len(pros_cons.right_cons)
    if left_score > right_score:
        parts.append(f"Left ({left.arm}) appears stronger (score: {left_score} vs {right_score})")
    elif right_score > left_score:
        parts.append(f"Right ({right.arm}) appears stronger (score: {right_score} vs {left_score})")
    else:
        parts.append(f"Attempts appear equally strong (score: {left_score})")
    return "\n".join(parts)
