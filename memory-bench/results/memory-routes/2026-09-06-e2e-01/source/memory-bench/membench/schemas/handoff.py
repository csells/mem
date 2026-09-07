"""Handoff-task schema for the §11 interruption generator (mem-dsu).

Adopts the frozen-checkpoint matched-pair protocol of "Handoff Debt"
(arXiv 2606.02875; memo .gc/docs/mem-sxe.1-handoff-debt-investigation.md): at a
deterministic agent-behavioral interruption point the repository checkpoint and
the original task prompt are held FIXED, and the ONLY thing that varies across the
4 view arms is the injected predecessor-memory context. That isolation is what
makes a per-view effort delta a clean measurement of the memory view's value.

This schema is self-contained — it does not modify the ``sequence`` schema. A
handoff task is a different eval object from a ``BenchmarkSequence`` step: it is a
(frozen checkpoint, fixed task, one predecessor-context view) takeover, not a
sequenced write→read workload.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# --- the 3 deterministic interruption points (arXiv 2606.02875 §3) -----------------
# Agent-behavioral triggers, not wall-clock — so they reproduce across runs.
FIRST_SOURCE_EDIT = "first_source_edit"
FIRST_VALIDATION_RESULT = "first_validation_result"
FIRST_POST_FAILURE_EDIT = "first_post_failure_edit"
INTERRUPTION_POINTS: tuple[str, ...] = (
    FIRST_SOURCE_EDIT,
    FIRST_VALIDATION_RESULT,
    FIRST_POST_FAILURE_EDIT,
)

# --- predecessor event kinds (the authored trajectory's vocabulary) ----------------
SOURCE_EDIT = "source_edit"  # first non-test code change drives the first/post-failure points
TEST_EDIT = "test_edit"  # a test/fixture change — a changed file, but not a source edit
VALIDATION = "validation"  # a test/build/lint run; carries an ``outcome``
VALIDATION_PASS = "pass"
VALIDATION_FAIL = "fail"

# --- the 4 view arms, mapped onto our condition ladder -----------------------------
# repo-only = the ``none`` control (filesystem checkpoint only);
# raw-trace = the raw-trajectory control (mem-l23), the full predecessor event log;
# structured-notes = the ``ours`` structured-memory arm (the field schema below);
# summary-notes = the added compression-only 4th arm — same information as
# structured-notes but as unstructured prose, so the eval can separate the value of
# STRUCTURE from the value of COMPRESSION.
VIEW_TO_ARM: dict[str, str] = {
    "repo-only": "none",
    "raw-trace": "raw-trajectory",
    "summary-notes": "summary",
    "structured-notes": "ours",
}
# Deterministic view order (dict insertion order) so emission is byte-reproducible.
VIEWS: tuple[str, ...] = tuple(VIEW_TO_ARM)


class PredecessorEvent(BaseModel):
    """One record in the authored predecessor trajectory — the analogue of an
    OpenHands trajectory event (an action + its observation). ``kind`` is the action
    class (see the kind constants above), ``target`` is the file edited or command
    run, and ``outcome`` is the validation result (``pass``/``fail``), ``None`` for
    edits. Authored as Tier-0 ground truth; never model-generated in CI."""

    kind: str
    target: str
    # ``detail`` is the short human label (what the notes views carry); ``observation``
    # is the verbose captured output — the diff hunk of an edit, the full test/build
    # output of a validation — which ONLY the raw-trace view reproduces. Holding the
    # short detail in the notes and the bulky observation in raw-trace is what makes
    # raw-trace the largest view and the notes its compression.
    detail: str = ""
    observation: str = ""
    outcome: str | None = None


class StructuredNotes(BaseModel):
    """The structured-notes view's field schema (arXiv 2606.02875 App. C).

    The first three fields are DETERMINISTIC extracts of the frozen checkpoint
    prefix (changed files / last validation command / handoff state); the remaining
    five are the predecessor's understanding, filled here from authored
    predecessor-observable evidence (Tier-0). A local model may later enrich the
    surface text offline into a frozen, ``generator_version``-tagged fixture — but
    the structure and the grounded fields are always ours."""

    changed_files: tuple[str, ...]
    validation_cmd: str | None
    handoff_state: str
    problem_understanding: str
    work_done: str
    evidence: str
    uncertainty: str
    next_steps: str


class HandoffTask(BaseModel):
    """One generated takeover task: a fixed (checkpoint, prompt) under ONE view arm.

    The 4 views sharing a ``matched_key`` form a matched set — same interruption
    point and frozen checkpoint, differing only in ``view``/``arm``/
    ``injected_context``. ``matched_key`` is ``(source, point, checkpoint)``; the
    successor model is a run-time axis added when the task is executed, completing
    the paper's (point, successor, checkpoint) matching key."""

    task_id: str
    source_task_id: str
    task_prompt: str
    point: str
    checkpoint_id: str
    view: str
    arm: str
    injected_context: str = ""
    matched_key: str
    generator_version: str = Field(default="")
