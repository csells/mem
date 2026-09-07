"""§11 — the interruption (handoff-debt) generator (Tier 0, pure Python).

Adopts the "Handoff Debt" (arXiv 2606.02875) frozen-checkpoint matched-pair
protocol into the mem-lvp §11 generator (mem-dsu; memo
.gc/docs/mem-sxe.1-handoff-debt-investigation.md). At each of 3 deterministic
agent-behavioral interruption points the repository checkpoint and the original
task prompt are held FIXED and the only thing that varies across the 4 view arms
is the injected predecessor-memory context:

  1. detect_interruption_points : scan an authored predecessor trajectory for the
     first source edit / first post-edit validation result / first post-failure
     edit — agent-behavioral triggers (reproducible), not wall-clock.
  2. the 4-view renderer         : at a frozen checkpoint, render the predecessor
     context as repo-only (none) / raw-trace (raw-trajectory) / summary-notes
     (compression) / structured-notes (ours), the last two from the SAME extracted
     evidence so the eval can separate STRUCTURE from COMPRESSION.
  3. generate_handoff_tasks      : emit one HandoffTask per (point x view), all 4
     views of a point sharing a matched_key — a matched set for the paired-bootstrap
     / McNemar treatment in ``membench.handoff_efficiency``.

The trajectory bank is authored here as ground truth (Tier 0): given a seed the
emission is byte-reproducible, and CI never calls a model. A local model may later
enrich the surface prose of the notes views offline into a frozen,
``generator_version``-tagged fixture, but the events, the interruption points, and
the structured fields are always ours.
"""

from __future__ import annotations

from dataclasses import dataclass

from membench.schemas.handoff import (
    FIRST_POST_FAILURE_EDIT,
    FIRST_SOURCE_EDIT,
    FIRST_VALIDATION_RESULT,
    INTERRUPTION_POINTS,
    SOURCE_EDIT,
    TEST_EDIT,
    VALIDATION,
    VALIDATION_FAIL,
    VIEW_TO_ARM,
    VIEWS,
    HandoffTask,
    PredecessorEvent,
    StructuredNotes,
)

GENERATOR_VERSION = "interruption.v1"

_CHANGED_KINDS = frozenset({SOURCE_EDIT, TEST_EDIT})


@dataclass(frozen=True)
class PredecessorTrajectory:
    """An authored predecessor run (Tier-0 ground truth). ``events`` is the agent
    trajectory whose deterministic structure places the 3 interruption points; the
    three NL fields are the predecessor's understanding, used verbatim to fill the
    model-side fields of the structured/summary views from observable evidence."""

    task_id: str
    title: str
    task_prompt: str
    problem_understanding: str
    uncertainty: str
    next_steps: str
    events: tuple[PredecessorEvent, ...]


# A small bank of authored takeover trajectories. Each is a realistic SWE task whose
# trajectory contains all 3 interruption points: a first source edit, a failing
# post-edit validation, then a post-failure edit and a passing validation.
_BANK: tuple[PredecessorTrajectory, ...] = (
    PredecessorTrajectory(
        task_id="fix-auth-test",
        title="Fix the expired-token check",
        task_prompt=(
            "The auth service accepts tokens after they should have expired. Make "
            "validate_token reject an expired token and keep the existing tests green."
        ),
        problem_understanding=(
            "The token is accepted past its expiry; the expiry comparison in "
            "validate_token is wrong."
        ),
        uncertainty="Unsure whether other callers depend on the old lenient expiry.",
        next_steps="Re-run the full auth suite and check every caller of validate_token.",
        events=(
            PredecessorEvent(
                kind=SOURCE_EDIT,
                target="auth.py",
                detail="tighten the expiry check in validate_token",
                observation=(
                    "--- a/auth.py\n+++ b/auth.py\n"
                    "@@ def validate_token(token):\n"
                    "-    return token.exp >= now()\n"
                    "+    return token.exp > now()\n"
                    "  (1 file changed, 1 insertion(+), 1 deletion(-))"
                ),
            ),
            PredecessorEvent(
                kind=VALIDATION,
                target="pytest tests/test_auth.py",
                outcome=VALIDATION_FAIL,
                detail="1 failed: expired token still accepted",
                observation=(
                    "== test session starts ==\n"
                    "collected 12 items\n"
                    "tests/test_auth.py F...........  [100%]\n"
                    "=== FAILURES ===\n"
                    "___ test_expired_token_rejected ___\n"
                    "    assert validate_token(expired) is False\n"
                    "    AssertionError: token still accepted 300s after expiry\n"
                    "== 1 failed, 11 passed in 0.51s =="
                ),
            ),
            PredecessorEvent(
                kind=SOURCE_EDIT,
                target="auth.py",
                detail="compare against issued_at + ttl, not wall-clock now",
                observation=(
                    "--- a/auth.py\n+++ b/auth.py\n"
                    "@@ def validate_token(token):\n"
                    "-    return token.exp > now()\n"
                    "+    return token.issued_at + token.ttl < now()\n"
                    "  (1 file changed, 1 insertion(+), 1 deletion(-))"
                ),
            ),
            PredecessorEvent(
                kind=VALIDATION,
                target="pytest tests/test_auth.py",
                outcome="pass",
                detail="12 passed",
                observation=(
                    "== test session starts ==\n"
                    "collected 12 items\n"
                    "tests/test_auth.py ............  [100%]\n"
                    "== 12 passed in 0.44s =="
                ),
            ),
        ),
    ),
    PredecessorTrajectory(
        task_id="add-pagination",
        title="Paginate the orders list endpoint",
        task_prompt=(
            "GET /v2/orders returns every order. Add limit/offset pagination without "
            "breaking callers that omit the params."
        ),
        problem_understanding=(
            "The orders list endpoint is unbounded; it needs limit/offset pagination "
            "that still works when the params are omitted."
        ),
        uncertainty="Unclear if the default page size must match the client's expected 50.",
        next_steps="Confirm the default page size with the API contract; cover omitted params.",
        events=(
            PredecessorEvent(
                kind=SOURCE_EDIT,
                target="orders_api.py",
                detail="read limit/offset from query params",
                observation=(
                    "--- a/orders_api.py\n+++ b/orders_api.py\n"
                    "@@ def list_orders(request):\n"
                    "-    return Order.all()\n"
                    "+    limit = request.query['limit']\n"
                    "+    offset = request.query['offset']\n"
                    "+    return Order.all()[offset:offset + limit]\n"
                    "  (1 file changed, 3 insertions(+), 1 deletion(-))"
                ),
            ),
            PredecessorEvent(
                kind=VALIDATION,
                target="pytest tests/test_orders.py",
                outcome=VALIDATION_FAIL,
                detail="1 failed: KeyError 'offset' when param omitted",
                observation=(
                    "== test session starts ==\n"
                    "collected 9 items\n"
                    "tests/test_orders.py F........  [100%]\n"
                    "=== FAILURES ===\n"
                    "___ test_list_without_params ___\n"
                    "    response = client.get('/v2/orders')\n"
                    "    KeyError: 'offset'\n"
                    "== 1 failed, 8 passed in 0.33s =="
                ),
            ),
            PredecessorEvent(
                kind=SOURCE_EDIT,
                target="orders_api.py",
                detail="default offset to 0 and limit to the contract page size",
                observation=(
                    "--- a/orders_api.py\n+++ b/orders_api.py\n"
                    "@@ def list_orders(request):\n"
                    "-    limit = request.query['limit']\n"
                    "-    offset = request.query['offset']\n"
                    "+    limit = int(request.query.get('limit', 50))\n"
                    "+    offset = int(request.query.get('offset', 0))\n"
                    "  (1 file changed, 2 insertions(+), 2 deletions(-))"
                ),
            ),
            PredecessorEvent(
                kind=VALIDATION,
                target="pytest tests/test_orders.py",
                outcome="pass",
                detail="9 passed",
                observation=(
                    "== test session starts ==\n"
                    "collected 9 items\n"
                    "tests/test_orders.py .........  [100%]\n"
                    "== 9 passed in 0.29s =="
                ),
            ),
        ),
    ),
    PredecessorTrajectory(
        task_id="patch-race-condition",
        title="Guard the cache read-modify-write",
        task_prompt=(
            "Concurrent writers corrupt cache entries. Make the read-modify-write in "
            "the cache mutually exclusive without deadlocking the eviction path."
        ),
        problem_understanding=(
            "Concurrent writers corrupt a cache entry; the read-modify-write needs "
            "mutual exclusion."
        ),
        uncertainty="Not sure the lock also covers the eviction path's read-modify-write.",
        next_steps="Audit the eviction path for the same unguarded read-modify-write.",
        events=(
            PredecessorEvent(
                kind=SOURCE_EDIT,
                target="cache.py",
                detail="wrap the read-modify-write in a lock",
                observation=(
                    "--- a/cache.py\n+++ b/cache.py\n"
                    "@@ def set(self, key, value):\n"
                    "+    with self._lock:\n"
                    "         entry = self._read(key)\n"
                    "         self._write(key, merge(entry, value))\n"
                    "  (1 file changed, 1 insertion(+))"
                ),
            ),
            PredecessorEvent(
                kind=VALIDATION,
                target="pytest tests/test_cache.py -k concurrency",
                outcome=VALIDATION_FAIL,
                detail="1 failed: deadlock, lock acquired twice on evict",
                observation=(
                    "== test session starts ==\n"
                    "collected 7 items / 6 deselected / 1 selected\n"
                    "tests/test_cache.py F  [100%]\n"
                    "=== FAILURES ===\n"
                    "___ test_concurrent_writers ___\n"
                    "    deadlock: self._lock acquired twice via the eviction path\n"
                    "    Failed: Timeout >5.0s\n"
                    "== 1 failed, 6 passed in 5.12s =="
                ),
            ),
            PredecessorEvent(
                kind=SOURCE_EDIT,
                target="cache.py",
                detail="use a single re-entrant lock across get/set/evict",
                observation=(
                    "--- a/cache.py\n+++ b/cache.py\n"
                    "@@ class Cache:\n"
                    "-    self._lock = threading.Lock()\n"
                    "+    self._lock = threading.RLock()\n"
                    "  (1 file changed, 1 insertion(+), 1 deletion(-))"
                ),
            ),
            PredecessorEvent(
                kind=VALIDATION,
                target="pytest tests/test_cache.py -k concurrency",
                outcome="pass",
                detail="7 passed",
                observation=(
                    "== test session starts ==\n"
                    "collected 7 items / 6 deselected / 1 selected\n"
                    "tests/test_cache.py .  [100%]\n"
                    "== 1 passed, 6 deselected in 0.18s =="
                ),
            ),
        ),
    ),
)


def detect_interruption_points(
    events: tuple[PredecessorEvent, ...],
) -> dict[str, int]:
    """Map each interruption point that OCCURS to the index of the event that
    triggers it. A point that never occurs is omitted (the paper: only 31/75 tasks
    have a post-failure edit) — never imputed.

    - first source edit: the first ``source_edit``.
    - first validation result: the first ``validation`` AFTER a source edit (a
      post-edit test/build/lint, not a pre-edit baseline run).
    - first post-failure edit: the first ``source_edit`` after a failed validation."""
    points: dict[str, int] = {}
    seen_source = False
    seen_failure = False
    for i, event in enumerate(events):
        if event.kind == SOURCE_EDIT:
            points.setdefault(FIRST_SOURCE_EDIT, i)
            if seen_failure:
                points.setdefault(FIRST_POST_FAILURE_EDIT, i)
            seen_source = True
        elif event.kind == VALIDATION:
            if seen_source:
                points.setdefault(FIRST_VALIDATION_RESULT, i)
            if event.outcome == VALIDATION_FAIL:
                seen_failure = True
    return points


def trajectory_for_seed(seed: int) -> PredecessorTrajectory:
    """Select an authored trajectory deterministically and seed-namespace its id, so
    distinct seeds never share a task scope even when they reuse the same base run."""
    base = _BANK[seed % len(_BANK)]
    return PredecessorTrajectory(
        task_id=f"{base.task_id}-seed{seed}",
        title=base.title,
        task_prompt=base.task_prompt,
        problem_understanding=base.problem_understanding,
        uncertainty=base.uncertainty,
        next_steps=base.next_steps,
        events=base.events,
    )


def _source_edits(prefix: tuple[PredecessorEvent, ...]) -> list[PredecessorEvent]:
    return [e for e in prefix if e.kind == SOURCE_EDIT]


def _last_validation(prefix: tuple[PredecessorEvent, ...]) -> PredecessorEvent | None:
    validations = [e for e in prefix if e.kind == VALIDATION]
    return validations[-1] if validations else None


def _structured_notes_from_prefix(
    traj: PredecessorTrajectory, prefix: tuple[PredecessorEvent, ...]
) -> StructuredNotes:
    """Assemble the structured-notes schema from the frozen checkpoint prefix. The
    first three fields are deterministic extracts; the rest are the trajectory's
    authored understanding, grounded by the prefix's edits and last validation."""
    changed_files = tuple(sorted({e.target for e in prefix if e.kind in _CHANGED_KINDS}))
    last_validation = _last_validation(prefix)
    validation_cmd = last_validation.target if last_validation is not None else None

    if last_validation is None:
        handoff_state = "no validation run yet"
        evidence = "No validation has run since the edits."
    else:
        verdict = "FAILED" if last_validation.outcome == VALIDATION_FAIL else "passed"
        first_line = last_validation.detail.splitlines()[0] if last_validation.detail else ""
        handoff_state = f"last validation {verdict}: {last_validation.target}"
        evidence = f"ran `{last_validation.target}`: {verdict}" + (
            f" — {first_line}" if first_line else ""
        )

    work_done = "; ".join(f"edited {e.target} ({e.detail})" for e in _source_edits(prefix))

    return StructuredNotes(
        changed_files=changed_files,
        validation_cmd=validation_cmd,
        handoff_state=handoff_state,
        problem_understanding=traj.problem_understanding,
        work_done=work_done,
        evidence=evidence,
        uncertainty=traj.uncertainty,
        next_steps=traj.next_steps,
    )


def structured_notes_at(traj: PredecessorTrajectory, *, point: str) -> StructuredNotes:
    """The structured-notes view of ``traj`` at the frozen checkpoint of ``point``."""
    points = detect_interruption_points(traj.events)
    if point not in points:
        raise ValueError(f"trajectory {traj.task_id!r} has no interruption point {point!r}")
    prefix = traj.events[: points[point] + 1]
    return _structured_notes_from_prefix(traj, prefix)


def _render_raw_trace(prefix: tuple[PredecessorEvent, ...]) -> str:
    """The raw-trajectory view: the full predecessor event log verbatim, including
    every observation. This is the largest view (the paper's ~12x initial prompt) —
    it carries everything the notes views compress away."""
    blocks = ["Predecessor trajectory (raw event log):"]
    for i, event in enumerate(prefix):
        block = [
            f"--- event {i} ---",
            f"action: {event.kind}",
            f"target: {event.target}",
        ]
        if event.detail:
            block.append(f"detail: {event.detail}")
        if event.outcome is not None:
            block.append(f"outcome: validation {event.outcome}")
        if event.observation:
            block.append(f"observation:\n{event.observation}")
        blocks.append("\n".join(block))
    return "\n".join(blocks)


def _render_summary(notes: StructuredNotes) -> str:
    """The summary-notes view: the SAME extracted evidence as structured-notes, but
    as unstructured prose. Holding the information fixed and dropping the field
    structure is what isolates the value of structure from the value of compression."""
    changed = ", ".join(notes.changed_files) if notes.changed_files else "none"
    return (
        f"{notes.problem_understanding} Files changed so far: {changed}. "
        f"{notes.work_done}. {notes.evidence}. "
        f"Open question: {notes.uncertainty} Next: {notes.next_steps}"
    )


def _render_structured(notes: StructuredNotes) -> str:
    """The structured-notes (``ours``) view: the bounded, auditable field record."""
    changed = ", ".join(notes.changed_files) if notes.changed_files else "none"
    return "\n".join(
        [
            f"changed_files: {changed}",
            f"validation_cmd: {notes.validation_cmd or 'none'}",
            f"handoff_state: {notes.handoff_state}",
            f"problem_understanding: {notes.problem_understanding}",
            f"work_done: {notes.work_done}",
            f"evidence: {notes.evidence}",
            f"uncertainty: {notes.uncertainty}",
            f"next_steps: {notes.next_steps}",
        ]
    )


def _render_view(
    traj: PredecessorTrajectory,
    prefix: tuple[PredecessorEvent, ...],
    view: str,
) -> str:
    if view == "repo-only":
        return ""
    if view == "raw-trace":
        return _render_raw_trace(prefix)
    notes = _structured_notes_from_prefix(traj, prefix)
    if view == "summary-notes":
        return _render_summary(notes)
    if view == "structured-notes":
        return _render_structured(notes)
    raise ValueError(f"unknown view {view!r}")


def generate_handoff_tasks(*, seed: int) -> tuple[HandoffTask, ...]:
    """Emit the frozen-checkpoint matched-pair handoff tasks for ``seed``: one task
    per (interruption point x view). Same seed ⇒ byte-identical emission. The 4
    views of each point share a ``matched_key`` (source, point, checkpoint), so the
    efficiency scorer can pair them against the repo-only baseline."""
    traj = trajectory_for_seed(seed)
    points = detect_interruption_points(traj.events)

    tasks: list[HandoffTask] = []
    for point in INTERRUPTION_POINTS:
        if point not in points:
            continue
        idx = points[point]
        prefix = traj.events[: idx + 1]
        checkpoint_id = f"{traj.task_id}@{idx}"
        matched_key = f"{traj.task_id}::{point}::{checkpoint_id}"
        for view in VIEWS:
            tasks.append(
                HandoffTask(
                    task_id=f"{traj.task_id}-{point}-{view}",
                    source_task_id=traj.task_id,
                    task_prompt=traj.task_prompt,
                    point=point,
                    checkpoint_id=checkpoint_id,
                    view=view,
                    arm=VIEW_TO_ARM[view],
                    injected_context=_render_view(traj, prefix, view),
                    matched_key=matched_key,
                    generator_version=GENERATOR_VERSION,
                )
            )
    return tuple(tasks)
