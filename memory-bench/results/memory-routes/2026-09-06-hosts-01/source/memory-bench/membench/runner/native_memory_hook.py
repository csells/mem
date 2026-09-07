"""Seeing a native-memory reach AS IT HAPPENS, and optionally answering it with the bd verbs.

The scoring path in `tool_surface` reads a finished stream: it says what a leg did once the leg
is over, for the legs that survived to be scored. This module installs the same recognition as a
`PreToolUse` hook inside the leg's own `CLAUDE_CONFIG_DIR`, so the reach is recorded at the moment
the agent makes it, and — in `redirect` mode only — the call is refused with a message naming the
`bd` verbs instead.

ONE recognizer, not two. The hook subprocess imports `tool_surface.native_memory_accesses` and
decides with it; nothing here re-derives which paths count. A second copy of that grammar would
agree with the first until the day it did not, and that day is the one the hook was installed for.

The policy constants live in `tool_surface` (`NATIVE_MEMORY_HOOK_*`) rather than here, because
`recognizer_policy` enumerates that module's constants into `surface_fingerprint`: a leg run with
the hook in `redirect` mode ran under different guidance than one in `observe`, and the resume
identity has to be able to tell them apart."""

from __future__ import annotations

import json
import os
import shlex
import stat
import sys
from pathlib import Path
from typing import Any

from membench.schemas.trace import ToolCall

from .tool_surface import (
    MEMORY_COMMAND,
    MEMORY_READ_VERBS,
    MEMORY_WRITE_VERBS,
    NATIVE_MEMORY_HOOK_EVENT,
    NATIVE_MEMORY_HOOK_EXIT_ALLOW,
    NATIVE_MEMORY_HOOK_EXIT_BLOCK,
    NATIVE_MEMORY_HOOK_LOG_NAME,
    NATIVE_MEMORY_HOOK_MODE_DEFAULT,
    NATIVE_MEMORY_HOOK_MODE_REDIRECT,
    NATIVE_MEMORY_HOOK_MODES,
    NATIVE_MEMORY_HOOK_REDIRECT_REASON,
    NATIVE_MEMORY_HOOK_SCRIPT_NAME,
    NATIVE_MEMORY_HOOK_TOOLS,
    MemoryToolError,
    native_memory_accesses,
)

SETTINGS_NAME = "settings.json"


def redirect_reason() -> str:
    """The sentence `redirect` mode puts in front of the model, rendered from the verb tables the
    counter scores. Rendered, not written out again: a redirect that named a verb the recognizer
    does not count would produce reaches the artifact cannot attribute to it."""
    return NATIVE_MEMORY_HOOK_REDIRECT_REASON.format(
        command=MEMORY_COMMAND,
        write=MEMORY_WRITE_VERBS[0],
        read=MEMORY_READ_VERBS[0],
        search=MEMORY_READ_VERBS[1],
    )


def hook_settings(script: Path) -> dict[str, Any]:
    """The `hooks` block that runs ``script`` before every tool the recognizer can see a reach
    through. The matcher is built from `NATIVE_MEMORY_HOOK_TOOLS`, so it cannot watch a narrower
    set than the one scored."""
    return {
        NATIVE_MEMORY_HOOK_EVENT: [
            {
                "matcher": "|".join(NATIVE_MEMORY_HOOK_TOOLS),
                "hooks": [
                    {"type": "command", "command": shlex.join([sys.executable, str(script)])}
                ],
            }
        ]
    }


def install_native_memory_hook(
    config_dir: Path, *, mode: str = NATIVE_MEMORY_HOOK_MODE_DEFAULT
) -> Path:
    """Write the hook script into ``config_dir`` and MERGE its settings into any already there.

    Merged rather than written: the rung seeds its own `settings.json` (the `autoMemoryEnabled`
    pin) through `seed_config_dir`, and a hook install that replaced the file would silently drop
    that pin — turning the CLI's own memory prompt back on for the one rung whose whole job is to
    be free of it. Returns the log path, which is where `hook_reaches` reads the record back."""
    if mode not in NATIVE_MEMORY_HOOK_MODES:
        raise MemoryToolError(
            f"unknown native-memory hook mode {mode!r}; the modes are "
            f"{', '.join(NATIVE_MEMORY_HOOK_MODES)}"
        )
    config_dir.mkdir(parents=True, exist_ok=True)
    log_path = config_dir / NATIVE_MEMORY_HOOK_LOG_NAME
    script = config_dir / NATIVE_MEMORY_HOOK_SCRIPT_NAME
    script.write_text(_script_body(config_dir=config_dir, log_path=log_path, mode=mode), "utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)

    settings_path = config_dir / SETTINGS_NAME
    settings: dict[str, Any] = {}
    if settings_path.exists():
        try:
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise MemoryToolError(
                f"{settings_path}: the seeded settings cannot be read ({exc}), so the hook cannot "
                "be merged into them without discarding whatever pin they carry."
            ) from exc
        if not isinstance(loaded, dict):
            raise MemoryToolError(
                f"{settings_path}: settings.json is a {type(loaded).__name__}, not an object."
            )
        settings = loaded
    settings["hooks"] = {**settings.get("hooks", {}), **hook_settings(script)}
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return log_path


def _script_body(*, config_dir: Path, log_path: Path, mode: str) -> str:
    """The hook process. It runs under the CLI, not under pytest, so it re-enters this package by
    absolute path rather than relying on whatever `sys.path` the CLI happened to have."""
    roots = json.dumps([str(Path(__file__).resolve().parents[2])])
    return (
        "import json, sys\n"
        f"sys.path[:0] = {roots}\n"
        "from membench.runner.native_memory_hook import hook_decision\n"
        "sys.exit(hook_decision(sys.stdin.read(), "
        f"config_dir={str(config_dir)!r}, log_path={str(log_path)!r}, mode={mode!r}))\n"
    )


def hook_decision(payload: str, *, config_dir: str, log_path: str, mode: str) -> int:
    """Decide ONE pending tool call: record it, and block it in `redirect` mode.

    Every failure of this function's own is an ALLOW. A hook that exits 2 because its input was
    malformed would block a tool call the agent was entitled to make and publish that as the
    agent having been redirected, which is a fabricated observation; a hook that exits 0 and
    leaves a `hook_error` line loses nothing but the line it failed to write."""
    log = Path(log_path)
    try:
        event = json.loads(payload)
        name = str(event.get("tool_name", ""))
        arguments = event.get("tool_input") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        accesses = native_memory_accesses(
            [ToolCall(name=name, arguments=arguments)], config_dir=Path(config_dir)
        )
    except Exception as exc:  # see the docstring: a hook fault is never a block
        _append(log, {"hook_error": repr(exc)})
        return NATIVE_MEMORY_HOOK_EXIT_ALLOW
    if not accesses:
        return NATIVE_MEMORY_HOOK_EXIT_ALLOW
    _append(
        log,
        {
            "tool": name,
            "mode": mode,
            "paths": [access.path for access in accesses],
            "is_write": any(access.is_write for access in accesses),
            "session_id": event.get("session_id", ""),
        },
    )
    if mode != NATIVE_MEMORY_HOOK_MODE_REDIRECT:
        return NATIVE_MEMORY_HOOK_EXIT_ALLOW
    print(redirect_reason(), file=sys.stderr)
    return NATIVE_MEMORY_HOOK_EXIT_BLOCK


def _append(log: Path, record: dict[str, Any]) -> None:
    """One JSON line, appended with O_APPEND. The legs of a cell run one at a time today, but a
    truncating rewrite would lose the earlier reaches of the SAME leg the moment two tool calls
    overlap, and a lost reach reads as a leg that never made one."""
    try:
        with os.fdopen(
            os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a", encoding="utf-8"
        ) as handle:
            handle.write(json.dumps(record) + "\n")
    except OSError:
        # Nothing to do and nothing worth blocking a tool call over: the stream scorer is the
        # endpoint of record, and this log is the corroborating instrument.
        pass


def hook_reaches(log_path: Path) -> list[dict[str, Any]]:
    """The reaches the hook recorded, in order. An absent log means no reach was recorded, which
    is what a leg that never touched the native surface leaves behind — distinct from a leg the
    hook was never installed for, which the caller knows because it did the installing."""
    if not log_path.exists():
        return []
    lines = log_path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]
