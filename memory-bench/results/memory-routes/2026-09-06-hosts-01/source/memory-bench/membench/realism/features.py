"""Mechanical task-feature extraction for the realism metric (axis 1, structural).

A *task feature vector* is the comparable mechanical shape of one task: how many
steps, how many tool calls, how diverse the tool surface, how deep the
memory-dependency chain, how much memory it reads/writes, and how long its
request text is. These are the features whose synthetic-vs-real distributions the
structural axis compares (see ``distance.py``).

ZFC: feature extraction is pure mechanism — counting and longest-path arithmetic
over a task's steps, no semantic judgment. The single reducer ``_reduce`` is
shared by both the synthetic side (``features_from_sequence``) and the real side
(``features_from_trace_steps``) so the two corpora are measured the *same* way —
that shared definition is what makes a cross-corpus distance meaningful.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from membench.schemas.sequence import BenchmarkSequence

# The structural feature names, in a fixed order. Reported per-feature (raw
# vector, no opaque composite — §4.2 style) so a large distance on one axis is
# never hidden inside an aggregate.
FEATURE_NAMES: tuple[str, ...] = (
    "n_steps",
    "n_tool_calls",
    "tool_diversity",
    "dependency_depth",
    "n_memory_writes",
    "n_memory_reads",
    "task_text_length",
)


@dataclass(frozen=True)
class TraceStep:
    """One step of a task, reduced to the fields the structural axis counts.

    This is the common currency between the synthetic generator (a
    ``SequenceStep``) and a real trace (a session's tool log). A real-corpus
    loader maps its own record shape into a list of these; the synthetic side is
    mapped by ``features_from_sequence``. Keeping one reduced shape means the same
    counting code runs over both corpora."""

    tools: tuple[str, ...] = ()
    memory_writes: tuple[str, ...] = ()
    memory_reads: tuple[str, ...] = ()
    text: str = ""


@dataclass(frozen=True)
class TaskFeatures:
    """The mechanical feature vector for one task."""

    n_steps: int
    n_tool_calls: int
    tool_diversity: int
    dependency_depth: int
    n_memory_writes: int
    n_memory_reads: int
    task_text_length: int

    def value(self, feature: str) -> float:
        """The numeric value of one named feature (raises on an unknown name)."""
        if feature not in FEATURE_NAMES:
            raise ValueError(f"unknown feature: {feature!r}")
        return float(getattr(self, feature))


def _dependency_depth(steps: Sequence[TraceStep]) -> int:
    """Longest write→read chain across the steps.

    A step depends on every EARLIER step that wrote a memory id this step reads.
    ``depth[i]`` is 0 with no dependency and ``1 + max(depth of its writers)``
    otherwise; the result is the maximum depth over all steps. Only the earliest
    writer of an id is its source, matching the supersession model (v1→v2 are
    distinct ids, so a v2 read points at the step that wrote v2)."""
    first_writer: dict[str, int] = {}
    for idx, step in enumerate(steps):
        for write_id in step.memory_writes:
            first_writer.setdefault(write_id, idx)

    depth: list[int] = [0] * len(steps)
    for idx, step in enumerate(steps):
        writer_depths = [
            depth[first_writer[read_id]]
            for read_id in step.memory_reads
            if read_id in first_writer and first_writer[read_id] < idx
        ]
        if writer_depths:
            depth[idx] = 1 + max(writer_depths)
    return max(depth, default=0)


def _reduce(steps: Sequence[TraceStep]) -> TaskFeatures:
    """Count the structural features over a task's reduced steps."""
    all_tools = [tool for step in steps for tool in step.tools]
    return TaskFeatures(
        n_steps=len(steps),
        n_tool_calls=len(all_tools),
        tool_diversity=len(set(all_tools)),
        dependency_depth=_dependency_depth(steps),
        n_memory_writes=sum(len(step.memory_writes) for step in steps),
        n_memory_reads=sum(len(step.memory_reads) for step in steps),
        task_text_length=sum(len(step.text) for step in steps),
    )


def features_from_trace_steps(steps: Sequence[TraceStep]) -> TaskFeatures:
    """Extract the feature vector for one REAL task from its reduced trace steps.

    A real-corpus loader is responsible for mapping its record shape into
    ``TraceStep`` (which tools were called, which memory ids were read/written,
    the request text); this reducer then counts them identically to the synthetic
    side."""
    return _reduce(steps)


def features_from_sequence(seq: BenchmarkSequence) -> TaskFeatures:
    """Extract the feature vector for one SYNTHETIC task from its sequence.

    The sequence's authored fields map onto a reduced step: ``available_tools``
    is the tool surface, ``expected_memory_writes`` / ``expected_memory_reads``
    are the memory ids, and ``user_request`` is the text. Title and goal framing
    are synthetic-specific and excluded so ``task_text_length`` measures the same
    thing (per-step request text) on both corpora."""
    reduced = [
        TraceStep(
            tools=tuple(step.available_tools),
            memory_writes=tuple(step.expected_memory_writes.keys()),
            memory_reads=tuple(step.expected_memory_reads),
            text=step.user_request,
        )
        for step in seq.steps
    ]
    return _reduce(reduced)
