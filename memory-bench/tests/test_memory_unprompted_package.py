from pathlib import Path

import pytest

from membench.runner.memory_unprompted_package import install


def test_both_arms_have_issue_skill_and_only_treatment_has_memory_guidance(tmp_path: Path) -> None:
    for arm in ("baseline", "memory"):
        work, store = tmp_path / arm / "work", tmp_path / arm / "store"
        work.mkdir(parents=True)
        store.mkdir()
        install(work, store, arm)
        assert (work / ".claude/skills/beads").resolve() == work / ".agents/skills/beads"
        assert (work / "CLAUDE.md").read_text() == "@AGENTS.md\n"
        assert (work / ".agents/skills/beads/SKILL.md").is_file()
        assert (work / ".agents/skills/beads/references/memory.md").exists() == (arm == "memory")
    a = (tmp_path / "baseline/work/AGENTS.md").read_text()
    b = (tmp_path / "memory/work/AGENTS.md").read_text()
    assert b.startswith(a)
    assert (tmp_path / "baseline/store/.beads/PRIME.md").read_bytes() == (
        tmp_path / "memory/store/.beads/PRIME.md"
    ).read_bytes()


def test_existing_or_symlinked_package_destinations_preserved(tmp_path: Path) -> None:
    work, store, outside = (tmp_path / n for n in ("work", "store", "outside"))
    for p in (work, store, outside):
        p.mkdir()
    (outside / "keep").write_text("original")
    (work / ".agents").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        install(work, store, "memory")
    assert (outside / "keep").read_text() == "original"
    assert not (work / "AGENTS.md").exists()
