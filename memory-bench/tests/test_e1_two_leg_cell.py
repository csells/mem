"""mem-gj0pc blocker 5 — the two-leg cell: one store, two calls, a write that can pay off.

Until this landed, an E1 cell minted a memory store INSIDE one leg and destroyed it on the way
out. An agent that recorded a durable fact recorded it into a directory nothing would ever open,
so a write rate of zero was the only number the rig could produce, whatever the agent's
disposition — and 0/160 is exactly what the ends fire published. Every test here pins one of the
properties that makes the pair a measurement rather than two unrelated calls: the store survives
the first leg, the cwd does not, both halves of the twin get a byte-identical establish leg, and
the price a human authorizes counts both legs.

Nothing here spends anything: every cell runs against an injected runner.
"""

from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from membench.runner import e1_grid
from membench.runner.e1_grid import LEG_ROLES, LEGS_PER_CELL, LegRecord
from membench.runner.headless_agent import result_event, serialize_stream
from membench.runner.toolreq_corpus import (
    CONTEXT_HEADING,
    context_block,
    established_context,
    unnecessary_twin,
)
from tests.toolreq_helpers import corpus_one

MODEL = "claude-test-model-1"


def _env(kwargs: dict[str, object]) -> dict[str, str]:
    """The env a leg was spawned with — the store's whole visibility, in one line."""
    return cast(dict[str, str], kwargs.get("env") or {})


def _recording_runner(calls: list[dict[str, str]]) -> Any:
    """A runner that makes no tool call and records WHERE it was run: the cwd it was spawned in
    and the config dir it was pinned to. Those two are what a shared store is visible as from
    inside a leg."""

    def runner(argv: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        env = _env(kwargs)
        calls.append(
            {"cwd": str(kwargs.get("cwd", "")), "config": env.get("CLAUDE_CONFIG_DIR", "")}
        )
        return subprocess.CompletedProcess(list(argv), 0, serialize_stream([result_event()]), "")

    return runner


def test_a_repeat_spends_two_legs_that_share_one_store_and_one_cwd(tmp_path: Path) -> None:
    """The pair, in one property: two calls per repeat, on the same cwd and the same config dir,
    and a DIFFERENT pair per repeat. Sharing across repeats would carry a fact between them and
    make the second repeat a different measurement from the first."""
    _seqs, tasks = corpus_one(tmp_path)
    calls: list[dict[str, str]] = []
    cell = e1_grid.run_rung_cell(
        tasks[0], rung="R4", repeats=2, model=MODEL, dry_run=False, runner=_recording_runner(calls)
    )
    assert len(calls) == 2 * LEGS_PER_CELL
    assert cell.runs == 2 * LEGS_PER_CELL
    first, second = calls[:LEGS_PER_CELL], calls[LEGS_PER_CELL:]
    assert first[0] == first[1], "the two legs of a repeat must share the store and the cwd"
    assert second[0] == second[1]
    assert first[0]["cwd"] != second[0]["cwd"], "repeats must not share a sandbox"
    assert first[0]["config"] != second[0]["config"], "repeats must not share a store"


def _store_writing_runner(seen: list[str]) -> Any:
    """Leg 0 drops a file under the pinned config dir; leg 1 reports whether it is still there.
    This is the payoff channel itself, exercised end to end without an agent."""
    token = "toolreq-carried-value"

    def runner(argv: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        env = _env(kwargs)
        carried = Path(env["CLAUDE_CONFIG_DIR"]) / "carried.txt"
        if not carried.exists():
            carried.write_text(token)
            seen.append("wrote")
        else:
            seen.append(carried.read_text())
        return subprocess.CompletedProcess(list(argv), 0, serialize_stream([result_event()]), "")

    return runner


def test_what_the_establish_leg_writes_is_there_for_the_goal_leg(tmp_path: Path) -> None:
    """The single property the whole restructure exists for. Under the old single-leg cell the
    second call opened a store that had just been created, so this reads ``wrote`` twice."""
    _seqs, tasks = corpus_one(tmp_path)
    seen: list[str] = []
    e1_grid.run_rung_cell(
        tasks[0],
        rung="R4",
        repeats=1,
        model=MODEL,
        dry_run=False,
        runner=_store_writing_runner(seen),
    )
    assert seen == ["wrote", "toolreq-carried-value"]


def _cwd_dropping_runner(seen: list[list[str]]) -> Any:
    """Leg 0 drops a file in the CWD; every leg reports what it found there on arrival."""

    def runner(argv: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        cwd = Path(str(kwargs.get("cwd")))
        seen.append(sorted(p.name for p in cwd.iterdir()))
        (cwd / "CLAUDE.md").write_text("the retention window is toolreq-carried-value")
        return subprocess.CompletedProcess(list(argv), 0, serialize_stream([result_event()]), "")

    return runner


def test_the_cwd_is_emptied_between_the_legs(tmp_path: Path) -> None:
    """The scavenge channel the ``--allowedTools`` clamp cannot close: Claude Code auto-loads
    ``CLAUDE.md`` from the cwd with no tool call, so an establish leg that drops the values in a
    file would hand them to the goal leg for free and a cell that never touched memory would score
    as one that did not need to."""
    _seqs, tasks = corpus_one(tmp_path)
    seen: list[list[str]] = []
    e1_grid.run_rung_cell(
        tasks[0],
        rung="R4",
        repeats=1,
        model=MODEL,
        dry_run=False,
        runner=_cwd_dropping_runner(seen),
    )
    assert seen == [[], []], "the goal leg must arrive in an empty cwd"


def test_every_leg_is_recorded_under_its_role_and_its_own_filename(tmp_path: Path) -> None:
    """Two legs per repeat, each with a record: the artifact is what a re-score reads, and two
    legs sharing a filename would leave the fire with half its evidence."""
    _seqs, tasks = corpus_one(tmp_path)
    legs: list[LegRecord] = []
    e1_grid.run_rung_cell(
        tasks[0],
        rung="R4",
        repeats=2,
        model=MODEL,
        dry_run=False,
        runner=_recording_runner([]),
        on_leg=legs.append,
    )
    assert [leg.role for leg in legs] == list(LEG_ROLES) * 2
    assert [leg.leg for leg in legs] == [0, 1, 2, 3]
    assert len({leg.filename for leg in legs}) == 4
    assert all(record.row()["role"] == record.role for record in legs)


def test_the_price_counts_both_legs_of_every_cell() -> None:
    """The number a human authorizes money against. A price that read one call per repeat quoted
    half the bill, which is what the single-leg ends fire was authorized under."""
    calls = e1_grid.planned_call_count(rungs=("R1", "R2", "R3"), n_tasks=8, repeats=5, n_variants=2)
    assert calls == 3 * 8 * 5 * 2 * LEGS_PER_CELL == 480
    plan = e1_grid.staged_plan(n_tasks_per_variant=8, n_variants=2, stage="interior")
    assert plan["calls"] == 480


def test_the_establish_leg_states_the_values_and_matches_across_a_twin_pair(tmp_path: Path) -> None:
    """The contrast, preserved. Both halves are established from the SAME text; the only thing
    that still differs between them is whether the goal request restates it, which is the single
    moved variable E1 measures."""
    _seqs, tasks = corpus_one(tmp_path)
    necessary = tasks[0]
    twin = unnecessary_twin(necessary)
    assert established_context(necessary) == established_context(twin) == context_block(necessary)
    for value in necessary.current_opaque_values:
        assert value in established_context(necessary)
    assert (
        e1_grid.establish_step(necessary, "R0").user_request
        == e1_grid.establish_step(twin, "R0").user_request
    )


def test_an_unnecessary_task_with_no_context_block_is_refused(tmp_path: Path) -> None:
    """Guessing an empty context would silently make the easy half the hard one."""
    _seqs, tasks = corpus_one(tmp_path)
    twin = unnecessary_twin(tasks[0])
    stripped = twin.goal_step.model_copy(update={"user_request": "do the thing"})
    with pytest.raises(ValueError, match=CONTEXT_HEADING):
        established_context(replace(twin, goal_step=stripped))


@pytest.mark.parametrize("rung", list(e1_grid.RUNG_IDS))
def test_the_establish_leg_carries_the_rungs_guidance_and_no_memory_wording_of_its_own(
    rung: str, tmp_path: Path
) -> None:
    """The establish instruction is the same at every rung; the ONLY memory wording in the leg is
    the ladder's own clause. R0's establish leg mentions memory nowhere, which is what makes it a
    floor rather than a fifth kind of prompt."""
    _seqs, tasks = corpus_one(tmp_path)
    request = e1_grid.establish_step(tasks[0], rung).user_request
    assert e1_grid.ESTABLISH_INSTRUCTION in request
    assert e1_grid.guidance_block(rung) in request
    for word in ("memory", "remember", "recall", "record"):
        assert (word in request.lower()) == (word in e1_grid.guidance_block(rung).lower())
