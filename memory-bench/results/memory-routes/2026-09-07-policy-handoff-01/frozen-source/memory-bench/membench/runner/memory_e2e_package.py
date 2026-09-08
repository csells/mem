"""Install the project-only workflow fixture without running tools or reading state.

The detailed memory procedure has one source: the skill's memory reference.
The explicit arm receives those bytes through candidate_policy(); only the
installed arm registers the skill. Repository/archived-source execution requires
the fixtures directory alongside membench. No global configuration is modified.
Existing destination files are refused, even when their bytes would match.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures/memory-e2e-package"
_SKILL = Path(".agents/skills/beads")
_REFERENCE = _SKILL / "references/memory.md"
_SLOT = "{{MEMORY_ROUTING}}"


def candidate_policy() -> str:
    """Return the exact installed memory procedure for explicit prompt delivery."""
    return (_FIXTURES / _REFERENCE).read_text(encoding="utf-8")


def _template(name: str, routing: str) -> bytes:
    text = (_FIXTURES / name).read_text(encoding="utf-8")
    if text.count(_SLOT) != 1:
        raise ValueError(f"Expected one routing slot in {name}")
    return (text.replace(_SLOT, routing).rstrip() + "\n").encode("utf-8")


def _preflight(root: Path, relative: Path) -> None:
    """Reject existing destinations and symlink/non-directory ancestors."""
    target = root / relative
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    parent = target.parent
    while True:
        if parent.is_symlink():
            raise ValueError(f"Package destination has a symlink ancestor: {parent}")
        if parent.exists() and not parent.is_dir():
            raise NotADirectoryError(parent)
        if parent == parent.parent:
            break
        parent = parent.parent


def install_package(workspace: Path, store: Path, arm: str) -> dict[str, Any]:
    """Install into scratch roots; return relative file hashes and alias targets.

    Accept only ``installed`` or ``explicit``. Missing directories are created
    after all targets pass preflight. The caller must serialize installation;
    preflight is a preservation check, not protection against concurrent hostile
    filesystem changes. No bd initialization, model invocation, or hooks occur.
    """
    if arm not in {"installed", "explicit"}:
        raise ValueError("arm must be 'installed' or 'explicit'")
    locations = {"workspace": workspace.resolve(), "store": store.resolve()}
    routing = (
        (_FIXTURES / "memory-routing.md").read_text(encoding="utf-8").rstrip()
        if arm == "installed"
        else ""
    )
    files: list[tuple[str, Path, bytes]] = [
        ("workspace", Path("AGENTS.md"), _template("AGENTS.md", routing)),
        ("workspace", Path("CLAUDE.md"), (_FIXTURES / "CLAUDE.md").read_bytes()),
        ("workspace", Path("GEMINI.md"), (_FIXTURES / "GEMINI.md").read_bytes()),
        ("workspace", Path(".beads/PRIME.md"), _template("PRIME.md", routing)),
        ("store", Path(".beads/PRIME.md"), _template("PRIME.md", routing)),
    ]
    aliases: list[tuple[str, Path, str]] = []
    if arm == "installed":
        files.extend(
            ("workspace", relative, (_FIXTURES / relative).read_bytes())
            for relative in (_SKILL / "SKILL.md", _REFERENCE)
        )
        aliases.append(("workspace", Path(".claude/skills/beads"), "../../.agents/skills/beads"))

    destinations: dict[Path, bytes] = {}
    for scope, relative, content in files:
        root = locations[scope]
        _preflight(root, relative)
        target = root / relative
        if target in destinations and destinations[target] != content:
            raise ValueError(f"Conflicting package destinations: {target}")
        destinations[target] = content
    for scope, relative, _ in aliases:
        alias = locations[scope] / relative
        if any(target.is_relative_to(alias) for target in destinations):
            raise ValueError(f"Package file overlaps a planned alias: {alias}")
        _preflight(locations[scope], relative)

    for target, content in destinations.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write(content)
    for scope, relative, alias_target in aliases:
        target = locations[scope] / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(alias_target, target_is_directory=True)

    return {
        "schema_version": 1,
        "arm": arm,
        "files": [
            {
                "root": scope,
                "path": relative.as_posix(),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            for scope, relative, content in files
        ],
        "symlinks": [
            {"root": scope, "path": relative.as_posix(), "target": alias_target}
            for scope, relative, alias_target in aliases
        ],
    }
