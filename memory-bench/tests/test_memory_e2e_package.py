from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from membench.runner.memory_e2e_corpus import build_e2e_case
from membench.runner.memory_e2e_package import candidate_policy, install_package


def roots(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "project"
    store = tmp_path / "store"
    workspace.mkdir()
    (store / ".beads").mkdir(parents=True)
    return workspace, store


def assert_manifest(manifest: dict[str, Any], workspace: Path, store: Path) -> None:
    assert json.loads(json.dumps(manifest)) == manifest
    assert str(workspace) not in json.dumps(manifest)
    assert str(store) not in json.dumps(manifest)
    locations = {"workspace": workspace, "store": store}
    for entry in manifest["files"]:
        relative = Path(entry["path"])
        assert not relative.is_absolute()
        assert ".." not in relative.parts
        target = locations[entry["root"]] / relative
        assert hashlib.sha256(target.read_bytes()).hexdigest() == entry["sha256"]
    for entry in manifest["symlinks"]:
        target = locations[entry["root"]] / entry["path"]
        assert target.is_symlink()
        assert target.readlink().as_posix() == entry["target"]
        assert target.resolve().is_relative_to(workspace.resolve())


def test_installed_imports_and_alias_resolve_to_one_canonical_procedure(tmp_path: Path) -> None:
    workspace, store = roots(tmp_path)
    manifest = install_package(workspace, store, "installed")
    assert manifest["arm"] == "installed"
    assert_manifest(manifest, workspace, store)
    for entry in ("CLAUDE.md", "GEMINI.md"):
        directive = (workspace / entry).read_text().strip()
        assert directive.startswith("@")
        assert (workspace / directive[1:]).resolve() == workspace / "AGENTS.md"
    canonical = workspace / ".agents/skills/beads"
    alias = workspace / ".claude/skills/beads"
    assert alias.resolve() == canonical.resolve()
    assert (alias / "SKILL.md").samefile(canonical / "SKILL.md")
    assert (canonical / "references/memory.md").read_text() == candidate_policy()
    assert (workspace / ".beads/PRIME.md").read_bytes() == (store / ".beads/PRIME.md").read_bytes()


def test_explicit_arm_does_not_register_or_repeat_candidate_procedure(tmp_path: Path) -> None:
    workspace, store = roots(tmp_path)
    manifest = install_package(workspace, store, "explicit")
    assert_manifest(manifest, workspace, store)
    assert not manifest["symlinks"]
    assert not list(workspace.rglob("SKILL.md"))
    assert not (workspace / ".agents").exists()
    assert not (workspace / ".claude").exists()
    for entry in manifest["files"]:
        base = workspace if entry["root"] == "workspace" else store
        content = (base / entry["path"]).read_text()
        assert candidate_policy() not in content
        assert "skills/beads" not in content
        assert "bd remember" not in content
        assert "bd recall" not in content
    assert "bd prime --no-memories" in (workspace / "AGENTS.md").read_text()


def test_shared_issue_guidance_and_candidate_bytes_match_between_arms(tmp_path: Path) -> None:
    installed, installed_store = roots(tmp_path)
    explicit = tmp_path / "explicit"
    explicit_store = tmp_path / "explicit-store"
    install_package(installed, installed_store, "installed")
    install_package(explicit, explicit_store, "explicit")
    installed_rules = (installed / "AGENTS.md").read_text()
    explicit_rules = (explicit / "AGENTS.md").read_text()
    assert installed_rules.startswith(explicit_rules.rstrip())
    # Explicit prompt delivery and a loaded skill reference expose identical bytes.
    assert (
        candidate_policy().encode()
        == (installed / ".agents/skills/beads/references/memory.md").read_bytes()
    )


def test_package_contains_no_corpus_approval_or_expected_configuration(tmp_path: Path) -> None:
    workspace, store = roots(tmp_path)
    manifest = install_package(workspace, store, "installed")
    content = "\n".join(
        ((workspace if entry["root"] == "workspace" else store) / entry["path"]).read_text()
        for entry in manifest["files"]
    )
    case = build_e2e_case()
    for source in (case.v1_source, case.v2_source, case.v1_rationale, case.v2_rationale):
        assert source not in content
    for config in (case.v1_policy, case.v2_policy):
        assert config["project"] not in content
        for field, value in config["cache"].items():
            assert f"{json.dumps(field)}: {json.dumps(value)}" not in content


@pytest.mark.parametrize("arm", ["installed", "explicit"])
def test_install_does_not_consume_or_modify_project_or_store_contents(
    tmp_path: Path, arm: str
) -> None:
    workspace, store = roots(tmp_path)
    sentinel = b"PRIVATE_APPROVAL_DO_NOT_INJECT=7198635\n"
    source = workspace / "approved.json"
    database = store / ".beads/store.db"
    source.write_bytes(sentinel)
    database.write_bytes(sentinel)
    manifest = install_package(workspace, store, arm)
    assert source.read_bytes() == sentinel
    assert database.read_bytes() == sentinel
    for entry in manifest["files"]:
        root = workspace if entry["root"] == "workspace" else store
        assert sentinel not in (root / entry["path"]).read_bytes()
    assert sentinel.decode().strip() not in candidate_policy()


def test_rejects_preexisting_store_prime_before_writing_any_project_file(tmp_path: Path) -> None:
    workspace, store = roots(tmp_path)
    prime = store / ".beads/PRIME.md"
    prime.write_text("User's existing workflow\n")
    with pytest.raises(FileExistsError):
        install_package(workspace, store, "installed")
    assert list(workspace.iterdir()) == []
    assert prime.read_text() == "User's existing workflow\n"


def test_refuses_repeat_install_without_overwriting_changed_files(tmp_path: Path) -> None:
    workspace, store = roots(tmp_path)
    install_package(workspace, store, "installed")
    rules = workspace / "AGENTS.md"
    rules.write_text("Local edit\n")
    with pytest.raises(FileExistsError):
        install_package(workspace, store, "installed")
    assert rules.read_text() == "Local edit\n"


def test_rejects_escape_through_existing_symlink_before_mutation(tmp_path: Path) -> None:
    workspace, store = roots(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / ".agents").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        install_package(workspace, store, "installed")
    assert list(outside.iterdir()) == []
    assert not (workspace / "AGENTS.md").exists()
    assert not (store / ".beads/PRIME.md").exists()


@pytest.mark.parametrize("arm", ["unknown", "Installed", "", "normal"])
def test_invalid_arm_creates_no_directories(tmp_path: Path, arm: str) -> None:
    with pytest.raises(ValueError, match="arm"):
        install_package(tmp_path / "absent", tmp_path / "absent-store", arm)
    assert list(tmp_path.iterdir()) == []


def test_shared_workspace_store_writes_prime_once(tmp_path: Path) -> None:
    project = tmp_path / "shared"
    manifest = install_package(project, project, "installed")
    assert_manifest(manifest, project, project)
    assert (project / ".beads/PRIME.md").is_file()


def test_non_directory_parent_is_rejected_before_other_writes(tmp_path: Path) -> None:
    workspace, store = roots(tmp_path)
    (workspace / ".agents").write_text("Existing file\n")
    with pytest.raises(NotADirectoryError):
        install_package(workspace, store, "installed")
    assert not (workspace / "AGENTS.md").exists()
    assert (workspace / ".agents").read_text() == "Existing file\n"


def test_store_root_below_file_is_rejected_before_workspace_writes(tmp_path: Path) -> None:
    workspace, _ = roots(tmp_path)
    obstruction = tmp_path / "not-a-directory"
    obstruction.write_text("Retain me\n")
    with pytest.raises(NotADirectoryError):
        install_package(workspace, obstruction / "store", "installed")
    assert list(workspace.iterdir()) == []
    assert obstruction.read_text() == "Retain me\n"


def test_store_under_planned_skill_alias_is_rejected_before_mutation(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    with pytest.raises(ValueError, match="alias"):
        install_package(workspace, workspace / ".claude/skills/beads", "installed")
    assert not workspace.exists()
