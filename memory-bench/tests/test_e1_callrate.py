"""mem-eg850 — the OFFLINE half of E1: the guidance ladder, the argv it moves, and the gates.

Nothing here spends anything: every test drives the ladder table, `argv_for`, and the gate
arithmetic directly. The paid halves (the top-rung mechanism preflight and the staged fire) are
wired in `membench.runner.e1_grid` and are the orchestrator's to trigger; what is tested here is
the PLUMBING around them — the argv they will send, the halt logic they will apply to a result,
and the priced plan they disclose.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import types
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from membench.runner import e1_grid
from membench.runner.e1_grid import (
    HALT_NO_CALL,
    HALT_UNPAID,
    OK_FIRED,
    RUNG_IDS,
    RUNG_TEXT,
    STAGED_REPEATS,
    STAGED_RUNGS,
    STAGED_TASKS,
    CorpusShapeError,
    LegRecord,
    PreflightHaltError,
    ResumeMismatchError,
    RungCell,
    assert_gates_ride_outside_metrics,
    assert_scoreable_corpus,
    call_rate_gates,
    corpus_fingerprint,
    discrimination_margins,
    grid_keys,
    guidance_words,
    monotonicity_violations,
    planned_call_count,
    pooled_rates,
    preflight_gate,
    preflight_verdict,
    resume_cells,
    rung_step,
    staged_plan,
    summarize,
)
from membench.runner.headless_agent import (
    HeadlessAgentError,
    HeadlessClaudeAgent,
    MemoryChannel,
    assistant_event,
    result_event,
    seed_config_dir,
    serialize_stream,
    tool_result_event,
)
from membench.runner.sandbox import CorpusReachableError
from membench.runner.tool_surface import surface_fingerprint
from membench.runner.toolreq_corpus import load_twin_corpus
from membench.runner.toolreq_realagent import VARIANT_NECESSARY, VARIANT_UNNECESSARY
from membench.spawn import with_child
from tests.toolreq_helpers import corpus_one, noop_cli_runner

MODEL = "claude-test-model-1"


def _agent(**kwargs: Any) -> HeadlessClaudeAgent:
    """A render-only agent: `argv_for` never spawns, and the runner is explicit so no test can
    acquire a real, unrecorded `claude -p` by omission."""
    return HeadlessClaudeAgent(model=MODEL, runner=noop_cli_runner, **kwargs)


def _cell(
    rung: str,
    variant: str,
    *,
    calling: int,
    runs: int = 4,
    work_id: str = "",
    reading: int | None = None,
    writing: int = 0,
) -> RungCell:
    """A cell whose calling legs each READ once unless ``reading`` says how many did, plus
    ``writing`` legs that each made one acknowledged write."""
    reading_runs = calling if reading is None else reading
    return RungCell(
        rung=rung,
        variant=variant,
        runs=runs,
        calling_runs=calling,
        memory_calls=max(calling, reading_runs + writing),
        read_calls=reading_runs,
        write_calls=writing,
        reading_runs=reading_runs,
        writing_runs=writing,
        paid=True,
        work_id=work_id,
    )


# --- AC1: the ladder is nested, asserted on the TABLE ---------------------------------


def test_ladder_is_nested() -> None:
    """Every rung's guidance CONTAINS its predecessor's, verbatim.

    Asserted on `RUNG_TEXT` — the table — and never on a rendered prompt: containment is what makes
    a rung difference an ADDED CLAUSE rather than a rewrite that merely reads stronger, and only
    the table can say that."""
    assert len(RUNG_TEXT) == len(RUNG_IDS) == 5
    assert RUNG_TEXT[0] == "", "R0 is the SILENT rung: it carries no guidance text at all"
    for n in range(len(RUNG_TEXT) - 1):
        assert RUNG_TEXT[n] in RUNG_TEXT[n + 1], (
            f"{RUNG_IDS[n]} text is not contained in {RUNG_IDS[n + 1]}: the ladder is no longer "
            "nested, so a rung comparison is a comparison of two different prompts"
        )
        assert len(RUNG_TEXT[n + 1]) > len(RUNG_TEXT[n]), (
            f"{RUNG_IDS[n + 1]} adds nothing to {RUNG_IDS[n]} — containment alone is satisfied by "
            "two identical rungs, which would be one treatment billed twice"
        )
    # The reported cost adjustment moves with the treatment, which is the whole reason it is
    # reported: R4's block is longer than R0's BY CONSTRUCTION.
    assert [guidance_words(rung) for rung in RUNG_IDS] == sorted(
        guidance_words(rung) for rung in RUNG_IDS
    )
    assert guidance_words("R0") == 0 < guidance_words("R4")


# --- AC2: every adjacent rung pair moves the argv --------------------------------------


def test_argv_diverges_per_rung(tmp_path: Any) -> None:
    """No two rungs send the same command line, so the resume cache cannot serve a neighbour's
    measurement as this rung's."""
    _seqs, tasks = corpus_one(tmp_path)
    task = tasks[0]
    agent = _agent()
    argvs = {rung: agent.argv_for(rung_step(task, rung), {}) for rung in RUNG_IDS}
    for lower, upper in pairwise(RUNG_IDS):
        assert argvs[lower] != argvs[upper], (
            f"{lower} and {upper} send the SAME argv — the cache identity cannot tell them apart, "
            "so one rung's cells would be served as the other's"
        )
    # And not merely adjacent-distinct: all five are pairwise distinct.
    assert len({tuple(a) for a in argvs.values()}) == len(RUNG_IDS)


def test_channel_axis_is_dropped_because_it_moves_nothing(tmp_path: Any) -> None:
    """The design note, enforced: on a BARE arm the two trust channels render byte-identical argv,
    which is why E1 pins one channel instead of sweeping them and billing twice."""
    _seqs, tasks = corpus_one(tmp_path)
    step = rung_step(tasks[0], "R4")
    recalled = _agent(memory_channel=MemoryChannel.RECALLED).argv_for(step, {})
    trusted = _agent(memory_channel=MemoryChannel.TRUSTED).argv_for(step, {})
    assert recalled == trusted
    assert e1_grid.CHANNEL is MemoryChannel.RECALLED


# --- AC3: the monotonicity detector actually fires -------------------------------------


def test_monotonicity_detector_fires() -> None:
    """An INVERTED fixture curve must be reported as a violation, WITH THE PAIR NAMED.

    The sharp one. A detector that stays green on inversion fails the bead, so the fixture is a
    curve that rises, falls, and rises again — the shape a mid-ladder clause that BACKFIRES
    produces, and the shape a "is the maximum at the top" check would call fine."""
    inverted = {"R0": 0.10, "R1": 0.60, "R2": 0.20, "R3": 0.30, "R4": 0.90}
    violations = monotonicity_violations(inverted)
    assert violations, "the detector stayed GREEN on an inverted curve"
    assert [f"{v.lower}->{v.upper}" for v in violations] == ["R1->R2"]
    (violation,) = violations
    assert violation.lower_rate == pytest.approx(0.60)
    assert violation.upper_rate == pytest.approx(0.20)
    assert violation.drop == pytest.approx(0.40)
    assert "R1->R2" in violation.describe()

    # The top-vs-bottom endpoints alone are monotone here (0.10 -> 0.90), so a detector reading
    # only the ends would report this curve clean. The named pair is what distinguishes them.
    assert inverted["R4"] > inverted["R0"]

    # A monotone curve is NOT reported: a detector that fires on everything names nothing.
    assert monotonicity_violations({"R0": 0.1, "R1": 0.1, "R2": 0.4, "R3": 0.4, "R4": 0.9}) == []

    # The violation reaches the emitted gate block, named — a detection nobody can read is not one.
    cells = [
        _cell(rung, VARIANT_NECESSARY, calling=int(rate * 10), runs=10)
        for rung, rate in inverted.items()
    ]
    gates = call_rate_gates(cells)
    assert gates["monotonicity"]["monotone"] is False
    assert gates["monotonicity"]["violation_pairs"] == ["R1->R2"]
    assert "R1->R2" in gates["monotonicity"]["reason"]


def test_monotonicity_tolerance_is_an_explicit_dead_band() -> None:
    """A drop inside the tolerance is not reported; the same drop at the default tolerance is.
    Softening the detector must be a visible argument, never the default."""
    curve = {"R0": 0.5, "R1": 0.45}
    assert monotonicity_violations(curve) != []
    assert monotonicity_violations(curve, tolerance=0.1) == []


def test_monotonicity_is_over_the_rungs_actually_measured() -> None:
    """The staged fire measures only the two ENDS, and those are adjacent in that run."""
    assert monotonicity_violations({"R0": 0.8, "R4": 0.2})[0].upper == "R4"


# --- AC4: R0 is not the none-arm cell --------------------------------------------------


def test_r0_argv_differs_from_none_arm(tmp_path: Any) -> None:
    """R0 carries no guidance TEXT, but it is not the existing none-arm cell: it hands the agent
    the memory tool surface, and that reaches the argv through `--allowedTools`. If the two
    collided, the none-arm's cached cells would be served as E1's tool-affordance floor."""
    _seqs, tasks = corpus_one(tmp_path)
    task = tasks[0]
    agent = _agent()
    none_arm = agent.argv_for(task.goal_step, {})
    r0 = agent.argv_for(rung_step(task, "R0"), {})
    assert r0 != none_arm
    assert "Bash" in r0[r0.index("--allowedTools") + 1]
    assert (
        "--allowedTools" not in none_arm
        or "Bash" not in none_arm[none_arm.index("--allowedTools") + 1]
    )
    # The step ids differ too, so the two cells cannot share a result identity even where a driver
    # keys on the step rather than the argv.
    assert rung_step(task, "R0").step_id != task.goal_step.step_id


# --- AC6: the gates ride on the summary, outside metrics() -----------------------------


def _summary_fixture() -> dict[str, Any]:
    cells = [
        _cell("R0", VARIANT_NECESSARY, calling=1),
        _cell("R0", VARIANT_UNNECESSARY, calling=0),
        _cell("R4", VARIANT_NECESSARY, calling=4),
        _cell("R4", VARIANT_UNNECESSARY, calling=1),
    ]
    return summarize(cells, model=MODEL, dry_run=False, repeats=4)


def test_gates_ride_outside_metrics() -> None:
    """`jq '.call_rate_gates'` is non-empty AND `jq '.cells[0].metrics.call_rate_gates'` is null —
    the acceptance criterion, on the object the driver writes to `summary-e1.json`."""
    summary = _summary_fixture()
    assert summary["call_rate_gates"]
    assert summary["cells"]
    for row in summary["cells"]:
        assert "call_rate_gates" not in row["metrics"]
    assert summary["cells"][0]["metrics"]["call_rate"] == pytest.approx(0.25)


def test_gate_placement_guard_refuses_a_smuggled_block() -> None:
    """The guard is checked at the WRITE boundary, so a summary that flattened the verdict into a
    metric vector cannot be published. Driven against a hand-built summary: the guard must reject
    the shape, not merely fail to produce it."""
    smuggled = _summary_fixture()
    smuggled["cells"][0]["metrics"]["call_rate_gates"] = {"monotone": True}
    with pytest.raises(ValueError, match="INSIDE its metrics"):
        assert_gates_ride_outside_metrics(smuggled)
    ungated = _summary_fixture()
    ungated["call_rate_gates"] = {}
    with pytest.raises(ValueError, match="no 'call_rate_gates' block"):
        assert_gates_ride_outside_metrics(ungated)


def test_primary_endpoint_is_the_margin_not_the_rate() -> None:
    """Both are emitted, and the margin is labelled the endpoint — a rung that lifts the raw rate
    with d flat bought nothing, and the block must let a reader see that."""
    summary = _summary_fixture()
    gates = summary["call_rate_gates"]
    assert gates["endpoint"] == "discrimination_margin"
    assert gates["discrimination"]["counts"] == "reads"
    assert gates["discrimination"]["margin_by_rung"] == {
        "R0": pytest.approx(0.25),
        "R4": pytest.approx(0.75),
    }
    assert gates["discrimination"]["any_call_margin_by_rung"] == {
        "R0": pytest.approx(0.25),
        "R4": pytest.approx(0.75),
    }
    assert gates["write_rate"]["by_rung"] == {
        VARIANT_NECESSARY: {"R0": 0.0, "R4": 0.0},
        VARIANT_UNNECESSARY: {"R0": 0.0, "R4": 0.0},
    }
    assert gates["monotonicity"]["call_rate_by_rung"] == {
        "R0": pytest.approx(0.25),
        "R4": pytest.approx(1.0),
    }
    # The reported (never applied) cost adjustment, and the affordance floor.
    assert gates["guidance_token_adjustment"]["guidance_words_by_rung"]["R0"] == 0
    assert gates["tool_affordance_floor"]["rung"] == "R0"
    assert gates["tool_affordance_floor"]["call_rate"] == pytest.approx(0.25)


def test_the_margin_is_on_reads_and_the_write_rate_is_reported_beside_it() -> None:
    """mem-zfm0m item 2. Reads are what the twin corpus manipulates: the necessary half needs a
    recall, the unnecessary half was handed the values. A WRITE is the same act in both halves
    (the agent storing what it just learned), so writes on both sides dilute an any-call margin
    toward zero without saying anything about discrimination. Fixture: reads on the necessary
    half only, one accepted write per leg on BOTH halves. The any-call margin is 0.0 — every
    leg on both halves called memory — while the read margin is 1.0, and the write rate is 1.0
    on both halves, reported on its own."""
    cells = [
        _cell("R2", VARIANT_NECESSARY, calling=4, reading=4, writing=4),
        _cell("R2", VARIANT_UNNECESSARY, calling=4, reading=0, writing=4),
    ]
    assert discrimination_margins(cells) == {"R2": pytest.approx(1.0)}
    assert discrimination_margins(cells, kind="call") == {"R2": pytest.approx(0.0)}
    assert pooled_rates(cells, VARIANT_NECESSARY, kind="read") == {"R2": pytest.approx(1.0)}
    assert pooled_rates(cells, VARIANT_UNNECESSARY, kind="read") == {"R2": pytest.approx(0.0)}
    assert pooled_rates(cells, VARIANT_UNNECESSARY, kind="write") == {"R2": pytest.approx(1.0)}
    gates = call_rate_gates(cells)
    assert gates["discrimination"]["margin_by_rung"] == {"R2": pytest.approx(1.0)}
    assert gates["discrimination"]["any_call_margin_by_rung"] == {"R2": pytest.approx(0.0)}
    assert gates["discrimination"]["read_rate_by_rung"] == {
        VARIANT_NECESSARY: {"R2": pytest.approx(1.0)},
        VARIANT_UNNECESSARY: {"R2": pytest.approx(0.0)},
    }
    assert gates["write_rate"]["by_rung"] == {
        VARIANT_NECESSARY: {"R2": pytest.approx(1.0)},
        VARIANT_UNNECESSARY: {"R2": pytest.approx(1.0)},
    }
    # The monotonicity gate and the affordance floor still read the ANY-call rate: they ask
    # whether guidance recruits legs to the tool at all, not whether it discriminates.
    assert gates["monotonicity"]["call_rate_by_rung"] == {"R2": pytest.approx(1.0)}


def test_a_cell_cannot_claim_reads_without_a_leg_that_read() -> None:
    """A read count with zero reading legs, or more reading legs than calling legs, is a cell
    that could not have been counted from any stream."""
    with pytest.raises(ValueError, match="read_calls 1 with reading_runs 0"):
        RungCell(
            rung="R1",
            variant=VARIANT_NECESSARY,
            runs=4,
            calling_runs=2,
            memory_calls=2,
            read_calls=1,
            write_calls=0,
            reading_runs=0,
            writing_runs=0,
            paid=True,
        )
    with pytest.raises(ValueError, match="reading_runs 3 > calling_runs 2"):
        RungCell(
            rung="R1",
            variant=VARIANT_NECESSARY,
            runs=4,
            calling_runs=2,
            memory_calls=3,
            read_calls=3,
            write_calls=0,
            reading_runs=3,
            writing_runs=0,
            paid=True,
        )
    with pytest.raises(ValueError, match="writing_runs 2 > write_calls 1"):
        RungCell(
            rung="R1",
            variant=VARIANT_NECESSARY,
            runs=4,
            calling_runs=2,
            memory_calls=3,
            read_calls=0,
            write_calls=1,
            reading_runs=0,
            writing_runs=2,
            paid=True,
        )


def test_a_cell_row_without_per_direction_leg_counts_is_refused() -> None:
    """An artifact written before the margin moved to reads has no ``reading_runs``; defaulting
    it to zero would resume the cell with a fabricated read rate of 0.0."""
    row = _cell("R0", VARIANT_NECESSARY, calling=2).row()
    del row["metrics"]["reading_runs"]
    with pytest.raises(ValueError, match="reading_runs"):
        RungCell.from_row(row)


def test_run_rung_cell_counts_reading_and_writing_legs_separately(tmp_path: Any) -> None:
    """Through the cell path: the necessary half's legs recall AND store, the unnecessary half's
    legs only store. Every leg on both halves is a calling leg; only the necessary half's read."""
    corpus_one(tmp_path)
    _, twins = load_twin_corpus(tmp_path / "corpus")
    by_variant = {task.variant: task for task in twins}
    necessary = e1_grid.run_rung_cell(
        by_variant[VARIANT_NECESSARY],
        rung="R2",
        repeats=2,
        model=MODEL,
        dry_run=False,
        runner=_calling_runner(("bd remember 'a value' --key k", REMEMBERED), "bd recall k"),
    )
    unnecessary = e1_grid.run_rung_cell(
        by_variant[VARIANT_UNNECESSARY],
        rung="R2",
        repeats=2,
        model=MODEL,
        dry_run=False,
        runner=_calling_runner(("bd remember 'a value' --key k", REMEMBERED)),
    )
    assert (necessary.reading_runs, necessary.writing_runs) == (2, 2)
    assert (unnecessary.reading_runs, unnecessary.writing_runs) == (0, 2)
    assert (necessary.calling_runs, unnecessary.calling_runs) == (2, 2)
    cells = [necessary, unnecessary]
    assert discrimination_margins(cells) == {"R2": pytest.approx(1.0)}
    assert discrimination_margins(cells, kind="call") == {"R2": pytest.approx(0.0)}
    assert necessary.metrics()["read_rate"] == pytest.approx(1.0)
    assert necessary.metrics()["write_rate"] == pytest.approx(1.0)
    assert unnecessary.metrics()["read_rate"] == pytest.approx(0.0)


def test_margin_needs_both_halves() -> None:
    """A rung with only one half measured gets NO margin — a one-sided margin is a call rate
    wearing the endpoint's name."""
    assert discrimination_margins([_cell("R2", VARIANT_NECESSARY, calling=2)]) == {}


def test_a_cell_cannot_claim_impossible_counts() -> None:
    with pytest.raises(ValueError, match="calling_runs 5 > measured 4"):
        _cell("R1", VARIANT_NECESSARY, calling=5)
    with pytest.raises(ValueError, match="cannot cover"):
        RungCell(
            rung="R1",
            variant=VARIANT_NECESSARY,
            runs=4,
            calling_runs=3,
            memory_calls=1,
            read_calls=1,
            write_calls=0,
            reading_runs=1,
            writing_runs=0,
            paid=True,
        )


# --- the paid plumbing: halt logic and the priced plan, driven by fixtures --------------


def test_preflight_halts_on_zero_calls() -> None:
    """AC5's halt rule, as a pure function over a FIXTURE result row: zero memory calls at the TOP
    rung is a HALT, and no interior rung is paid for."""
    kind, line = preflight_verdict({"rung": "R4", "memory_calls": 0, "paid": True})
    assert kind == HALT_NO_CALL
    assert "ZERO memory calls" in line
    with pytest.raises(PreflightHaltError) as excinfo:
        preflight_gate({"rung": "R4", "memory_calls": 0, "paid": True})
    assert excinfo.value.kind == HALT_NO_CALL


def test_preflight_halts_on_an_unpaid_row() -> None:
    """A fixture runner's calls are the fixture's. An unpaid row halts however many calls it
    shows — the mechanism claim is only ever about a real `claude -p`."""
    kind, _line = preflight_verdict({"rung": "R4", "memory_calls": 7, "paid": False})
    assert kind == HALT_UNPAID


def test_preflight_passes_a_fired_paid_row() -> None:
    kind, line = preflight_verdict({"rung": "R4", "memory_calls": 2, "paid": True})
    assert kind == OK_FIRED and "fired" in line
    assert preflight_gate({"rung": "R4", "memory_calls": 2, "paid": True})["kind"] == OK_FIRED


def test_preflight_runs_at_the_top_rung_and_has_no_free_path() -> None:
    """The preflight is deliberately NOT simulated (the `toolreq_builtin_grid.preflight` stance):
    it takes no `dry_run` and no `runner`, so there is no way to satisfy the mechanism check with
    a cooperating stand-in."""
    assert e1_grid.PREFLIGHT_RUNG == RUNG_IDS[-1] == "R4"
    params = e1_grid.preflight.__code__.co_varnames[
        : e1_grid.preflight.__code__.co_argcount + e1_grid.preflight.__code__.co_kwonlyargcount
    ]
    assert "dry_run" not in params and "runner" not in params


def test_staged_plan_is_priced_not_quoted() -> None:
    """T=8, R=5, the two ends of the ladder, both corpus halves: 160 real calls."""
    assert STAGED_RUNGS == ("R0", "R4")
    plan = staged_plan(n_tasks_per_variant=64, n_variants=2)
    assert plan == {
        "stage": "ends",
        "rungs": ["R0", "R4"],
        "n_tasks": STAGED_TASKS,
        "repeats": STAGED_REPEATS,
        "n_variants": 2,
        "calls": 160,
        "halt_rule": plan["halt_rule"],
    }
    assert "ZERO" in plan["halt_rule"] or "zero" in plan["halt_rule"]
    # Priced by product over what is actually run, so adding a rung moves the disclosed cost.
    assert planned_call_count(rungs=RUNG_IDS, n_tasks=8, repeats=5, n_variants=2) == 400
    # A corpus smaller than the staged size is priced at the corpus, never at the constant.
    assert staged_plan(n_tasks_per_variant=3, n_variants=2)["calls"] == 60


def test_cli_refuses_to_spend_without_a_pinned_model(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The paid entrypoint refuses BEFORE the corpus loads, so a refused run costs nothing."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    assert e1_grid.main(["--preflight", "--rung", "R4"]) == e1_grid.EXIT_REFUSED
    assert "model" in capsys.readouterr().err.lower()


def test_cli_refuses_to_spend_without_an_oauth_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    # --staged prices and spends nothing, so it is no longer a paid path; --fire-staged is.
    assert e1_grid.main(["--fire-staged", "--model", MODEL]) == e1_grid.EXIT_REFUSED
    assert "CLAUDE_CODE_OAUTH_TOKEN" in capsys.readouterr().err


def test_cli_plan_path_spends_nothing_and_names_the_paid_commands(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The default path prices the ladder and fires nothing; the paid commands are printed so the
    orchestrator has them verbatim."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _seqs, _tasks = corpus_one(tmp_path)
    assert e1_grid.main(["--corpus-dir", str(tmp_path / "corpus"), "--json"]) == e1_grid.EXIT_OK
    captured = capsys.readouterr()
    plan = __import__("json").loads(captured.out)
    assert plan["rungs"] == list(RUNG_IDS)
    assert plan["staged_plan"]["repeats"] == STAGED_REPEATS


def test_cli_reports_a_missing_corpus_as_infrastructure_not_a_result(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / "empty").mkdir()
    assert e1_grid.main(["--corpus-dir", str(tmp_path / "empty")]) == e1_grid.EXIT_NO_CORPUS


# --------------------------------------------------------------------------------------
# run_rung_cell end-to-end (pre-spend smoke, mem-eg850)
#
# Every other test in this file exercises run_rung_cell's PARTS — rung_step, the counter, the
# gates — and none of them execute the function itself. That left the first paid keystroke as the
# first end-to-end execution of the cell, which is the one place a wiring defect costs money to
# find. These two tests drive the real function with an injected runner: the store provisioning,
# the sandbox, the argv render, the stream parse and the counter all run for real, and only the
# `claude -p` spawn is replaced.
# --------------------------------------------------------------------------------------


# bd's own acknowledgement of a stored memory, as bd 1.3.0-rc.1 prints it.
REMEMBERED = "Remembered [k]: a value"

# The exact tool_use / tool_result the 160-leg staged fire scored as its ONLY endogenous write
# (R4 / unnecessary / world-seed2-task0, leg 1). `is_error` is FALSE on the real record: the
# `2>&1 | head` pipe exits 0, so the refusal is visible in the content and nowhere else.
REFUSED_REMEMBER_LIST = (
    "cd /tmp/membench-memory-bsi54bav/store && /tmp/membench-memory-bsi54bav/bin/bd remember "
    "list 2>&1 | head -100"
)
REFUSED_REMEMBER_LIST_RESULT = (
    'Error: "list" looks like a command, not something to remember\n'
    "Hint: Did you mean 'bd list'? To store \"list\" as a memory anyway, give it an explicit "
    'key: bd remember "list" --key <key>\n'
    "Shell cwd was reset to /tmp/e1-r4-5hy4nzs5"
)


def _calling_runner(*commands: str | tuple[str, str]) -> Any:
    """A `claude -p` stand-in whose stream carries `commands` as Bash tool_use blocks, each
    followed by its tool_result when given as ``(command, result)``.

    Deliberately UNCONDITIONAL: it emits the same calls at every rung, so it can prove the cell
    counts what the stream contains and can never reproduce a rung effect. `_silent_runner` is the
    zero end of the same fixture."""

    def runner(argv: Any, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        events: list[dict[str, object]] = []
        for i, entry in enumerate(commands):
            command, result = entry if isinstance(entry, tuple) else (entry, None)
            call_id = f"toolu_{i}"
            events.append(assistant_event([("Bash", {"command": command}, call_id)]))
            if result is not None:
                events.append(tool_result_event(call_id, result))
        events.append(result_event())
        return subprocess.CompletedProcess(list(argv), 0, serialize_stream(events), "")

    return runner


def test_run_rung_cell_counts_the_memory_calls_its_stream_carries(tmp_path: Any) -> None:
    """The whole cell, executed: provision a store, render the rung's step, parse the stream, count.

    Three calls per repeat over two repeats is six, split two reads / one write per repeat. The
    read and write counts are deliberately UNEQUAL and neither equals the total: a fixture with
    reads == writes passes whether or not the two filters are swapped, which is the geometry this
    test was first written with and which let a swapped-filter mutant survive."""
    _seqs, tasks = corpus_one(tmp_path)
    cell = e1_grid.run_rung_cell(
        tasks[0],
        rung="R4",
        repeats=2,
        model=MODEL,
        dry_run=False,
        runner=_calling_runner(
            ("bd remember 'a value' --key k", REMEMBERED), "bd recall k", "bd recall other"
        ),
    )
    assert cell.runs == 2
    assert cell.calling_runs == 2
    assert cell.memory_calls == 6
    assert cell.read_calls == 4
    assert cell.write_calls == 2
    assert set(cell.verbs) == {"remember", "recall"}
    assert cell.paid is False


def test_run_rung_cell_is_unpaid_and_empty_on_the_dry_run_path(tmp_path: Any) -> None:
    """The free path proves the plumbing and measures zero, and says so in `paid` — the pairing that
    keeps a green smoke from reading as a mechanism result."""
    _seqs, tasks = corpus_one(tmp_path)
    cell = e1_grid.run_rung_cell(tasks[0], rung="R4", repeats=1, model=MODEL, dry_run=True)
    assert cell.memory_calls == 0
    assert cell.calling_runs == 0
    assert cell.paid is False


def _native_reach_runner() -> Any:
    """mem-gj0pc's exact transcript: the agent says it will check memory and Reads MEMORY.md under
    the pinned config dir. The path is read back off the env the cell handed the runner, which is
    the only way a fixture can name a per-repeat tempdir it never chose."""

    def runner(argv: Any, **kwargs: object) -> subprocess.CompletedProcess[str]:
        env = kwargs.get("env") or {}
        config = env["CLAUDE_CONFIG_DIR"]  # type: ignore[index]
        target = f"{config}/projects/-tmp/memory/MEMORY.md"
        events = [
            assistant_event([("Read", {"file_path": target})]),
            result_event(),
        ]
        return subprocess.CompletedProcess(list(argv), 0, serialize_stream(events), "")

    return runner


def test_a_native_memory_reach_counts_as_a_memory_call(tmp_path: Any) -> None:
    """The first paid R4 cycle scored this reach as ZERO because the counter saw bd verbs only.
    Both surfaces count now, so the same stream is one read and no writes."""
    _seqs, tasks = corpus_one(tmp_path)
    cell = e1_grid.run_rung_cell(
        tasks[0], rung="R4", repeats=1, model=MODEL, dry_run=False, runner=_native_reach_runner()
    )
    assert cell.memory_calls == 1
    assert cell.calling_runs == 1
    assert cell.read_calls == 1
    assert cell.write_calls == 0
    assert list(cell.verbs) == ["native_read"]


def _bash_reach_runner(template: str) -> Any:
    """mem-zfm0m item 3: the agent reaches the native memory file through a Bash command instead
    of the Read/Write tools. ``template`` names the file as ``{m}``, resolved off the pinned
    config dir the cell handed the runner."""

    def runner(argv: Any, **kwargs: object) -> subprocess.CompletedProcess[str]:
        env = kwargs.get("env") or {}
        config = env["CLAUDE_CONFIG_DIR"]  # type: ignore[index]
        command = template.format(m=f"{config}/projects/-tmp/memory/MEMORY.md")
        events = [assistant_event([("Bash", {"command": command})]), result_event()]
        return subprocess.CompletedProcess(list(argv), 0, serialize_stream(events), "")

    return runner


@pytest.mark.parametrize(
    ("template", "reads", "writes", "verbs"),
    [
        ("cat {m}", 1, 0, ["native_read"]),
        ("head -40 {m} 2>/dev/null", 1, 0, ["native_read"]),
        ("echo '- note' >> {m}", 0, 1, ["native_write"]),
        ("printf x | tee -a {m}", 0, 1, ["native_write"]),
    ],
)
def test_a_bash_reach_into_the_native_memory_file_counts_by_direction(
    tmp_path: Any, template: str, reads: int, writes: int, verbs: list[str]
) -> None:
    """A `cat`/`head` of the pinned memory file is a read and a `>>`/`tee` into it is a write, by
    path-prefix match on the config dir the harness pinned — the Bash door counts like the Read
    tool door."""
    _seqs, tasks = corpus_one(tmp_path)
    cell = e1_grid.run_rung_cell(
        tasks[0],
        rung="R4",
        repeats=1,
        model=MODEL,
        dry_run=False,
        runner=_bash_reach_runner(template),
    )
    assert (cell.memory_calls, cell.calling_runs) == (1, 1)
    assert (cell.read_calls, cell.write_calls) == (reads, writes)
    assert list(cell.verbs) == verbs


def test_a_bash_call_that_runs_bd_and_cats_the_memory_file_is_one_memory_call(
    tmp_path: Any,
) -> None:
    """Memory calls are TOOL CALLS, not verbs: one Bash block that does `bd recall k` and then
    cats MEMORY.md reached memory once, through two doors. Reads count per door."""
    _seqs, tasks = corpus_one(tmp_path)
    cell = e1_grid.run_rung_cell(
        tasks[0],
        rung="R4",
        repeats=1,
        model=MODEL,
        dry_run=False,
        runner=_bash_reach_runner("bd recall k; cat {m}"),
    )
    assert (cell.memory_calls, cell.calling_runs) == (1, 1)
    assert (cell.read_calls, cell.write_calls) == (2, 0)
    assert list(cell.verbs) == ["recall", "native_read"]


def test_a_bash_command_that_mentions_memory_but_touches_no_pinned_path_is_not_a_call(
    tmp_path: Any,
) -> None:
    _seqs, tasks = corpus_one(tmp_path)
    cell = e1_grid.run_rung_cell(
        tasks[0],
        rung="R4",
        repeats=1,
        model=MODEL,
        dry_run=False,
        runner=_bash_reach_runner("echo 'checking memory first'  # memory: {m}"),
    )
    assert (cell.memory_calls, cell.calling_runs) == (0, 0)
    assert (cell.read_calls, cell.write_calls) == (0, 0)


def test_staged_cells_applies_the_task_cap_per_variant_not_across_the_list(tmp_path: Any) -> None:
    """The priced bill is len(rungs) * n_tasks * repeats * 2, so `n_tasks` is PER VARIANT. Capping
    the flat list instead would run half the grid and report a whole one."""
    _seqs, tasks = corpus_one(tmp_path)
    calls: list[tuple[str, str]] = []

    def counting(argv: Any, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(list(argv), 0, serialize_stream([result_event()]), "")

    cells = e1_grid.staged_cells(
        tasks * 4,
        model=MODEL,
        corpus_dir=tmp_path / "corpus",
        rungs=("R0",),
        n_tasks=2,
        repeats=1,
        runner=counting,
        on_cell=lambda cell: calls.append((cell.rung, cell.variant)),
    )
    variants = {task.variant for task in tasks * 4}
    assert len(cells) == 2 * len(variants)
    assert calls == [(cell.rung, cell.variant) for cell in cells]


def test_fire_staged_is_a_different_flag_from_the_one_that_prices_it(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--staged still prices and spends nothing. Authorization and execution stay two keystrokes."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    _seqs, _tasks = corpus_one(tmp_path)
    code = e1_grid.main(["--corpus-dir", str(tmp_path / "corpus"), "--staged", "--model", MODEL])
    assert code == e1_grid.EXIT_OK
    assert "PRICED, NOT FIRED" in capsys.readouterr().err


def test_fire_staged_refuses_without_a_token(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert e1_grid.main(["--fire-staged", "--model", MODEL]) == e1_grid.EXIT_REFUSED
    assert "CLAUDE_CODE_OAUTH_TOKEN" in capsys.readouterr().err


# --- timeouts are unmeasured legs, cells pool, and a dead fire resumes -----------------


def _timeout_error(stdout: str | bytes | None = None) -> HeadlessAgentError:
    """The exact shape ``spawn.run_checked`` raises: a HeadlessAgentError CAUSED BY
    TimeoutExpired, carrying whatever the child wrote before the bound (``run_in_session`` hands
    it over decoded; ``subprocess.run`` as bytes; a child that wrote nothing, None)."""
    try:
        raise subprocess.TimeoutExpired(cmd=["claude", "-p"], timeout=600.0, output=stdout)
    except subprocess.TimeoutExpired as exc:
        err = HeadlessAgentError("claude -p did not finish within 600.0s")
        err.__cause__ = exc
        return err


def _timing_out_runner(timeout_legs: set[int], *commands: str | tuple[str, str]) -> Any:
    """`_calling_runner`, except the legs numbered in ``timeout_legs`` (0-based, per cell) time out
    the way the first staged fire's cell 13 did."""
    leg = {"n": 0}
    calling = _calling_runner(*commands)

    def runner(argv: Any, **kwargs: object) -> subprocess.CompletedProcess[str]:
        i = leg["n"]
        leg["n"] += 1
        if i in timeout_legs:
            raise _timeout_error()
        result: subprocess.CompletedProcess[str] = calling(argv, **kwargs)
        return result

    return runner


def _partial_stream_runner(timeout_leg: int, partial: str | bytes) -> Any:
    """`_calling_runner("bd recall k")` except leg ``timeout_leg`` times out AFTER writing
    ``partial`` — the shape ``run_in_session`` raises when the bound fires mid-stream."""
    leg = {"n": 0}
    calling = _calling_runner("bd recall k")

    def runner(argv: Any, **kwargs: object) -> subprocess.CompletedProcess[str]:
        i = leg["n"]
        leg["n"] += 1
        if i == timeout_leg:
            raise _timeout_error(partial)
        result: subprocess.CompletedProcess[str] = calling(argv, **kwargs)
        return result

    return runner


@pytest.mark.parametrize("encode", [False, True], ids=["str", "bytes"])
def test_a_timed_out_leg_is_scored_from_its_partial_stream_and_stays_unmeasured(
    tmp_path: Any, encode: bool
) -> None:
    """mem-zfm0m item 4. A leg that timed out after two memory calls made two memory calls; the
    first fire threw its partial stream away and persisted an empty one. The partial stream is
    scored by the same arithmetic as a complete one and persisted with ``truncated=True`` — and
    the leg stays OUT of the measured denominator and out of every cell numerator, because a
    truncated stream bounds the count from below only."""
    _seqs, tasks = corpus_one(tmp_path)
    partial = serialize_stream(
        [
            assistant_event([("Bash", {"command": "bd recall k"})]),
            assistant_event([("Bash", {"command": "bd recall other"})]),
        ]
    )
    legs: list[e1_grid.LegRecord] = []
    cell = e1_grid.run_rung_cell(
        tasks[0],
        rung="R4",
        repeats=3,
        model=MODEL,
        dry_run=False,
        runner=_partial_stream_runner(1, partial.encode() if encode else partial),
        on_leg=legs.append,
    )
    # The cell: two measured legs, one call each. The timed-out leg's two calls are NOT in here.
    assert (cell.runs, cell.timed_out_runs, cell.measured_runs) == (3, 1, 2)
    assert (cell.calling_runs, cell.memory_calls, cell.read_calls) == (2, 2, 2)
    assert cell.call_rate == pytest.approx(1.0)
    # The leg: scored, persisted with its events, marked truncated.
    truncated = legs[1]
    assert truncated.status == "timeout"
    assert truncated.truncated is True
    assert (truncated.memory_calls, truncated.read_calls, truncated.write_calls) == (2, 2, 0)
    assert list(truncated.verbs) == ["recall", "recall"]
    assert "bd recall other" in truncated.stream
    assert "did not finish" in truncated.detail
    assert [leg.truncated for leg in legs] == [False, True, False]


def test_a_leg_cannot_reach_the_corpus_from_its_env_or_its_cwd_tree(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mem-zfm0m item 7. The corpus reaches the agent through the prompt and nowhere else. Read
    off the spawn itself: no env value names the corpus root or anything under it, ``PWD`` is the
    sandbox (the operator's shell, whose ``PWD`` is the checkout holding the corpus, must not leak
    through the env merge), and the cwd tree holds nothing resolving into the corpus."""
    _seqs, tasks = corpus_one(tmp_path)
    corpus = (tmp_path / "corpus").resolve()
    # The operator's shell: its cwd IS the tree the corpus lives in.
    monkeypatch.setenv("PWD", str(tmp_path))
    seen: list[dict[str, Any]] = []

    def capturing(argv: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        cwd = Path(kwargs["cwd"])
        env = dict(kwargs["env"])
        seen.append(
            {
                "cwd": cwd,
                "env": env,
                "tree": [p.resolve() for p in cwd.rglob("*")],
            }
        )
        return subprocess.CompletedProcess(list(argv), 0, serialize_stream([result_event()]), "")

    e1_grid.run_rung_cell(
        tasks[0],
        rung="R4",
        repeats=2,
        model=MODEL,
        dry_run=False,
        runner=capturing,
        corpus_dir=tmp_path / "corpus",
    )
    assert len(seen) == 2
    for leg in seen:
        assert leg["env"]["PWD"] == str(leg["cwd"])
        for key, value in leg["env"].items():
            for segment in value.split(os.pathsep):
                if os.path.isabs(segment):
                    resolved = Path(segment).resolve()
                    assert resolved != corpus and corpus not in resolved.parents, (key, value)
        assert not any(p == corpus or corpus in p.parents for p in leg["tree"])


def test_a_leg_env_that_names_the_corpus_refuses_before_spending(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guard runs BEFORE the spawn: a harness variable pointing at the corpus is a refusal
    with nothing bought, not a leg to re-score."""
    _seqs, tasks = corpus_one(tmp_path)
    monkeypatch.setenv("MEMBENCH_CORPUS_HINT", str(tmp_path / "corpus" / "0"))
    spawned: list[Any] = []

    def counting(argv: Any, **kwargs: object) -> subprocess.CompletedProcess[str]:
        spawned.append(argv)
        return subprocess.CompletedProcess(list(argv), 0, serialize_stream([result_event()]), "")

    with pytest.raises(CorpusReachableError, match="MEMBENCH_CORPUS_HINT"):
        e1_grid.run_rung_cell(
            tasks[0],
            rung="R4",
            repeats=2,
            model=MODEL,
            dry_run=False,
            runner=counting,
            corpus_dir=tmp_path / "corpus",
        )
    assert spawned == []


def test_a_sandbox_entry_pointing_into_the_corpus_refuses_before_spending(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sandbox is minted empty; one that arrives with a link into the corpus (a future
    "copy the task's files in" that symlinked instead) is refused with nothing bought."""
    _seqs, tasks = corpus_one(tmp_path)
    spawned: list[Any] = []

    @contextmanager
    def planted(prefix: str) -> Iterator[Path]:
        with tempfile.TemporaryDirectory(prefix=prefix) as raw:
            sandbox = Path(raw).resolve()
            (sandbox / "fixtures").symlink_to(tmp_path / "corpus", target_is_directory=True)
            yield sandbox

    monkeypatch.setattr(e1_grid, "paid_sandbox", planted, raising=True)

    def counting(argv: Any, **kwargs: object) -> subprocess.CompletedProcess[str]:
        spawned.append(argv)
        return subprocess.CompletedProcess(list(argv), 0, serialize_stream([result_event()]), "")

    with pytest.raises(CorpusReachableError, match="fixtures"):
        e1_grid.run_rung_cell(
            tasks[0],
            rung="R4",
            repeats=1,
            model=MODEL,
            dry_run=False,
            runner=counting,
            corpus_dir=tmp_path / "corpus",
        )
    assert spawned == []


def test_the_paid_spawn_starts_the_child_in_its_own_session(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mem-zfm0m item 8: with no runner injected and no dry run, the cell spawns through
    ``run_in_session`` — the runner whose timeout kills the process group — not
    ``subprocess.run``. Proven by substitution: the name the cell resolves is the one patched."""
    _seqs, tasks = corpus_one(tmp_path)
    seen: list[list[str]] = []

    def fake(argv: Any, **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(list(argv))
        return subprocess.CompletedProcess(list(argv), 0, serialize_stream([result_event()]), "")

    monkeypatch.setattr(e1_grid, "run_in_session", fake, raising=True)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    cell = e1_grid.run_rung_cell(tasks[0], rung="R0", repeats=1, model=MODEL, dry_run=False)
    assert cell.paid is True
    assert len(seen) == 1 and seen[0][0].endswith("claude")


def test_a_timed_out_leg_is_unmeasured_not_a_non_calling_run(tmp_path: Any) -> None:
    """Three legs, the middle one times out, the other two call: the rate is 2/2, not 2/3, and
    the timeout is REPORTED on the cell rather than folded into the zero side of the rate."""
    _seqs, tasks = corpus_one(tmp_path)
    cell = e1_grid.run_rung_cell(
        tasks[0],
        rung="R0",
        repeats=3,
        model=MODEL,
        dry_run=False,
        runner=_timing_out_runner({1}, "bd recall k"),
    )
    assert cell.runs == 3
    assert cell.timed_out_runs == 1
    assert cell.measured_runs == 2
    assert cell.calling_runs == 2
    assert cell.call_rate == pytest.approx(1.0)
    assert cell.work_id == tasks[0].work_id
    assert cell.metrics()["timed_out_runs"] == 1


def test_an_isolated_failed_leg_is_unmeasured_and_kept_apart_from_a_timeout(
    tmp_path: Any,
) -> None:
    """One leg fails, the others return: the failure leaves the DENOMINATOR the way a timeout does,
    and is reported on its own field so the diagnosis is not folded into 'it timed out'."""
    _seqs, tasks = corpus_one(tmp_path)
    calls = {"n": 0}

    def flaky(argv: Any, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls["n"] += 1
        if calls["n"] == 2:
            raise HeadlessAgentError("claude -p failed (exit 1): transient")
        return _calling_runner("bd recall k")(argv)

    cell = e1_grid.run_rung_cell(
        tasks[0], rung="R0", repeats=3, model=MODEL, dry_run=False, runner=flaky
    )
    assert (cell.runs, cell.errored_runs, cell.timed_out_runs) == (3, 1, 0)
    assert cell.measured_runs == 2
    assert cell.calling_runs == 2
    assert cell.call_rate == pytest.approx(1.0)
    assert cell.metrics()["errored_runs"] == 1


def test_consecutive_failed_legs_halt_rather_than_filling_the_grid(tmp_path: Any) -> None:
    """A broken rig fails EVERY leg. Tolerating that leg by leg buys a whole grid of cells that
    measured nothing, so a run of failures is a halt — and the run has to be CONSECUTIVE, or a
    flake in each of three cells would halt a fire that is working."""
    _seqs, tasks = corpus_one(tmp_path)

    def broken(argv: Any, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise HeadlessAgentError("claude -p failed (exit 1): rig is broken")

    with pytest.raises(e1_grid.RigHaltError, match="3 consecutive"):
        e1_grid.run_rung_cell(
            tasks[0], rung="R0", repeats=5, model=MODEL, dry_run=False, runner=broken
        )

    interleaved = {"n": 0}

    def every_other(argv: Any, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        interleaved["n"] += 1
        if interleaved["n"] % 2 == 0:
            raise HeadlessAgentError("claude -p failed (exit 1): flake")
        return _calling_runner("bd recall k")(argv)

    cell = e1_grid.run_rung_cell(
        tasks[0], rung="R0", repeats=5, model=MODEL, dry_run=False, runner=every_other
    )
    assert (cell.errored_runs, cell.measured_runs, cell.calling_runs) == (2, 3, 3)


def test_a_quota_refusal_halts_the_fire_and_is_read_off_the_stream_not_the_message(
    tmp_path: Any,
) -> None:
    """The account refusing is not a defect and not a measurement: every further leg would fail the
    same way and be billed as nothing.

    Classified on the CLI's own ``api_error_status`` field, carried on the exception by
    ``run_checked``. Not on the message — ``run_checked`` redacts and truncates that by design, so
    a fire that matched prose there would keep spending against an exhausted account whenever the
    wording moved."""
    _seqs, tasks = corpus_one(tmp_path)
    refusal = subprocess.CompletedProcess(
        ["claude"],
        1,
        json.dumps(
            {
                "type": "result",
                "is_error": True,
                "api_error_status": 429,
                "result": "session limit",
            }
        ),
        "",
    )

    def refused(argv: Any, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise with_child(HeadlessAgentError("claude -p failed (exit 1): <redacted>"), refusal)

    with pytest.raises(e1_grid.QuotaHaltError, match="refused the call") as halted:
        e1_grid.run_rung_cell(
            tasks[0], rung="R0", repeats=5, model=MODEL, dry_run=False, runner=refused
        )
    # Raised FROM the agent error (review G6): the cause chain reaches the CLI's own result
    # event the refusal was classified on, and a wrapper lost it once.
    cause = halted.value.__cause__
    assert isinstance(cause, HeadlessAgentError)
    assert e1_grid.is_quota_halt(cause) is True
    # The message says nothing about a quota; only the stream field does.
    assert e1_grid.is_quota_halt(HeadlessAgentError("You've hit your session limit")) is False
    served = subprocess.CompletedProcess(["claude"], 1, '{"type":"result","is_error":true}', "")
    assert e1_grid.is_quota_halt(with_child(HeadlessAgentError("boom"), served)) is False
    # A non-result event carrying a status is NOT the account refusing.
    tool = subprocess.CompletedProcess(
        ["claude"], 1, '{"type":"assistant","api_error_status":429}', ""
    )
    assert e1_grid.is_quota_halt(with_child(HeadlessAgentError("boom"), tool)) is False


def test_the_timeout_classifier_reads_the_cause_chain(tmp_path: Any) -> None:
    assert e1_grid.is_spawn_timeout(_timeout_error()) is True
    assert e1_grid.is_spawn_timeout(HeadlessAgentError("did not finish within 600.0s")) is False


def test_a_cell_whose_every_leg_timed_out_has_no_rate() -> None:
    """Measured nothing is not measured zero: no ``call_rate``, and it contributes NOTHING to a
    pooled rate rather than a 0 to its numerator and denominator."""
    cell = RungCell(
        rung="R4",
        variant=VARIANT_NECESSARY,
        runs=5,
        calling_runs=0,
        memory_calls=0,
        read_calls=0,
        write_calls=0,
        reading_runs=0,
        writing_runs=0,
        paid=True,
        work_id="w-dead",
        timed_out_runs=5,
    )
    with pytest.raises(ValueError, match="no leg returned a stream"):
        _ = cell.call_rate
    assert cell.metrics()["call_rate"] is None
    assert pooled_rates([cell], VARIANT_NECESSARY) == {}
    with pytest.raises(ValueError, match="timed_out_runs 6"):
        RungCell(
            rung="R4",
            variant=VARIANT_NECESSARY,
            runs=5,
            calling_runs=0,
            memory_calls=0,
            read_calls=0,
            write_calls=0,
            reading_runs=0,
            writing_runs=0,
            paid=True,
            timed_out_runs=6,
        )


def test_rates_pool_over_task_cells_not_last_wins_and_not_a_mean() -> None:
    """The first staged fire's gate block read R0/necessary as 0.8 — the LAST task cell's 4/5 —
    while the pooled rate over eight cells was 16/40 = 0.4. Three cells here: 4/5, 1/5, and 1/2
    (three of its legs timed out). Pooled = 6/12 = 0.5. Last-wins says 0.5 too by accident of
    order, so the cells are listed with the 4/5 LAST; a mean of cell rates says 0.5 as well, so
    the 1/2 cell's denominator is what separates the three readings: pooled 6/12, last 0.8,
    mean (0.8 + 0.2 + 0.5) / 3 = 0.5. The 1/5 cell is therefore weighted 5:2 against the 1/2."""
    cells = [
        _cell("R0", VARIANT_NECESSARY, calling=1, runs=5),
        RungCell(
            rung="R0",
            variant=VARIANT_NECESSARY,
            runs=5,
            calling_runs=1,
            memory_calls=1,
            read_calls=1,
            write_calls=0,
            reading_runs=1,
            writing_runs=0,
            paid=True,
            timed_out_runs=3,
        ),
        _cell("R0", VARIANT_NECESSARY, calling=4, runs=5),
        _cell("R0", VARIANT_UNNECESSARY, calling=1, runs=5),
        _cell("R0", VARIANT_UNNECESSARY, calling=2, runs=5),
    ]
    assert pooled_rates(cells, VARIANT_NECESSARY) == {"R0": pytest.approx(6 / 12)}
    assert pooled_rates(cells, VARIANT_UNNECESSARY) == {"R0": pytest.approx(3 / 10)}
    assert discrimination_margins(cells) == {"R0": pytest.approx(6 / 12 - 3 / 10)}
    gates = call_rate_gates(cells)
    assert gates["monotonicity"]["call_rate_by_rung"] == {"R0": pytest.approx(6 / 12)}


def test_a_cell_row_round_trips_through_the_artifact() -> None:
    cell = RungCell(
        rung="R4",
        variant=VARIANT_UNNECESSARY,
        runs=5,
        calling_runs=2,
        memory_calls=7,
        read_calls=5,
        write_calls=2,
        reading_runs=2,
        writing_runs=1,
        paid=True,
        verbs=("native_read", "recall"),
        work_id="w-7",
        timed_out_runs=1,
    )
    assert RungCell.from_row(cell.row()) == cell
    assert cell.key == ("R4", VARIANT_UNNECESSARY, "w-7")


def test_staged_cells_keeps_landed_cells_and_buys_only_the_rest(tmp_path: Any) -> None:
    """Resume: a cell already keyed ``(rung, variant, work_id)`` in ``landed`` is returned in place
    and its runner is never invoked. The kept cell is distinguishable from a re-run (its counts are
    ones the runner could not produce), so a resume that quietly re-bought it would show."""
    _seqs, tasks = corpus_one(tmp_path)
    spawned: list[str] = []

    def counting(argv: Any, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        spawned.append(" ".join(argv))
        return subprocess.CompletedProcess(list(argv), 0, serialize_stream([result_event()]), "")

    prior = RungCell(
        rung="R0",
        variant=tasks[0].variant,
        runs=1,
        calling_runs=1,
        memory_calls=9,
        read_calls=9,
        write_calls=0,
        reading_runs=1,
        writing_runs=0,
        paid=True,
        work_id=tasks[0].work_id,
    )
    cells = e1_grid.staged_cells(
        tasks,
        model=MODEL,
        corpus_dir=tmp_path / "corpus",
        rungs=("R0", "R4"),
        n_tasks=1,
        repeats=1,
        runner=counting,
        landed=[prior],
    )
    key = (tasks[0].variant, tasks[0].work_id)
    assert [c.key for c in cells] == [("R0", *key), ("R4", *key)]
    assert cells[0] is prior
    assert cells[1].memory_calls == 0
    assert len(spawned) == 1


IDENTITY = {"cli_version": "9.9.9", "corpus": "corpus-abc", "repeats": 5}


def _fake_cells(tasks: Any) -> Any:
    """``run_rung_cell`` without the spawn: the CLI paths under test are the resume, the lock, the
    artifact and the halts, and driving those through a real sandbox per leg buys nothing but
    minutes."""

    def make(task: Any, **kwargs: Any) -> RungCell:
        on_leg = kwargs.get("on_leg")
        if on_leg is not None:
            for i in range(int(kwargs["repeats"])):
                on_leg(
                    LegRecord(
                        rung=str(kwargs["rung"]),
                        variant=task.variant,
                        work_id=task.work_id,
                        leg=i,
                        status="ok",
                        memory_calls=1,
                        read_calls=1,
                        stream='{"type":"result"}',
                    )
                )
        return RungCell(
            rung=str(kwargs["rung"]),
            variant=task.variant,
            runs=int(kwargs["repeats"]),
            calling_runs=int(kwargs["repeats"]),
            memory_calls=int(kwargs["repeats"]),
            read_calls=int(kwargs["repeats"]),
            write_calls=0,
            reading_runs=int(kwargs["repeats"]),
            writing_runs=0,
            paid=True,
            work_id=task.work_id,
        )

    return make


def _identified(cells: list[RungCell], **over: Any) -> dict[str, Any]:
    return summarize(
        cells,
        model=MODEL,
        dry_run=False,
        repeats=5,
        cli_version=str(IDENTITY["cli_version"]),
        corpus=str(IDENTITY["corpus"]),
        **over,
    )


def test_resume_refuses_another_rigs_artifact_and_drops_unmeasured_cells() -> None:
    dead = RungCell(
        rung="R0",
        variant=VARIANT_NECESSARY,
        runs=5,
        calling_runs=0,
        memory_calls=0,
        read_calls=0,
        write_calls=0,
        reading_runs=0,
        writing_runs=0,
        paid=True,
        work_id="w-dead",
        timed_out_runs=5,
    )
    live = _cell("R0", VARIANT_UNNECESSARY, calling=2, runs=5, work_id="w-live")
    summary = _identified([dead, live])
    assert resume_cells(summary, model=MODEL, **IDENTITY) == [live]
    with pytest.raises(ResumeMismatchError, match="model"):
        resume_cells(summary, model="claude-other-model-2", **IDENTITY)
    with pytest.raises(ResumeMismatchError, match="surface_fingerprint"):
        resume_cells({**summary, "surface_fingerprint": "stale"}, model=MODEL, **IDENTITY)


def test_resume_refuses_an_artifact_from_another_execution_protocol() -> None:
    """Review F4. The sandbox guard, the PWD pin, the session runner and the timeout scoring all
    change what a leg MEASURES without moving the tool surface, the binary or the corpus. They
    are versioned as one number, and a partial artifact that does not carry THIS number (an
    older one, or none at all) is refused as loudly as a stale fingerprint."""
    summary = _identified([_cell("R0", VARIANT_NECESSARY, calling=2, runs=5, work_id="w-0")])
    assert summary["execution_protocol"] == e1_grid.EXECUTION_PROTOCOL_VERSION
    assert e1_grid.EXECUTION_PROTOCOL_VERSION >= 1
    with pytest.raises(ResumeMismatchError, match="execution_protocol"):
        resume_cells(
            {**summary, "execution_protocol": e1_grid.EXECUTION_PROTOCOL_VERSION + 1},
            model=MODEL,
            **IDENTITY,
        )
    with pytest.raises(ResumeMismatchError, match="execution_protocol"):
        resume_cells(
            {k: v for k, v in summary.items() if k != "execution_protocol"},
            model=MODEL,
            **IDENTITY,
        )


def test_resume_refuses_every_identity_field_it_cannot_match() -> None:
    """Each field names something that changes what a leg MEASURES, so each one alone is enough to
    refuse: a different binary, a different corpus, a different number of legs per cell."""
    summary = _identified([_cell("R0", VARIANT_NECESSARY, calling=2, runs=5, work_id="w-0")])
    with pytest.raises(ResumeMismatchError, match="cli_version"):
        resume_cells(summary, model=MODEL, **{**IDENTITY, "cli_version": "9.9.10"})
    with pytest.raises(ResumeMismatchError, match="corpus_fingerprint"):
        resume_cells(summary, model=MODEL, **{**IDENTITY, "corpus": "corpus-xyz"})
    with pytest.raises(ResumeMismatchError, match="repeat"):
        resume_cells(summary, model=MODEL, **{**IDENTITY, "repeats": 3})
    # A blank field on the RIG is a refusal too: an identity it cannot state cannot be matched.
    with pytest.raises(ResumeMismatchError, match="cannot state its own"):
        resume_cells(summary, model=MODEL, **{**IDENTITY, "cli_version": ""})


def test_resume_drops_unpaid_and_unkeyed_rows_and_refuses_duplicates_and_strangers() -> None:
    """The filters and the refusals are different answers to different problems, and which is
    which is load-bearing.

    An unpaid row is a FIXTURE's call rate and a row with no ``work_id`` keys to a cell no task
    has: both are dropped, and the real cells get bought. A duplicate key or a cell outside this
    grid means the artifact was written by a fire this one is not continuing — nothing here can
    pick the right row, so it refuses rather than publishing half of each."""
    paid = _cell("R0", VARIANT_NECESSARY, calling=2, runs=5, work_id="w-0")
    unpaid = RungCell(
        rung="R0",
        variant=VARIANT_UNNECESSARY,
        runs=5,
        calling_runs=5,
        memory_calls=5,
        read_calls=5,
        write_calls=0,
        reading_runs=5,
        writing_runs=0,
        paid=False,
        work_id="w-0",
    )
    unkeyed = _cell("R4", VARIANT_NECESSARY, calling=3, runs=5)
    assert resume_cells(_identified([paid, unpaid, unkeyed]), model=MODEL, **IDENTITY) == [paid]

    dup = _identified([paid, paid])
    with pytest.raises(ResumeMismatchError, match="twice"):
        resume_cells(dup, model=MODEL, **IDENTITY)

    with pytest.raises(ResumeMismatchError, match="not a cell of the grid"):
        resume_cells(
            _identified([paid]), model=MODEL, grid=[("R0", VARIANT_NECESSARY, "w-9")], **IDENTITY
        )


def test_grid_keys_names_exactly_the_cells_the_fire_buys(tmp_path: Any) -> None:
    """The set a resume is checked against is built by the same per-variant slice the fire
    executes, so a row can never be refused as a stranger to a grid that will in fact buy it."""
    _seqs, tasks = corpus_one(tmp_path)
    keys = grid_keys(tasks, rungs=("R0", "R4"), n_tasks=1)
    spawned: list[Any] = []

    def counting(argv: Any, **kwargs: object) -> subprocess.CompletedProcess[str]:
        spawned.append(argv)
        return _calling_runner()(argv, **kwargs)

    cells = e1_grid.staged_cells(
        tasks,
        model=MODEL,
        corpus_dir=tmp_path / "corpus",
        rungs=("R0", "R4"),
        n_tasks=1,
        repeats=1,
        runner=counting,
    )
    assert [cell.key for cell in cells] == keys


def test_the_corpus_fingerprint_moves_when_a_task_does(tmp_path: Any) -> None:
    """Order is not a measured input; the task set is. A twin whose request changed is a different
    measurement, and this is the field that stops a resume pooling it with the old one."""
    _seqs, tasks = corpus_one(tmp_path)
    twin = replace(tasks[0], variant=VARIANT_UNNECESSARY)
    both = [tasks[0], twin]
    assert corpus_fingerprint(both) == corpus_fingerprint(list(reversed(both)))
    assert corpus_fingerprint(both) != corpus_fingerprint(tasks)
    reworded = replace(
        twin,
        goal_step=twin.goal_step.model_copy(
            update={"user_request": f"{twin.goal_step.user_request} (and the other two subjects)"}
        ),
    )
    assert corpus_fingerprint([tasks[0], reworded]) != corpus_fingerprint(both)


def test_every_leg_is_persisted_with_the_stream_it_was_counted_from(tmp_path: Any) -> None:
    """The cell is a count; the leg is the evidence under it.

    Every counter change this rig has made changed what a leg SCORES, and a scoring fix with no
    stream to re-score costs the whole grid again in real money. The stream is redacted on the way
    out: an evidence file outlives the reason it was kept, and the env this runs under carries an
    OAuth token."""
    _seqs, tasks = corpus_one(tmp_path)
    legs: list[LegRecord] = []
    cell = e1_grid.run_rung_cell(
        tasks[0],
        rung="R4",
        repeats=3,
        model=MODEL,
        dry_run=False,
        runner=_timing_out_runner({1}, "bd recall k", ("bd remember k=v", "Remembered [k]: v")),
        on_leg=legs.append,
    )
    assert [leg.status for leg in legs] == ["ok", "timeout", "ok"]
    assert [leg.leg for leg in legs] == [0, 1, 2]
    assert {leg.work_id for leg in legs} == {tasks[0].work_id}
    ok = [leg for leg in legs if leg.status == "ok"]
    # The legs RECONSTRUCT the cell: same calls, same read/write split. A per-leg record that
    # cannot be summed back to the cell it came from is not evidence for that cell.
    assert sum(leg.memory_calls for leg in ok) == cell.memory_calls
    assert sum(leg.read_calls for leg in ok) == cell.read_calls
    assert sum(leg.write_calls for leg in ok) == cell.write_calls
    assert all("bd recall k" in leg.stream for leg in ok)
    timed_out = next(leg for leg in legs if leg.status == "timeout")
    assert timed_out.stream == "" and timed_out.detail
    assert timed_out.truncated is True
    assert all(leg.truncated is False for leg in ok)
    assert legs[0].filename == f"R4__{tasks[0].variant}__{tasks[0].work_id}__0.json"


def test_a_refused_bd_remember_is_a_memory_call_but_never_a_write(tmp_path: Any) -> None:
    """mem-8fv4t. The 160-leg staged fire scored write_calls=1 from exactly this record: the agent
    ran `bd remember list`, bd REFUSED it, and the verb-token counter scored the refusal as an
    endogenous write. A write is scored only on bd's own acknowledgement in the persisted stream.
    The reach still happened, so the leg stays a CALLING run; it just wrote nothing."""
    _seqs, tasks = corpus_one(tmp_path)
    cell = e1_grid.run_rung_cell(
        tasks[0],
        rung="R4",
        repeats=1,
        model=MODEL,
        dry_run=False,
        runner=_calling_runner((REFUSED_REMEMBER_LIST, REFUSED_REMEMBER_LIST_RESULT)),
    )
    assert (cell.memory_calls, cell.calling_runs) == (1, 1)
    assert cell.write_calls == 0
    assert cell.read_calls == 0


def test_an_acknowledged_bd_remember_is_scored_a_write(tmp_path: Any) -> None:
    """The positive twin of the refusal test: same verb, and bd's `Remembered [k]:` line in the
    tool_result. The two tests differ ONLY in the result text, which is what the scorer must key
    on, so a scorer that ignores results cannot pass both."""
    _seqs, tasks = corpus_one(tmp_path)
    cell = e1_grid.run_rung_cell(
        tasks[0],
        rung="R4",
        repeats=1,
        model=MODEL,
        dry_run=False,
        runner=_calling_runner(("bd remember 'a value' --key k", REMEMBERED)),
    )
    assert (cell.memory_calls, cell.calling_runs) == (1, 1)
    assert cell.write_calls == 1
    assert cell.read_calls == 0


def test_a_bare_key_bd_remember_that_bd_recalled_is_scored_a_read(tmp_path: Any) -> None:
    """`bd remember <existing-key>` READS: bd answers `(recalled "k" -- ...)` and stores nothing."""
    _seqs, tasks = corpus_one(tmp_path)
    recalled = (
        '(recalled "k" -- a bare existing key READS. To overwrite: bd remember "..." --key k)\n'
        "a value"
    )
    cell = e1_grid.run_rung_cell(
        tasks[0],
        rung="R4",
        repeats=1,
        model=MODEL,
        dry_run=False,
        runner=_calling_runner(("bd remember k", recalled)),
    )
    assert (cell.memory_calls, cell.read_calls, cell.write_calls) == (1, 1, 0)


def test_a_bd_remember_with_no_tool_result_in_the_stream_is_not_a_write(tmp_path: Any) -> None:
    """No acknowledgement, no write. A stream that lost its tool_result (a leg cut off mid-call)
    must not be scored as if bd had accepted the memory."""
    _seqs, tasks = corpus_one(tmp_path)
    cell = e1_grid.run_rung_cell(
        tasks[0],
        rung="R4",
        repeats=1,
        model=MODEL,
        dry_run=False,
        runner=_calling_runner("bd remember 'a value' --key k"),
    )
    assert (cell.memory_calls, cell.write_calls) == (1, 0)


def test_a_json_acknowledged_bd_remember_is_scored_a_write(tmp_path: Any) -> None:
    """`bd remember --json` acknowledges as `{"action": "remembered"}`, not the prose line."""
    _seqs, tasks = corpus_one(tmp_path)
    ack = '{"action":"remembered","key":"k","content":"a value"}'
    cell = e1_grid.run_rung_cell(
        tasks[0],
        rung="R4",
        repeats=1,
        model=MODEL,
        dry_run=False,
        runner=_calling_runner(("bd remember 'a value' --key k --json", ack)),
    )
    assert cell.write_calls == 1


def test_a_secret_in_a_leg_stream_is_redacted_before_it_is_persisted(tmp_path: Any) -> None:
    """The stream is written to a file that outlives the run. Redaction happens where the record is
    BUILT, not where it is written, so a caller that persists it some other way cannot leak."""
    _seqs, tasks = corpus_one(tmp_path)
    legs: list[LegRecord] = []

    def leaky(argv: Any, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        events = [
            assistant_event([("Bash", {"command": "bd recall k"})]),
            result_event("token sk-ant-oat01-DEADBEEFdeadbeefDEADBEEFdeadbeef0123456789ab"),
        ]
        return subprocess.CompletedProcess(list(argv), 0, serialize_stream(events), "")

    e1_grid.run_rung_cell(
        tasks[0], rung="R0", repeats=1, model=MODEL, dry_run=False, runner=leaky, on_leg=legs.append
    )
    assert "DEADBEEFdeadbeef" not in legs[0].stream
    assert "bd recall k" in legs[0].stream


def test_the_out_file_is_written_atomically(tmp_path: Any) -> None:
    """A truncate-then-write leaves a window where the file that makes a resume possible is a
    partial file, and a kill inside it costs every cell the fire has bought.

    Content and a clean tmp are NOT enough to assert here: a copy-over-the-top passes both while
    still writing in place. What separates a rename from a copy is observable, so assert THAT — the
    destination gets a new inode, and a reader holding the old file keeps reading the old bytes
    rather than watching them change underneath it (an isolated-revert mutant that swapped
    ``os.replace`` for ``shutil.copyfile`` survived the weaker assertions)."""
    out = tmp_path / "summary.json"
    out.write_text('{"cells": []}', encoding="utf-8")
    before = out.stat().st_ino
    held = out.open("rb")
    try:
        e1_grid.atomic_write_json(out, {"cells": [1, 2, 3]})
        assert json.loads(out.read_text(encoding="utf-8")) == {"cells": [1, 2, 3]}
        assert list(tmp_path.glob("*.tmp-*")) == []
        assert out.stat().st_ino != before
        assert json.loads(held.read().decode("utf-8")) == {"cells": []}
    finally:
        held.close()


def test_two_fires_cannot_share_one_out_file(tmp_path: Any) -> None:
    """Both would resume from it, both would re-buy the cells the other is buying, and the last
    writer would publish its own half as the grid."""
    out = tmp_path / "summary.json"
    with e1_grid.out_lock(out):
        assert (tmp_path / "summary.json.lock").exists()
        with pytest.raises(ResumeMismatchError, match="another fire holds"), e1_grid.out_lock(out):
            pass
    assert not (tmp_path / "summary.json.lock").exists()
    # Released on the way out of a FAILING fire too, or one crash locks the artifact forever.
    with pytest.raises(RuntimeError, match="boom"), e1_grid.out_lock(out):
        raise RuntimeError("boom")
    assert not (tmp_path / "summary.json.lock").exists()


def test_fire_staged_resumes_from_its_own_out_file(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """End to end through the CLI: a --fire-staged pointed at an --out written by a rig with a
    different surface fingerprint is REFUSED, so a mid-run upgrade cannot land in the old grid."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    monkeypatch.setattr(e1_grid, "resolve_cli_version", lambda: "9.9.9")
    _seqs, _tasks = corpus_one(tmp_path)
    out = tmp_path / "partial.json"
    cell = _cell("R0", VARIANT_NECESSARY, calling=1, work_id="w-0")
    summary = _identified([cell])
    out.write_text(json.dumps({**summary, "surface_fingerprint": "stale"}), encoding="utf-8")
    argv = ["--corpus-dir", str(tmp_path / "corpus"), "--fire-staged", "--model", MODEL]
    code = e1_grid.main([*argv, "--out", str(out)])
    assert code == e1_grid.EXIT_REFUSED
    assert "REFUSED" in capsys.readouterr().err


def test_a_fire_publishes_the_grid_it_ran_and_the_legs_under_it(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """What --out holds when the fire finishes is what stdout printed. They diverged before: --out
    was last written by the per-cell accumulator, so a resumed fire published the accumulator's
    order and the reader of the file got a different grid from the reader of the pipe."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    monkeypatch.setattr(e1_grid, "resolve_cli_version", lambda: "9.9.9")
    monkeypatch.setattr(e1_grid, "STAGED_REPEATS", 1)
    _seqs, tasks = corpus_one(tmp_path)
    monkeypatch.setattr(e1_grid, "run_rung_cell", _fake_cells(tasks))
    out = tmp_path / "summary.json"
    code = e1_grid.main(
        [
            "--corpus-dir",
            str(tmp_path / "corpus"),
            "--fire-staged",
            "--model",
            MODEL,
            "--out",
            str(out),
        ]
    )
    assert code == e1_grid.EXIT_OK
    printed = json.loads(capsys.readouterr().out)
    assert json.loads(out.read_text(encoding="utf-8")) == printed
    assert printed["cli_version"] == "9.9.9"
    _, twins = load_twin_corpus(tmp_path / "corpus")
    assert printed["corpus_fingerprint"] == corpus_fingerprint(twins)
    assert printed["rungs"] == ["R0", "R4"]
    # Both halves of the twin, at both ends of the ladder: the grid the fire actually buys.
    assert [(row["rung"], row["variant"]) for row in printed["cells"]] == [
        (rung, variant)
        for rung in ("R0", "R4")
        for variant in (VARIANT_NECESSARY, VARIANT_UNNECESSARY)
    ]
    assert not (tmp_path / "summary.json.lock").exists()
    legs = sorted(path.name for path in (tmp_path / "summary.json.legs").iterdir())
    assert legs == sorted(
        f"{rung}__{variant}__{tasks[0].work_id}__0.json"
        for rung in ("R0", "R4")
        for variant in (VARIANT_NECESSARY, VARIANT_UNNECESSARY)
    )


def test_a_resumed_fire_publishes_the_grid_order_not_the_order_it_bought_them_in(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The per-cell accumulator writes ``--out`` as the fire goes, and the accumulator is ordered
    RESUMED-FIRST, then newly bought. The grid is ordered by (rung, variant, task). Those coincide
    on a fresh fire, which is why a mutant that dropped the final rewrite survived the fresh-fire
    test. Resume the LAST two cells of the grid so the two orders genuinely disagree, and pin that
    --out publishes the grid."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    monkeypatch.setattr(e1_grid, "resolve_cli_version", lambda: "9.9.9")
    monkeypatch.setattr(e1_grid, "STAGED_REPEATS", 1)
    _seqs, tasks = corpus_one(tmp_path)
    monkeypatch.setattr(e1_grid, "run_rung_cell", _fake_cells(tasks))
    _, twins = load_twin_corpus(tmp_path / "corpus")
    work_id = tasks[0].work_id

    # R4 is the TAIL of the grid; resuming it and buying R0 puts the accumulator at R4,R4,R0,R0.
    out = tmp_path / "summary.json"
    resumed = [
        _cell("R4", VARIANT_NECESSARY, calling=1, runs=1, work_id=work_id),
        _cell("R4", VARIANT_UNNECESSARY, calling=0, runs=1, work_id=work_id),
    ]
    out.write_text(
        json.dumps(
            summarize(
                resumed,
                model=MODEL,
                dry_run=False,
                repeats=1,
                cli_version="9.9.9",
                corpus=corpus_fingerprint(twins),
            )
        ),
        encoding="utf-8",
    )

    code = e1_grid.main(
        [
            "--corpus-dir",
            str(tmp_path / "corpus"),
            "--fire-staged",
            "--model",
            MODEL,
            "--out",
            str(out),
        ]
    )
    assert code == e1_grid.EXIT_OK
    printed = json.loads(capsys.readouterr().out)
    grid_order = [
        (rung, variant)
        for rung in ("R0", "R4")
        for variant in (VARIANT_NECESSARY, VARIANT_UNNECESSARY)
    ]
    assert [(row["rung"], row["variant"]) for row in printed["cells"]] == grid_order
    # The whole point: the file and the pipe agree, and both hold the grid.
    assert json.loads(out.read_text(encoding="utf-8")) == printed
    # Only the two R0 cells were bought; the R4 pair came back from the artifact untouched.
    assert sum(1 for row in printed["cells"] if row["rung"] == "R4") == 2


def test_a_halt_on_the_very_first_cell_still_leaves_an_artifact(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every completed cell persists ``--out`` on its way out, so a halt LATER in the fire is
    already covered by the last cell's write. The uncovered case is a halt before any cell
    completes: without the halt handler's own write there is no artifact at all, and the operator
    is left with a legs directory and no record of which rig produced it."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    monkeypatch.setattr(e1_grid, "resolve_cli_version", lambda: "9.9.9")
    monkeypatch.setattr(e1_grid, "STAGED_REPEATS", 1)
    _seqs, _tasks = corpus_one(tmp_path)

    def refuse_immediately(task: Any, **kwargs: Any) -> RungCell:
        raise e1_grid.QuotaHaltError("the account refused the call")

    monkeypatch.setattr(e1_grid, "run_rung_cell", refuse_immediately)
    out = tmp_path / "summary.json"
    code = e1_grid.main(
        [
            "--corpus-dir",
            str(tmp_path / "corpus"),
            "--fire-staged",
            "--model",
            MODEL,
            "--out",
            str(out),
        ]
    )
    assert code == e1_grid.EXIT_HALT
    assert out.exists()
    kept = json.loads(out.read_text(encoding="utf-8"))
    assert kept["cells"] == []
    # The identity is the part worth keeping: it says which rig halted, so the next fire can tell
    # a resume from a restart.
    assert kept["cli_version"] == "9.9.9"
    assert kept["model"] == MODEL
    assert not (tmp_path / "summary.json.lock").exists()


def test_a_quota_refusal_mid_fire_keeps_what_it_bought(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The second staged fire died here and lost the in-flight cell's paid legs. A quota halt is a
    clean stop: the artifact holds every cell already bought, and the same command resumes."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    monkeypatch.setattr(e1_grid, "resolve_cli_version", lambda: "9.9.9")
    monkeypatch.setattr(e1_grid, "STAGED_REPEATS", 1)
    _seqs, tasks = corpus_one(tmp_path)
    made = _fake_cells(tasks)

    def quota_on_the_second(task: Any, **kwargs: Any) -> RungCell:
        if kwargs["rung"] == "R4":
            raise e1_grid.QuotaHaltError("the account refused the call")
        return made(task, **kwargs)

    monkeypatch.setattr(e1_grid, "run_rung_cell", quota_on_the_second)
    out = tmp_path / "summary.json"
    code = e1_grid.main(
        [
            "--corpus-dir",
            str(tmp_path / "corpus"),
            "--fire-staged",
            "--model",
            MODEL,
            "--out",
            str(out),
        ]
    )
    assert code == e1_grid.EXIT_HALT
    assert "HALT" in capsys.readouterr().err
    kept = json.loads(out.read_text(encoding="utf-8"))
    assert [row["rung"] for row in kept["cells"]] == ["R0", "R0"]
    assert kept["cli_version"] == "9.9.9"
    assert not (tmp_path / "summary.json.lock").exists()


# --------------------------------------------------------------------------------------
# the dead-run family: a leg that exited 0 without running
#
# `run_checked` raises on a NON-ZERO exit and nothing else, so the whole classification ladder
# above — quota, timeout, error — is reached only when the CLI exits non-zero. Everything that
# exits 0 arrives at the counter, which asks the stream how many memory calls it carries and gets
# the honest answer: none, because nothing ran. That leg is then scored as a MEASURED run on which
# the agent chose not to touch memory, which is the exact reading this experiment exists to
# refuse, manufactured by the rig rather than produced by the agent.
# --------------------------------------------------------------------------------------


def _dead_runner(**result_fields: Any) -> Any:
    """A `claude -p` stand-in that EXITS 0 while its own result event reports the run failed.

    Zero tool calls, because a refused run makes none. The fields are the CLI's own — the same
    `api_error_status` / `is_error` the raising path is classified on."""

    def runner(argv: Any, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        events = [{"type": "result", "result": "", **result_fields}]
        return subprocess.CompletedProcess(list(argv), 0, serialize_stream(events), "")

    return runner


def test_a_leg_that_exits_zero_carrying_a_quota_status_halts_instead_of_scoring_a_zero(
    tmp_path: Any,
) -> None:
    """An exhausted account, if it ever exits 0, must not buy the rest of the grid.

    Without this the whole authorization is spent against a dead account, every cell reads 0.0,
    and the gate block publishes a manufactured null over it. The refusal is read off the stream's
    own `api_error_status`, the same field and the same `QUOTA_STATUSES` set the raising path
    uses — one classifier, reached from both sides."""
    _seqs, tasks = corpus_one(tmp_path)
    with pytest.raises(e1_grid.QuotaHaltError) as excinfo:
        e1_grid.run_rung_cell(
            tasks[0],
            rung="R4",
            repeats=5,
            model=MODEL,
            dry_run=False,
            runner=_dead_runner(is_error=True, api_error_status=429),
        )
    assert "429" in str(excinfo.value)


def test_a_leg_that_exits_zero_declaring_its_own_failure_is_unmeasured_not_silent(
    tmp_path: Any,
) -> None:
    """`is_error` with no api status — a failed run that is not the account's fault.

    It leaves the DENOMINATOR, exactly as a timeout does. Two of the three legs return normally,
    so the rate is 2/2 and not 2/3: a dead leg scored as a non-calling one drags the measured rate
    toward zero, and zero at the top rung is the verdict that ends the experiment."""
    _seqs, tasks = corpus_one(tmp_path)
    calling = _calling_runner("bd recall k")
    dead = _dead_runner(is_error=True)
    legs = {"n": 0}

    def mixed(argv: Any, **kwargs: object) -> subprocess.CompletedProcess[str]:
        i = legs["n"]
        legs["n"] += 1
        result: subprocess.CompletedProcess[str] = (dead if i == 1 else calling)(argv, **kwargs)
        return result

    cell = e1_grid.run_rung_cell(
        tasks[0], rung="R0", repeats=3, model=MODEL, dry_run=False, runner=mixed
    )
    assert cell.runs == 3
    assert cell.errored_runs == 1
    assert cell.timed_out_runs == 0
    assert cell.measured_runs == 2
    assert cell.calling_runs == 2
    assert cell.call_rate == pytest.approx(1.0)


def test_a_result_event_without_the_error_flag_is_a_measured_leg(tmp_path: Any) -> None:
    """The negative half: `is_error` ABSENT, and `is_error: false`, are both ordinary legs.

    A detector that treated a missing field as a failure would score every healthy leg unmeasured
    and report a grid of zeros as an infrastructure problem."""
    assert e1_grid.stream_is_error(serialize_stream([result_event()])) is False
    ok = serialize_stream([{"type": "result", "is_error": False}])
    assert e1_grid.stream_is_error(ok) is False
    assert e1_grid.stream_is_error(serialize_stream([{"type": "result", "is_error": True}])) is True
    # Not any event that carries the flag — a TOOL result that failed is not a failed RUN.
    assert e1_grid.stream_is_error(serialize_stream([{"type": "user", "is_error": True}])) is False


# --------------------------------------------------------------------------------------
# the halt budget: what "the rig is broken" counts
# --------------------------------------------------------------------------------------


def test_a_rig_whose_every_leg_times_out_halts_rather_than_burning_the_grid(
    tmp_path: Any,
) -> None:
    """Timeouts count toward the halt. They did not, and that is the shape that actually burns a
    budget: an account whose every spawn hangs fills each cell with five unmeasured legs at up to
    `timeout_s` apiece, trips no limit that counts only errors, and leaves a grid the next resume
    drops and re-buys."""
    _seqs, tasks = corpus_one(tmp_path)
    with pytest.raises(e1_grid.RigHaltError):
        e1_grid.run_rung_cell(
            tasks[0],
            rung="R0",
            repeats=5,
            model=MODEL,
            dry_run=False,
            runner=_timing_out_runner({0, 1, 2, 3, 4}, "bd recall k"),
        )


def test_alternating_failures_halt_even_though_neither_kind_repeats(tmp_path: Any) -> None:
    """timeout, error, timeout: three consecutive UNMEASURED legs and never two of a kind.

    A counter that tracked errors and timeouts separately saw one of each and tolerated all of
    them. The question the budget asks is not which way the leg failed, it is whether anything is
    still being measured."""
    _seqs, tasks = corpus_one(tmp_path)
    legs = {"n": 0}

    def alternating(argv: Any, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        i = legs["n"]
        legs["n"] += 1
        if i % 2 == 0:
            raise _timeout_error()
        raise HeadlessAgentError("claude -p failed (exit 1): transient")

    with pytest.raises(e1_grid.RigHaltError):
        e1_grid.run_rung_cell(
            tasks[0], rung="R0", repeats=5, model=MODEL, dry_run=False, runner=alternating
        )


def test_a_measured_leg_clears_the_streak(tmp_path: Any) -> None:
    """Two failures, a good leg, two more failures: five legs, four unmeasured, no halt.

    The limit is CONSECUTIVE, and a rig that still returns streams is flaky, not broken. Without
    the reset a merely flaky account halts a fire that was working."""
    _seqs, tasks = corpus_one(tmp_path)
    calling = _calling_runner("bd recall k")
    legs = {"n": 0}

    def flaky(argv: Any, **kwargs: object) -> subprocess.CompletedProcess[str]:
        i = legs["n"]
        legs["n"] += 1
        if i == 2:
            result: subprocess.CompletedProcess[str] = calling(argv, **kwargs)
            return result
        raise HeadlessAgentError("claude -p failed (exit 1): transient")

    cell = e1_grid.run_rung_cell(
        tasks[0], rung="R0", repeats=5, model=MODEL, dry_run=False, runner=flaky
    )
    assert cell.errored_runs == 4
    assert cell.measured_runs == 1
    assert cell.calling_runs == 1


def test_the_unmeasured_streak_survives_a_cell_boundary(tmp_path: Any) -> None:
    """Two failures at the end of one cell and one at the start of the next is a broken rig.

    A counter local to `run_rung_cell` restarts at every cell, so a rig failing two legs per cell
    never reaches three in one place and buys the ENTIRE grid one unmeasured cell at a time. The
    streak is threaded through `staged_cells` for exactly this."""
    _seqs, tasks = corpus_one(tmp_path)
    attempts = {"n": 0}

    def always_fails(argv: Any, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        attempts["n"] += 1
        raise HeadlessAgentError("claude -p failed (exit 1): transient")

    with pytest.raises(e1_grid.RigHaltError):
        e1_grid.staged_cells(
            tasks,
            model=MODEL,
            corpus_dir=tmp_path / "corpus",
            rungs=STAGED_RUNGS,
            n_tasks=1,
            repeats=2,
            runner=always_fails,
        )
    # Two legs in the first cell, one in the second, then the halt: the streak crossed the
    # boundary. A per-cell counter would have spent every leg of every cell in the grid.
    assert attempts["n"] == 3


def test_the_streak_counts_both_kinds_and_resets_only_on_a_measurement() -> None:
    """The budget itself, as a unit: three of ANY mix trips it, and a measurement clears it."""
    streak = e1_grid.UnmeasuredStreak(limit=3)
    assert streak.unmeasured() is False
    assert streak.unmeasured() is False
    streak.measured()
    assert streak.unmeasured() is False
    assert streak.unmeasured() is False
    assert streak.unmeasured() is True


# --------------------------------------------------------------------------------------
# the preflight: one leg, and the verdict that ends the experiment
# --------------------------------------------------------------------------------------


def test_a_preflight_leg_that_measured_nothing_is_not_a_null() -> None:
    """The preflight runs ONE leg. A single spawn timeout returns a row with zero memory calls
    because nothing ran, and read as NO-MEMORY-CALL that row terminates E1 on its strongest
    verdict — the interior rungs are never bought and the null is published.

    UNMEASURED is a distinct kind, and it is tested BEFORE the call count."""
    kind, line = preflight_verdict(
        {
            "rung": "R4",
            "paid": True,
            "runs": 1,
            "measured_runs": 0,
            "timed_out_runs": 1,
            "errored_runs": 0,
            "memory_calls": 0,
        }
    )
    assert kind == e1_grid.HALT_UNMEASURED
    assert kind != HALT_NO_CALL
    assert "timed out" in line
    with pytest.raises(PreflightHaltError):
        preflight_gate({"rung": "R4", "paid": True, "measured_runs": 0, "memory_calls": 0})


def test_a_measured_preflight_leg_with_no_calls_is_still_the_null() -> None:
    """The other side: nothing here weakens the verdict the gate exists to reach. A leg that RAN
    and made no memory call is the halt it always was."""
    kind, _line = preflight_verdict(
        {"rung": "R4", "paid": True, "runs": 1, "measured_runs": 1, "memory_calls": 0}
    )
    assert kind == HALT_NO_CALL


def test_the_preflight_row_carries_what_it_measured(tmp_path: Any, monkeypatch: Any) -> None:
    """The producer's half: the row `preflight` returns has the fields the verdict reads.

    The defect was in neither piece on its own — the verdict grew an UNMEASURED branch and the row
    omitted the counters it reads, so on a real preflight that branch could never fire however
    correct it was. `preflight` takes no runner ON PURPOSE (there is no free path through a
    mechanism check), so the cell it builds is stubbed rather than a spawn being simulated."""
    _seqs, tasks = corpus_one(tmp_path)
    timed_out = RungCell(
        rung="R4",
        variant=tasks[0].variant,
        runs=1,
        calling_runs=0,
        memory_calls=0,
        read_calls=0,
        write_calls=0,
        reading_runs=0,
        writing_runs=0,
        paid=True,
        work_id=tasks[0].work_id,
        timed_out_runs=1,
    )
    monkeypatch.setattr(e1_grid, "run_rung_cell", lambda *a, **k: timed_out, raising=True)
    row = e1_grid.preflight(tasks[0], model=MODEL, corpus_dir=tmp_path / "corpus")
    assert row["runs"] == 1
    assert row["measured_runs"] == 0
    assert row["timed_out_runs"] == 1
    assert row["errored_runs"] == 0
    # End to end: the row this producer emits reaches the UNMEASURED verdict, not the null.
    assert preflight_verdict(row)[0] == e1_grid.HALT_UNMEASURED


# --------------------------------------------------------------------------------------
# the evidence: what a paid leg leaves behind
# --------------------------------------------------------------------------------------


def test_leg_evidence_keeps_the_whole_stream_not_a_head_and_tail(tmp_path: Any) -> None:
    """Leg streams were stored through the TRUNCATING redactor, which keeps a head and a tail and
    drops the middle. A `claude -p` stream is long and the tool calls are in the middle, so the
    stored evidence excised exactly the thing it exists to prove — and a re-count from the archive
    disagrees with the counter that ran, with no way to tell which is right.

    The bulk here is deliberate: enough that a head+tail window cannot reach the call."""
    _seqs, tasks = corpus_one(tmp_path)
    filler = [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "x" * 400}]}}
        for _ in range(60)
    ]
    events = [
        *filler,
        assistant_event([("Bash", {"command": "bd recall k"})]),
        *filler,
        result_event(),
    ]
    stream = serialize_stream(events)
    assert len(stream) > 12000

    def runner(argv: Any, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(list(argv), 0, stream, "")

    legs: list[LegRecord] = []
    cell = e1_grid.run_rung_cell(
        tasks[0],
        rung="R0",
        repeats=1,
        model=MODEL,
        dry_run=False,
        runner=runner,
        on_leg=legs.append,
    )
    assert cell.memory_calls == 1
    kept = legs[0].stream
    assert "bd recall k" in kept
    # The whole stream, so a re-count off the archive reproduces the counter that ran.
    assert len(kept) == len(stream)


def test_leg_evidence_never_overwrites_a_leg_that_was_paid_for(tmp_path: Any) -> None:
    """A fire halted MID-CELL re-runs that cell from leg 0, so the resumed leg 0 has the same
    ``(rung, variant, work_id, leg)`` filename as the one already bought. An overwrite there
    destroys evidence for a leg spent with real money; the second write lands beside the first."""
    path = tmp_path / "R0__necessary__w-0__0.json"
    first = e1_grid.write_json_new(path, {"leg": 0, "attempt": "before the halt"})
    second = e1_grid.write_json_new(path, {"leg": 0, "attempt": "after the resume"})
    third = e1_grid.write_json_new(path, {"leg": 0, "attempt": "and again"})
    assert first == path
    assert second == tmp_path / "R0__necessary__w-0__0.attempt1.json"
    assert third == tmp_path / "R0__necessary__w-0__0.attempt2.json"
    assert json.loads(first.read_text(encoding="utf-8"))["attempt"] == "before the halt"


def test_leg_evidence_is_owner_only(tmp_path: Any) -> None:
    """The stream is redacted, not clean: it carries the agent's prompts and outputs, and these
    files are written under a shared /tmp."""
    path = e1_grid.write_json_new(tmp_path / "leg.json", {"leg": 0})
    assert path.stat().st_mode & 0o077 == 0


def test_a_stale_lock_names_the_process_that_wrote_it(tmp_path: Any) -> None:
    """A lock left by a killed fire and a lock a LIVE fire holds refuse identically, and the
    operator's only move is then to delete a lock they cannot check. Carrying the pid makes the
    difference checkable (`ps -p`) instead of guessed."""
    out = tmp_path / "summary.json"
    with e1_grid.out_lock(out):
        holder = (tmp_path / "summary.json.lock").read_text(encoding="utf-8").strip()
        assert holder == str(os.getpid())
        with pytest.raises(RuntimeError) as excinfo, e1_grid.out_lock(out):
            pass
    assert holder in str(excinfo.value)
    assert "ps -p" in str(excinfo.value)
    # And released, so the next fire is not locked out by a fire that finished.
    assert not (tmp_path / "summary.json.lock").exists()


# --------------------------------------------------------------------------------------
# what the fire refuses, and what the grid may claim
# --------------------------------------------------------------------------------------


def test_a_binary_that_changes_mid_sweep_halts(tmp_path: Any) -> None:
    """The resume identity pins the CLI BETWEEN fires and is blind WITHIN one. A binary upgraded
    while a sweep runs measures the later cells on a different tool surface, and the fire pools
    both into one rate — the exact confound the identity check exists to refuse, arriving through
    the one door it does not watch."""
    _seqs, tasks = corpus_one(tmp_path)

    def upgraded(argv: Any, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        events = [
            {"type": "system", "subtype": "init", "claude_code_version": "2.1.300"},
            result_event(),
        ]
        return subprocess.CompletedProcess(list(argv), 0, serialize_stream(events), "")

    with pytest.raises(e1_grid.RigHaltError) as excinfo:
        e1_grid.run_rung_cell(
            tasks[0],
            rung="R0",
            repeats=5,
            model=MODEL,
            dry_run=False,
            runner=upgraded,
            expect_cli_version="2.1.258",
        )
    assert "2.1.300" in str(excinfo.value)
    # A leg that does not state its version is not a mismatch: the check is for a version that
    # DISAGREES, and treating silence as drift would halt a healthy fire.
    quiet = e1_grid.run_rung_cell(
        tasks[0],
        rung="R0",
        repeats=1,
        model=MODEL,
        dry_run=False,
        runner=_calling_runner("bd recall k"),
        expect_cli_version="2.1.258",
    )
    assert quiet.measured_runs == 1


def test_a_grid_that_measured_one_rung_does_not_publish_a_passing_monotonicity() -> None:
    """With one rung there is no adjacent pair, hence no violation, hence `monotone: true` — a
    passing-looking gate over a grid that tested nothing. Untested is not passed."""
    one = call_rate_gates([_cell("R4", VARIANT_NECESSARY, calling=5, runs=5)])["monotonicity"]
    assert one["monotone"] is True
    assert one["comparable"] is False
    assert "UNTESTED" in one["reason"]
    assert "Not a pass" in one["reason"]
    two = call_rate_gates(
        [
            _cell("R0", VARIANT_NECESSARY, calling=2, runs=5),
            _cell("R4", VARIANT_NECESSARY, calling=5, runs=5),
        ]
    )["monotonicity"]
    assert two["comparable"] is True
    assert "UNTESTED" not in two["reason"]


def test_resume_drops_a_cell_that_ran_a_different_number_of_legs() -> None:
    """A 3-leg row in a 5-leg grid weights wrong when pooled and cannot be completed in place.

    The artifact-level `repeats` check does not catch it: that compares one field, and a row can
    disagree with the very artifact that carries it (a hand edit, or a merge of two fires). Dropped
    means re-bought, and the legs already paid for survive as leg evidence."""
    short = _cell("R0", VARIANT_NECESSARY, calling=2, runs=3, work_id="w-0")
    full = _cell("R4", VARIANT_NECESSARY, calling=5, runs=5, work_id="w-0")
    summary = _identified([short, full])
    assert summary["repeats"] == 5
    assert resume_cells(summary, model=MODEL, **IDENTITY) == [full]


def test_the_plan_prices_the_smaller_variant_half() -> None:
    """`staged_cells` slices `[:n_tasks]` PER VARIANT, so a plan priced off the combined list
    promises twice the grid it runs whenever the twin halves are uneven."""

    class _T:
        def __init__(self, variant: str) -> None:
            self.variant = variant

    even = [_T(VARIANT_NECESSARY), _T(VARIANT_UNNECESSARY), _T(VARIANT_NECESSARY)]
    assert e1_grid.per_variant_task_count(even) == 1
    assert e1_grid.per_variant_task_count([]) == 0
    assert e1_grid.per_variant_task_count([_T(VARIANT_NECESSARY), _T(VARIANT_UNNECESSARY)]) == 1
    # Priced per variant, and the plan doubles it back for the two halves.
    assert (
        staged_plan(n_tasks_per_variant=1, n_variants=2)["calls"]
        == len(STAGED_RUNGS) * 1 * STAGED_REPEATS * 2
    )


def test_fire_staged_without_an_out_refuses_before_it_spends(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without ``--out`` this path spends the whole authorization and persists nothing: no resume,
    no leg evidence, no lock, and a summary that lives only in a terminal someone has to keep
    open. It refuses BEFORE the first leg, which is the only point at which refusing is free."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    monkeypatch.setattr(e1_grid, "resolve_cli_version", lambda: "9.9.9")
    monkeypatch.setattr(e1_grid, "STAGED_REPEATS", 1)
    _seqs, tasks = corpus_one(tmp_path)
    spent = {"legs": 0}

    def counting(task: Any, **kwargs: Any) -> RungCell:
        spent["legs"] += int(kwargs["repeats"])
        return _fake_cells(tasks)(task, **kwargs)

    monkeypatch.setattr(e1_grid, "run_rung_cell", counting)
    code = e1_grid.main(
        ["--corpus-dir", str(tmp_path / "corpus"), "--fire-staged", "--model", MODEL]
    )
    assert code == e1_grid.EXIT_REFUSED
    assert spent["legs"] == 0


def test_a_resume_keeps_the_provenance_the_prior_artifact_carried(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--out`` is rewritten from the resumed cells after every paid cell, so anything the prior
    artifact carried that ``summarize`` does not re-derive is erased by the first resumed cell.

    The block that matters is ``identity_backfilled``: the record of WHY a pre-hardening artifact
    was admissible into this grid. Losing it leaves a grid whose provenance is unstateable and
    whose paid cells therefore cannot be defended."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    monkeypatch.setattr(e1_grid, "resolve_cli_version", lambda: "9.9.9")
    monkeypatch.setattr(e1_grid, "STAGED_REPEATS", 1)
    _seqs, tasks = corpus_one(tmp_path)
    monkeypatch.setattr(e1_grid, "run_rung_cell", _fake_cells(tasks))
    _, twins = load_twin_corpus(tmp_path / "corpus")
    landed = RungCell(
        rung="R0",
        variant=tasks[0].variant,
        runs=1,
        calling_runs=1,
        memory_calls=1,
        read_calls=1,
        write_calls=0,
        reading_runs=1,
        writing_runs=0,
        paid=True,
        work_id=tasks[0].work_id,
    )
    note = {"reason": "produced before the exit-0 classifier landed", "reviewed": "mem-1qmoo"}
    out = tmp_path / "summary.json"
    out.write_text(
        json.dumps(
            summarize(
                [landed],
                model=MODEL,
                dry_run=False,
                repeats=1,
                cli_version="9.9.9",
                corpus=corpus_fingerprint(twins),
            )
            | {"identity_backfilled": note}
        ),
        encoding="utf-8",
    )
    code = e1_grid.main(
        [
            "--corpus-dir",
            str(tmp_path / "corpus"),
            "--fire-staged",
            "--model",
            MODEL,
            "--out",
            str(out),
        ]
    )
    assert code == e1_grid.EXIT_OK
    printed = json.loads(capsys.readouterr().out)
    assert printed["identity_backfilled"] == note
    assert json.loads(out.read_text(encoding="utf-8"))["identity_backfilled"] == note
    # And the carry does not fabricate the fields `summarize` owns.
    assert printed["cli_version"] == "9.9.9"
    assert len(printed["cells"]) == len(STAGED_RUNGS) * 2


def test_a_halt_leaves_out_holding_the_grid_the_resume_will_start_from(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After a halt, ``--out`` states the cells that will actually be resumed from, not the cells
    that happened to be in the file when the fire opened it.

    On a fresh fire the halt's write is indistinguishable from the per-cell one, because every
    COMPLETED cell has already been persisted by the time a mid-cell halt raises (an isolated-
    revert mutant that deleted the halt's persist survived the fresh-fire test for that reason).
    What separates them is a RESUME that drops a row: the prior artifact carries a cell this grid
    will re-buy, the fire halts before completing anything, and without the halt's write ``--out``
    still advertises the dropped cell as bought."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    monkeypatch.setattr(e1_grid, "resolve_cli_version", lambda: "9.9.9")
    monkeypatch.setattr(e1_grid, "STAGED_REPEATS", 1)
    _seqs, tasks = corpus_one(tmp_path)
    _, twins = load_twin_corpus(tmp_path / "corpus")
    work_id = tasks[0].work_id

    def _row(rung: str, variant: str, runs: int) -> RungCell:
        return RungCell(
            rung=rung,
            variant=variant,
            runs=runs,
            calling_runs=runs,
            memory_calls=runs,
            read_calls=runs,
            write_calls=0,
            reading_runs=runs,
            writing_runs=0,
            paid=True,
            work_id=work_id,
        )

    keep = _row("R0", VARIANT_NECESSARY, 1)
    # A cell of the right key but the wrong leg count: in the grid, so not a stranger, and
    # dropped by the resume because a 2-leg cell cannot be pooled with 1-leg cells.
    drop = _row("R4", VARIANT_UNNECESSARY, 2)
    out = tmp_path / "summary.json"
    out.write_text(
        json.dumps(
            summarize(
                [keep, drop],
                model=MODEL,
                dry_run=False,
                repeats=1,
                cli_version="9.9.9",
                corpus=corpus_fingerprint(twins),
            )
        ),
        encoding="utf-8",
    )

    def halts(task: Any, **kwargs: Any) -> RungCell:
        raise e1_grid.RigHaltError("three consecutive legs measured nothing")

    monkeypatch.setattr(e1_grid, "run_rung_cell", halts)
    code = e1_grid.main(
        [
            "--corpus-dir",
            str(tmp_path / "corpus"),
            "--fire-staged",
            "--model",
            MODEL,
            "--out",
            str(out),
        ]
    )
    assert code == e1_grid.EXIT_HALT
    kept = json.loads(out.read_text(encoding="utf-8"))
    assert [(c["rung"], c["variant"], c["metrics"]["runs"]) for c in kept["cells"]] == [
        ("R0", VARIANT_NECESSARY, 1)
    ]


# --------------------------------------------------------------------------------------
# mem-2vyej: R0 is silent by PIN — autoMemoryEnabled:false in the minted CLAUDE_CONFIG_DIR
# --------------------------------------------------------------------------------------


def _config_dir_witness() -> tuple[Any, list[dict[str, Any]]]:
    """A ``claude -p`` stand-in that reads the minted config dir AT SPAWN TIME — the only moment
    it exists — and keeps what it found there: the listing, and the parsed ``settings.json`` when
    one is present. The path is read off the env the cell handed the runner, so the fixture
    witnesses the dir the agent would have read, not one it chose."""
    seen: list[dict[str, Any]] = []

    def runner(argv: Any, **kwargs: object) -> subprocess.CompletedProcess[str]:
        env = kwargs.get("env")
        assert isinstance(env, dict)
        config = Path(env["CLAUDE_CONFIG_DIR"])
        settings = config / "settings.json"
        seen.append(
            {
                "entries": sorted(p.name for p in config.iterdir()),
                "settings": (
                    json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else None
                ),
            }
        )
        return subprocess.CompletedProcess(list(argv), 0, serialize_stream([result_event()]), "")

    return runner, seen


def test_r0_pins_native_memory_off_in_its_minted_config_dir(tmp_path: Any) -> None:
    """RULED "pin R0 off" (2026-09-03). An EMPTY config dir leaves the CLI's own auto-memory
    system prompt ON, so the floor rung was never silent: the first paid R4 cycle read the native
    memory path directly (mem-gj0pc), and at R0 that reach would be scored as unprompted
    disposition while a standing native instruction about memory prompted it (mem-zfm0m item 5).
    The pin is the same config-dir-local key the probe seeds false and the builtin arm seeds true,
    written through the same seeder, and it is read BACK off disk onto the leg and the cell."""
    _seqs, tasks = corpus_one(tmp_path)
    runner, seen = _config_dir_witness()
    legs: list[LegRecord] = []
    cell = e1_grid.run_rung_cell(
        tasks[0],
        rung="R0",
        repeats=2,
        model=MODEL,
        dry_run=False,
        runner=runner,
        on_leg=legs.append,
    )
    assert [s["settings"] for s in seen] == [{"autoMemoryEnabled": False}] * 2
    assert [s["entries"] for s in seen] == [["settings.json"]] * 2
    assert cell.native_memory_pinned_off is True
    assert [leg.native_memory_pinned_off for leg in legs] == [True, True]
    assert legs[0].row()["native_memory_pinned_off"] is True


@pytest.mark.parametrize("rung", RUNG_IDS[1:])
def test_the_guided_rungs_mint_an_empty_config_dir(tmp_path: Any, rung: str) -> None:
    """R1..R4 stay EXACTLY as they were: no settings.json, native memory at the CLI's default.
    They measure guidance on top of native memory, and pinning them would change what they
    measure. The read-back says so from disk, not from the table."""
    _seqs, tasks = corpus_one(tmp_path)
    runner, seen = _config_dir_witness()
    cell = e1_grid.run_rung_cell(
        tasks[0], rung=rung, repeats=1, model=MODEL, dry_run=False, runner=runner
    )
    assert seen == [{"entries": [], "settings": None}]
    assert cell.native_memory_pinned_off is False


def test_rung_settings_pins_only_the_floor_and_is_frozen() -> None:
    """The table covers every rung, pins exactly R0, and refuses an in-place edit — the same
    ``MappingProxyType`` discipline as ``toolreq_builtin.BUILTIN_SETTINGS``, for the same reason:
    a mutated table would diverge what is WRITTEN from what the identity HASHES."""
    assert tuple(e1_grid.RUNG_SETTINGS) == RUNG_IDS
    assert dict(e1_grid.rung_settings("R0")) == {"autoMemoryEnabled": False}
    assert all(not e1_grid.rung_settings(rung) for rung in RUNG_IDS[1:])
    with pytest.raises(TypeError):
        e1_grid.RUNG_SETTINGS["R0"]["autoMemoryEnabled"] = True  # type: ignore[index]
    with pytest.raises(TypeError):
        e1_grid.RUNG_SETTINGS["R1"] = {"autoMemoryEnabled": False}  # type: ignore[index]
    with pytest.raises(ValueError, match="unknown rung"):
        e1_grid.rung_settings("R9")


def test_legs_that_disagree_about_the_pin_halt_and_keep_what_was_paid_for(
    tmp_path: Any, monkeypatch: Any
) -> None:
    """A cell whose legs ran under different pin states is TWO floors, so it is not a rate.

    Reachable only through a fault -- every leg of a cell seeds the same rung table -- which is
    exactly why the refusal needs a test: nothing in normal operation exercises it, so a later
    change that softened it to `any(pinned)` would look green. The legs already bought are
    asserted to have reached the caller BEFORE the raise: a refusal that discarded them would
    throw away the paid evidence it is refusing to average (mem-zfm0m)."""
    _seqs, tasks = corpus_one(tmp_path)
    runner, _seen = _config_dir_witness()
    reads = iter([True, False])
    monkeypatch.setattr(e1_grid, "native_memory_pinned_off", lambda _dir: next(reads))
    legs: list[LegRecord] = []
    with pytest.raises(e1_grid.RigHaltError, match="two different floors"):
        e1_grid.run_rung_cell(
            tasks[0],
            rung="R0",
            repeats=2,
            model=MODEL,
            dry_run=False,
            runner=runner,
            on_leg=legs.append,
        )
    assert [leg.native_memory_pinned_off for leg in legs] == [True, False]


def test_the_pin_is_read_back_off_disk_not_off_the_intent(tmp_path: Any) -> None:
    """``native_memory_pinned_off`` is a READ of the minted dir: absent file, key true, and key
    false are three different answers, and only the last one is the pin."""
    config = tmp_path / "config"
    config.mkdir()
    assert e1_grid.native_memory_pinned_off(config) is False
    seed_config_dir(config, {"autoMemoryEnabled": True})
    assert e1_grid.native_memory_pinned_off(config) is False
    seed_config_dir(config, {"autoMemoryEnabled": False})
    assert e1_grid.native_memory_pinned_off(config) is True


def _unpinned(monkeypatch: Any) -> None:
    """The ladder as the 160-leg grid was bought: every rung minted EMPTY, R0 included."""
    monkeypatch.setattr(
        e1_grid,
        "RUNG_SETTINGS",
        types.MappingProxyType({rung: types.MappingProxyType({}) for rung in RUNG_IDS}),
    )


def test_the_pin_moves_the_settings_fingerprint_and_nothing_else(monkeypatch: Any) -> None:
    """Checked against ``headless_agent.seed_config_dir``, not assumed: the seed writes a FILE.
    Nothing in E1's identity read that file — ``surface_fingerprint`` digests the recognizer
    policy, ``execution_protocol`` is a hand-bumped integer, and the model, binary and corpus
    fields are what they say — so before this field an R0 bought pinned and an R0 bought unpinned
    hashed to ONE identity. The pin needs its own field, and toggling it moves exactly that one."""
    cell = _cell("R0", VARIANT_NECESSARY, calling=2, runs=5, work_id="w-0")
    pinned = _identified([cell])
    surface_before = surface_fingerprint()
    protocol_before = e1_grid.EXECUTION_PROTOCOL_VERSION
    _unpinned(monkeypatch)
    unpinned = _identified([cell])
    assert surface_fingerprint() == surface_before
    assert protocol_before == e1_grid.EXECUTION_PROTOCOL_VERSION
    assert pinned["settings_fingerprint"] != unpinned["settings_fingerprint"]
    assert unpinned["settings_fingerprint"] == e1_grid.rung_settings_fingerprint()
    assert {k for k in pinned if pinned[k] != unpinned[k]} == {"settings_fingerprint"}


def test_resume_refuses_an_artifact_counted_with_r0_unpinned(monkeypatch: Any) -> None:
    """An R0 cell bought before the ruling measured the agent under the CLI's own memory prompt;
    pooled into a pinned grid it would publish two floors as one. Both shapes of that artifact are
    refused — one hashed under the unpinned table, and one from before the field existed."""
    cell = _cell("R0", VARIANT_NECESSARY, calling=2, runs=5, work_id="w-0")
    current = _identified([cell])
    with monkeypatch.context() as m:
        _unpinned(m)
        stale = _identified([cell])
    assert resume_cells(current, model=MODEL, **IDENTITY) == [cell]
    with pytest.raises(ResumeMismatchError, match="settings_fingerprint"):
        resume_cells(stale, model=MODEL, **IDENTITY)
    with pytest.raises(ResumeMismatchError, match="settings_fingerprint"):
        resume_cells(
            {k: v for k, v in current.items() if k != "settings_fingerprint"},
            model=MODEL,
            **IDENTITY,
        )


def test_the_pin_rides_on_the_cell_row_and_a_row_without_it_cannot_resume() -> None:
    cell = RungCell(
        rung="R0",
        variant=VARIANT_NECESSARY,
        runs=5,
        calling_runs=1,
        memory_calls=1,
        read_calls=1,
        write_calls=0,
        reading_runs=1,
        writing_runs=0,
        paid=True,
        work_id="w-0",
        native_memory_pinned_off=True,
    )
    row = cell.row()
    assert row["native_memory_pinned_off"] is True
    assert "native_memory_pinned_off" not in row["metrics"]
    assert RungCell.from_row(row) == cell
    with pytest.raises(ValueError, match="native_memory_pinned_off"):
        RungCell.from_row({k: v for k, v in row.items() if k != "native_memory_pinned_off"})


def test_the_preflight_row_carries_the_cells_pin(tmp_path: Any, monkeypatch: Any) -> None:
    """The gated preflight row reports the pin, so a preflight artifact says which floor the
    mechanism check ran on.

    The CELL is what reads the config dir; `preflight` has no free path (no `dry_run`, no
    `runner`) and cannot be driven without spending, so `run_rung_cell` is replaced here and
    this test covers only the plumbing from cell to row to gate. The disk read itself is
    covered by `test_the_pin_is_read_back_off_disk_not_off_the_intent` and by the per-rung
    witnesses."""
    _seqs, tasks = corpus_one(tmp_path)
    for pinned in (True, False):
        fired = RungCell(
            rung="R0",
            variant=tasks[0].variant,
            runs=1,
            calling_runs=1,
            memory_calls=1,
            read_calls=1,
            write_calls=0,
            reading_runs=1,
            writing_runs=0,
            paid=True,
            work_id=tasks[0].work_id,
            native_memory_pinned_off=pinned,
        )
        # `fired` bound as a default: a bare closure over the loop variable would make both
        # iterations return whichever cell the loop ended on (ruff B023).
        monkeypatch.setattr(
            e1_grid,
            "run_rung_cell",
            lambda *a, _cell=fired, **k: _cell,
            raising=True,
        )
        row = e1_grid.preflight(tasks[0], model=MODEL, corpus_dir=tmp_path / "corpus", rung="R0")
        assert row["native_memory_pinned_off"] is pinned
        assert preflight_gate(row)["native_memory_pinned_off"] is pinned


# --- mem-k36dc: the interior rungs are reachable without a source edit ----------------


def test_the_authorized_ladder_slices_are_a_frozen_table() -> None:
    """R1-R3 exist in RUNG_TEXT and in RUNG_SETTINGS, and every function under the fire path takes
    a ``rungs`` argument, but the fire itself only ever passed STAGED_RUNGS. Reaching the interior
    meant editing a module constant, on the one path in this package that spends money.

    The fix is a NAMED table rather than a free-form ``--rungs``: pricing a grid stays something a
    bead authorizes, not something a caller composes at the prompt."""
    assert set(e1_grid.STAGED_SLICES) == {"ends", "interior", "full"}
    assert e1_grid.STAGED_SLICES["ends"] == ("R0", "R4") == STAGED_RUNGS
    assert e1_grid.STAGED_SLICES["interior"] == ("R1", "R2", "R3")
    assert e1_grid.STAGED_SLICES["full"] == RUNG_IDS
    # ends + interior partition full. Not asserted here: the three literals above already imply
    # it, so a check on them cannot fail on its own. It is asserted where it can fail, over prices
    # computed separately per slice, in test_the_plan_path_prices_every_authorized_slice.
    assert e1_grid.staged_rungs("interior") == ("R1", "R2", "R3")
    assert e1_grid.staged_rungs(e1_grid.DEFAULT_STAGE) == STAGED_RUNGS
    with pytest.raises(ValueError, match="unknown stage"):
        e1_grid.staged_rungs("R1")
    with pytest.raises(TypeError):
        e1_grid.STAGED_SLICES["ends"] = ()  # type: ignore[index]


def test_staged_plan_prices_the_slice_it_is_asked_for() -> None:
    """The disclosed cost is a product over the rungs actually run, so naming a slice moves it."""
    assert staged_plan(n_tasks_per_variant=64, n_variants=2)["stage"] == "ends"
    assert staged_plan(n_tasks_per_variant=64, n_variants=2)["calls"] == 160
    interior = staged_plan(n_tasks_per_variant=64, n_variants=2, stage="interior")
    assert interior["stage"] == "interior"
    assert interior["rungs"] == ["R1", "R2", "R3"]
    assert interior["calls"] == 240
    full = staged_plan(n_tasks_per_variant=64, n_variants=2, stage="full")
    assert full["rungs"] == list(RUNG_IDS)
    assert full["calls"] == 400
    # Every slice's rule turns on R4, and the two that buy an interior rung before observing it
    # extend the ends sentence rather than restating it. See the prerequisite test below.
    ends_rule = str(staged_plan(n_tasks_per_variant=64, n_variants=2)["halt_rule"])
    assert str(interior["halt_rule"]).startswith(ends_rule)
    assert interior["halt_rule"] != ends_rule
    assert "R4" in ends_rule


def test_the_priced_plan_and_the_fired_plan_count_the_same_grid(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--staged`` priced off ``len(tasks)`` while ``--fire-staged`` priced off
    ``per_variant_task_count``. On the 16-task corpus both cap at STAGED_TASKS and agree, which is
    why it survived a test that only ever checked ``per_variant_task_count`` in isolation; on an
    UNEVEN corpus they diverge and the number a human authorizes money against is the wrong one.
    Both go through ``priced_plan`` now, and this drives the CLI to say so."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _seqs, _tasks = corpus_one(tmp_path)
    # Both halves, which is what the CLI itself loads: `corpus_one` returns the NECESSARY tasks
    # only, and the twin half is minted by `load_twin_corpus`.
    _, twins = load_twin_corpus(tmp_path / "corpus")
    necessary = next(t for t in twins if t.variant == VARIANT_NECESSARY)
    unnecessary = next(t for t in twins if t.variant == VARIANT_UNNECESSARY)
    uneven = [replace(necessary, work_id=f"w-{i}") for i in range(3)] + [unnecessary]
    monkeypatch.setattr(e1_grid, "load_twin_corpus", lambda _dir: ([], uneven))
    code = e1_grid.main(["--corpus-dir", str(tmp_path / "corpus"), "--staged", "--model", MODEL])
    assert code == e1_grid.EXIT_OK
    priced = json.loads(capsys.readouterr().out)["staged_plan"]
    # One task per variant is what the fire slices to, so 2 rungs x 1 task x 5 repeats x 2 halves.
    assert priced["n_tasks"] == 1
    assert priced["calls"] == 20
    # And it is the SAME plan object the fire path prices its spend from.
    assert priced == e1_grid.priced_plan(uneven)


def test_fire_staged_buys_the_slice_the_stage_flag_names(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    monkeypatch.setattr(e1_grid, "resolve_cli_version", lambda: "9.9.9")
    monkeypatch.setattr(e1_grid, "STAGED_REPEATS", 1)
    _seqs, tasks = corpus_one(tmp_path)
    monkeypatch.setattr(e1_grid, "run_rung_cell", _fake_cells(tasks))
    out = tmp_path / "interior.json"
    code = e1_grid.main(
        [
            "--corpus-dir",
            str(tmp_path / "corpus"),
            "--fire-staged",
            "--stage",
            "interior",
            "--model",
            MODEL,
            "--out",
            str(out),
        ]
    )
    assert code == e1_grid.EXIT_OK
    printed = json.loads(capsys.readouterr().out)
    assert printed["rungs"] == ["R1", "R2", "R3"]
    assert printed["stage"] == "interior"
    assert [(row["rung"], row["variant"]) for row in printed["cells"]] == [
        (rung, variant)
        for rung in ("R1", "R2", "R3")
        for variant in (VARIANT_NECESSARY, VARIANT_UNNECESSARY)
    ]
    legs = sorted(path.name.split("__")[0] for path in (out.with_suffix(".json.legs")).iterdir())
    assert legs == ["R1", "R1", "R2", "R2", "R3", "R3"]


def test_an_ends_artifact_resumes_into_the_full_ladder_and_buys_only_the_interior(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The workflow the ruling implies: R0/R4 are already paid for, the interior is what is
    missing. Under ``--stage full`` the landed ends cells are INSIDE the grid, so they are kept and
    the six interior cells are the only ones bought."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    monkeypatch.setattr(e1_grid, "resolve_cli_version", lambda: "9.9.9")
    monkeypatch.setattr(e1_grid, "STAGED_REPEATS", 1)
    _seqs, tasks = corpus_one(tmp_path)
    monkeypatch.setattr(e1_grid, "run_rung_cell", _fake_cells(tasks))
    _, twins = load_twin_corpus(tmp_path / "corpus")
    work_id = tasks[0].work_id
    out = tmp_path / "summary.json"
    out.write_text(
        json.dumps(
            summarize(
                [
                    _cell(rung, variant, calling=1, runs=1, work_id=work_id)
                    for rung in ("R0", "R4")
                    for variant in (VARIANT_NECESSARY, VARIANT_UNNECESSARY)
                ],
                model=MODEL,
                dry_run=False,
                repeats=1,
                cli_version="9.9.9",
                corpus=corpus_fingerprint(twins),
            )
        ),
        encoding="utf-8",
    )
    code = e1_grid.main(
        [
            "--corpus-dir",
            str(tmp_path / "corpus"),
            "--fire-staged",
            "--stage",
            "full",
            "--model",
            MODEL,
            "--out",
            str(out),
        ]
    )
    assert code == e1_grid.EXIT_OK
    captured = capsys.readouterr()
    printed = json.loads(captured.out)
    assert [(row["rung"], row["variant"]) for row in printed["cells"]] == [
        (rung, variant) for rung in RUNG_IDS for variant in (VARIANT_NECESSARY, VARIANT_UNNECESSARY)
    ]
    # Only the interior was bought: a leg file exists for R1-R3 and for nothing else.
    legs = sorted({path.name.split("__")[0] for path in (out.with_suffix(".json.legs")).iterdir()})
    assert legs == ["R1", "R2", "R3"]
    # And the fire disclosed the residual, not the whole slice's price. `plan.calls` is 10 (5
    # rungs x 1 task x 1 repeat x 2 halves) while this fire buys 6, so an operator reading
    # `firing.calls` alone would over-state the spend by 4 on the workflow this bead exists for.
    announced = json.loads(captured.err[captured.err.index("{") : captured.err.rindex("}") + 1])
    assert announced["firing"]["calls"] == 10
    assert announced["resumed_cells"] == 4
    assert announced["remaining_calls"] == 6


def test_an_ends_artifact_is_refused_by_the_interior_stage(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same artifact under ``--stage interior`` carries R0/R4 cells the interior grid will not
    run, and pooling them into interior-only rates would publish two designs as one. It is a
    refusal, and the message has to name the stage so the operator reaches for ``full``."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    monkeypatch.setattr(e1_grid, "resolve_cli_version", lambda: "9.9.9")
    monkeypatch.setattr(e1_grid, "STAGED_REPEATS", 1)
    _seqs, tasks = corpus_one(tmp_path)
    monkeypatch.setattr(e1_grid, "run_rung_cell", _fake_cells(tasks))
    _, twins = load_twin_corpus(tmp_path / "corpus")
    out = tmp_path / "summary.json"
    out.write_text(
        json.dumps(
            summarize(
                [_cell("R0", VARIANT_NECESSARY, calling=1, runs=1, work_id=tasks[0].work_id)],
                model=MODEL,
                dry_run=False,
                repeats=1,
                cli_version="9.9.9",
                corpus=corpus_fingerprint(twins),
            )
        ),
        encoding="utf-8",
    )
    code = e1_grid.main(
        [
            "--corpus-dir",
            str(tmp_path / "corpus"),
            "--fire-staged",
            "--stage",
            "interior",
            "--model",
            MODEL,
            "--out",
            str(out),
        ]
    )
    assert code == e1_grid.EXIT_REFUSED
    err = capsys.readouterr().err
    # "REFUSED" and "R0" both predate this change (the prefix, and `cell.key` inside the
    # out-of-grid message), so neither pins the suffix. `--stage interior` does: it is the only
    # part of the message that tells the operator which slice refused and that `full` is the one
    # that would take this artifact.
    assert "REFUSED" in err and "R0" in err and "--stage interior" in err
    # Nothing was bought: the refusal happens before the first leg.
    assert not out.with_suffix(".json.legs").exists()


def test_the_plan_path_prices_every_authorized_slice(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A human choosing what to authorize should see all three prices without running anything."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _seqs, _tasks = corpus_one(tmp_path)
    assert e1_grid.main(["--corpus-dir", str(tmp_path / "corpus"), "--json"]) == e1_grid.EXIT_OK
    plan = json.loads(capsys.readouterr().out)
    assert set(plan["staged_plans"]) == {"ends", "interior", "full"}
    assert plan["staged_plans"]["ends"]["rungs"] == ["R0", "R4"]
    # Hand-written: `corpus_one` is 1 task per variant, so 2/3/5 rungs x 1 x 5 repeats x 2 halves.
    calls = [plan["staged_plans"][s]["calls"] for s in ("ends", "interior", "full")]
    assert calls == [20, 30, 50]
    # And the partition holds in the prices, not just in the rung table.
    assert calls[2] == calls[0] + calls[1]


def test_an_unknown_stage_is_rejected_before_anything_is_priced(
    tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """``staged_rungs``' ValueError is defense-in-depth for programmatic callers; on the CLI the
    guard that actually fires is argparse's ``choices``, bound to ``STAGED_SLICES`` so the two
    cannot drift. A typo must not reach a default and price the wrong grid."""
    corpus_one(tmp_path)
    with pytest.raises(SystemExit) as exc:
        e1_grid.main(["--corpus-dir", str(tmp_path / "corpus"), "--json", "--stage", "endz"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "invalid choice" in err and "'endz'" in err


# --- mem-k36dc (Codex review): priced == spent over the corpus actually loaded ---


def test_pricing_counts_the_variant_labels_the_corpus_actually_has(tmp_path: Any) -> None:
    """``staged_cells`` runs every variant label present; a hard-coded two-half price does not.

    ``variant`` is an unrestricted ``str`` and these helpers are exported, so a corpus carrying a
    third label spends 1.5x its quote while one missing a half spends half of it. Both directions
    are the defect this bead already fixed once in the other axis: an authorization written for a
    grid other than the one that runs. The check is against ``grid_keys``, the derivation
    ``staged_cells`` itself slices, so the price cannot drift away from the spend."""
    corpus_one(tmp_path)
    _, twins = load_twin_corpus(tmp_path / "corpus")
    necessary = next(t for t in twins if t.variant == VARIANT_NECESSARY)
    shapes = {
        "twin": (VARIANT_NECESSARY, VARIANT_UNNECESSARY),
        "one half only": (VARIANT_NECESSARY,),
        "a third label": (VARIANT_NECESSARY, VARIANT_UNNECESSARY, "control"),
    }
    ends_calls: dict[str, int] = {}
    for shape, variants in shapes.items():
        tasks = [
            replace(necessary, work_id=f"{variant}-{i}", variant=variant)
            for variant in variants
            for i in range(3)
        ]
        for stage in e1_grid.STAGED_SLICES:
            plan = e1_grid.priced_plan(tasks, stage=stage)
            spent = grid_keys(
                tasks, rungs=e1_grid.staged_rungs(stage), n_tasks=int(plan["n_tasks"])
            )
            assert plan["n_variants"] == len(variants), (shape, stage)
            assert plan["calls"] == len(spent) * STAGED_REPEATS, (shape, stage)
        ends_calls[shape] = int(e1_grid.priced_plan(tasks)["calls"])
    # Hand-written, so the loop above is comparing two different derivations and not one constant
    # to itself: 2 ends rungs x 3 tasks x 5 repeats, times the labels the corpus carries.
    assert ends_calls == {"twin": 60, "one half only": 30, "a third label": 90}


def test_the_halt_rule_is_a_prerequisite_on_the_slices_that_cannot_enforce_it(
    tmp_path: Any,
) -> None:
    """``staged_cells`` runs the rungs IN ORDER and has no mid-fire zero-call halt.

    So ``full`` buys R0-R3 before its own R4 lands and ``interior`` never observes R4 at all: for
    both, "if R4 shows zero the interior is not run" is a promise the fire cannot keep. Their rule
    has to name PRIOR evidence -- the R4 preflight, or a landed ends fire -- and say plainly that
    this fire does not enforce it. ``ends`` buys no interior rung, so there the sentence is a
    statement about the NEXT fire and stays exactly as the module comment writes it."""
    rules = {
        name: str(staged_plan(n_tasks_per_variant=8, n_variants=2, stage=name)["halt_rule"])
        for name in e1_grid.STAGED_SLICES
    }
    assert all(RUNG_IDS[-1] in rule for rule in rules.values())
    for name in ("interior", "full"):
        assert "ALREADY" in rules[name], name
        assert "this fire does not enforce it" in rules[name], name
    assert "ALREADY" not in rules["ends"]
    # The ordering that makes the promise unkeepable, asserted rather than assumed: under `full`
    # the interior cells are bought before the first R4 cell is.
    corpus_one(tmp_path)
    _, twins = load_twin_corpus(tmp_path / "corpus")
    order = [
        rung for rung, _v, _w in grid_keys(twins, rungs=e1_grid.staged_rungs("full"), n_tasks=1)
    ]
    assert order.index("R1") < order.index(RUNG_IDS[-1])


def test_the_plan_only_guidance_names_the_flags_that_actually_spend(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``paid = args.preflight or args.fire_staged``, and the guidance disagreed with it twice.

    It called ``--staged`` "the staged spend", said it needed CLAUDE_CODE_OAUTH_TOKEN, and said it
    spent real money; ``--staged`` prices and returns. And ``--fire-staged``, the flag that does
    buy the staged grid, appeared nowhere in it. A reader following this text either believed a
    free dry run would bill them or could not find the command that bills."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    corpus_one(tmp_path)
    # No token, no --model, and it still succeeds: that is the behavior the text has to describe.
    assert e1_grid.main(["--corpus-dir", str(tmp_path / "corpus"), "--staged"]) == e1_grid.EXIT_OK
    assert e1_grid.main(["--corpus-dir", str(tmp_path / "corpus")]) == e1_grid.EXIT_OK
    guidance = capsys.readouterr().err
    assert "--preflight" in guidance and "--fire-staged" in guidance
    free = next(
        line for line in guidance.splitlines() if "--staged" in line and "--fire-staged" not in line
    )
    assert "free" in free
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in free
    # And the money sentence excludes the free flag rather than sweeping it in with "both".
    assert "--staged needs neither" in guidance


def test_the_spend_paths_will_not_take_a_slice_by_omission(tmp_path: Any) -> None:
    """A typo in a slice name raises; an omitted slice used to quietly mean ``ends``.

    ``grid_keys`` decides which landed cells a resume may keep and ``staged_cells`` buys the grid,
    so both defaulting to ``STAGED_RUNGS`` meant a caller who wrote out every other argument and
    forgot this one bought 160 ends calls while intending 400 full ones. ``corpus_dir`` on the same
    function is already required for this reason; once more than one slice exists, so is this."""
    _seqs, tasks = corpus_one(tmp_path)
    with pytest.raises(TypeError, match="rungs"):
        grid_keys(tasks, n_tasks=1)  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="rungs"):
        e1_grid.staged_cells(  # type: ignore[call-arg]
            tasks,
            model=MODEL,
            corpus_dir=tmp_path / "corpus",
            n_tasks=1,
            repeats=1,
            runner=noop_cli_runner,
        )


def test_the_preflight_refuses_a_stage_it_would_ignore(
    tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--preflight`` runs the ONE rung named by ``--rung``; ``--stage`` names a ladder slice that
    only ``--staged`` and ``--fire-staged`` read. Accepting it here was inert on a path that spends
    real money, which invites the reading that the interior was preflighted."""
    corpus_one(tmp_path)
    with pytest.raises(SystemExit) as exc:
        e1_grid.main(
            [
                "--corpus-dir",
                str(tmp_path / "corpus"),
                "--preflight",
                "--stage",
                "interior",
                "--model",
                MODEL,
            ]
        )
    assert exc.value.code == 2
    assert "--rung" in capsys.readouterr().err


class _Variant:
    """A task stand-in carrying the variant the shape guard reads and the ``work_id`` the
    derivations key on, so the same object can be handed to both."""

    def __init__(self, variant: str, work_id: str = "w-0") -> None:
        self.variant = variant
        self.work_id = work_id


def test_a_corpus_that_cannot_produce_a_margin_is_refused() -> None:
    """`discrimination_margins` compares P(call | necessary) against P(call | unnecessary), so a
    corpus that is not exactly that pair prices correctly, spends the full authorization, and
    yields an artifact with no d() in it. The refusal names what it observed."""
    both = [_Variant(VARIANT_NECESSARY), _Variant(VARIANT_UNNECESSARY)]
    assert assert_scoreable_corpus(both) is None
    # Repeats of the same two labels are still the scoreable pair.
    assert assert_scoreable_corpus(both * 4) is None

    with pytest.raises(CorpusShapeError) as one_half:
        assert_scoreable_corpus([_Variant(VARIANT_NECESSARY)] * 8)
    assert VARIANT_UNNECESSARY in str(one_half.value)

    with pytest.raises(CorpusShapeError) as third:
        assert_scoreable_corpus([*both, _Variant("ambiguous")])
    assert "ambiguous" in str(third.value)

    with pytest.raises(CorpusShapeError):
        assert_scoreable_corpus([])


def test_the_shape_guard_is_not_wired_into_the_derivations() -> None:
    """`staged_cells` and `grid_keys` are derivations that unit tests legitimately drive over a
    single label; a refusal buried in one of them would fire on the tests rather than on the
    spend. They still enumerate whatever they are handed."""
    one_half = [_Variant(VARIANT_NECESSARY)]
    with pytest.raises(CorpusShapeError):
        assert_scoreable_corpus(one_half)
    assert grid_keys(one_half, rungs=("R0",), n_tasks=1) == [("R0", VARIANT_NECESSARY, "w-0")]
    assert e1_grid.per_variant_task_count(one_half) == 1


def test_a_one_half_corpus_refuses_the_fire_before_the_first_leg(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The guard sits on the paid entries, so an unscoreable corpus costs nothing. Unreachable
    through `load_twin_corpus` today, which always emits two equal halves — but `variant` is an
    unrestricted str and `--corpus-dir` points at a directory on disk."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    monkeypatch.setattr(e1_grid, "resolve_cli_version", lambda: "9.9.9")
    seqs, tasks = corpus_one(tmp_path)
    # `corpus_one` loads the authored half only; `load_twin_corpus` is what mints the twin. So
    # this IS the one-half shape, and stubbing the loader is how it reaches the paid entries.
    assert {t.variant for t in tasks} == {VARIANT_NECESSARY}
    monkeypatch.setattr(e1_grid, "load_twin_corpus", lambda _dir: (seqs, tasks))

    spent = {"legs": 0}

    def counting(task: Any, **kwargs: Any) -> RungCell:
        spent["legs"] += int(kwargs["repeats"])
        return _fake_cells(tasks)(task, **kwargs)

    monkeypatch.setattr(e1_grid, "run_rung_cell", counting)
    argv = ["--corpus-dir", str(tmp_path / "corpus"), "--model", MODEL]
    assert e1_grid.main([*argv, "--fire-staged", "--out", str(tmp_path / "o.json")]) == (
        e1_grid.EXIT_REFUSED
    )
    assert e1_grid.main([*argv, "--preflight", "--rung", "R4"]) == e1_grid.EXIT_REFUSED
    assert spent["legs"] == 0
    assert VARIANT_UNNECESSARY in capsys.readouterr().err
    assert not (tmp_path / "o.json").exists()


def test_pricing_a_corpus_the_fire_would_refuse_is_still_allowed(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--staged` prices and spends nothing, so a shape it cannot buy is still a number worth
    printing — the guard must not turn a free disclosure into a refusal."""
    seqs, tasks = corpus_one(tmp_path)
    assert {t.variant for t in tasks} == {VARIANT_NECESSARY}
    monkeypatch.setattr(e1_grid, "load_twin_corpus", lambda _dir: (seqs, tasks))
    code = e1_grid.main(["--corpus-dir", str(tmp_path / "corpus"), "--staged", "--model", MODEL])
    assert code == e1_grid.EXIT_OK
    assert json.loads(capsys.readouterr().out)["staged_plan"]["calls"] > 0
