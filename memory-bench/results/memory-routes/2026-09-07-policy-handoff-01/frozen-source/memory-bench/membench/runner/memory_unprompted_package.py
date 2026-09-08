"""One deployable issue workflow, with a generic memory addition in one arm."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures/memory-unprompted-package"


def install(work: Path, store: Path, arm: str) -> dict[str, Any]:
    if arm not in {"baseline", "memory"}:
        raise ValueError("Unknown instruction arm")
    rules = (FIXTURE / "issue-rules.md").read_text()
    skill = (FIXTURE / "issue-skill.md").read_text()
    if arm == "memory":
        rules += "\n" + (FIXTURE / "memory-routing.md").read_text()
        skill = skill.replace(
            "description: Inspect, claim, implement, verify, and close assigned Beads issues.",
            "description: Work on Beads issues and preserve or retrieve useful durable project "
            "knowledge during implementation, investigation, and permanent changes.",
        )
        skill += "\n" + (FIXTURE / "memory-skill-routing.md").read_text()
    prime = "# Project workflow\n\nRead AGENTS.md for the project workflow and Beads skill.\n"
    files = {
        work / "AGENTS.md": rules,
        work / "CLAUDE.md": "@AGENTS.md\n",
        work / "GEMINI.md": "@AGENTS.md\n",
        work / ".agents/skills/beads/SKILL.md": skill,
        work / ".beads/PRIME.md": prime,
        store / ".beads/PRIME.md": prime,
    }
    if arm == "memory":
        files[work / ".agents/skills/beads/references/memory.md"] = (
            FIXTURE / "memory.md"
        ).read_text()
    alias = work / ".claude/skills/beads"
    for p in [*files, alias]:
        if p.exists() or p.is_symlink():
            raise FileExistsError(p)
        for parent in p.parents:
            if parent.is_symlink():
                raise ValueError(f"Package destination has symlink ancestor: {parent}")
    for path, body in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as output:
            output.write(body)
    alias.parent.mkdir(parents=True, exist_ok=True)
    alias.symlink_to("../../.agents/skills/beads", target_is_directory=True)
    return {
        "arm": arm,
        "files": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        "skill_alias": str(alias),
        "alias_target": "../../.agents/skills/beads",
    }
