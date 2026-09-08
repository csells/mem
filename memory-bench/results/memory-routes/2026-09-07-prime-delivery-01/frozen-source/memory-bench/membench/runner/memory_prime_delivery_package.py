"""Deliver unchanged occasions guidance through three matched startup surfaces."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from membench.runner import memory_policy_handoff_package as previous

ARMS = ("thin-prime", "rich-prime", "startup-briefing")


def thin_prime() -> str:
    """Return the previous experiment's exact project-prime pointer."""
    return "# Project workflow\n\nRead AGENTS.md for the project workflow and Beads skill.\n"


def briefing() -> str:
    """Assemble existing guidance verbatim, without task or memory contents."""
    return (
        (previous.OLD / "issue-rules.md").read_text()
        + "\n"
        + (previous.NEW / "memory.md").read_text()
        + previous.CATALOG
    )


def install(work: Path, store: Path, arm: str) -> dict[str, Any]:
    """Install into new destinations; only rich-prime changes PRIME.md bytes.

    Startup briefing delivery belongs to the session launcher. Its on-disk prime
    remains thin so invoking the command does not deliver the rich text twice.
    """
    if arm not in ARMS:
        raise ValueError("Unknown instruction arm")
    rules = (previous.OLD / "issue-rules.md").read_text()
    rules += "\n" + (previous.NEW / "memory-routing.md").read_text() + previous.CATALOG
    skill = (
        (previous.OLD / "issue-skill.md")
        .read_text()
        .replace(
            "description: Inspect, claim, implement, verify, and close assigned Beads issues.",
            "description: Work on Beads issues and preserve or retrieve durable project "
            "policies and verified engineering findings during implementation and revision.",
        )
    )
    skill += "\n" + (previous.NEW / "memory-skill-routing.md").read_text()
    prime = briefing() if arm == "rich-prime" else thin_prime()
    files = {
        work / "AGENTS.md": rules,
        work / "CLAUDE.md": "@AGENTS.md\n",
        work / "GEMINI.md": "@AGENTS.md\n",
        work / ".agents/skills/beads/SKILL.md": skill,
        work
        / ".agents/skills/beads/references/memory.md": (previous.NEW / "memory.md").read_text(),
        work / ".beads/PRIME.md": prime,
        store / ".beads/PRIME.md": prime,
    }
    alias = work / ".claude/skills/beads"
    for path in [*files, alias]:
        if path.exists() or path.is_symlink():
            raise FileExistsError(path)
        for parent in path.parents:
            if parent.is_symlink():
                raise ValueError(f"Package destination has symlink ancestor: {parent}")
            if parent.exists() and not parent.is_dir():
                raise FileExistsError(f"Package destination has non-directory ancestor: {parent}")
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
        "briefing_sha256": hashlib.sha256(briefing().encode()).hexdigest(),
        "prime_content": "rich" if arm == "rich-prime" else "thin",
    }
