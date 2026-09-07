"""Admission and preservation boundaries for the new workflow screen."""

import json

import pytest

from scripts import memory_e2e_experiment as driver


def test_failed_or_partial_instruction_read_is_not_delivery(tmp_path):
    skill = tmp_path / ".agents/skills/beads"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Beads\nUse the full procedure.\n")
    (skill / "references/memory.md").write_text("First action.\nSecond action.\n")
    failed = {
        "name": "Read",
        "arguments": {"file_path": ".agents/skills/beads/SKILL.md"},
        "result": "file missing",
        "tool_result_index": 2,
        "is_error": True,
    }
    assert driver.instruction_reads([failed], tmp_path)["skill_file_read_calls"] == 0
    partial = {
        "name": "Read",
        "arguments": {"file_path": "references/memory.md"},
        "result": "1 First action.\n",
        "tool_result_index": 2,
        "is_error": False,
    }
    assert driver.instruction_reads([partial], tmp_path)["memory_workflow_read_calls"] == 0
    full = {**partial, "result": "1 First action.\n2 Second action.\n"}
    assert driver.instruction_reads([full], tmp_path)["memory_workflow_read_calls"] == 1


def test_frozen_sources_and_existing_lifecycles_cannot_be_replaced(tmp_path, monkeypatch):
    source = tmp_path / "source.py"
    source.write_text("original")
    monkeypatch.setattr(driver.base, "REPO", tmp_path)
    frozen = {"source_sha256": {"source.py": driver.base.sha(source)}, "binary_sha256": {}}
    source.write_text("changed")
    with pytest.raises(ValueError, match="Frozen source"):
        driver.assert_frozen(frozen)
    case = tmp_path / "cases/claude-installed"
    case.mkdir(parents=True)
    (case / "stream.jsonl").write_text("paid evidence")
    with pytest.raises(FileExistsError):
        driver.run_lifecycle(
            tmp_path, {"id": "claude-installed", "host": "claude", "arm": "installed"}, {}
        )
    assert (case / "stream.jsonl").read_text() == "paid evidence"


def test_qualified_smoke_cannot_survive_changed_package(tmp_path, monkeypatch):
    smoke = tmp_path / "smoke"
    smoke.mkdir()
    (smoke / "result.json").write_text(json.dumps({"admitted": True}))
    (smoke / "source-sha256.json").write_text(json.dumps({"package": "old"}))
    monkeypatch.setattr(driver, "sources", lambda: {"package": "new"})
    with pytest.raises(ValueError, match="differs"):
        driver.freeze(tmp_path / "cohort", {"claude": smoke, "codex": smoke})


def test_installed_package_mutation_is_detected_without_repair(tmp_path):
    work, store = tmp_path / "work", tmp_path / "store"
    package = driver.install_package(work, store, "installed")
    state = {"workspace": str(work), "store": str(store), "package": package}
    assert driver.package_unchanged(state)
    (work / "AGENTS.md").write_text("agent changed it")
    assert not driver.package_unchanged(state)
    assert (work / "AGENTS.md").read_text() == "agent changed it"
