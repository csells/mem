"""Install neutral per-leg execution receipts alongside the native-memory hook."""

from __future__ import annotations

import hashlib
import json
import shlex
import sys
from pathlib import Path
from typing import Any

from membench.runner.tool_surface import MemoryToolSurface

SCRIPT_NAME = "bd-receipt-hook.py"


def receipt_path(surface: MemoryToolSurface, leg: int) -> Path:
    if surface.config_dir is None:
        raise ValueError("receipt instrumentation requires an isolated config directory")
    identity = hashlib.sha256(str(surface.config_dir.resolve()).encode()).hexdigest()[:16]
    return surface.config_dir / f"bd-{identity}-leg-{leg}.jsonl"


def prepare_receipt_leg(surface: MemoryToolSurface, *, leg: int) -> Path:
    """Replace the shim and neutral hook before each serial leg; keep prior receipts."""
    path = receipt_path(surface, leg)
    if path.exists() or path.is_symlink():
        raise ValueError("existing leg receipt evidence requires a fresh surface or cached result")
    config = path.parent
    script = config / SCRIPT_NAME
    roots = repr([str(Path(__file__).resolve().parents[2])])
    shim = surface.bin_dir / "bd"
    wrapper = config / "bd-receipt-wrapper.py"
    wrapper.write_text(
        f"import sys\nsys.path[:0] = {roots}\n"
        "from membench.runner.bd_receipts import wrapper_main\n"
        f"sys.exit(wrapper_main(binary={surface.bd_binary!r}, "
        f"store={str(surface.store_dir)!r}, receipt_path={str(path)!r}))\n",
        encoding="utf-8",
    )
    # Kernel shebang parsing cannot quote an interpreter path containing spaces.
    shim.write_text(
        f'#!/bin/sh\nexec {shlex.join([sys.executable, str(wrapper)])} "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o700)
    script.write_text(
        f"import sys\nsys.path[:0] = {roots}\n"
        "from membench.runner.bd_receipt_surface import hook_main\n"
        f"hook_main({str(path)!r})\n",
        encoding="utf-8",
    )
    settings_path = config / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    command = shlex.join([sys.executable, str(script)])
    hooks = settings.get("hooks", {})
    existing = []
    for entry in hooks.get("PreToolUse", []):
        retained = [hook for hook in entry.get("hooks", []) if hook.get("command") != command]
        if retained:
            existing.append({**entry, "hooks": retained})
    updated = {
        **settings,
        "hooks": {
            **hooks,
            "PreToolUse": [
                *existing,
                {"matcher": "Bash", "hooks": [{"type": "command", "command": command}]},
            ],
        },
    }
    settings_path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    return path


def hook_main(path_text: str) -> None:
    """Allow on instrumentation errors and preserve a diagnostic beside the receipts."""
    from membench.runner.bd_receipts import append_record, hook_response

    path = Path(path_text)
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("hook event must be an object")
        print(json.dumps(hook_response(event, leg_id=path.stem)))
    except (ValueError, TypeError) as exc:
        try:
            append_record(path, {"instrumentation_error": str(exc), "leg_id": path.stem})
        except OSError as log_error:
            print(
                f"bd receipt instrumentation: hook diagnostic write failed "
                f"({type(log_error).__name__})",
                file=sys.stderr,
            )


def read_receipts(path: Path) -> tuple[dict[str, Any], ...]:
    """Preserve malformed or interrupted rows as unknown observations, never omit them."""
    if not path.exists():
        return ()
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("receipt must be an object")
        except ValueError:
            row = {"instrumentation_error": "incomplete or malformed receipt", "raw": line}
        rows.append(row)
    return tuple(rows)
