"""mem-rk41.3.2 / mem-mpxie — the tool-requiring BUILTIN grid: the native-memory arm's cells, its
verdict rule, and the measured inputs only this experiment has.

The sibling of ``toolreq_grid`` (none/oracle/ours), over the same frozen corpus and through the same
resume cache (``membench.runner.resume_cache`` — read the cache invariant there). It runs ONE arm,
``builtin``, under both memory-trust channels: two real ``claude -p`` calls per repeat (establish,
then a bare goal call) sharing one sandbox cwd + one ``CLAUDE_CONFIG_DIR``, so Claude Code's own
native memory is the sole continuity channel (``membench.runner.toolreq_builtin``).

It lives HERE, not in ``scripts/``, for the reason the 3-arm core does: ``scripts/`` is not
type-checked (the CI mypy gate checks the tree but names ``^scripts/`` in ``[tool.mypy].exclude``),
and every resume-cache defect this codebase has shipped lived in an untyped script. The driver
keeps argparse, the refuse-to-spend gate, the paid preflight and its printing; everything that
decides what is EXECUTED, what is SCORED, and what may be REUSED is in this module, inside the
type checker and on top of the shared cache.

What this grid adds beyond the shared core: a cell that carries its DIAGNOSTICS, not just its score
(``BuiltinCell``). ``engaged`` and ``leaked`` are what make a builtin ``passes`` interpretable at
all: a pass WITHOUT engagement is a leak (the sandbox let a Write scavenge a stale file), not a
builtin win, and zero engagement is the mechanism never firing. Their cross-field bounds are schema,
not caller discipline.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Self

from pydantic import Field, model_validator

from membench.runner.headless_agent import (
    CHANNELS,
    CellCalls,
    CellRecorder,
    HeadlessAgentError,
    resolve_cli_version,
    resolve_model,
)
from membench.runner.realagent_probe import ArmOutcome
from membench.runner.resume_cache import (
    LEAK,
    SEPARATES,
    WEAK,
    BaseCachedResult,
    BaseCellOutcome,
    BaseRunIdentity,
    CachePlan,
    corpus_summary,
    pending_tasks,
    render_verdict,
    run_cached_corpus,
)
from membench.runner.sandbox import SandboxContaminationError
from membench.runner.toolreq_builtin import (
    ARM,
    BuiltinDiagnostics,
    cell_calls,
    cell_legs,
    mechanism_fingerprint,
    run_builtin_arm,
)
from membench.runner.toolreq_realagent import ToolReqRealAgentTask, task_fingerprint

# This module's public surface, declared for the reason `toolreq_grid.__all__` is: the driver
# imports `LEAK` from here, but `LEAK` is `resume_cache`'s — it arrives by an implicit re-export
# that `--strict`'s `no_implicit_reexport` refuses. The declaration below is what makes the import
# legal, so `mypy --strict scripts/grid_toolreq_builtin.py` is clean today; delete `__all__` and it
# reports the error, even though CI's mypy gate excludes `scripts/`. Keep it declared: the day
# `scripts/` joins the checked surface — one deleted line in `[tool.mypy].exclude`, the direction
# this module's own docstring argues for, since every resume-cache defect this codebase shipped
# lived in an untyped script — an undeclared surface breaks that import.
__all__ = [
    "AGENT_ERROR",
    "ARM",
    "CHANNELS",
    "ENGAGED",
    "EXECUTION_PROTOCOL",
    "LEAK",
    "NOT_ENGAGED",
    "SEPARATES",
    "SUMMARY_NAME",
    "WEAK",
    "BuiltinCachedResult",
    "BuiltinCell",
    "PreflightHaltError",
    "calls_per_repeat",
    "cell_kind",
    "evaluate_task",
    "paid_call_count",
    "planned_calls",
    "preflight",
    "preflight_gate",
    "preflight_kind",
    "remaining_tasks",
    "run_corpus",
    "uniform_calls_per_repeat",
]

# The run summary, written into the SAME directory as the per-task `<work_id>.json` results —
# hence a name the tasks are not allowed to claim (resume_cache.assert_usable_work_ids).
SUMMARY_NAME = "summary-toolreq-builtin.json"

# The executing/scoring CODE this grid's cached cells were measured under
# (BaseRunIdentity.protocol) — what MOVES A RESULT while every fingerprint stays identical:
# `run_builtin_arm`'s cwd firewall (`wipe_cwd_contents`) and its ancestor guard
# (`sandbox.assert_neutral_ancestry`, run at mint AND after the wipe),
# `_memory_engaged` + NATIVE_MEMORY_GLOB, the stream-json parser, `score_goal_action`,
# DEFAULT_TIMEOUT_S, and `simulated_builtin_runner` (which decides the ENTIRE dry-run measurement —
# free runs only, since `dry_run` is itself in the identity).
# NOT here, because the identity now carries them: the prompts, --allowedTools, --model,
# --strict-mcp-config, and the legs' count and order (`invocation_fingerprint`); the seeded
# `autoMemoryEnabled` settings dict (`settings_fingerprint`); the claude binary's version
# (`cli_version`, resolved off the instrument).
# NOT here either, for a different reason: `preflight` / `preflight_kind`. They are a GATE on
# whether the sweep runs at all, not a step that executes or scores a cell — the preflight's own
# measurement is DISCARDED and never persisted (it runs at repeats=1 in a fresh TemporaryDirectory
# + CLAUDE_CONFIG_DIR and leaves nothing the sweep reads), so no cached cell moves when they change
# and a bump would only re-spend the whole paid grid for zero information.
# BUMP on any change to the former that could move a result.
EXECUTION_PROTOCOL = 3


def calls_per_repeat(task: ToolReqRealAgentTask) -> int:
    """Real ``claude -p`` calls one repeat of one cell makes — DERIVED from the legs the arm
    actually executes (``cell_legs``), never a hand-written constant modelling them. The
    refuse-to-spend gate discloses this number to the human authorizing the paid sweep; if it were a
    literal ``2``, adding a leg (which now correctly moves the argv and the fingerprint) would leave
    the disclosed cost under-reporting the real spend by a leg's share (mem-swp43 review reject)."""
    return len(cell_legs(task))


def paid_call_count(tasks: Sequence[ToolReqRealAgentTask], *, repeats: int) -> int:
    """Total real ``claude -p`` calls the paid sweep makes across the whole corpus and both
    channels.

    Summed per task off ``calls_per_repeat``, never modelled as ``n_tasks x
    calls_per_repeat(tasks[0])``: that form reads the FIRST task's leg count and bills every other
    task at it, under-reporting silently the moment one differs. This is the number a human
    authorizes real money against, so it is a sum, exact for any corpus, rather than a model that
    holds only while ``cell_legs`` returns what it returns today (mem-663ga)."""
    return len(CHANNELS) * repeats * sum(calls_per_repeat(task) for task in tasks)


def uniform_calls_per_repeat(tasks: Sequence[ToolReqRealAgentTask]) -> int:
    """The one ``calls_per_repeat`` every task in ``tasks`` shares — the per-repeat factor a cost
    factorization (``n_tasks x channel x repeat x per_repeat``) multiplies out to
    ``paid_call_count``'s summed total. Raises when the corpus is NON-UNIFORM: then no single factor
    reproduces that sum, so any factorization printed would misdescribe the number it explains.

    The single home for that guard. Both surfaces that factorize the cost — the refuse-to-spend
    disclosure (``_print_go_command``, the REFUSE path) and main()'s pre-sweep banner (the
    AUTHORIZED path, printed as the sweep starts spending) — read the factor from here, so the check
    lives once (mem-de455) rather than as a second copy free to drift from the first (mem-swp43).
    Callers refuse an empty corpus first; an empty ``tasks`` raises here too, but with this generic
    non-uniform message rather than a caller-specific one."""
    per_repeat_counts = {calls_per_repeat(task) for task in tasks}
    if len(per_repeat_counts) != 1:
        raise ValueError(
            f"tasks have non-uniform calls/repeat {sorted(per_repeat_counts)} — a single "
            "per-repeat factor cannot reproduce paid_call_count's summed total; show a per-task "
            "breakdown before spending."
        )
    (per_repeat,) = per_repeat_counts  # singleton, by the guard above
    return per_repeat


class BuiltinCell(BaseCellOutcome):
    """One persisted ``(builtin, channel)`` row: the score AND the engagement diagnostics that make
    the score interpretable.

    ``leaked`` is defined by the arm as the number of repeats that PASSED while NOT engaging
    (``run_builtin_arm``), and the four cross-field bounds below fall straight out of that
    definition. A row is a claim about what happened across ``runs`` repeats; these are the claims
    that cannot all be true at once:

    * ``engaged <= runs`` — the fact cannot have reached native memory in more repeats than ran.
    * ``leaked <= passes`` — a leak IS a pass, so it cannot outnumber the passes it is drawn from.
    * ``leaked <= runs - engaged`` — the same, from the other side: a leaked repeat is by definition
      one that did NOT engage, so the leaks cannot outnumber the non-engaged repeats.
    * ``leaked >= passes - engaged`` — the LOWER bound, and the one whose absence is a hole rather
      than a slack: by inclusion-exclusion, at least ``passes - engaged`` of the passing repeats
      cannot have been engaged ones. Without it a row can claim ``passes=2, engaged=0, leaked=0``,
      which is arithmetically impossible — both passes were leaks — and ``cell_kind`` then reports
      NOT-ENGAGED for a cell that actually LEAKED. That is a one-field edit to a ``<work_id>.json``
      that erases the most severe verdict the arm can produce (a pass the sandbox handed over, not
      a builtin win) and quietly moves the task from the summary's ``leaked`` list to its
      ``not_engaged`` list. The upper bounds do not catch it: they only ever say leaked is too BIG.

    Together they make the pass accounting checkable rather than merely reported. They do NOT make
    ``leaked`` derivable — with ``passes=1, engaged=1, runs=2`` the passing repeat may or may not be
    the engaged one — so the field carries real information and is bounded, not computed.
    """

    engaged: int = Field(ge=0)
    leaked: int = Field(ge=0)
    establish_tool_calls: int = Field(ge=0)
    establish_tool_names: list[str]

    @model_validator(mode="after")
    def _engagement_accounting_is_possible(self) -> Self:
        if self.engaged > self.runs:
            raise ValueError(f"{self.channel}: engaged {self.engaged} > runs {self.runs}")
        if self.leaked > self.passes:
            raise ValueError(
                f"{self.channel}: leaked {self.leaked} > passes {self.passes} — a leak is a PASS "
                "without engagement, so it cannot outnumber the passes"
            )
        if self.leaked > self.runs - self.engaged:
            raise ValueError(
                f"{self.channel}: leaked {self.leaked} > non-engaged repeats "
                f"{self.runs - self.engaged} — a leak is a pass WITHOUT engagement"
            )
        if self.leaked < self.passes - self.engaged:
            raise ValueError(
                f"{self.channel}: leaked {self.leaked} < passes {self.passes} - engaged "
                f"{self.engaged} — at least {self.passes - self.engaged} of the passing repeat(s) "
                "cannot have engaged native memory, and a pass without engagement IS a leak"
            )
        return self


def _cell(outcome: ArmOutcome, diagnostics: BuiltinDiagnostics) -> BuiltinCell:
    """One measured cell as a persisted row — the parse boundary crossed in the WRITE direction, so
    a row this grid could not have loaded is a row it cannot publish either.

    The arm reports ``runs`` on BOTH halves it returns; they are the same measurement, so a
    disagreement means one of the two is fabricated and the record must not be written."""
    if outcome.runs != diagnostics.runs:
        raise ValueError(
            f"{outcome.channel}: outcome measured {outcome.runs} run(s) but its diagnostics claim "
            f"{diagnostics.runs}"
        )
    return BuiltinCell(
        arm=outcome.arm,
        channel=outcome.channel,
        passes=outcome.passes,
        runs=outcome.runs,
        engaged=diagnostics.engaged,
        leaked=diagnostics.leaked,
        establish_tool_calls=diagnostics.establish_tool_calls,
        establish_tool_names=list(diagnostics.establish_tool_names),
    )


def evaluate_task(
    task: ToolReqRealAgentTask, *, repeats: int, model: str, dry_run: bool, recorder: CellRecorder
) -> list[BuiltinCell]:
    """Run every channel cell for one task and hand back the rows they scored. The invocations are
    recorded THROUGH the ``recorder`` — ``run_cached_corpus`` owns it and checks the recording
    against this run's identity before it will publish (``resume_cache.run_cached_corpus``); this
    function never returns the invocations."""
    outcomes: list[BuiltinCell] = []
    for channel in CHANNELS:
        outcome, diagnostics = run_builtin_arm(
            task, repeats=repeats, model=model, dry_run=dry_run, channel=channel, recorder=recorder
        )
        outcomes.append(_cell(outcome, diagnostics))
    return outcomes


# The verdict kind only THIS grid has; LEAK/SEPARATES/WEAK are the shared vocabulary imported from
# resume_cache, the owner corpus_summary counts them from. `cell_kind` returns one kind per cell and
# the summary counts them: `NOT-ENGAGED` is the kind the 3-arm grid has no room for, and it is the
# point of the arm.
NOT_ENGAGED = "NOT-ENGAGED"


def cell_kind(cell: BuiltinCell) -> tuple[str, str]:
    """Classify one cell into its (kind, display-line). Returning both from one branch ladder is
    what keeps the verdict (display) and the summary (counts) from desyncing — they read the same
    tuple rather than two chains that must agree.

    Priority: a LEAK (pass without engagement) outranks everything else — it means the shared
    sandbox let a Write scavenge a stale file, not that builtin memory worked. Otherwise: full
    engagement + full pass separates; zero engagement means the mechanism never fired (the
    mem-hb9o precedent); partial is WEAK."""
    runs = cell.runs  # >= 1 by schema: a 0-run cell cannot be constructed or loaded
    if cell.leaked:
        return LEAK, f"LEAK: {cell.leaked}/{runs} passed WITHOUT engaging native memory"
    if cell.passes == runs and cell.engaged == runs:
        return SEPARATES, f"SEPARATES: {cell.passes}/{runs} (engaged {cell.engaged}/{runs})"
    if cell.engaged == 0:
        return NOT_ENGAGED, f"NOT-ENGAGED: the fact never reached native memory (0/{runs})"
    return WEAK, f"WEAK: {cell.passes}/{runs} passed, engaged {cell.engaged}/{runs}"


def task_verdict(cells: Sequence[BuiltinCell]) -> str:
    """The human-readable verdict line, rendered from ``cell_kind``."""
    return render_verdict([(cell.channel, *cell_kind(cell)) for cell in cells])


# The two preflight-only kinds. `preflight_kind` otherwise reuses `cell_kind`'s LEAK / NOT-ENGAGED
# above: the gate and the grid diagnose the same two conditions, so they say them in ONE vocabulary
# rather than a second set of names that drift from the first. They are NOT summary kinds — the
# preflight measures one cell at repeats=1 and its measurement is discarded — so SEPARATES (a
# both-channel claim) and WEAK (a partial-repeat claim) have nothing to say about it.
ENGAGED = "ENGAGED"
AGENT_ERROR = "AGENT-ERROR"
# The sandbox's ancestor chain carried agent context, so the arm refused to mint a cwd it could not
# call neutral (`sandbox.assert_neutral_ancestry`). Its own kind, not folded into AGENT_ERROR: this
# fires BEFORE any `claude -p` runs, so "the real establish/goal call failed" would name a call that
# was never made, and the fix is the operator's TMPDIR rather than anything about the agent.
CONTAMINATED_SANDBOX = "CONTAMINATED-SANDBOX"


class PreflightHaltError(RuntimeError):
    """The preflight's refusal to authorize the paid sweep, carrying the DIAGNOSIS that produced it.

    Raised out of the ``before_first_spend`` hook, so it aborts the sweep before its first measured
    task (``resume_cache.run_cached_corpus``). It carries the ``(kind, line)`` and NOT the prose:
    what a human should DO about each kind is the shell's IO policy; which kind it IS is a decision
    about a measurement and lives here, under the type checker.

    A distinct type from ``HeadlessAgentError`` because the two want opposite counsel: a preflight
    halt has measured nothing, while a mid-sweep failure leaves finished tasks persisted and the run
    resumable."""

    def __init__(self, kind: str, line: str) -> None:
        super().__init__(line)
        self.kind = kind
        self.line = line


def preflight(task: ToolReqRealAgentTask, *, model: str) -> BuiltinDiagnostics:
    """One real establish+check cycle (repeats=1, so one cell's worth of legs —
    ``calls_per_repeat(task)`` calls) BEFORE the full paid sweep. Self-diagnoses "is builtin even
    enabled on this account" (mem-rk41.3.2 Q3 / mem-xe2p's enforce_mechanism_fires doctrine) instead
    of letting a disabled feature flag silently produce an uninterpretable all-null sweep.

    Its measurement is DISCARDED, deliberately and permanently: a repeats=1 measurement cannot
    satisfy a repeats=3 identity (``resume_cache`` bounds ``runs`` to the identity's
    ``repeats``), so persisting it as a cell would need a second identity and a second grid to
    hold it."""
    # A throwaway recorder: preflight's invocations are discarded (never fingerprinted), so its
    # recording is not read back — the recorder exists only because `run_builtin_arm` records
    # through one.
    _outcome, diagnostics = run_builtin_arm(
        task, repeats=1, model=model, dry_run=False, channel=CHANNELS[0], recorder=CellRecorder()
    )
    return diagnostics


def preflight_kind(diagnostics: BuiltinDiagnostics) -> tuple[str, str]:
    """Classify the preflight cycle into its (kind, display-line) — ``cell_kind``'s shape and for
    its reason: both halves out of ONE branch, so the kind the gate ACTS on and the line the human
    READS cannot desync.

    Same priority as ``cell_kind``, which is why this returns a kind rather than a bool: ``engaged
    == 0`` alone reads a LEAK as "the mechanism never fired", and the two want opposite responses
    from a human."""
    if diagnostics.leaked:
        return LEAK, (
            f"the goal leg PASSED without engaging native memory ({diagnostics.leaked}/"
            f"{diagnostics.runs}) — the sandbox handed the answer over"
        )
    if diagnostics.engaged == 0:
        return NOT_ENGAGED, (
            "the real establish call never persisted the fact to native memory (searched every "
            ".md under the config dir's memory/ — index AND topic files)"
        )
    return ENGAGED, f"native memory engaged ({diagnostics.engaged}/{diagnostics.runs})"


def preflight_gate(
    task: ToolReqRealAgentTask, *, model: str, announce: Callable[[str], None]
) -> Callable[[], None]:
    """The paid preflight as the hook ``run_cached_corpus`` fires immediately before the first task
    it will MEASURE (``resume_cache.before_first_spend``, whose contract this relies on).

    A hook rather than a step the driver runs ahead of the sweep, so the gate costs exactly what the
    sweep costs: a fully cache-served resume measures nothing, so there is nothing for a mechanism
    check to protect and it must not spend (mem-dblue).

    ``announce`` is injected for the same reason ``identity_of`` and ``evaluate`` are: what to SAY
    about a diagnosis is the shell's, what a diagnosis IS is this module's."""

    def _gate() -> None:
        announce("PREFLIGHT: one real establish+check cycle before the full sweep...")
        try:
            diagnostics = preflight(task, model=model)
        except SandboxContaminationError as exc:
            # Converted for the same reason as the agent error below, and the module's own rule
            # decides it: PreflightHaltError is "a distinct type from HeadlessAgentError because the
            # two want opposite counsel: a preflight halt has measured nothing". A refused sandbox
            # has measured nothing and spent nothing, so it wants the halt counsel, not the
            # mid-sweep one that points at a resume with no finished tasks to skip.
            raise PreflightHaltError(CONTAMINATED_SANDBOX, str(exc)) from exc
        except HeadlessAgentError as exc:
            # Converted, not propagated: raw, this would leave the hook as a HeadlessAgentError and
            # the driver would report a preflight failure — nothing measured, nothing to resume —
            # under its mid-sweep SWEEP HALT counsel, which points the human at a resume that has
            # no finished tasks to skip.
            raise PreflightHaltError(
                AGENT_ERROR, f"the real establish/goal call failed ({exc})"
            ) from exc
        kind, line = preflight_kind(diagnostics)
        if kind != ENGAGED:
            raise PreflightHaltError(kind, line)
        announce(f"PREFLIGHT OK: {line} on {task.work_id}; proceeding.")

    return _gate


def planned_calls(task: ToolReqRealAgentTask, *, model: str) -> list[CellCalls]:
    """The ``claude -p`` cycles every cell WILL spawn — the plan ``CachePlan.lookup`` hashes into
    ``invocation_fingerprint``, and ``run_cached_corpus`` checks the recorded invocations against.

    Rendered from ``toolreq_builtin.cell_legs`` through ``cell_calls``: the same legs
    ``run_builtin_arm`` executes, through the same rendering. So the plan cannot describe an
    invocation the arm does not make — it is not a copy of the arm's behaviour kept beside it, it is
    the arm's own plan. This grid hands the cache the plan and never authors the fingerprint field
    itself: the seam digests it and refuses an identity that carries any other value, and the write
    boundary then checks the RECORDED invocations against it (``resume_cache.run_cached_corpus``),
    which is what catches a leg the plan never declared."""
    return [cell_calls(task, channel, model=model) for channel in CHANNELS]


class BuiltinCachedResult(BaseCachedResult[BaseRunIdentity, BuiltinCell]):
    """One task's persisted builtin result. Every invariant is the shared core's; this class only
    tells it what the grid is and how its rows classify.

    The identity is plain ``BaseRunIdentity``: this grid seeds ``autoMemoryEnabled: True`` into each
    repeat's ``CLAUDE_CONFIG_DIR`` — the measured input the argv cannot carry — and that surface now
    rides in the shared ``settings_fingerprint`` (``_identity`` fills it from
    ``toolreq_builtin.mechanism_fingerprint``), the field this grid first shipped as its own
    ``mechanism_fingerprint`` and which was generalized onto the base once the none/oracle/ours grid
    needed the identical protection (mem-mv67o). Unlike ``ours``, ``builtin`` retrieves nothing from
    an external store, so there is no cross-task payload field to add — the subclass carries none.
    """

    @classmethod
    def expected_cells(cls) -> set[tuple[str, str]]:
        # One arm here, so the grid is exactly the channels.
        return {(ARM, channel.value) for channel in CHANNELS}

    @classmethod
    def classify(cls, outcomes: Sequence[BuiltinCell]) -> list[tuple[str, str, str]]:
        return [(cell.channel, *cell_kind(cell)) for cell in outcomes]


def _identity(
    task: ToolReqRealAgentTask,
    *,
    repeats: int,
    resolved_model: str,
    cli_version: str,
    dry_run: bool,
    invocation_fingerprint: str,
) -> BaseRunIdentity:
    """The cache identity for one task (see ``BaseRunIdentity``).

    ``invocation_fingerprint`` is not computed here — ``resume_cache.CachePlan.lookup`` derives it
    from ``planned_calls`` and hands it in, refusing an identity that carries any other value, so
    the grid cannot author the field by a route of its own.

    ``settings_fingerprint`` carries this grid's seeded ``CLAUDE_CONFIG_DIR`` surface — the
    ``autoMemoryEnabled: True`` dict ``mechanism_fingerprint`` hashes — a measured input the argv
    cannot carry (it reaches the agent through a FILE). It is the shared base field, filled here
    from the arm's own ``mechanism_fingerprint`` so the value is unchanged from when it was this
    grid's private ``mechanism_fingerprint`` field."""
    return BaseRunIdentity(
        repeats=repeats,
        dry_run=dry_run,
        model=resolved_model,
        cli_version=cli_version,
        protocol=EXECUTION_PROTOCOL,
        task_fingerprint=task_fingerprint(task),
        invocation_fingerprint=invocation_fingerprint,
        settings_fingerprint=mechanism_fingerprint(),
    )


def cache_plan(
    *,
    out_dir: Path,
    repeats: int,
    model: str,
    dry_run: bool,
    version_fn: Callable[[], str] | None = None,
    resume: bool = True,
) -> CachePlan[ToolReqRealAgentTask, BaseRunIdentity, BuiltinCell]:
    """This grid's ``resume_cache.CachePlan`` — what decides whether a persisted cell may be
    reused, read by both ``run_corpus`` and ``remaining_tasks``. Built here rather than assembled at
    each call site, so a knob cannot reach one and miss the other — see ``CachePlan``.

    ``model`` is RESOLVED here, never taken raw — through ``headless_agent.resolve_model``, the same
    rule the agent itself runs under, CALLED and never copied. ``run_corpus`` calls it too, for the
    model it hands ``evaluate``; that is the one rule applied twice to one input, not a second copy
    of it, and the two cannot disagree without moving the argv the plan hashes — which the write
    boundary refuses. ``BaseRunIdentity`` refuses an unresolved model outright, so the schema is the
    backstop rather than a rule restated here.

    The claude BINARY is resolved on the same terms (``toolreq_grid.cache_plan``), and matters to
    this grid for an EXTRA reason — ours-vs-builtin is a comparison BETWEEN grids
    (``headless_agent.cell_agent``), so a binary drift that missed one grid while the other reused
    would corrupt exactly that comparison. It SPAWNS a subprocess (``claude --version``), which is
    why this is not free of preconditions even for a caller that only wants to price a fire:
    token-free is not spawn-free, and a paid identity that cannot name its instrument cannot be
    constructed at all."""
    resolved_model = resolve_model(model)
    cli_version = "" if dry_run else (version_fn or resolve_cli_version)()
    return CachePlan(
        out_dir=out_dir,
        result_cls=BuiltinCachedResult,
        plan_of=lambda task: planned_calls(task, model=resolved_model),
        identity_of=lambda task, invocation_fingerprint: _identity(
            task,
            repeats=repeats,
            resolved_model=resolved_model,
            cli_version=cli_version,
            dry_run=dry_run,
            invocation_fingerprint=invocation_fingerprint,
        ),
        summary_name=SUMMARY_NAME,
        resume=resume,
    )


def remaining_tasks(
    tasks: Sequence[ToolReqRealAgentTask],
    *,
    out_dir: Path,
    repeats: int,
    model: str,
    version_fn: Callable[[], str] | None = None,
    resume: bool = True,
) -> list[ToolReqRealAgentTask]:
    """The tasks a PAID fire over ``out_dir`` would actually measure — the work that REMAINS, which
    the refuse-to-spend disclosure prices instead of the whole corpus (mem-u9nu2). Price it with
    ``paid_call_count``, the same function the whole-corpus cost is summed by.

    ``dry_run=False`` is not a parameter: this answers what a PAID fire costs, and a free run's
    identity is a different one (``BaseRunIdentity.dry_run``) that no disclosure authorizes money
    against.

    RAISES ``HeadlessAgentError`` when the claude binary cannot be identified, because then the paid
    identity cannot be constructed and there IS no honest answer — a paid cell is a measurement made
    by a named instrument (``BaseRunIdentity.cli_version``). What a driver should SAY about that is
    the shell's (the same split as ``preflight_gate``'s ``announce`` and ``_HALT_COUNSEL``); that
    there is no answer is this module's. Every other failure propagates untouched — in particular
    the ``ValueError`` from ``CachePlan.lookup`` when an identity's fingerprint is not the plan's,
    the loudest structural defect this cache has, which must never be softened into a cost."""
    return pending_tasks(
        cache_plan(
            out_dir=out_dir,
            repeats=repeats,
            model=model,
            dry_run=False,
            version_fn=version_fn,
            resume=resume,
        ),
        tasks,
    )


def run_corpus(
    tasks: Sequence[ToolReqRealAgentTask],
    *,
    out_dir: Path,
    repeats: int,
    model: str,
    dry_run: bool,
    version_fn: Callable[[], str] | None = None,
    resume: bool = True,
    before_first_spend: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Evaluate every task through the shared resume cache and shape this grid's summary.

    The cache identity — the resolved model, the binary, and the rest — is ``cache_plan``'s, so this
    run and the disclosure that priced it read one answer.

    ``before_first_spend`` is forwarded, not interpreted — ``preflight_gate`` is what the driver
    passes, and the hook's contract is ``resume_cache.run_cached_corpus``'s."""
    resolved_model = resolve_model(model)
    run = run_cached_corpus(
        cache_plan(
            out_dir=out_dir,
            repeats=repeats,
            model=model,
            dry_run=dry_run,
            version_fn=version_fn,
            resume=resume,
        ),
        tasks,
        evaluate=lambda task, recorder: evaluate_task(
            task, repeats=repeats, model=resolved_model, dry_run=dry_run, recorder=recorder
        ),
        before_first_spend=before_first_spend,
    )
    results = run.results
    return {
        **corpus_summary(tasks, run, dry_run=dry_run, repeats=repeats, n_channels=len(CHANNELS)),
        # `not_engaged` is the builtin grid's OWN headline (see NOT_ENGAGED) — it stays here, not in
        # corpus_summary where no other grid would emit it. separates_all_channels / leaked now come
        # from that one owner.
        "not_engaged": [r.work_id for r in results if NOT_ENGAGED in r.kinds],
    }
