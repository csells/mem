"""Map real §8 ``Trace`` records into structural ``TaskFeatures`` (mem-28n5, mem-ovi.1).

Binding blocker for the STRUCTURAL axis of the realism metric (mem-ovi). The
synthetic corpus is reduced to a feature vector by
``features.features_from_sequence``; this module reduces the REAL corpus the SAME
way (``features.features_from_trace_steps``) so the cross-corpus KS distance in
``distance.structural_realism`` measures realism rather than a representation gap.

Two modeling decisions — the actual work, not glue — are resolved here, and a
fidelity finding is recorded for the run leg (mem-ovi.2).

Decision 1 — SESSION -> STEP segmentation (Fork B).
    A synthetic ``BenchmarkSequence`` is multi-step (one ``user_request`` per
    step); a real §8 ``Trace`` is one flat session (a single ``task_id`` /
    ``step_id`` with flat ``messages`` / ``tool_calls`` / ``memory_events``). Some
    segmentation rule is unavoidable — a structural vector cannot be computed at
    all without one — so the DEFAULT (``_turn_texts``) segments by USER TURN: one
    step per ``role == "user"`` message, in order. That makes ``n_steps`` the
    faithful analog of the synthetic per-request step count and
    ``task_text_length`` the same quantity (per-request text) on both sides. A
    session with no user messages falls back to its full message list, then to a
    single empty step. Like Fork A (corpus subset, ``mem_corpus.py``) and Fork C
    (``message_filter``, ``mem_corpus.py``), this default is injectable — every
    public function here takes a ``segmenter`` — so Stephanie's eventual call on
    an alternative segmentation does not require touching this module.

Decision 2 — MEMORY / TOOL feature fidelity.
    The §8 schema does NOT timestamp ``messages`` or ``tool_calls``, so a tool
    call or memory event cannot be attributed to the user turn that triggered it.
    Six of the seven features are nonetheless faithful because they are sums or
    set-unions over the whole session and so are invariant to how activity
    distributes across steps: ``n_steps`` (user turns), ``n_tool_calls``,
    ``tool_diversity``, ``n_memory_writes``, ``n_memory_reads``,
    ``task_text_length``. The seventh — ``dependency_depth`` — is NOT recoverable:
    it is a cross-step write->read chain, and without per-turn attribution it can
    only be fabricated or silently read as 0. It is therefore declared N/A on the
    real side (``RECOVERABLE_FEATURES`` excludes it — built from
    ``perfeature_reference``'s own signed-off ``MATCHABLE_FEATURES`` +
    ``MEMORY_OP_FEATURES`` split, which already excludes ``dependency_depth`` the
    same way; a caller still on the older full-vector ``distance.structural_realism``
    can restrict its own comparison to ``RECOVERABLE_FEATURES`` by hand).
    The actual memory-dependency depth that occurred in the session — over the
    timestamp-ordered memory events, a faithful but DIFFERENT-granularity measure
    — is exposed as a diagnostic by ``memory_dependency_depth`` so the finding is
    backed by data rather than asserted.

Tool-surface asymmetry (documented, accepted): the synthetic side counts
``available_tools`` (the offered surface) while the real side counts
``tool_calls[].name`` (the invoked surface), and the offered surface is >= the
invoked one. Both capture tool breadth; the asymmetry is reported, not hidden.

Source of real ``Trace`` records: this module is pure — its input is an iterable
of already-loaded ``Trace`` objects. Querying the live ``.mem`` substrate for the
real reference corpus, and parsing raw transcript JSONL into ``Trace`` objects,
is ``mem_corpus.py`` (the gated RUN leg, mem-ovi.2, stays out of this BUILD leg,
so the realism NUMBERS stay under the publication freeze).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from membench.realism.features import TaskFeatures, TraceStep, features_from_trace_steps
from membench.realism.perfeature_reference import MATCHABLE_FEATURES, MEMORY_OP_FEATURES
from membench.schemas.memory_event import MemoryEvent
from membench.schemas.trace import Trace

# ``dependency_depth`` is not recoverable from a flat, un-timestamped session (see
# the module docstring), so the real side reports only these six features. Built
# from ``perfeature_reference``'s own signed-off feature groups (rather than a
# second, independently-maintained "FEATURE_NAMES minus one" derivation) so both
# modules exclude dependency_depth the same way.
RECOVERABLE_FEATURES: tuple[str, ...] = MATCHABLE_FEATURES + MEMORY_OP_FEATURES

# Reduces a real Trace to its ordered step-defining turn texts (Fork B: SESSION ->
# STEP segmentation). Injectable so a caller can resolve Fork B without editing
# this module — mirrors how Fork A (corpus subset) and Fork C (message_filter,
# mem_corpus.py) are already parameterized. Defaults to ``_turn_texts``
# (segmentation by user turn, Decision 1 below).
#
# Contract: MUST return a non-empty list. ``trace_to_steps`` indexes the first
# element unconditionally to build the step carrying the session's tool/memory
# surface; ``_turn_texts`` upholds this (falls back to all messages, then to a
# single empty turn) but a caller-supplied segmenter that can return `[]` will
# raise IndexError.
Segmenter = Callable[[Trace], list[str]]


def _written_ids(event: MemoryEvent) -> tuple[str, ...]:
    """The ids this event wrote, taken from the recorded ``written_ids`` field.

    We trust the field rather than gating on the operation label: an UPDATE,
    CONSOLIDATE, or PROMOTE that both retrieves an old id and writes a new one
    legitimately contributes to BOTH writes and reads (it is the real analog of a
    synthetic step appearing in both ``expected_memory_writes`` and
    ``expected_memory_reads``). Trusting the fields keeps this pure counting, with
    no semantic op-classification (ZFC)."""
    return tuple(event.written_ids)


def _read_ids(event: MemoryEvent) -> tuple[str, ...]:
    """The ids this event retrieved, taken from the recorded ``retrieved_ids``
    field (see ``_written_ids`` for why the op label is not consulted)."""
    return tuple(event.retrieved_ids)


def _turn_texts(trace: Trace) -> list[str]:
    """The text of each step-defining turn, in order.

    A step is a user turn. If the session recorded no user messages we fall back
    to all of its messages (so ``n_steps`` still reflects the conversation length),
    and if it has no messages at all to a single empty turn (so a tool/memory-only
    session is one step, not zero)."""
    user = [m.content for m in trace.messages if m.role == "user"]
    if user:
        return user
    if trace.messages:
        return [m.content for m in trace.messages]
    return [""]


def trace_to_steps(trace: Trace, *, segmenter: Segmenter = _turn_texts) -> list[TraceStep]:
    """Reduce one real session into the shared ``TraceStep`` shape.

    One step per turn (``segmenter``, default ``_turn_texts``: Fork B resolved as
    user-turn segmentation, Decision 1 above). The session's full tool surface and
    memory ids — which the schema does not attribute to a particular turn — are
    consolidated onto the first step; because every structural feature that
    survives is a session sum/union, this placement does not change them, and
    ``dependency_depth`` (the one feature it would affect) is excluded as N/A."""
    texts = segmenter(trace)

    tools = tuple(call.name for call in trace.tool_calls)
    writes = tuple(mid for ev in trace.memory_events for mid in _written_ids(ev))
    reads = tuple(mid for ev in trace.memory_events for mid in _read_ids(ev))

    first = TraceStep(text=texts[0], tools=tools, memory_writes=writes, memory_reads=reads)
    rest = [TraceStep(text=text) for text in texts[1:]]
    return [first, *rest]


def features_from_trace(trace: Trace, *, segmenter: Segmenter = _turn_texts) -> TaskFeatures:
    """The structural feature vector for one real session.

    ``dependency_depth`` is present in the returned vector but is N/A by
    construction (always 0 — see the module docstring); callers compare on
    ``RECOVERABLE_FEATURES`` only."""
    return features_from_trace_steps(trace_to_steps(trace, segmenter=segmenter))


def load_real_features(
    traces: Iterable[Trace], *, segmenter: Segmenter = _turn_texts
) -> list[TaskFeatures]:
    """Reduce a real reference corpus to its structural feature vectors."""
    return [features_from_trace(trace, segmenter=segmenter) for trace in traces]


def memory_dependency_depth(trace: Trace) -> int:
    """Diagnostic: the longest write->read chain over the session's memory events,
    ordered by timestamp.

    This is the faithful memory-dependency depth that actually occurred, measured
    at MEMORY-EVENT granularity — a different unit than the synthetic step-granular
    ``dependency_depth``, which is why it is reported as a diagnostic and NOT
    folded into the cross-corpus structural vector. It lets the run leg show
    whether real sessions even contain memory dependency chains (the evidence
    behind the N/A finding) instead of asserting they do not."""
    events = sorted(trace.memory_events, key=lambda ev: ev.timestamp)
    steps = [TraceStep(memory_writes=_written_ids(ev), memory_reads=_read_ids(ev)) for ev in events]
    return features_from_trace_steps(steps).dependency_depth
