"""The PreToolUse interception: does the harness see a native-memory reach as it happens, and can
it answer that reach with the bd verbs instead?

Every test here drives the hook the way the CLI would — a JSON payload on stdin of the script that
was actually installed — rather than calling `hook_decision` in-process. The script body, the
`sys.path` it re-enters this package through, and the settings entry that points the CLI at it are
each part of the mechanism, and a test that skipped them would pass for a hook the CLI could not
run."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from membench.runner.native_memory_hook import (
    hook_reaches,
    install_native_memory_hook,
    redirect_reason,
)
from membench.runner.tool_surface import (
    MEMORY_COMMAND,
    NATIVE_MEMORY_HOOK_EVENT,
    NATIVE_MEMORY_HOOK_EXIT_ALLOW,
    NATIVE_MEMORY_HOOK_EXIT_BLOCK,
    NATIVE_MEMORY_HOOK_MODE_OBSERVE,
    NATIVE_MEMORY_HOOK_MODE_REDIRECT,
    NATIVE_MEMORY_HOOK_SCRIPT_NAME,
    MemoryToolError,
    recognizer_policy,
    surface_fingerprint,
)


def _fire(config_dir: Path, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    """Run the installed hook script exactly as the CLI runs it: the command out of settings.json,
    the event JSON on stdin."""
    entry = json.loads((config_dir / "settings.json").read_text("utf-8"))
    command = entry["hooks"][NATIVE_MEMORY_HOOK_EVENT][0]["hooks"][0]["command"]
    assert shlex.split(command)[-1].endswith(NATIVE_MEMORY_HOOK_SCRIPT_NAME)
    return subprocess.run(
        command, shell=True, input=json.dumps(payload), capture_output=True, text=True, timeout=60
    )


def _read_of(config_dir: Path) -> dict[str, object]:
    """A pending `Read` of the native memory file inside the pinned config dir — the exact call
    the first paid R4 cycle made 59 times (mem-gj0pc)."""
    return {
        "tool_name": "Read",
        "tool_input": {"file_path": str(config_dir / "memory" / "MEMORY.md")},
        "session_id": "s-1",
    }


def test_observe_mode_records_the_reach_and_lets_the_call_through(tmp_path: Path) -> None:
    """The instrument. The agent is told nothing, so the leg still measures its own disposition,
    and the harness still learns the reach happened."""
    config_dir = tmp_path / "config"
    log = install_native_memory_hook(config_dir, mode=NATIVE_MEMORY_HOOK_MODE_OBSERVE)

    done = _fire(config_dir, _read_of(config_dir))

    assert done.returncode == NATIVE_MEMORY_HOOK_EXIT_ALLOW
    assert done.stderr == ""
    (reach,) = hook_reaches(log)
    assert reach["tool"] == "Read"
    assert reach["is_write"] is False
    assert reach["session_id"] == "s-1"


@pytest.mark.parametrize("spaced_paths", [False, True])
def test_redirect_mode_blocks_the_reach_and_names_the_bd_verbs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spaced_paths: bool
) -> None:
    """The treatment. Exit 2 is the CLI's block-and-tell-the-model code, so what lands on stderr
    is what the agent reads in place of the file it asked for."""
    if spaced_paths:
        tmp_path = tmp_path / "team member's checkout"
        tmp_path.mkdir()
        interpreter = tmp_path / "python interpreter"
        interpreter.symlink_to(sys.executable)
        monkeypatch.setattr(sys, "executable", str(interpreter))
    config_dir = tmp_path / "config"
    log = install_native_memory_hook(config_dir, mode=NATIVE_MEMORY_HOOK_MODE_REDIRECT)

    done = _fire(config_dir, _read_of(config_dir))

    assert done.returncode == NATIVE_MEMORY_HOOK_EXIT_BLOCK
    assert done.stderr.strip() == redirect_reason()
    assert f"{MEMORY_COMMAND} remember" in done.stderr
    assert f"{MEMORY_COMMAND} recall" in done.stderr
    assert len(hook_reaches(log)) == 1


def test_a_bash_reach_is_caught_by_the_same_recognizer_the_stream_is_scored_with(
    tmp_path: Path,
) -> None:
    """The file tools are not the only way in. A shell command naming the pinned path is a reach,
    and it is the recognizer in `tool_surface` that says so — here and in the stream scorer."""
    config_dir = tmp_path / "config"
    log = install_native_memory_hook(config_dir, mode=NATIVE_MEMORY_HOOK_MODE_REDIRECT)

    done = _fire(
        config_dir,
        {
            "tool_name": "Bash",
            "tool_input": {"command": f"cat {config_dir}/memory/MEMORY.md"},
        },
    )

    assert done.returncode == NATIVE_MEMORY_HOOK_EXIT_BLOCK
    (reach,) = hook_reaches(log)
    assert reach["tool"] == "Bash"


def test_a_call_that_is_not_a_memory_reach_is_never_touched(tmp_path: Path) -> None:
    """The hook watches every file tool and Bash, so most of what it sees is ordinary work. A
    redirect on ordinary work would be a coercion the artifact reports as a memory finding."""
    config_dir = tmp_path / "config"
    log = install_native_memory_hook(config_dir, mode=NATIVE_MEMORY_HOOK_MODE_REDIRECT)

    done = _fire(
        config_dir,
        {"tool_name": "Read", "tool_input": {"file_path": str(tmp_path / "src" / "app.py")}},
    )

    assert done.returncode == NATIVE_MEMORY_HOOK_EXIT_ALLOW
    assert done.stderr == ""
    assert hook_reaches(log) == []


def test_a_malformed_event_allows_the_call_and_leaves_its_own_fault_in_the_log(
    tmp_path: Path,
) -> None:
    """A hook fault is never a block. Exiting 2 because the input could not be parsed would refuse
    a tool call the agent was entitled to make and publish it as a redirect that never happened."""
    config_dir = tmp_path / "config"
    log = install_native_memory_hook(config_dir, mode=NATIVE_MEMORY_HOOK_MODE_REDIRECT)
    entry = json.loads((config_dir / "settings.json").read_text("utf-8"))
    command = entry["hooks"][NATIVE_MEMORY_HOOK_EVENT][0]["hooks"][0]["command"]

    done = subprocess.run(
        command, shell=True, input="{not json", capture_output=True, text=True, timeout=60
    )

    assert done.returncode == NATIVE_MEMORY_HOOK_EXIT_ALLOW
    (record,) = hook_reaches(log)
    assert "hook_error" in record


def test_the_install_merges_into_the_rungs_seeded_settings_rather_than_replacing_them(
    tmp_path: Path,
) -> None:
    """R0's whole job is to run with the CLI's own memory system pinned off. The hook is seeded
    into the same file AFTER that pin, and an install that wrote the file fresh would turn the
    native prompt back on for exactly the rung that must not have it."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.json").write_text('{"autoMemoryEnabled": false}\n', "utf-8")

    install_native_memory_hook(config_dir)

    settings = json.loads((config_dir / "settings.json").read_text("utf-8"))
    assert settings["autoMemoryEnabled"] is False
    assert NATIVE_MEMORY_HOOK_EVENT in settings["hooks"]


def test_an_unreadable_settings_file_refuses_rather_than_dropping_the_pin(tmp_path: Path) -> None:
    """The merge cannot be done, so the alternative is discarding whatever the file held. Refusing
    costs a run; discarding silently publishes a leg as pinned when it was not."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.json").write_text("{oops", "utf-8")

    with pytest.raises(MemoryToolError, match="cannot be read"):
        install_native_memory_hook(config_dir)


def test_an_unknown_mode_is_refused_before_anything_is_written(tmp_path: Path) -> None:
    """A typo'd mode that fell through to `observe` would run a fire the operator believes is
    redirecting, and publish the resulting call rate as a redirect's effect."""
    config_dir = tmp_path / "config"

    with pytest.raises(MemoryToolError, match="unknown native-memory hook mode"):
        install_native_memory_hook(config_dir, mode="block")
    assert not (config_dir / NATIVE_MEMORY_HOOK_SCRIPT_NAME).exists()


def test_the_hook_mode_is_part_of_the_surface_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A leg run under `redirect` received guidance at the moment of its reach; one run under
    `observe` received none. Two artifacts that hashed the same would let a resume serve one for
    the other, which is how an intervention gets published as a disposition."""
    import membench.runner.tool_surface as tool_surface

    before = surface_fingerprint()
    assert "NATIVE_MEMORY_HOOK_MODE_DEFAULT" in recognizer_policy()
    monkeypatch.setattr(
        tool_surface, "NATIVE_MEMORY_HOOK_MODE_DEFAULT", NATIVE_MEMORY_HOOK_MODE_REDIRECT
    )

    assert surface_fingerprint() != before


def test_the_redirect_text_is_rendered_from_the_verbs_the_counter_scores() -> None:
    """A redirect that named a verb the recognizer does not count would produce reaches the
    artifact cannot attribute to the redirect that caused them."""
    import membench.runner.tool_surface as tool_surface

    reason = redirect_reason()
    for verb in (tool_surface.MEMORY_WRITE_VERBS[0], tool_surface.MEMORY_READ_VERBS[0]):
        assert verb in reason


def test_the_matcher_covers_every_tool_a_reach_can_arrive_through(tmp_path: Path) -> None:
    """The CLI decides which pending calls the hook even sees, from the matcher in settings.json.
    A matcher narrower than the recognizer is silent by construction: the shell path — `cat
    $CLAUDE_CONFIG_DIR/memory/MEMORY.md` — is a reach the scorer counts and the hook would never
    be asked about, so the two instruments would disagree with nothing raising."""
    import membench.runner.tool_surface as tool_surface

    config_dir = tmp_path / "config"
    install_native_memory_hook(config_dir)
    entry = json.loads((config_dir / "settings.json").read_text("utf-8"))
    matched = set(entry["hooks"][NATIVE_MEMORY_HOOK_EVENT][0]["matcher"].split("|"))

    assert matched >= {*tool_surface.NATIVE_MEMORY_TOOL_NAMES, tool_surface.NATIVE_MEMORY_BASH_TOOL}


def test_redirect_distinguishes_exact_keys_from_search_queries() -> None:
    reason = redirect_reason()
    assert 'bd remember "<content>"' in reason
    assert "bd recall <key>" in reason
    assert "bd memories <query>" in reason
    assert "bd recall <query>" not in reason
