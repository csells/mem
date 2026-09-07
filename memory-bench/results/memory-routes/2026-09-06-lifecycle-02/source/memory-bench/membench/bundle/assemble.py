"""Bundle assembler + admission filter (mem-75t.7.2, plan §4 P1 + §9.3).

Assembles a `TaskBundle` from a Mapping-shaped WorkRecord (the same JSON shape
`validity.query_from_record` and `assess` read) plus its P0 `ReplayResult`. Three
invariants are enforced here, mechanically:

1. **Admission (plan §9.3 + the mem-75t.7.1 validation-derived gates,
   .gc/docs/mem-75t.7.1-replay-validation.md).** The trace-derived gold diff is "what
   the agent did", not "the correct fix" -- this corpus has no merged-PR/CI outcome
   linkage to vouch for it. The only structural evidence the work ended well is the
   record's own lifecycle + trace: admit ONLY a bead that is closed (status AND
   timestamp agree) AND whose trace tail is clean -- no unresolved trace_errors in
   the final segment, where "final segment" is each runner's LAST execution in
   transcript order (an early failure fixed by a later pass of the same runner is
   resolved; a failure nothing ran after is not). Further structural gates make the
   bundle a real, trustworthy eval object:

   - **not a shared trace** -- a transcript the corpus maps to OTHER work_ids is a
     multi-bead mega-session (the validation found one spanning 9 work_records);
     replaying the full stream against one bead's base mixes nine beads' edit
     streams. Per-bead segmentation is explicitly deferred -- rejection only.
   - **an env anchor** (repo + base_commit -- without it the bundle is not
     runnable);
   - **base does not predate the tree** -- a first-touch FILE_ABSENT Edit
     (`ReplayResult.base_predates_tree`) means the timestamp-approximate
     base_commit resolves to a tree OLDER than the session's;
   - **a non-empty gold diff** (without it there is no output leg; `ReplayResult`
     itself pins the empty-replay rate to 0.0 as "non-admittable");
   - **replay fidelity at oracle grade** -- ``adjusted_replay_success_rate`` (the
     out-of-repo auto-memory writes excluded from the denominator) at least
     `MIN_ADJUSTED_REPLAY_SUCCESS_RATE`: a partial replay is a gold diff with
     MISSING hunks, a corrupted oracle that is worse than no bundle.

   Every rejection is a typed `Rejection` with a `RejectionReason` -- never a
   silent drop, so batch admission stats are computable from the rejections.

2. **Issue-leg resolution.** Workflow-formula records (gc.kind=workflow) store the
   formula name (e.g. "mol-focus-review") in ``title``; the agent-facing task
   statement lives on the bead named by ``metadata["gc.var.issue"]``. The assembler
   resolves that bead from ``corpus`` and uses ITS title/body for the issue leg,
   keeping the record's work_id as the bundle anchor and recording the referenced
   id in ``issue_work_id``. This lives HERE, not in the batch script's record
   projection: the issue leg is a bundle invariant (leak-guarded, LOO-relevant,
   rejection-typed), and the batch layer is pure plumbing -- any other caller of
   `assemble_bundle` must get the same issue semantics for free. An unresolvable
   ref is the typed `ISSUE_REF_UNRESOLVED` rejection (the leg would otherwise be
   the formula name -- meaningless), never a silent fall-back.

3. **Leak guard.** The issue leg (title/body) is agent-readable text; the record's
   high-entropy outcome labels must not appear in it. Reuses
   `grading.leak_guard.assert_no_outcome_leak`, which RAISES -- a planted outcome
   label is a validity bug that must fail the run, not a rejection to tally. A
   resolved issue bead's text is scanned against BOTH records' outcome labels.

4. **LOO invariant (plan §9.3).** The bundle stores the work_ids any grid run must
   withhold from memory arms: the record itself, its undirected supersedes closure,
   its convoy/pr/branch siblings -- the exact `validity` exclusion semantics
   (same `query_from_record` boundary) -- PLUS the gc-metadata link group
   (convoy/issue beads and records sharing those refs; see `loo_excluded_ids`),
   frozen INTO the bundle so enforcement is mechanical rather than a per-run
   convention.

ZFC: pure mechanism -- structural field reads, set arithmetic, no IO, no model
calls. The pass/fail status this module keys on was produced upstream by the
deterministic trace parse (``parse/trace-parse.ts``), not judged here.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from membench.bundle.replay import ReplayResult
from membench.grading.leak_guard import assert_no_outcome_leak, outcome_labels
from membench.harbor.env_recon import DEFAULT_BASE_IMAGE, DEFAULT_BASE_IMAGES
from membench.schemas.bundle import BundleEnv, BundleVerification, TaskBundle
from membench.validity import (
    is_sibling,
    query_from_record,
    supersedes_closure,
    work_ref_from_record,
)

# Validation-derived admission threshold (.gc/docs/mem-75t.7.1-replay-validation.md):
# a partial replay means a gold diff with MISSING hunks -- a corrupted oracle, worse
# than no bundle. On the validation sample, >= 0.9 ADJUSTED admitted 3/8 beads at
# oracle grade; the 0.6-0.9 band stays context-only (trace-as-context rungs don't
# need an exact diff). Thresholded on `adjusted_replay_success_rate`, never the raw
# rate: OUTSIDE_WORK_DIR calls are out-of-repo by construction (see ReplayResult).
MIN_ADJUSTED_REPLAY_SUCCESS_RATE: float = 0.9


class RejectionReason(StrEnum):
    """Why a record was not admitted. Reasons are checked in this order; the first
    failure wins, so a rejection names the gate that actually fired. The replay-side
    gates are ordered most- to least-diagnostic: BASE_PREDATES_TREE explains WHY a
    diff came out empty (the zg4da/041jz shape), so it outranks EMPTY_OUTPUT, which
    outranks the generic LOW_REPLAY_FIDELITY."""

    NOT_CLOSED = "not_closed"
    NO_TRACE = "no_trace"
    DIRTY_TRACE_TAIL = "dirty_trace_tail"
    SHARED_TRACE = "shared_trace"
    ISSUE_REF_UNRESOLVED = "issue_ref_unresolved"
    MISSING_ENV = "missing_env"
    BASE_PREDATES_TREE = "base_predates_tree"
    EMPTY_OUTPUT = "empty_output"
    LOW_REPLAY_FIDELITY = "low_replay_fidelity"
    # Post-assembly guard (mem-75t.7.7): the issue bead fanned out to many sibling
    # work beads, so its text over-describes this bundle's narrow gold-diff slice and
    # the model judged the scopes mismatched. Checked AFTER the replay gates by
    # `fanout_scope_guard`, not inside `assemble_bundle`.
    ISSUE_FANOUT_SCOPE_MISMATCH = "issue_fanout_scope_mismatch"


@dataclass(frozen=True)
class Rejection:
    """A typed non-admission -- the anti-silent-drop contract. ``detail`` localizes
    the evidence (which runner failed, which anchor is missing)."""

    work_id: str
    reason: RejectionReason
    detail: str = ""


# The gc workflow-metadata key naming the bead that carries the REAL task statement.
# Workflow-formula records (gc.kind=workflow) store the formula name (e.g.
# "mol-focus-review") in their own ``title``; the agent-facing issue leg must come
# from the referenced bead instead.
ISSUE_REF_KEY = "gc.var.issue"

# The gc metadata link fields whose values are work-id refs to "the same work":
# the input-convoy bead and the underlying issue bead. The store's workflow records
# carry these in ``metadata`` -- ``links.convoy_id`` is null on every one of them --
# so the LOO sibling detection must key on the same values (mechanical same-value
# grouping, mirroring `validity.is_sibling`'s one-hop semantics).
_GC_LINK_KEYS: tuple[str, ...] = ("gc.input_convoy_id", "gc.var.convoy_id", ISSUE_REF_KEY)


def _mapping(record: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = record.get(key)
    return value if isinstance(value, Mapping) else {}


def _text(record: Mapping[str, Any], key: str) -> str:
    value = record.get(key)
    return value.strip() if isinstance(value, str) else ""


def _issue_body(record: Mapping[str, Any]) -> str:
    """The long-form spec text -- the same forward-shaped ``description``/``body``
    read as `assess._body_text` (current ingest carries only ``title``; the body
    rides in for free once the export carries it)."""
    return _text(record, "description") or _text(record, "body")


def _unresolved_tail_failures(trace: Mapping[str, Any]) -> list[str]:
    """The runners whose FINAL execution failed or still carried errors -- the
    trace's unresolved tail. Transcript order is the resolution evidence: a later
    pass of the same runner resolves its earlier failures; nothing after a failure
    leaves it unresolved.

    A trace with extracted ``errors`` but NO per-execution outcomes offers no
    resolution evidence at all -- conservative direction is dirty (reject), never
    admit-by-ignorance."""
    outcomes = trace.get("tool_outcomes")
    if not isinstance(outcomes, list) or not outcomes:
        return ["<unparsed>"] if trace.get("errors") else []
    final_by_runner: dict[str, Mapping[str, Any]] = {}
    for execution in outcomes:
        if not isinstance(execution, Mapping):
            raise ValueError(f"malformed trace execution (not a mapping): {execution!r}")
        final_by_runner[str(execution.get("runner") or "<unknown>")] = execution
    return sorted(
        runner
        for runner, execution in final_by_runner.items()
        if execution.get("status") == "fail" or execution.get("errors")
    )


def admit_record(record: Mapping[str, Any]) -> Rejection | None:
    """The plan-§9.3 admission filter over the record alone; None means admitted.

    Closed requires lifecycle AGREEMENT (status == "closed" AND a closed
    timestamp): the timestamp is what makes the record LOO-eligible for other
    queries, so a status-only close is treated as not closed."""
    work_id = str(record.get("work_id"))
    lifecycle = _mapping(record, "lifecycle")
    if lifecycle.get("status") != "closed" or not lifecycle.get("closed"):
        return Rejection(
            work_id=work_id,
            reason=RejectionReason.NOT_CLOSED,
            detail=f"status={lifecycle.get('status')!r}, closed={lifecycle.get('closed')!r}",
        )
    trace = _mapping(record, "trace")
    if not trace.get("jsonl_path"):
        return Rejection(
            work_id=work_id,
            reason=RejectionReason.NO_TRACE,
            detail="record carries no trace.jsonl_path",
        )
    failing = _unresolved_tail_failures(trace)
    if failing:
        return Rejection(
            work_id=work_id,
            reason=RejectionReason.DIRTY_TRACE_TAIL,
            detail=f"unresolved final-segment failures: {', '.join(failing)}",
        )
    return None


def _gc_link_ids(record: Mapping[str, Any]) -> frozenset[str]:
    """The work-id refs the record's gc metadata link fields carry (convoy bead,
    issue bead). Empty/non-string values are skipped."""
    metadata = _mapping(record, "metadata")
    return frozenset(
        value.strip()
        for key in _GC_LINK_KEYS
        if isinstance((value := metadata.get(key)), str) and value.strip()
    )


def _same_work_ids(record: Mapping[str, Any], corpus: Sequence[Mapping[str, Any]]) -> set[str]:
    """The corpus work_ids in ``record``'s gc-metadata same-work group: records
    whose key set ({work_id} + gc link ids) intersects the record's own. One-hop,
    undirected, pure same-value grouping -- this catches the convoy/issue beads
    themselves (their work_id IS the link value) and other sessions carrying the
    same convoy/issue refs, with no semantic judgment."""
    own_keys = _gc_link_ids(record) | {str(record.get("work_id"))}
    related: set[str] = set()
    for other in corpus:
        other_id = str(other.get("work_id"))
        if other_id in own_keys or _gc_link_ids(other) & own_keys:
            related.add(other_id)
    related.discard(str(record.get("work_id")))
    return related


def _resolve_issue_record(
    record: Mapping[str, Any], corpus: Sequence[Mapping[str, Any]]
) -> Mapping[str, Any] | Rejection | None:
    """The bead carrying the record's REAL task statement, when the record is a
    workflow-formula bead (``metadata["gc.var.issue"]``): the referenced record from
    ``corpus``, a typed `Rejection` when the corpus cannot resolve it (the issue leg
    would otherwise be the formula name -- meaningless to an agent), or None when the
    record carries no issue ref (its own title/body ARE the issue leg)."""
    metadata = _mapping(record, "metadata")
    raw = metadata.get(ISSUE_REF_KEY)
    issue_ref = raw.strip() if isinstance(raw, str) else ""
    if not issue_ref or issue_ref == str(record.get("work_id")):
        return None
    for other in corpus:
        if str(other.get("work_id")) == issue_ref:
            return other
    return Rejection(
        work_id=str(record.get("work_id")),
        reason=RejectionReason.ISSUE_REF_UNRESOLVED,
        detail=(
            f"metadata[{ISSUE_REF_KEY!r}] names {issue_ref!r}, which is not in the "
            "assembly corpus -- the issue leg would carry the workflow formula name "
            "instead of the task statement"
        ),
    )


def _shared_trace_work_ids(
    record: Mapping[str, Any], corpus: Sequence[Mapping[str, Any]]
) -> tuple[str, ...]:
    """The OTHER work_ids in ``corpus`` whose record points at this record's
    transcript -- non-empty means a multi-bead mega-session (mem-75t.7.1 found one
    transcript the store maps to 9 work_records). The record itself (same work_id)
    never counts as a sharer, and neither does its gc-metadata same-work group:
    a workflow bead and its OWN issue bead pointing at one transcript (the tkhkg
    shape) is one unit of work recorded on two beads, not a mixed edit stream."""
    own_id = str(record.get("work_id"))
    same_work = _same_work_ids(record, corpus)
    trace_ref = _text(_mapping(record, "trace"), "jsonl_path")
    return tuple(
        sorted(
            {
                str(other.get("work_id"))
                for other in corpus
                if str(other.get("work_id")) != own_id
                and str(other.get("work_id")) not in same_work
                and _text(_mapping(other, "trace"), "jsonl_path") == trace_ref
            }
        )
    )


def _env_from_record(record: Mapping[str, Any], base_images: Mapping[str, str]) -> BundleEnv | None:
    """The runnable env anchor, or None when the record carries none. ``outcome``
    (PR-authoritative base) is preferred over ``provenance`` (locally derived,
    commit-by-date approximate) -- the same precedence as `assess`'s env-anchor
    read."""
    for key in ("outcome", "provenance"):
        anchor = _mapping(record, key)
        repo, base_commit = anchor.get("repo"), anchor.get("base_commit")
        if repo and base_commit:
            rig = str(record["rig"])
            return BundleEnv(
                repo=str(repo),
                base_commit=str(base_commit),
                base_image=base_images.get(rig, DEFAULT_BASE_IMAGE),
            )
    return None


def loo_excluded_ids(
    record: Mapping[str, Any], corpus: Sequence[Mapping[str, Any]]
) -> tuple[str, ...]:
    """The bundle-level LOO exclusion set: the record itself + its undirected
    supersedes closure + its convoy/pr/branch siblings over ``corpus``, sorted.
    Exactly the `validity` same-work semantics, materialized as ids so any grid
    run can enforce the boundary without re-deriving it.

    The record's own ref is always part of the adjacency input: its
    ``links.supersedes`` edges must seed the closure even when ``corpus`` omits
    the record itself (the default ``corpus=()``).

    Extended beyond the `validity` projection with the gc METADATA link group
    (`_GC_LINK_KEYS`): the store's workflow records carry their convoy/issue refs
    in ``metadata``, never ``links.convoy_id``, so `work_ref_from_record` alone
    sees no siblings there. The extension lives HERE rather than in `validity`
    because that module deliberately mirrors the TS retrieval surface
    (`retrieve/exclusions.ts`) -- the bundle invariant may be wider, never the
    mirror. The link VALUES themselves are included unconditionally: they are
    work-id refs by the gc contract (the issue/convoy beads), and the set must
    name them even when the corpus omits them."""
    query = query_from_record(record)
    refs = [work_ref_from_record(record)] + [work_ref_from_record(r) for r in corpus]
    excluded = {query.work_id}
    excluded |= supersedes_closure(refs, query.work_id)
    excluded |= {ref.work_id for ref in refs if is_sibling(ref, query)}
    excluded |= _gc_link_ids(record)
    excluded |= _same_work_ids(record, corpus)
    return tuple(sorted(excluded))


def assemble_bundle(
    record: Mapping[str, Any],
    replay: ReplayResult,
    *,
    corpus: Sequence[Mapping[str, Any]] = (),
    base_images: Mapping[str, str] = DEFAULT_BASE_IMAGES,
) -> TaskBundle | Rejection:
    """Admit + assemble one record into a `TaskBundle`, or return the typed
    `Rejection`. Raises `OutcomeLeakError` on a planted outcome label in the
    issue text (a validity bug, not an admission outcome) and `ValueError` on a
    record too malformed to evaluate (no LOO boundary, malformed executions)."""
    rejection = admit_record(record)
    if rejection is not None:
        return rejection

    work_id = str(record["work_id"])
    sharers = _shared_trace_work_ids(record, corpus)
    if sharers:
        return Rejection(
            work_id=work_id,
            reason=RejectionReason.SHARED_TRACE,
            detail=(
                "transcript also maps to work_ids: "
                f"{', '.join(sharers)} -- replaying the full stream against one bead's "
                "base mixes edit streams; per-bead segmentation deferred"
            ),
        )
    issue_record = _resolve_issue_record(record, corpus)
    if isinstance(issue_record, Rejection):
        return issue_record
    env = _env_from_record(record, base_images)
    if env is None:
        return Rejection(
            work_id=work_id,
            reason=RejectionReason.MISSING_ENV,
            detail="no repo + base_commit anchor on outcome or provenance",
        )
    if replay.base_predates_tree:
        return Rejection(
            work_id=work_id,
            reason=RejectionReason.BASE_PREDATES_TREE,
            detail=(
                "first mutation is an Edit of file(s) absent at base: "
                f"{', '.join(replay.first_edit_absent_paths())} -- the "
                "timestamp-approximate base_commit predates the session tree"
            ),
        )
    if not replay.file_diffs:
        return Rejection(
            work_id=work_id,
            reason=RejectionReason.EMPTY_OUTPUT,
            detail="replay produced no gold diff -- nothing to verify against",
        )
    if replay.adjusted_replay_success_rate < MIN_ADJUSTED_REPLAY_SUCCESS_RATE:
        return Rejection(
            work_id=work_id,
            reason=RejectionReason.LOW_REPLAY_FIDELITY,
            detail=(
                f"adjusted replay success rate {replay.adjusted_replay_success_rate:.2f} "
                f"< {MIN_ADJUSTED_REPLAY_SUCCESS_RATE} -- a partial replay is a gold diff "
                "with missing hunks (corrupted oracle)"
            ),
        )

    # The issue leg: the referenced issue bead's text for workflow-formula records
    # (the record's own title is the formula name), the record's own otherwise. The
    # referenced text passes the SAME leak guard, against both records' outcome
    # labels -- the issue bead is the same work, so its identifiers leak too.
    issue_source = issue_record if issue_record is not None else record
    issue_title = _text(issue_source, "title")
    issue_body = _issue_body(issue_source)
    assert_no_outcome_leak(
        {"issue_title": issue_title, "issue_body": issue_body},
        outcome_labels(record) + outcome_labels(issue_source),
    )

    return TaskBundle(
        work_id=work_id,
        rig=str(record["rig"]),
        issue_title=issue_title,
        issue_body=issue_body,
        issue_work_id=(str(issue_record["work_id"]) if issue_record is not None else None),
        trace_ref=_text(_mapping(record, "trace"), "jsonl_path"),
        output=replay,
        env=env,
        loo_excluded_work_ids=loo_excluded_ids(record, corpus),
        verification=BundleVerification(),
    )


# ---------------------------------------------------------------------------
# Issue-fanout scope guard (mem-75t.7.7) -- the post-assembly admission gate the
# mem-75t.7.6 gate verdict demanded. The gate measured the failure mode directly:
# e29gw's issue bead spawned 31 sibling work beads, so the bundle's issue leg
# described far more work than its narrow gold diff covered, and both eval arms
# scored 0 against the wrong scope (the issue-fanout confound). The guard is two
# stages by the bead's ZFC split:
#   - MECHANICAL: `issue_fanout` counts the sibling work records sharing the issue
#     bead -- pure dependency-graph arithmetic. Fanout < `DEFAULT_MIN_FANOUT` (no
#     decomposition) needs no review; a bare count cannot reject, since a clean
#     bundle and a confound both sit at fanout 2 (gye8 vs 035r).
#   - SEMANTIC: whether the issue text actually matches the gold diff's scope is a
#     judgment, delegated to an injected `ScopeMatchJudge` exactly like the Tier-2
#     oracle curator -- no keyword/regex scope heuristic lives here. The concrete
#     `claude -p` judge is wired by the batch runner; this module ships only the
#     protocol + a deterministic stub, so it stays model-call-free and unit-testable.

# Fanout at or above this routes a candidate to the scope judge. 2 is the structural
# definition of "the issue spawned sibling work" (this record + >=1 other sharing the
# issue bead), not a tuned magic number; exposed so a batch can raise it.
DEFAULT_MIN_FANOUT: int = 2


def issue_fanout(record: Mapping[str, Any], corpus: Sequence[Mapping[str, Any]]) -> int:
    """How many corpus work records were decomposed from the SAME issue bead as
    ``record`` -- the breadth of the issue's fanout, counting ``record`` itself.

    Records sharing this record's ``metadata[gc.var.issue]`` value. 0 means the
    record names no issue bead (its own text is the issue leg -- no fanout); 1 means
    a 1:1 issue->work mapping; >= 2 means the issue spawned sibling work, so its text
    over-describes any single sibling's gold diff. Pure structural arithmetic."""
    metadata = _mapping(record, "metadata")
    raw = metadata.get(ISSUE_REF_KEY)
    issue_ref = raw.strip() if isinstance(raw, str) else ""
    if not issue_ref:
        return 0
    return sum(1 for other in corpus if _issue_ref_of(other) == issue_ref)


def _issue_ref_of(record: Mapping[str, Any]) -> str:
    raw = _mapping(record, "metadata").get(ISSUE_REF_KEY)
    return raw.strip() if isinstance(raw, str) else ""


@dataclass(frozen=True)
class ScopeVerdict:
    """One scope-match judgment for a high-fanout candidate. ``keep`` is the model's
    call (does the gold diff's scope match the issue's stated scope?); ``error`` set
    => the judge could not score, and the guard rejects conservatively (a high-fanout
    candidate the model cannot vouch for is the risky case)."""

    keep: bool
    rationale: str = ""
    error: str | None = None


class ScopeMatchJudge(Protocol):
    """Judges whether a bundle's gold diff matches the SCOPE of its (decomposed) issue
    text. The view is exactly ``(issue_title, issue_body, gold_files)`` -- the task
    statement and what the run actually touched; no eval outcome is passed, so the
    answer cannot leak. The concrete `claude -p` judge lives in the batch runner."""

    def judge(
        self, *, issue_title: str, issue_body: str, gold_files: Sequence[str]
    ) -> ScopeVerdict: ...


@dataclass(frozen=True)
class StubScopeJudge:
    """Deterministic, offline scope judge. The whole guard and every test run on this;
    supply exactly one of ``keep`` (a constant verdict) or ``fn`` (a pure function over
    the same view)."""

    keep: bool | None = None
    fn: Callable[[str, str, tuple[str, ...]], ScopeVerdict] | None = None

    def __post_init__(self) -> None:
        if (self.keep is None) == (self.fn is None):
            raise ValueError("StubScopeJudge needs exactly one of keep or fn")

    def judge(
        self, *, issue_title: str, issue_body: str, gold_files: Sequence[str]
    ) -> ScopeVerdict:
        if self.fn is not None:
            return self.fn(issue_title, issue_body, tuple(gold_files))
        assert self.keep is not None  # __post_init__ guarantees it
        return ScopeVerdict(keep=self.keep, rationale="stub")


@dataclass(frozen=True)
class FanoutDecision:
    """The guard's verdict for one assembled bundle, the per-bundle admission
    provenance the bead requires. ``rejection`` is None when admitted. ``fanout`` is
    the mechanical count; ``reviewed`` is whether the scope judge actually ran (False
    when fanout was below the review threshold, or no judge was supplied);
    ``rationale`` records WHY -- the no-silent-decision contract."""

    rejection: Rejection | None
    fanout: int
    reviewed: bool
    rationale: str

    @property
    def admitted(self) -> bool:
        return self.rejection is None


def fanout_scope_guard(
    bundle: TaskBundle,
    record: Mapping[str, Any],
    corpus: Sequence[Mapping[str, Any]],
    *,
    judge: ScopeMatchJudge | None = None,
    min_fanout: int = DEFAULT_MIN_FANOUT,
) -> FanoutDecision:
    """Guard an assembled ``bundle`` against issue-fanout scope mismatch.

    Mechanical fanout < ``min_fanout`` => admit unreviewed (no decomposition, no scope
    risk). Otherwise the scope judgment is delegated to ``judge``: keep => admitted,
    reject or judge-error => `ISSUE_FANOUT_SCOPE_MISMATCH` rejection. With no judge a
    high-fanout candidate is admitted but flagged unreviewed -- the guard never
    fabricates a scope verdict without the model."""
    fanout = issue_fanout(record, corpus)
    if fanout < min_fanout:
        return FanoutDecision(
            None, fanout, reviewed=False, rationale="no fanout (below review threshold)"
        )
    if judge is None:
        return FanoutDecision(
            None, fanout, reviewed=False, rationale=f"fanout={fanout} but no scope judge supplied"
        )

    gold_files = tuple(sorted(path for path, _ in bundle.output.file_diffs))
    verdict = judge.judge(
        issue_title=bundle.issue_title, issue_body=bundle.issue_body, gold_files=gold_files
    )
    if verdict.error is not None:
        return FanoutDecision(
            Rejection(
                work_id=bundle.work_id,
                reason=RejectionReason.ISSUE_FANOUT_SCOPE_MISMATCH,
                detail=f"fanout={fanout}; scope judge error: {verdict.error}",
            ),
            fanout,
            reviewed=True,
            rationale=f"judge error: {verdict.error}",
        )
    if verdict.keep:
        return FanoutDecision(None, fanout, reviewed=True, rationale=verdict.rationale)
    return FanoutDecision(
        Rejection(
            work_id=bundle.work_id,
            reason=RejectionReason.ISSUE_FANOUT_SCOPE_MISMATCH,
            detail=f"fanout={fanout}; scope mismatch: {verdict.rationale}",
        ),
        fanout,
        reviewed=True,
        rationale=verdict.rationale,
    )
