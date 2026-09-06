"""The deployment-context arm: what `bd init` actually injects, planted where the agent reads it.

The interior fire (mem-gj0pc) scored zero bd calls against an agent that was never told bd
existed, because `scrub_store_guidance` removes the very drop-ins whose managed block says to use
`bd remember`. These tests pin the arm that puts that context back: captured from bd rather than
paraphrased, planted in the cwd rather than the store, and restored after the wipe that would
otherwise leave the two legs of a pair on different arms.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from membench.runner.tool_surface import (
    BD_CONTEXT_ADDENDUM,
    MemoryToolError,
    MemoryToolSurface,
    capture_bd_context,
    memory_invocations,
    observed_written_content,
    plant_bd_context,
    provision_memory_tool,
    scrub_store_guidance,
)
from membench.schemas.trace import ToolCall

# The line that makes this arm worth firing: bd's own managed block both names the tool and
# redirects off the native path. Asserted as the reason the capture exists, not as bd's wording --
# a release that rewords it should fail this and be looked at, not silently measure something else.
REDIRECT_SENTENCE = "Use `bd remember` for persistent knowledge"


def _store_with_dropins(tmp_path: Path) -> Path:
    """A store carrying the drop-ins `bd init` writes, without paying for a real `bd init`."""
    store = tmp_path / "store"
    store.mkdir()
    (store / "CLAUDE.md").write_text(
        f"# Project Instructions\n\n## Beads Issue Tracker\n\n- {REDIRECT_SENTENCE} "
        "— do NOT use MEMORY.md files\n",
        encoding="utf-8",
    )
    (store / "AGENTS.md").write_text(
        f"# Agent Instructions\n\n- {REDIRECT_SENTENCE} — do NOT use MEMORY.md files\n",
        encoding="utf-8",
    )
    return store


def _surface(tmp_path: Path, store: Path) -> MemoryToolSurface:
    return MemoryToolSurface(
        store_dir=store,
        bin_dir=tmp_path / "bin",
        bd_binary="/usr/bin/bd",
        bd_context=capture_bd_context(store),
    )


def test_the_capture_takes_both_drop_ins_verbatim(tmp_path: Path) -> None:
    store = _store_with_dropins(tmp_path)
    captured = capture_bd_context(store)
    assert sorted(captured) == ["AGENTS.md", "CLAUDE.md"]
    for name, text in captured.items():
        assert text == (store / name).read_text(encoding="utf-8")


def test_the_captured_text_carries_the_redirect_sentence(tmp_path: Path) -> None:
    """The capture is worth nothing if it loses the one line that names the tool."""
    captured = capture_bd_context(_store_with_dropins(tmp_path))
    assert all(REDIRECT_SENTENCE in text for text in captured.values())


def test_capturing_after_the_scrub_returns_nothing(tmp_path: Path) -> None:
    """Ordering is load-bearing: the scrub is what makes a late capture empty."""
    store = _store_with_dropins(tmp_path)
    scrub_store_guidance(store)
    assert capture_bd_context(store) == {}


def test_planting_lands_in_the_cwd_and_never_in_the_store(tmp_path: Path) -> None:
    """The CLI auto-loads from the working directory; the agent never chdirs to the store."""
    store = _store_with_dropins(tmp_path)
    surface = _surface(tmp_path, store)
    scrub_store_guidance(store)
    cwd = tmp_path / "sandbox"
    cwd.mkdir()

    planted = plant_bd_context(cwd, surface)

    assert planted == ("AGENTS.md", "CLAUDE.md")
    assert sorted(p.name for p in cwd.iterdir()) == ["AGENTS.md", "CLAUDE.md"]
    assert not (store / "CLAUDE.md").exists()


def test_the_planted_file_carries_bd_s_text_and_then_the_addendum(tmp_path: Path) -> None:
    store = _store_with_dropins(tmp_path)
    surface = _surface(tmp_path, store)
    cwd = tmp_path / "sandbox"
    cwd.mkdir()

    plant_bd_context(cwd, surface)
    planted = (cwd / "CLAUDE.md").read_text(encoding="utf-8")

    assert REDIRECT_SENTENCE in planted
    assert BD_CONTEXT_ADDENDUM in planted
    assert planted.index(REDIRECT_SENTENCE) < planted.index(BD_CONTEXT_ADDENDUM)


def test_the_addendum_supplies_recall_which_bd_s_own_block_does_not(tmp_path: Path) -> None:
    """bd says to WRITE durable knowledge and never says how to read it back. An agent told only
    to write has no reason to read, and the read is the half the discrimination margin scores."""
    store = _store_with_dropins(tmp_path)
    assert "bd recall" not in (store / "CLAUDE.md").read_text(encoding="utf-8")
    assert "bd recall" in BD_CONTEXT_ADDENDUM
    assert "bd remember" in BD_CONTEXT_ADDENDUM


def test_the_addendum_gives_no_worked_example_of_when_to_recall(tmp_path: Path) -> None:
    """Supplying WHEN would hand over the disposition under test. Verbs and argv shape only."""
    lowered = BD_CONTEXT_ADDENDUM.lower()
    for supplied in ("if the task", "when the task", "before you answer", "check it first"):
        assert supplied not in lowered


@pytest.mark.skipif(shutil.which("bd") is None, reason="bd is not installed on this host")
def test_addendum_commands_round_trip_through_the_agent_surface(tmp_path: Path) -> None:
    """Execute the taught argv through PATH, checking actual content instead of command exit."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    surface = provision_memory_tool(tmp_path / "surface", sandbox=sandbox)
    env = {**os.environ, **surface.env()}
    content = "parser contract retained words"
    commands = BD_CONTEXT_ADDENDUM.split("```bash\n", 1)[1].split("```", 1)[0].splitlines()
    for template in commands:
        command = (
            template.replace("<content>", content)
            .replace("<key>", "contract-key")
            .replace("<query>", "parser")
        )
        argv = [*shlex.split(command, comments=True), "--json"]
        result = subprocess.run(
            argv,
            cwd=sandbox,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert content in result.stdout
        if argv[1] == "remember":
            call = ToolCall(
                name="Bash", arguments={"command": shlex.join(argv)}, result=result.stdout
            )
            (invocation,) = memory_invocations([call])
            assert invocation.is_accepted_write
            assert observed_written_content([call]) == content
            acknowledgement = json.loads(result.stdout)
            recalled = subprocess.run(
                ["bd", "recall", acknowledgement["key"], "--json"],
                cwd=sandbox,
                env=env,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert json.loads(recalled.stdout)["value"] == content


def test_planting_an_empty_capture_refuses(tmp_path: Path) -> None:
    """A cell that asked for the deployment context and silently got none is the null this
    surface exists to avoid, so it raises instead of planting nothing."""
    cwd = tmp_path / "sandbox"
    cwd.mkdir()
    bare = MemoryToolSurface(
        store_dir=tmp_path / "store", bin_dir=tmp_path / "bin", bd_binary="/usr/bin/bd"
    )

    with pytest.raises(MemoryToolError, match="nothing to plant"):
        plant_bd_context(cwd, bare)

    assert list(cwd.iterdir()) == []


def test_replanting_overwrites_rather_than_appends(tmp_path: Path) -> None:
    """`close_cwd_channel` re-plants every pair. Appending would grow the context leg over leg
    and make a later repeat a different treatment than the first."""
    store = _store_with_dropins(tmp_path)
    surface = _surface(tmp_path, store)
    cwd = tmp_path / "sandbox"
    cwd.mkdir()

    plant_bd_context(cwd, surface)
    once = (cwd / "CLAUDE.md").read_text(encoding="utf-8")
    plant_bd_context(cwd, surface)

    assert (cwd / "CLAUDE.md").read_text(encoding="utf-8") == once


# --------------------------------------------------------------------------------------
# the property the pair depends on: the arm survives the wipe between the legs
# --------------------------------------------------------------------------------------


def test_the_wipe_between_legs_restores_the_context(tmp_path: Path) -> None:
    """`close_cwd_channel` empties the cwd to close the scavenge channel, which eats the planted
    context too. Without the re-plant the goal leg runs a different arm than its establish leg."""
    from membench.runner.e1_grid import _CellStore, close_cwd_channel

    store = _store_with_dropins(tmp_path)
    surface = _surface(tmp_path, store)
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    plant_bd_context(sandbox, surface)
    (sandbox / "scavenged.txt").write_text("what the establish leg left behind", encoding="utf-8")

    close_cwd_channel(
        _CellStore(
            surface=surface,
            sandbox=sandbox,
            config_dir=tmp_path / "config",
            hook_log=tmp_path / "hook.jsonl",
            pinned_off=False,
            probe="probe",
            bd_context=True,
        )
    )

    survivors = sorted(p.name for p in sandbox.iterdir())
    assert survivors == ["AGENTS.md", "CLAUDE.md"], "the arm must survive, the scavenge must not"
    assert REDIRECT_SENTENCE in (sandbox / "CLAUDE.md").read_text(encoding="utf-8")


def test_the_wipe_plants_nothing_when_the_arm_is_off(tmp_path: Path) -> None:
    """`bd_context=False` is the arm the interior fire ran, and is no longer the default. It stays
    reachable so protocol 2 can be reproduced; with it off the wipe must leave the cwd empty."""
    from membench.runner.e1_grid import _CellStore, close_cwd_channel

    store = _store_with_dropins(tmp_path)
    surface = _surface(tmp_path, store)
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "scavenged.txt").write_text("what the establish leg left behind", encoding="utf-8")

    close_cwd_channel(
        _CellStore(
            surface=surface,
            sandbox=sandbox,
            config_dir=tmp_path / "config",
            hook_log=tmp_path / "hook.jsonl",
            pinned_off=False,
            probe="probe",
            bd_context=False,
        )
    )

    assert list(sandbox.iterdir()) == []


def test_provisioning_captures_before_it_scrubs(tmp_path: Path) -> None:
    """The ordering, against a REAL `bd init` rather than a hand-built store.

    Capturing after the scrub yields an empty mapping, and every hand-built-store test above still
    passes with the order reversed, because they call the two functions themselves. Only a real
    provision can say which order shipped. Slow (a real `bd init`) and worth it: the failure it
    catches is an arm that provisions clean, plants nothing, and refuses at the first paid leg."""
    from membench.runner.tool_surface import provision_memory_tool

    surface = provision_memory_tool(tmp_path / "root", sandbox=None)

    assert surface.bd_context, "provisioning must capture the drop-ins before scrubbing them"
    assert sorted(surface.bd_context) == ["AGENTS.md", "CLAUDE.md"]
    assert any(REDIRECT_SENTENCE in text for text in surface.bd_context.values())
    # ...and the scrub still ran: the STORE carries none of it.
    assert not (surface.store_dir / "CLAUDE.md").exists()


def test_the_arm_is_on_by_default_for_every_rung() -> None:
    """Stephanie's call: the deployment context is the standing environment, not an axis. Pinned
    here rather than left to the call sites, because a rung that quietly ran without it would be
    compared against rungs that had it and the ladder would measure the difference."""
    import inspect

    from membench.runner import e1_grid

    assert e1_grid.BD_CONTEXT_DEFAULT is True
    assert inspect.signature(e1_grid.cell_store).parameters["bd_context"].default is True
    for rung in e1_grid.RUNG_IDS:
        assert rung in e1_grid.RUNG_IDS  # every rung; none opts out, there is no per-rung switch


def test_the_protocol_bump_refuses_the_pre_context_artifact() -> None:
    """interior-480 was bought at protocol 2 WITHOUT the context. Pooling it with a protocol-3
    fire would report two different floors as one number, so the resume must refuse it."""
    import pytest as _pytest

    from membench.runner.e1_grid import (
        EXECUTION_PROTOCOL_VERSION,
        ResumeMismatchError,
        resume_cells,
        rung_settings_fingerprint,
    )
    from membench.runner.tool_surface import surface_fingerprint

    assert EXECUTION_PROTOCOL_VERSION >= 3, "the context arm must be inside the resume identity"
    stale = {
        "model": "cli-default",
        "surface_fingerprint": surface_fingerprint(),
        "settings_fingerprint": rung_settings_fingerprint(),
        "execution_protocol": 2,
        "cli_version": "2.1.260",
        "corpus_fingerprint": "c5f13bbe8c877a2b",
        "repeats": 5,
        "cells": [],
    }
    with _pytest.raises(ResumeMismatchError, match="different rig"):
        resume_cells(
            stale,
            model="cli-default",
            cli_version="2.1.260",
            corpus="c5f13bbe8c877a2b",
            repeats=5,
        )
