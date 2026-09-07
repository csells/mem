"""mem-rk41.5 — synthetic tool-requiring world → WorkRecord + TaskBundle + lesson adapter.

The staging finding (mem-rk41.3): ``run_grid_3arm`` consumes real-rig ``TaskBundle``s
(rig clone + ftp_oracle + ``.mem/store.db`` keyed by ``work_id``), NOT frozen worlds,
so the tool-requiring synthetic corpus (mem-rk41.1, ``materialize_world(tool_requiring=
True)``) could not reach the grid. This is the missing seam: a pure-Python projection
that turns the tool-requiring sequences into the exact shapes the grid's
mechanism-fires gate reads — WorkRecords ``mem import-records`` ingests, lessons
``mem import-lessons`` attaches, and TaskBundles ``load_admitted_bundles`` loads.

The mechanism the offline gate must fire (``tier1_exact_signature_retrieval``,
mem-xe2p): each tool-requiring sequence becomes a closed WorkRecord carrying ONE
SUBJECT-AGNOSTIC ``apply_config`` staleness trace error. Every record carries the
byte-identical error, so ``mem`` computes the byte-identical failure signature across
tasks (``failureSignature`` = ``tool:normalizePath(file):line:errorClass``,
src/parse/recurrence.ts). Retrieving a later task's record (default trace trigger)
matches the earlier tasks at the exact-signature tier; the earlier task's lesson —
whose facts embed the CANONICAL signature ``mem retrieve`` reported — then rides along,
so the injected payload contains the held record's own query signature and
``signature_overlap`` > 0. That overlap is the covariate the pre-run gate thresholds.

Leak-safety (do NOT leak the authored answer into retrievable context):

* the staleness trace error is VALUE-FREE — its message names the failure MODE
  ("a stale configuration value was applied"), never the current or a superseded
  subject value, so the shared signature carries no answer;
* the lesson facts embed only the signature strings (also value-free) plus a
  value-free narrative;
* every agent-readable string this module emits (record title, bundle issue title,
  trace message, lesson fact) is mechanically re-scanned against the sequence's OWN
  authored current + superseded values (``metrics.scorers.states_value``, the grading
  contract) and raises on any hit.

ZFC: a deterministic projection of authored ground truth. No model call, no semantic
judgment, and — the parity rule — NO Python re-computation of the failure signature:
the signatures embedded in lessons are supplied by the caller, read verbatim from the
``mem retrieve`` envelope (``query_signatures`` / ``query_signatures_relaxed``), never
recomputed here. The one thing this module authors is the value-free error FIELDS;
``mem`` owns the signature.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from membench.bundle.replay import ReplayResult
from membench.metrics.scorers import states_value
from membench.schemas.bundle import BundleEnv, TaskBundle
from membench.schemas.sequence import BenchmarkSequence, ExpectedAction, SequenceStep

# The tool the tool-requiring goal variant demands (mem-31vl). Hard-pinned here rather
# than imported from the private ``enterprise_workflow._APPLY_TOOL``; a parity test
# (tests/test_toolreq_bundle_adapter.py) asserts the two stay equal so a rename in the
# materialiser can never silently desync the adapter's tool-requiring recognition.
APPLY_TOOL = "apply_config"

# The synthetic provenance namespace. It doubles as the ``rig`` — generated work has no
# real repository, and a single rig keeps every record inside one same-rig retrieval
# scope. (The WorkRecord schema has no ``origin`` field; ``rig`` is the marker that
# survives the ``mem import-records`` round-trip.)
SYNTHETIC_RIG = "synthetic"
TOOLREQ_LABEL = "toolreq-substrate"


def _synthetic_trace_ref(work_id: str) -> str:
    """The synthetic transcript ref. A record's ``trace.jsonl_path`` and its bundle's
    ``trace_ref`` MUST be byte-identical — retrieval resolves one against the other
    (``schemas/bundle.py``) — so both derive the string here instead of repeating the
    literal, which could silently desync and break resolution with no error."""
    return f"{SYNTHETIC_RIG}:{work_id}"


# THE subject-agnostic apply_config staleness failure. Byte-identical across every
# task so ``mem`` derives one shared failure signature; value-free so that signature
# leaks no answer. ``apply_config`` is not in ``CLASS_BY_TOOL`` (src/parse/
# recurrence.ts), so its error class is ``classFallback(message)`` — deterministic and
# still value-free. Keep the message digit-free and under 80 chars so the class is the
# whole message, unambiguous and untruncated.
_STALENESS_TOOL = APPLY_TOOL
_STALENESS_FILE = "config/apply_config.yaml"
_STALENESS_LINE = 1
_STALENESS_MESSAGE = (
    "applied a stale configuration value; supersession-aware current value required"
)

# The append-only lesson framing. ``subtitle``/``narrative`` are value-free; the
# reward-bearing content is the signature strings the caller injects into ``facts``.
_LESSON_SUBTITLE = "apply_config staleness recurrence"
_LESSON_CONCEPTS = ("problem-solution", "gotcha")
_SIGNATURE_FACT = "prior apply_config task recurred on failure signature {signature}"
_STALENESS_FACT = (
    "apply the supersession-aware current value; a stale value fails inside the tool "
    "argument, not the prose"
)

# Default lifecycle base and per-task stride. The base is a fixed literal (never a wall
# clock — the projection is deterministic); the stride guarantees strict ordering
# ``task_i.closed < task_{i+1}.started`` (closed at day 2i+1 < started at day 2i+2), so
# temporal leave-one-out admits earlier tasks as retrievable neighbours of later ones.
DEFAULT_BASE_STARTED = "2020-01-01T00:00:00Z"
_STRIDE_DAYS = 2
_ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


def staleness_error() -> dict[str, Any]:
    """A fresh copy of THE shared value-free apply_config staleness trace error (a new
    dict per call so a caller mutation cannot bleed across records)."""
    return {
        "tool": _STALENESS_TOOL,
        "severity": "error",
        "message": _STALENESS_MESSAGE,
        "file": _STALENESS_FILE,
        "line": _STALENESS_LINE,
    }


def _parse_iso(value: str) -> datetime:
    return datetime.strptime(value, _ISO_FMT).replace(tzinfo=UTC)


def _lifecycle(base_started: str, index: int) -> tuple[str, str]:
    """The ``(started, closed)`` ISO pair for the ``index``-th task, strictly ordered
    against its neighbours. Deterministic in ``(base_started, index)`` — no wall clock."""
    base = _parse_iso(base_started)
    started = base + timedelta(days=index * _STRIDE_DAYS)
    closed = base + timedelta(days=index * _STRIDE_DAYS + 1)
    return started.strftime(_ISO_FMT), closed.strftime(_ISO_FMT)


def _goal_step(seq: BenchmarkSequence) -> SequenceStep:
    """The sequence's goal step — the one carrying the outcome checks. Raises if the
    sequence has no goal step (a malformed sequence, not something to project)."""
    for step in reversed(seq.steps):
        if step.outcome_checks:
            return step
    raise ValueError(f"{seq.sequence_id}: no goal step with an outcome check to project")


def _apply_action(seq: BenchmarkSequence) -> ExpectedAction:
    """The goal's required ``apply_config`` action — proof the sequence is tool-requiring
    (mem-31vl). Raises if absent: this adapter is for tool-requiring worlds ONLY, and a
    text-answer sequence must fail loudly rather than be projected into a shape whose
    signature mechanism it cannot exercise."""
    for check in _goal_step(seq).outcome_checks:
        for action in check.requires_action:
            if action.tool == APPLY_TOOL:
                return action
    raise ValueError(
        f"{seq.sequence_id}: no required {APPLY_TOOL!r} action — this adapter needs a "
        "tool-requiring world (materialize_world(tool_requiring=True)); a text-answer "
        "sequence cannot fire the apply_config staleness signature"
    )


def _authored_values(seq: BenchmarkSequence) -> tuple[str, ...]:
    """The sequence's reward-bearing values — the current value the tool must apply and
    every superseded (forbidden) value — the answer no agent-readable synthetic string
    may reveal."""
    action = _apply_action(seq)
    values = tuple(dict.fromkeys([*action.arg_values, *action.forbidden_values]))
    # Defense-in-depth: the leak firewall is a no-op on an empty value set, so a producer
    # that ever emitted a value-free apply action would silently disarm it. The upstream
    # materialiser already guards this (enterprise_workflow: chain_current_value not None),
    # but the firewall the whole track rests on must not depend silently on another module.
    if not values:
        raise ValueError(
            f"{seq.sequence_id}: apply_config action has no authored values to protect; "
            "the leak firewall cannot be exercised on a value-free action"
        )
    return values


def _assert_no_value_leak(text: str, values: Iterable[str], *, where: str) -> None:
    """Raise if ``text`` states any authored answer value as a standalone token (the
    ``states_value`` grading contract — word-boundary matched, so ``v2`` never matches
    inside ``checkout_v2``). The mechanical firewall the whole track's validity rests on."""
    leaked = [value for value in values if states_value(text, value)]
    if leaked:
        raise ValueError(f"{where} leaks authored answer value(s) {sorted(leaked)}: {text!r}")


def sequence_records(
    sequences: Sequence[BenchmarkSequence],
    *,
    base_started: str = DEFAULT_BASE_STARTED,
) -> list[dict[str, Any]]:
    """Project each tool-requiring sequence into a closed WorkRecord (the
    ``mem import-records`` JSON shape, validated against ``src/schemas/workrecord.ts``).

    Every record carries THE shared value-free apply_config staleness trace error, so
    ``mem`` derives one shared failure signature across tasks (the exact-signature
    retrieval lever). Lifecycles are strictly ordered so temporal LOO admits earlier
    tasks as retrievable neighbours; ``links`` are empty so the tasks are independent,
    non-sibling (no convoy/supersedes exclusion between them)."""
    records: list[dict[str, Any]] = []
    for index, seq in enumerate(sequences):
        values = _authored_values(seq)  # also asserts the sequence is tool-requiring
        started, closed = _lifecycle(base_started, index)
        _assert_no_value_leak(seq.title, values, where=f"{seq.sequence_id} record.title")
        error = staleness_error()
        _assert_no_value_leak(
            str(error["message"]), values, where=f"{seq.sequence_id} trace.error.message"
        )
        records.append(
            {
                "work_id": seq.sequence_id,
                "rig": SYNTHETIC_RIG,
                "title": seq.title,
                "labels": [TOOLREQ_LABEL, SYNTHETIC_RIG],
                "lifecycle": {
                    "created": started,
                    "started": started,
                    "closed": closed,
                    "status": "closed",
                },
                # Empty links: independent, non-sibling tasks. The default-factory shape
                # the reader expects (deps/supersedes lists).
                "links": {"deps": [], "supersedes": []},
                "trace": {
                    "jsonl_path": _synthetic_trace_ref(seq.sequence_id),
                    "errors": [error],
                },
            }
        )
    return records


def sequence_bundles(sequences: Sequence[BenchmarkSequence]) -> list[TaskBundle]:
    """Project each tool-requiring sequence into a ``TaskBundle`` (the grid's eval object,
    ``load_admitted_bundles`` loads it by ``work_id``).

    ``work_id`` is the sequence id (== the WorkRecord's, so ``mem retrieve`` resolves it);
    ``issue_title`` is the goal's user request (leak-asserted); the output is an empty
    ``ReplayResult`` and the env is a synthetic placeholder — this offline gate exercises
    only the retrieval/signature mechanism, never a checkout or a replay. ``loo_excluded``
    is self only: independent tasks have no convoy/supersedes siblings to add."""
    bundles: list[TaskBundle] = []
    for seq in sequences:
        values = _authored_values(seq)  # asserts tool-requiring
        issue_title = _goal_step(seq).user_request
        _assert_no_value_leak(issue_title, values, where=f"{seq.sequence_id} issue_title")
        bundles.append(
            TaskBundle(
                work_id=seq.sequence_id,
                rig=SYNTHETIC_RIG,
                issue_title=issue_title,
                issue_body="",
                trace_ref=_synthetic_trace_ref(seq.sequence_id),
                output=ReplayResult(calls=(), file_diffs=(), replay_success_rate=0.0),
                env=BundleEnv(
                    repo=SYNTHETIC_RIG,
                    base_commit="0" * 40,
                    base_image="synthetic:offline",
                ),
                loo_excluded_work_ids=(seq.sequence_id,),
            )
        )
    return bundles


def sequence_lessons(
    sequences: Sequence[BenchmarkSequence],
    signatures_by_work: Mapping[str, Sequence[str]],
    *,
    base_started: str = DEFAULT_BASE_STARTED,
) -> list[dict[str, Any]]:
    """Author one lesson per sequence (the ``mem import-lessons`` JSON shape), whose facts
    EMBED the canonical failure signatures the caller resolved from ``mem retrieve``.

    ``signatures_by_work`` maps ``work_id`` → the record's ``query_signatures`` +
    ``query_signatures_relaxed`` (verbatim from the retrieval envelope). Those strings are
    dropped into ``facts`` unchanged — no Python signature recompute (the trace_score
    parity rule) — so when a later task retrieves this record the injected payload
    contains the held record's own query signature and ``signature_overlap`` > 0.

    ``extracted_at`` is the record's own closed time (so the lesson shares its provenance
    clock). Every fact is leak-asserted against the sequence's authored values."""
    lessons: list[dict[str, Any]] = []
    for index, seq in enumerate(sequences):
        values = _authored_values(seq)  # asserts tool-requiring
        signatures = list(dict.fromkeys(signatures_by_work.get(seq.sequence_id, ())))
        if not signatures:
            raise ValueError(
                f"{seq.sequence_id}: no canonical signatures resolved from mem retrieve; "
                "the record must be imported and carry trace errors before authoring lessons"
            )
        facts = [_SIGNATURE_FACT.format(signature=signature) for signature in signatures]
        facts.append(_STALENESS_FACT)
        for fact in facts:
            _assert_no_value_leak(fact, values, where=f"{seq.sequence_id} lesson fact")
        _, closed = _lifecycle(base_started, index)
        lessons.append(
            {
                "work_id": seq.sequence_id,
                "extracted_at": closed,
                "payload": {
                    "subtitle": _LESSON_SUBTITLE,
                    "facts": facts,
                    "concepts": list(_LESSON_CONCEPTS),
                },
            }
        )
    return lessons
