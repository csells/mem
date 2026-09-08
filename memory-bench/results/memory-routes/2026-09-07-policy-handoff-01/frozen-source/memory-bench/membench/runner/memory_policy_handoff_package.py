"""Matched generic/occasion guidance with the same optional actual-key catalog."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
OLD = FIXTURES / "memory-unprompted-package"
NEW = FIXTURES / "memory-policy-handoff-package"
CATALOG = """
## Project reference catalog

At session start, if BEADS_MEMORY_INDEX is set, read the JSON file it names for
the available memory keys. This catalog is a reference index, not the contents
of those records. Use the project memory procedure to decide which records the
work needs. An unset variable means this project uses search without a catalog.
"""


def install(work: Path, store: Path, arm: str) -> dict[str, Any]:
    if arm not in {"generic", "occasions"}:
        raise ValueError("Unknown instruction arm")
    source = OLD if arm == "generic" else NEW
    rules = (OLD / "issue-rules.md").read_text()
    rules += "\n" + (source / "memory-routing.md").read_text() + CATALOG
    skill = (
        (OLD / "issue-skill.md")
        .read_text()
        .replace(
            "description: Inspect, claim, implement, verify, and close assigned Beads issues.",
            "description: Work on Beads issues and preserve or retrieve durable project "
            "policies and verified engineering findings during implementation and revision.",
        )
    )
    skill += "\n" + (source / "memory-skill-routing.md").read_text()
    prime = "# Project workflow\n\nRead AGENTS.md for the project workflow and Beads skill.\n"
    files = {
        work / "AGENTS.md": rules,
        work / "CLAUDE.md": "@AGENTS.md\n",
        work / "GEMINI.md": "@AGENTS.md\n",
        work / ".agents/skills/beads/SKILL.md": skill,
        work / ".agents/skills/beads/references/memory.md": (source / "memory.md").read_text(),
        work / ".beads/PRIME.md": prime,
        store / ".beads/PRIME.md": prime,
    }
    alias = work / ".claude/skills/beads"
    for path in [*files, alias]:
        if path.exists() or path.is_symlink():
            raise FileExistsError(path)
        if any(parent.is_symlink() for parent in path.parents):
            raise ValueError(f"Package destination has symlink ancestor: {path}")
    for path, body in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as output:
            output.write(body)
    alias.parent.mkdir(parents=True, exist_ok=True)
    alias.symlink_to("../../.agents/skills/beads", target_is_directory=True)
    return {
        "arm": arm,
        "files": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
        "skill_alias": str(alias),
        "alias_target": "../../.agents/skills/beads",
        "catalog": "BEADS_MEMORY_INDEX; keys only; unset for search-only deployments",
    }
