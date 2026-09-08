"""Delivery arms differ only at their declared briefing surface."""

import hashlib
from pathlib import Path

import pytest

from membench.runner import memory_policy_handoff_package as previous
from membench.runner import memory_prime_delivery_package as package


def test_briefing_reuses_existing_guidance_without_policy_answers() -> None:
    expected = (
        (previous.OLD / "issue-rules.md").read_text()
        + "\n"
        + (previous.NEW / "memory.md").read_text()
        + previous.CATALOG
    )
    assert package.briefing() == expected
    assert "bd memories '<query>'" in expected
    assert "bd recall '<key>'" in expected
    assert "bd remember '<complete record>' --key '<key>'" in expected
    assert "Fully supplied one-off" in expected
    assert not any(value in expected for value in ("2400", "3000", "Meridian", "Courier"))


@pytest.mark.parametrize("arm", package.ARMS)
def test_same_rules_skills_and_aliases_with_only_declared_prime_difference(
    tmp_path: Path, arm: str
) -> None:
    old_work, old_store = tmp_path / "previous/work", tmp_path / "previous/store"
    reference = previous.install(old_work, old_store, "occasions")
    work, store = tmp_path / "candidate/work", tmp_path / "candidate/store"
    result = package.install(work, store, arm)
    assert result["arm"] == arm
    assert set(result["files"]) == {
        (
            str(work / Path(path).relative_to(old_work))
            if Path(path).is_relative_to(old_work)
            else str(store / Path(path).relative_to(old_store))
        )
        for path in reference["files"]
    }
    for old_path in map(Path, reference["files"]):
        relative = old_path.relative_to(
            old_work if old_path.is_relative_to(old_work) else old_store
        )
        new_path = (work if old_path.is_relative_to(old_work) else store) / relative
        if relative != Path(".beads/PRIME.md"):
            assert new_path.read_bytes() == old_path.read_bytes()
        assert result["files"][str(new_path)] == hashlib.sha256(new_path.read_bytes()).hexdigest()
    expected = (
        package.briefing() if arm == "rich-prime" else (old_work / ".beads/PRIME.md").read_text()
    )
    assert (work / ".beads/PRIME.md").read_text() == expected
    assert (store / ".beads/PRIME.md").read_text() == expected
    alias = work / ".claude/skills/beads"
    assert alias.is_symlink()
    assert alias.readlink() == Path("../../.agents/skills/beads")
    assert (alias / "SKILL.md").resolve() == work / ".agents/skills/beads/SKILL.md"
    assert result["briefing_sha256"] == hashlib.sha256(package.briefing().encode()).hexdigest()


@pytest.mark.parametrize("arm", package.ARMS)
def test_existing_prime_prevents_any_partial_install(tmp_path: Path, arm: str) -> None:
    work, store = tmp_path / "work", tmp_path / "store"
    occupied = store / ".beads/PRIME.md"
    occupied.parent.mkdir(parents=True)
    occupied.write_text("existing project workflow")
    with pytest.raises(FileExistsError):
        package.install(work, store, arm)
    assert occupied.read_text() == "existing project workflow"
    assert not work.exists()


@pytest.mark.parametrize("destination", [".agents", ".claude/skills/beads"])
def test_symlink_routes_are_rejected_before_any_write(tmp_path: Path, destination: str) -> None:
    work, store, outside = (tmp_path / name for name in ("work", "store", "outside"))
    outside.mkdir()
    (outside / "keep.txt").write_text("untouched")
    route = work / destination
    route.parent.mkdir(parents=True)
    route.symlink_to(outside, target_is_directory=True)
    with pytest.raises((ValueError, FileExistsError)):
        package.install(work, store, "rich-prime")
    assert (outside / "keep.txt").read_text() == "untouched"
    assert sorted(path.name for path in outside.iterdir()) == ["keep.txt"]
    assert not (work / "AGENTS.md").exists()
    assert not store.exists()


def test_nondirectory_parent_fails_before_any_write(tmp_path: Path) -> None:
    work, store = tmp_path / "work", tmp_path / "store"
    work.mkdir()
    (work / ".agents").write_text("existing file")
    with pytest.raises(FileExistsError):
        package.install(work, store, "rich-prime")
    assert (work / ".agents").read_text() == "existing file"
    assert not (work / "AGENTS.md").exists()
    assert not store.exists()


def test_unknown_arm_has_no_side_effects(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown"):
        package.install(tmp_path / "work", tmp_path / "store", "unknown")
    assert not list(tmp_path.iterdir())
