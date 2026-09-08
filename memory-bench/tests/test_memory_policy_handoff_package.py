from pathlib import Path

import pytest

from membench.runner import memory_policy_handoff_package as package


@pytest.mark.parametrize("arm", ["generic", "occasions"])
def test_deployed_skill_references_and_host_aliases_resolve(tmp_path: Path, arm: str) -> None:
    work, store = tmp_path / "work", tmp_path / "store"
    result = package.install(work, store, arm)
    skill = work / ".agents/skills/beads/SKILL.md"
    assert (work / ".claude/skills/beads/SKILL.md").resolve() == skill
    for path in result["files"]:
        assert Path(path).is_file()
    assert (skill.parent / "references/memory.md").is_file()
    assert (work / "CLAUDE.md").read_text() == (work / "GEMINI.md").read_text()
    assert (work / ".beads/PRIME.md").read_bytes() == (store / ".beads/PRIME.md").read_bytes()
    assert not any(
        "MC-" in Path(path).read_text() or "CR-" in Path(path).read_text()
        for path in result["files"]
    )


def test_install_preserves_existing_content_without_partial_write(tmp_path: Path) -> None:
    work, store = tmp_path / "work", tmp_path / "store"
    occupied = store / ".beads/PRIME.md"
    occupied.parent.mkdir(parents=True)
    occupied.write_text("existing project workflow")
    with pytest.raises(FileExistsError):
        package.install(work, store, "occasions")
    assert occupied.read_text() == "existing project workflow"
    assert not work.exists()


def test_symlink_destination_never_writes_external_location(tmp_path: Path) -> None:
    work, store = tmp_path / "work", tmp_path / "store"
    external = tmp_path / "external"
    external.mkdir()
    work.mkdir()
    (work / ".agents").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError):
        package.install(work, store, "generic")
    assert not list(external.iterdir())
    assert not (work / "AGENTS.md").exists()
