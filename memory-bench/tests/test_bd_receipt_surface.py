"""The neutral receipt hook and shim coexist with condition-specific native hooks."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from membench.runner.bd_receipt_surface import prepare_receipt_leg, read_receipts
from membench.runner.native_memory_hook import install_native_memory_hook
from membench.runner.tool_surface import MemoryToolSurface


@pytest.mark.parametrize("spaced_paths", [False, True])
def test_hook_preserves_settings_and_executes_attributed_shim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spaced_paths: bool
) -> None:
    if spaced_paths:
        tmp_path = tmp_path / "team member's checkout"
        tmp_path.mkdir()
        interpreter = tmp_path / "python interpreter"
        interpreter.symlink_to(sys.executable)
        monkeypatch.setattr(sys, "executable", str(interpreter))
    config = tmp_path / "config"
    config.mkdir()
    (config / "settings.json").write_text('{"autoMemoryEnabled": false}')
    install_native_memory_hook(config, mode="redirect")
    binary = tmp_path / "backend"
    binary.write_text('#!/bin/sh\nprintf "Remembered [example]\\n"\n')
    binary.chmod(0o700)
    bins = tmp_path / "bin"
    bins.mkdir()
    surface = MemoryToolSurface(
        store_dir=tmp_path, bin_dir=bins, bd_binary=str(binary), config_dir=config
    )
    receipt = prepare_receipt_leg(surface, leg=0)
    settings = json.loads((config / "settings.json").read_text())
    assert settings["autoMemoryEnabled"] is False
    hooks = settings["hooks"]["PreToolUse"]
    assert len(hooks) == 2
    event = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_use_id": "call-one",
        "session_id": "session",
        "tool_input": {"command": 'bd remember "fact" --key example; echo done', "timeout": 1000},
    }
    hooked = subprocess.run(
        hooks[-1]["hooks"][0]["command"],
        shell=True,
        input=json.dumps(event),
        text=True,
        capture_output=True,
        check=True,
    )
    updated = json.loads(hooked.stdout)["hookSpecificOutput"]["updatedInput"]
    assert updated["timeout"] == 1000
    result = subprocess.run(
        updated["command"],
        shell=True,
        env={**surface.env(), "PATH": str(bins)},
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == "Remembered [example]\ndone\n"
    rows = read_receipts(receipt)
    assert [row["event"] for row in rows] == ["start", "finish"]
    assert rows[-1]["argv"] == [
        str(binary),
        "-C",
        str(tmp_path),
        "remember",
        "fact",
        "--key",
        "example",
    ]
    assert rows[-1]["returncode"] == 0
    assert rows[-1]["tool_use_id"] == "call-one"
    assert rows[-1]["leg_id"] == receipt.stem
    second = prepare_receipt_leg(surface, leg=1)
    assert read_receipts(second) == ()
    assert len(json.loads((config / "settings.json").read_text())["hooks"]["PreToolUse"]) == 2
    assert len(read_receipts(receipt)) == 2


def test_partial_receipt_is_preserved_as_instrumentation_error(tmp_path: Path) -> None:
    path = tmp_path / "receipt.jsonl"
    path.write_text('{"event":"start"}\n{"event":')
    rows = read_receipts(path)
    assert rows[0]["event"] == "start"
    assert "instrumentation_error" in rows[1]


def _surface(tmp_path: Path) -> MemoryToolSurface:
    config = tmp_path / "config"
    config.mkdir(parents=True)
    (config / "settings.json").write_text('{"autoMemoryEnabled": false}')
    bins = tmp_path / "bin"
    bins.mkdir()
    return MemoryToolSurface(
        store_dir=tmp_path, bin_dir=bins, bd_binary="/bin/true", config_dir=config
    )


def test_existing_leg_receipts_cannot_be_reused(tmp_path: Path) -> None:
    import pytest

    surface = _surface(tmp_path)
    receipt = prepare_receipt_leg(surface, leg=0)
    receipt.write_text('{"event":"start"}\n')
    before = (surface.bin_dir / "bd").read_bytes()
    with pytest.raises(ValueError, match="existing"):
        prepare_receipt_leg(surface, leg=0)
    assert (surface.bin_dir / "bd").read_bytes() == before
    assert receipt.read_text() == '{"event":"start"}\n'


def test_leg_identity_distinguishes_cells(tmp_path: Path) -> None:
    from membench.runner.bd_receipt_surface import receipt_path

    first = _surface(tmp_path / "first")
    second = _surface(tmp_path / "second")
    assert receipt_path(first, 0).stem != receipt_path(second, 0).stem
    assert receipt_path(first, 0) == receipt_path(first, 0)


def test_reinstall_preserves_grouped_foreign_hook(tmp_path: Path) -> None:
    surface = _surface(tmp_path)
    prepare_receipt_leg(surface, leg=0)
    settings_path = surface.config_dir / "settings.json"
    settings = json.loads(settings_path.read_text())
    foreign = {"type": "command", "command": "foreign-observer"}
    settings["hooks"]["PreToolUse"][0]["hooks"].append(foreign)
    settings_path.write_text(json.dumps(settings))
    prepare_receipt_leg(surface, leg=1)
    updated = json.loads(settings_path.read_text())
    hooks = [hook for entry in updated["hooks"]["PreToolUse"] for hook in entry["hooks"]]
    assert foreign in hooks
    assert len(hooks) == 2
    assert updated["autoMemoryEnabled"] is False


def test_malformed_hook_with_unwritable_log_fails_open(tmp_path: Path, monkeypatch, capsys) -> None:
    import io

    from membench.runner.bd_receipt_surface import hook_main

    monkeypatch.setattr("sys.stdin", io.StringIO("{"))
    hook_main(str(tmp_path / "missing" / "receipts.jsonl"))
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "instrumentation" in captured.err
