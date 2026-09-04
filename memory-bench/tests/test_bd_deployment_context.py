"""The deployment-context arm: what `bd init` actually injects, planted where the agent reads it.

The interior fire (mem-gj0pc) scored zero bd calls against an agent that was never told bd
existed, because `scrub_store_guidance` removes the very drop-ins whose managed block says to use
`bd remember`. These tests pin the arm that puts that context back: captured from bd rather than
paraphrased, planted in the cwd rather than the store, and restored after the wipe that would
otherwise leave the two legs of a pair on different arms.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from membench.runner.tool_surface import (
    BD_CONTEXT_ADDENDUM,
    MemoryToolError,
    MemoryToolSurface,
    capture_bd_context,
    plant_bd_context,
    scrub_store_guidance,
)

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


def test_the_wipe_plants_nothing_on_the_control_arm(tmp_path: Path) -> None:
    """`bd_context=False` is the arm the interior fire ran. The wipe must leave it empty, or the
    control silently becomes the treatment and the contrast measures nothing."""
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
