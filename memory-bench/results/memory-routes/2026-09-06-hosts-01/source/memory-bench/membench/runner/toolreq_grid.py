"""mem-rk41.3 / .3.1 — the tool-requiring real-agent grid: the none/oracle/ours arms, their
verdict rule, and the measured inputs only this experiment has.

The pure half of ``scripts/grid_toolreq_realagent.py``, and it lives HERE rather than there for one
reason: ``scripts/`` is not type-checked — the CI mypy gate checks the tree but names ``^scripts/``
in ``[tool.mypy].exclude`` — and every resume-cache defect this code has shipped lived in an
untyped script. The driver keeps its argparse/main, its repo-root path constants, and its printing;
everything that decides what is EXECUTED, what is SCORED, and what may be REUSED is inside the type
checker — the ``ours``-store seeder included
(``toolreq_realagent.seed_ours_store_and_resolve_payloads``, mem-rsmq7).

The RESUME CACHE is not here — it is ``membench.runner.resume_cache``, shared with the builtin grid
(``toolreq_builtin_grid``). Read the cache invariant there; this module supplies only what is
specific to three arms: the arms themselves, the payload the ``ours`` arm retrieves, the prompts
those arms send, and the verdict their rows imply. What this module adds to the identity is the
``ours`` retrieval — the one measured input the shared core cannot know about.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Self

from pydantic import model_validator

from membench.runner.headless_agent import (
    CHANNELS,
    CellCalls,
    CellRecorder,
    Leg,
    MemoryChannel,
    render_cell_calls,
    resolve_cli_version,
    resolve_model,
)
from membench.runner.realagent_probe import ArmOutcome, probe_settings_fingerprint, run_arm
from membench.runner.resume_cache import (
    LEAK,
    SEPARATES,
    WEAK,
    BaseCachedResult,
    BaseCellOutcome,
    BaseRunIdentity,
    CachePlan,
    Cell,
    corpus_summary,
    digest,
    pending_tasks,
    render_verdict,
    run_cached_corpus,
)
from membench.runner.toolreq_realagent import ToolReqRealAgentTask, task_fingerprint
from membench.schemas.sequence import BenchmarkSequence

__all__ = [
    "ARMS",
    "CHANNELS",
    "EXECUTION_PROTOCOL",
    "KILL",
    "LEAK",
    "NONE_CHANNEL",
    "SEPARATES",
    "SUMMARY_NAME",
    "WEAK",
    "CachedResult",
    "CellOutcome",
    "PlannedCell",
    "RunIdentity",
    "SeedFn",
    "arm_memories",
    "classify_channels",
    "evaluate_task",
    "expected_cells",
    "payload_fingerprint",
    "planned_calls",
    "planned_cells",
    "remaining_tasks",
    "run_corpus",
    "task_verdict",
    "worst_case_calls_per_task",
    "worst_case_paid_call_count",
]

ARMS = ("none", "oracle", "ours")

# The run summary, written into the SAME directory as the per-task `<work_id>.json` results —
# hence a name the tasks are not allowed to claim (resume_cache.assert_usable_work_ids).
SUMMARY_NAME = "summary-toolreq-realagent.json"

# The executing/scoring CODE this grid's cached cells were measured under
# (BaseRunIdentity.protocol) — what MOVES A RESULT while every fingerprint stays identical: the
# stream-json parser, `score_goal_action`, DEFAULT_TIMEOUT_S, `simulated_runner` (which decides
# the ENTIRE dry-run measurement — free runs only, since `dry_run` is itself in the identity),
# and `realagent_probe`'s sandbox construction — its ancestor guard (`sandbox.paid_sandbox`)
# decides what agent context the "neutral" cwd auto-loads, which moves a result while every
# fingerprint stays identical (mem-rx11w).
# NOT here, because `invocation_fingerprint` now carries them: the prompts, --allowedTools, --model,
# --strict-mcp-config, and which cells run at all; nor the claude binary's version, which
# `cli_version` now carries (resolved off the instrument — a drift no one performs on purpose is not
# a thing to bump a constant for).
# BUMP on any change to the former that could move a result.
EXECUTION_PROTOCOL = 3

# Seeds the `ours` store + resolves its payload: (sequences, tasks, store_path, mem_bin)
# -> work_id -> (source work_id -> rendered payload). Injected by the caller, never defaulted:
# the real seeder (`toolreq_realagent.seed_ours_store_and_resolve_payloads`) needs a built
# `bin/mem`, whose repo-root path only the driver knows, and a hermetic test stubs it out (this
# codebase's Runner/RetrieveRunner injection convention — see spawn.Runner).
SeedFn = Callable[
    [Sequence[BenchmarkSequence], Sequence[ToolReqRealAgentTask], Path, str],
    dict[str, dict[str, str]],
]

# The one arm whose memory can legitimately come back EMPTY: `ours` retrieves, and temporal
# LOO admits no priors for the lifecycle-earliest task. See evaluate_task.
RETRIEVING_ARM = "ours"

# `none` surfaces empty memory, so `build_agent_prompt` renders the same bare-request prompt under
# every channel: the cell is channel-INVARIANT. It is therefore measured ONCE, under this canonical
# channel, and its row is relabeled into every other channel (evaluate_task). Paying it per channel
# would buy byte-identical `claude -p` calls and spend `none`'s sample twice for one measurement
# (mem-dg5fm). CHANNELS[0] is an arbitrary-but-fixed choice among channel-equivalent options; the
# byte-identity that makes it sound is locked by test_none_prompt_is_byte_identical_across_channels
# (the sibling builtin grid likewise uses CHANNELS[0] as its arbitrary preflight channel).
NONE_CHANNEL: MemoryChannel = CHANNELS[0]


def arm_memories(
    task: ToolReqRealAgentTask, ours_payload: Mapping[str, str] | None = None
) -> dict[str, dict[str, str]]:
    """The surfaced memory per arm, resolved once per task: nothing for ``none`` (the leak
    detector), the id-exact opaque ceiling for ``oracle``, the genuine ``mem retrieve``
    payload (rendered citation+lessons text, keyed by source work_id) for ``ours``."""
    memories = {
        "none": {},
        "oracle": dict(task.oracle_memory),
        "ours": dict(ours_payload or {}),
    }
    if set(memories) != set(ARMS):
        raise ValueError(f"arm memories {sorted(memories)} out of sync with ARMS {ARMS}")
    return memories


@dataclass(frozen=True)
class PlannedCell:
    """One ``(arm, channel)`` cell this task will actually RUN, and the ``claude -p`` leg it runs.

    A cell carries the call it will make — a ``headless_agent.Leg``, the type ``render_cell_calls``
    renders and the builtin grid's ``cell_legs`` returns — rather than a second copy of that call's
    fields. This grid's cell is ONE leg: the scored goal call under the arm's surfaced memory, with
    nothing to establish first (the fact, or its absence, IS the memory)."""

    arm: str
    channel: MemoryChannel
    leg: Leg


def planned_cells(
    task: ToolReqRealAgentTask, ours_payload: Mapping[str, str] | None = None
) -> list[PlannedCell]:
    """THE definition of what this grid executes: every cell that will spawn a ``claude -p``.

    ``evaluate_task`` runs it, ``planned_calls`` renders it, and ``_identity`` derives
    ``ours_retrieval_empty`` from it, so the three cannot disagree about what the grid does. The
    skip/dedup predicates below used to be written three ways in this file — once in the executor,
    once (as "never skip") in the fingerprint, once in the identity flag — the same defect shape,
    at a smaller scale, that this whole change exists to close.

    Two cells are handled off the plain per-channel grid — both because a channel is not a real
    variable for them, so paying per channel would buy byte-identical ``claude -p`` calls:

    * ``none`` is planned ONCE, under ``NONE_CHANNEL``. Its surfaced memory is always empty, so
      ``build_agent_prompt`` renders the bare request under EVERY channel and the cell is
      channel-invariant. ``evaluate_task`` measures it once and relabels the row into every channel;
      planning it per channel would spend ``none``'s sample twice for one measurement (mem-dg5fm).

    * ``ours`` when its retrieval came back EMPTY is planned NOT AT ALL — not an edge case but a
      guarantee for the lifecycle-earliest task, which temporal LOO leaves with no priors. An empty
      payload makes the ``ours`` prompt byte-identical to ``none``, so it is none-equivalent by
      construction (delta exactly 0); running it would spend ``repeats`` real ``claude -p`` turns
      per channel to re-measure ``none``, and would leave a flat ``(ours 0/N)`` unattributable — a
      retrieval miss reads exactly like memory-did-not-help. The ``none`` cell is relabeled instead
      (``evaluate_task``), and ``ours_retrieval_empty`` records which happened so the two causes
      stay distinguishable.

    So both are ABSENT from the plan they would otherwise fill, and hence from
    ``invocation_fingerprint``: the plan is the command lines that will be SENT, and those are not
    sent. Nothing is lost — an empty-payload run differs from a non-empty one in
    ``ours_payload_fingerprint`` AND ``ours_retrieval_empty``, both identity fields, and identity
    acceptance is a whole-object ``==``. NOTE that ``expected_cells`` still includes ``none`` and
    ``ours`` for every channel: the relabels produce the ROWS even though fewer calls were made, and
    the completeness validator requires them."""
    memories = arm_memories(task, ours_payload)

    def _goal(arm: str) -> Leg:
        return Leg("goal", task.goal_step, memories[arm])

    # `none` once (channel-invariant), every other arm per channel — `ours` only when its retrieval
    # surfaced something (else it is relabeled from `none`, never planned). The one dedup/skip site.
    return [
        PlannedCell(arm="none", channel=NONE_CHANNEL, leg=_goal("none")),
        *(
            PlannedCell(arm=arm, channel=channel, leg=_goal(arm))
            for channel in CHANNELS
            for arm in ARMS
            if arm != "none" and (memories[arm] or arm != RETRIEVING_ARM)
        ),
    ]


def evaluate_task(
    task: ToolReqRealAgentTask,
    *,
    repeats: int,
    model: str,
    dry_run: bool,
    recorder: CellRecorder,
    ours_payload: Mapping[str, str] | None = None,
) -> list[CellOutcome]:
    """Run every planned cell for one task and hand back the rows they scored. The invocations are
    recorded THROUGH the ``recorder`` — ``run_cached_corpus`` owns it and checks the recording
    against this run's identity before it will publish (``resume_cache.run_cached_corpus``); this
    function never returns the invocations, so it cannot hand back a value that merely agrees with
    the plan.

    The plan is ITERATED ONCE, never re-indexed or re-filtered: every cell in it is run, in plan
    order, with no second skip predicate to keep in step with ``planned_cells``'. Every cell the
    plan OMITS — the channel-invariant ``none`` under each non-canonical channel, the never-run
    empty-retrieval ``ours`` — is an empty-memory cell, so all are FILLED below from the single
    canonical ``none`` row by one relabel: each contributes a ROW but no invocation, exactly what
    it did."""
    plan = planned_cells(task, ours_payload)
    by_channel: dict[MemoryChannel, dict[str, ArmOutcome]] = {channel: {} for channel in CHANNELS}
    for cell in plan:
        by_channel[cell.channel][cell.arm] = run_arm(
            arm=cell.arm,
            step=cell.leg.step,
            memory=dict(cell.leg.memory),
            channel=cell.channel,
            repeats=repeats,
            model=model,
            dry_run=dry_run,
            current_values=task.current_opaque_values,
            recorder=recorder,
        )

    # Every arm the plan OMITS is an empty-memory cell — `none` under each non-canonical channel,
    # and `ours` on an empty retrieval — so it is none-equivalent by construction and was measured
    # once, as the single canonical `none` row. Fill each by relabeling that one row. Read it BEFORE
    # the loop; `replace` is non-mutating, so the reference stays valid as cells are filled.
    canonical = by_channel[NONE_CHANNEL]["none"]
    outcomes: list[ArmOutcome] = []
    for channel in CHANNELS:
        cells = by_channel[channel]
        for arm in ARMS:
            if arm not in cells:  # absent => empty memory => relabel the canonical `none` row
                cells[arm] = replace(canonical, arm=arm, channel=channel.value)
        # `ARMS` order, not plan order: the canonical row order the scorer and the summary read.
        outcomes.extend(cells[arm] for arm in ARMS)
    return _cells(outcomes)


# The verdict is decided by these two arms alone; every other ARMS member rides along as
# an informational suffix (see classify_channels).
_GATING_ARMS = ("none", "oracle")

# The verdict kind only THIS grid has; LEAK/SEPARATES/WEAK are the shared vocabulary imported from
# resume_cache, the owner corpus_summary counts them from. `classify_channels` returns one kind per
# channel and the summary COUNTS them; nothing derives a headline by matching substrings of the
# rendered line.
KILL = "KILL"


def classify_channels(outcomes: Sequence[Cell]) -> list[tuple[str, str, str]]:
    """The probe's per-channel verdict rule (valid again under opaque values), as one ladder:
    ``none`` passing means a leak; ``none`` 0 + ``oracle`` ceiling means the arms separate. Arms
    beyond ``_GATING_ARMS`` (today: ``ours``) never gate the call — each rides along as an
    informational suffix, because ``ours`` scoring near ``none`` is the expected substrate finding,
    not a failure of the grid.

    Kind and line leave the same branch (see ``BaseCachedResult.classify``), so the suffix loop
    below can grow an arm whose NAME contains "LEAK" without moving a single headline count."""
    by = {(o.arm, o.channel): o for o in outcomes}
    classified: list[tuple[str, str, str]] = []
    for channel in (c.value for c in CHANNELS):
        none_o = by.get(("none", channel))
        oracle_o = by.get(("oracle", channel))
        if none_o is None or oracle_o is None:
            continue
        runs = oracle_o.runs
        if none_o.passes > 0:
            kind = LEAK
            call = f"LEAK: none {none_o.passes}/{none_o.runs} — value reached the prompt"
        elif oracle_o.passes == runs and runs > 0:
            kind = SEPARATES
            call = f"SEPARATES: none 0/{runs}, oracle {oracle_o.passes}/{runs}"
        elif oracle_o.passes == 0:
            kind = KILL
            call = f"KILL: oracle ceiling 0/{runs} — no separation"
        else:
            kind = WEAK
            call = f"WEAK: none 0/{runs}, oracle {oracle_o.passes}/{runs} — add repeats"
        for arm in ARMS:
            if arm in _GATING_ARMS:
                continue
            extra = by.get((arm, channel))
            if extra is not None:
                call += f" ({arm} {extra.passes}/{extra.runs})"
        classified.append((channel, kind, call))
    return classified


def task_verdict(outcomes: Sequence[Cell]) -> str:
    """The human-readable verdict line, rendered from ``classify_channels``."""
    return render_verdict(classify_channels(outcomes))


def expected_cells() -> set[tuple[str, str]]:
    """The full (arm, channel) grid one task must cover to be scored as complete."""
    return {(arm, channel.value) for arm in ARMS for channel in CHANNELS}


def payload_fingerprint(ours_payload: Mapping[str, str]) -> str:
    """Identifies the ``ours`` arm's actual MEASURED INPUT — the text retrieval surfaced.

    ``task_fingerprint`` is task-LOCAL; this payload is not. It comes from CROSS-TASK retrieval
    over the whole seeded store, so it moves when a sibling sequence is added, when the corpus is
    regenerated, or when ``bin/mem``'s retrieval changes — none of which touch the queried task's
    own fields. Hashing the payload puts all three in the identity without modelling any of them.

    ORDER-PRESERVING, for the same reason ``oracle_memory`` is: ``resolve_payloads`` inserts in
    ``mem retrieve``'s RANK order and the prompt renders that order, so the same SET of lessons
    ranked differently is a different prompt and must miss."""
    return digest(list(ours_payload.items()))


def planned_calls(
    task: ToolReqRealAgentTask, ours_payload: Mapping[str, str], *, model: str
) -> list[CellCalls]:
    """The ``claude -p`` cycles every planned cell WILL spawn — the plan ``CachePlan.lookup`` hashes
    into ``invocation_fingerprint``, and ``run_cached_corpus`` checks the recorded invocations
    against.

    Rendered from ``planned_cells`` through ``headless_agent.render_cell_calls`` — the same cells
    ``evaluate_task`` runs, through the same rendering ``run_arm`` records off the CLI seam. This
    grid hands the cache the PLAN and never authors the fingerprint field itself: the seam digests
    this and refuses an identity that carries any other value (see
    ``resume_cache.CachePlan.lookup`` and ``BaseRunIdentity.invocation_fingerprint``, which argues
    why hashing the whole argv cannot be incomplete about the invocation). Building one is string
    assembly: FREE, no agent turn."""
    return [
        render_cell_calls(arm=cell.arm, channel=cell.channel, legs=[cell.leg], model=model)
        for cell in planned_cells(task, ours_payload)
    ]


# A non-empty `ours` payload the WORST-CASE cost disclosure prices against: it makes `ours` present
# in the plan for every channel (planned_cells keys ours' inclusion on payload truthiness), which is
# the most `claude -p` a task can spend. A module-private sentinel, never a real retrieval.
_WORST_CASE_OURS_PAYLOAD: Mapping[str, str] = {"_worst_case_retrieval": "present"}


def worst_case_calls_per_task(task: ToolReqRealAgentTask) -> int:
    """The most real ``claude -p`` calls one repeat of one task can spend across BOTH channels —
    DERIVED from ``planned_cells`` (one goal leg per cell), never a hand-written
    ``len(ARMS) * len(CHANNELS)`` that would re-count the deduped ``none`` cell twice. ``none`` is
    measured once (channel-invariant; mem-dg5fm), so this is 5 and not 6 for the current roster,
    and the moment the plan shape changes it moves with the plan rather than lying by a constant —
    the mem-swp43 / mem-663ga review precedent, on the sibling builtin grid's ``calls_per_repeat``.

    WORST case because ``ours`` with an empty retrieval is relabeled from ``none`` and spends
    nothing, so this prices every task as if ``ours`` retrieved (the ceiling). Over-disclosing the
    ceiling is the safe direction — and unlike the builtin grid's EXACT ``calls_per_repeat`` this is
    an upper bound, hence the name.

    The ceiling was once forced: "the pre-seed cost disclosure cannot yet know which tasks
    retrieve". That premise is GONE — since mem-u9nu2 the disclosure must seed and resolve payloads
    before it can price anything at all (the payload rides in ``RunIdentity``, so the miss set is
    unknowable without it), and ``planned_cells(task, real_payload)`` is then the exact count. So
    this is now a DEFERRAL, not an invariant: it costs a per-task over-report in the safe direction,
    on an axis (ours-retrieval) independent of the one mem-u9nu2 fixed (the cache miss set). Filed
    as mem-fjfaf rather than widened into that bead. Until then, an upper bound because it prices a
    sentinel payload, not because it could not price the real one."""
    return len(planned_cells(task, _WORST_CASE_OURS_PAYLOAD))


def worst_case_paid_call_count(tasks: Sequence[ToolReqRealAgentTask], *, repeats: int) -> int:
    """Worst-case total real ``claude -p`` calls the paid sweep makes across the whole corpus — the
    number a human authorizes money against (``grid_toolreq_realagent._print_go_command``). Summed
    per task off ``worst_case_calls_per_task``, never
    ``n_tasks * worst_case_calls_per_task(tasks[0])`` (which would bill every task at the first's
    shape); exact-summed for any corpus and moves with the plan. No separate ``len(CHANNELS)``
    factor — ``planned_cells`` already spans both channels."""
    return repeats * sum(worst_case_calls_per_task(task) for task in tasks)


class RunIdentity(BaseRunIdentity):
    """What a persisted cell was measured under. The shared knobs and fingerprints are
    ``BaseRunIdentity``'s — including ``settings_fingerprint``, which pins the
    ``CLAUDE_CONFIG_DIR`` this grid seeds each cell under (``realagent_probe.PROBE_SETTINGS``,
    native memory declared OFF), the field that closes mem-mv67o's ambient-``~/.claude`` cache
    collision. These three fields are the measured inputs only THIS grid has.

    ``ours_payload_fingerprint`` is the retrieval the ``ours`` arm actually surfaced — cross-task,
    so it moves when nothing about the queried task did (see ``payload_fingerprint``).

    ``ours_retrieval_empty`` is a first-class identity field, live-computed like the fingerprints,
    never carried forward from the file. It says whether the ``ours`` cell was measured at all or
    relabeled from ``none``, which makes it the denominator the headline is read through. A value
    outside the identity is not defended by the checks that surround it.

    ``arms`` pins the roster the grid was measured over."""

    arms: list[str]
    ours_payload_fingerprint: str
    ours_retrieval_empty: bool


# This grid's cells carry no field beyond the shared four — `ArmOutcome` is exactly
# (arm, channel, passes, runs) — so the base row IS the row, strict typing and `passes <= runs`
# bound included. Named for the readers that persist and assert against it.
CellOutcome = BaseCellOutcome


class CachedResult(BaseCachedResult[RunIdentity, CellOutcome]):
    """One task's persisted result. The complete-grid and verdict-is-derived invariants are the
    shared core's; the one below is this grid's, and it exists because ``ours_retrieval_empty`` is
    an identity field whose truth is also visible in the ROWS."""

    @classmethod
    def expected_cells(cls) -> set[tuple[str, str]]:
        return expected_cells()

    @classmethod
    def classify(cls, outcomes: Sequence[CellOutcome]) -> list[tuple[str, str, str]]:
        return classify_channels(outcomes)

    @model_validator(mode="after")
    def _empty_retrieval_flag_agrees_with_the_rows_filed_next_to_it(self) -> Self:
        """``ours_retrieval_empty`` asserts the ``ours`` cell was never run — it was relabeled from
        ``none`` (evaluate_task) and so is none-equal by construction. A record claiming the flag
        while carrying an ``ours`` row that DIFFERS from its channel's ``none`` row is
        self-contradictory: one of the two is fabricated.

        It stays TOTAL over its input — ``.get``, not ``[]`` — rather than depending on the
        completeness check having run first: a ``KeyError`` is not a ``ValidationError``, so on a
        truncated file it would sail past ``load_cached``'s handler and kill a PAID resume."""
        if not self.identity.ours_retrieval_empty:
            return self
        by_cell = {(cell.arm, cell.channel): cell for cell in self.outcomes}
        for channel in (c.value for c in CHANNELS):
            ours, none = by_cell.get((RETRIEVING_ARM, channel)), by_cell.get(("none", channel))
            if ours is None or none is None:
                continue
            if (ours.passes, ours.runs) != (none.passes, none.runs):
                raise ValueError(
                    f"[{channel}] ours_retrieval_empty claims `ours` was never run, but its "
                    f"row {ours.passes}/{ours.runs} differs from `none` {none.passes}/{none.runs}"
                )
        return self


def _cells(outcomes: Sequence[ArmOutcome]) -> list[CellOutcome]:
    """The measured rows as persisted ones — the parse boundary crossed in the WRITE direction, so
    a row this grid could not have loaded is a row it cannot publish either."""
    return [CellOutcome(**asdict(outcome)) for outcome in outcomes]


def _identity(
    task: ToolReqRealAgentTask,
    ours_payload: Mapping[str, str],
    *,
    repeats: int,
    resolved_model: str,
    cli_version: str,
    dry_run: bool,
    invocation_fingerprint: str,
) -> RunIdentity:
    """The cache identity for one task (see ``RunIdentity`` / ``BaseRunIdentity``).

    ``invocation_fingerprint`` is not computed here — ``resume_cache.CachePlan.lookup`` derives it
    from ``planned_calls`` and hands it in, and refuses an identity that carries any other value. So
    the grid cannot author the field by a route of its own; it passes through the one the seam owns.

    The three payload-derived fields are bound from ONE payload object, not three lookups of it:
    they must describe the same retrieval or they describe nothing, and a fourth such field added
    later must inherit that by construction rather than by everyone remembering the same default.

    ``ours_retrieval_empty`` is read off the PLAN, not recomputed as ``not ours_payload``. It
    means "the ``ours`` cell was never run", and the plan is what decides that — asserting it
    from a second expression is how the flag and the executor come to disagree about the very run
    the flag is the denominator for."""
    planned = planned_cells(task, ours_payload)
    return RunIdentity(
        repeats=repeats,
        dry_run=dry_run,
        model=resolved_model,
        cli_version=cli_version,
        arms=list(ARMS),
        protocol=EXECUTION_PROTOCOL,
        task_fingerprint=task_fingerprint(task),
        invocation_fingerprint=invocation_fingerprint,
        settings_fingerprint=probe_settings_fingerprint(),
        ours_payload_fingerprint=payload_fingerprint(ours_payload),
        ours_retrieval_empty=not any(cell.arm == RETRIEVING_ARM for cell in planned),
    )


def cache_plan(
    tasks: Sequence[ToolReqRealAgentTask],
    sequences: Sequence[BenchmarkSequence],
    *,
    out_dir: Path,
    repeats: int,
    model: str,
    dry_run: bool,
    store_path: Path,
    mem_bin: str,
    seed_fn: SeedFn,
    version_fn: Callable[[], str] | None = None,
    resume: bool = True,
) -> tuple[
    CachePlan[ToolReqRealAgentTask, RunIdentity, CellOutcome],
    Mapping[str, Mapping[str, str]],
]:
    """This grid's ``resume_cache.CachePlan``, and the payloads it was built from — the one home
    for the miss decision's inputs, read by both ``run_corpus`` and ``remaining_tasks``. See
    ``CachePlan``.

    ``seed_fn`` runs BEFORE the cache is consulted and over the WHOLE corpus, every invocation, even
    when every task is cache-served: it is free, and the payload it resolves rides in the identity,
    so it has to be recomputed to know whether a cached cell is still current. That last clause is
    why the disclosure cannot skip it either — the miss set is not knowable without the payloads, so
    pricing a resume means seeding first, on a path that spends no tokens and never did.

    The payloads are RETURNED as well as closed over: ``run_corpus`` needs them again for
    ``evaluate``, and handing back the ones this plan was built from is what keeps the arm measured
    under the payload the identity names.

    ``model`` is RESOLVED here, never taken raw — through ``headless_agent.resolve_model``, the
    same rule the agent itself runs under, CALLED and never copied. ``run_corpus`` calls it too, for
    the model it hands ``evaluate``; that is the one rule applied twice to one input, not a second
    copy of it, and the two cannot disagree without moving the argv the plan hashes — which the
    write boundary refuses. ``RunIdentity`` refuses an unresolved model outright
    (``BaseRunIdentity``), so the schema is the backstop rather than a rule restated here.

    The claude BINARY is resolved the same way and in the same place — ONCE per run, so every task
    in one sweep is filed under one instrument rather than each racing an upgrade. Only for a PAID
    run: a dry run spawns no binary, and short-circuiting here is what keeps a free run runnable
    with no ``claude`` installed at all. It is resolved BEFORE seeding: a paid run that cannot name
    its binary is over, and there is no reason to build a store for it.

    ``version_fn`` overrides that resolver for a hermetic test; omitted, it is looked up on this
    module at call time, so ``monkeypatch.setattr(grid, "resolve_cli_version", ...)`` reaches it
    like every other double here. Why it defaults to the real thing where ``seed_fn`` does not is
    argued at ``headless_agent.resolve_cli_version``."""
    # Fail before seeding: a paid run that cannot name its binary is over.
    resolved_model = resolve_model(model)
    cli_version = "" if dry_run else (version_fn or resolve_cli_version)()
    ours_payloads = seed_fn(sequences, tasks, store_path, mem_bin)
    plan: CachePlan[ToolReqRealAgentTask, RunIdentity, CellOutcome] = CachePlan(
        out_dir=out_dir,
        result_cls=CachedResult,
        plan_of=lambda task: planned_calls(
            task, ours_payloads.get(task.work_id, {}), model=resolved_model
        ),
        identity_of=lambda task, invocation_fingerprint: _identity(
            task,
            ours_payloads.get(task.work_id, {}),
            repeats=repeats,
            resolved_model=resolved_model,
            cli_version=cli_version,
            dry_run=dry_run,
            invocation_fingerprint=invocation_fingerprint,
        ),
        summary_name=SUMMARY_NAME,
        resume=resume,
    )
    return plan, ours_payloads


def remaining_tasks(
    tasks: Sequence[ToolReqRealAgentTask],
    sequences: Sequence[BenchmarkSequence],
    *,
    out_dir: Path,
    repeats: int,
    model: str,
    mem_bin: str,
    seed_fn: SeedFn,
    version_fn: Callable[[], str] | None = None,
    resume: bool = True,
) -> list[ToolReqRealAgentTask]:
    """The tasks a PAID fire over ``out_dir`` would actually measure — the work that REMAINS, which
    the refuse-to-spend disclosure prices instead of the whole corpus (mem-u9nu2). Price it with
    ``worst_case_paid_call_count``, the same function the whole-corpus cost is summed by.

    NOT a cheap read, and the disclosure's shape follows from that: ``RunIdentity`` carries
    ``ours_payload_fingerprint``, so knowing whether a cached cell is current means resolving the
    payloads, which means seeding a store (``seed_ours_store_and_resolve_payloads``, which says so
    itself). Free of tokens and agents, not free of preconditions: it needs a built ``mem`` CLI.

    Takes NO ``store_path``, and seeds a THROWAWAY one instead — the reason is the whole
    character of the path this runs on. Pricing a fire is a READ
    (``resume_cache.pending_tasks``), and the refuse-to-spend gate is the surface an operator is
    meant to hit casually, repeatedly, to decide whether to spend at all. Handed the run's real
    ``--store``, this would ``_reset_store`` it — UNLINK ``store.db``/``-wal``/``-shm`` — before
    printing a price, and before the ``MemCliError``
    branch that reports it could not compute one. An operator who pointed ``--store`` at a store
    they cared about would lose it to a question, having answered nothing. So the question is not
    asked of their store.

    A throwaway answers it EXACTLY, and not approximately: the store is a derived artifact of the
    corpus and free to rebuild (``toolreq_realagent._reset_store``), the fire resets ``--store`` and
    reseeds it from these same ``sequences``/``tasks`` anyway, and the payload
    ``resolve_payloads`` renders is retrieval TEXT, carrying no trace of the path it was retrieved
    through. So the fingerprint this computes is the one the fire will file under. Pinned by
    ``test_pricing_a_fire_seeds_a_throwaway_store_and_gets_the_real_ones_payload``: were it ever
    false, the probe would price a fire under a payload the fire does not use and under-report by
    the whole corpus.

    ``dry_run=False`` is not a parameter: this answers what a PAID fire costs, and a free run's
    identity is a different one (``BaseRunIdentity.dry_run``) that no disclosure authorizes money
    against.

    RAISES ``HeadlessAgentError`` when the claude binary cannot be identified — then the paid
    identity cannot be constructed and there IS no honest answer (``BaseRunIdentity.cli_version``).
    What a driver should SAY about that is the shell's; that there is no answer is this module's.
    Every other failure propagates untouched — in particular the ``ValueError`` from
    ``CachePlan.lookup`` when an identity's fingerprint is not the plan's, the loudest structural
    defect this cache has, which must never be softened into a cost."""
    with tempfile.TemporaryDirectory(prefix="toolreq-price-") as throwaway:
        plan, _payloads = cache_plan(
            tasks,
            sequences,
            out_dir=out_dir,
            repeats=repeats,
            model=model,
            dry_run=False,
            store_path=Path(throwaway) / "store.db",
            mem_bin=mem_bin,
            seed_fn=seed_fn,
            version_fn=version_fn,
            resume=resume,
        )
        return pending_tasks(plan, tasks)


def run_corpus(
    tasks: Sequence[ToolReqRealAgentTask],
    sequences: Sequence[BenchmarkSequence],
    *,
    out_dir: Path,
    repeats: int,
    model: str,
    dry_run: bool,
    store_path: Path,
    mem_bin: str,
    seed_fn: SeedFn,
    version_fn: Callable[[], str] | None = None,
    resume: bool = True,
) -> dict[str, Any]:
    """Evaluate every task through the shared resume cache and shape this grid's summary.

    The cache identity — the resolved model, the binary, the seeded payloads — is ``cache_plan``'s,
    so this run and the disclosure that priced it read one answer."""
    resolved_model = resolve_model(model)
    plan, ours_payloads = cache_plan(
        tasks,
        sequences,
        out_dir=out_dir,
        repeats=repeats,
        model=model,
        dry_run=dry_run,
        store_path=store_path,
        mem_bin=mem_bin,
        seed_fn=seed_fn,
        version_fn=version_fn,
        resume=resume,
    )
    run = run_cached_corpus(
        plan,
        tasks,
        evaluate=lambda task, recorder: evaluate_task(
            task,
            repeats=repeats,
            model=resolved_model,
            dry_run=dry_run,
            recorder=recorder,
            ours_payload=ours_payloads.get(task.work_id, {}),
        ),
    )
    results = run.results
    return {
        **corpus_summary(tasks, run, dry_run=dry_run, repeats=repeats, n_channels=len(CHANNELS)),
        # Attribution, not trivia: for these tasks `ours` was never actually run (empty retrieval,
        # scored none-equivalent), so a flat ours-vs-none result over them means "retrieval
        # surfaced nothing", NOT "memory did not help".
        "ours_empty_retrieval": [r.work_id for r in results if r.identity.ours_retrieval_empty],
    }
