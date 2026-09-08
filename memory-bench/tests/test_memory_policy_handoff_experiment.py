from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from membench.runner.memory_host_types import HostLaunch, HostObservation
from scripts import memory_policy_handoff_experiment as policy
from scripts import memory_unprompted_experiment as runtime


def test_fixed_schedule_pairs_world_and_route_without_exposing_variant_in_lifecycle() -> None:
    rows = policy.schedule()
    assert len(rows) == len({r["slot"] for r in rows}) == 264
    assert {p: sum(r["phase"] == p for r in rows) for p in policy.PHASES} == {
        "phase1": 80,
        "phase2": 160,
        "normal": 24,
    }
    for profile in policy.profiles.PROFILES:
        modes = []
        for family in policy.WORLDS:
            selected = [
                r
                for r in rows
                if r["profile_id"] == profile and r["family"] == family and r["mode"] == "isolated"
            ]
            assert len(selected) == 12
            assert len({r["corpus_family"] for r in selected}) == 1
            assert len({r["catalog_mode"] for r in selected}) == 1
            modes.append(selected[0]["catalog_mode"])
            assert all(r["corpus_family"].split("/")[-1] not in r["lifecycle"] for r in selected)
        assert set(modes) == {"indexed", "search-only"}
    anchors = [r for r in rows if r["phase"] == "normal" and r["stage"] == 1]
    assert len({(r["corpus_family"], r["catalog_mode"]) for r in anchors}) == 4


@pytest.mark.parametrize("ids", [["codex-astra", "codex-astra"], ["invented-profile"]])
def test_schedule_rejects_invalid_profile_identity(ids: list[str]) -> None:
    with pytest.raises(ValueError):
        policy.schedule(ids)


def test_freeze_requires_explicit_profile_and_complete_input_admission(tmp_path: Path) -> None:
    review = tmp_path / "review.json"
    review.write_text(json.dumps({"approved": True, "admitted_profile_ids": ["codex-astra"]}))
    with pytest.raises(ValueError, match="All ten"):
        policy.freeze(tmp_path / "cohort", review)
    assert not (tmp_path / "cohort").exists()
    review.write_text(
        json.dumps(
            {
                "approved": True,
                "admitted_profile_ids": list(policy.profiles.PROFILES),
                "reviewed_sha256": {},
                "behavioral_diagnostics_passed": False,
            }
        )
    )
    with pytest.raises(ValueError, match="every new corpus"):
        policy.freeze(tmp_path / "cohort", review)
    assert not (tmp_path / "cohort").exists()


def test_catalog_contains_actual_keys_only_and_never_changes_the_store(tmp_path: Path) -> None:
    before = {"project/é": "private full body", "project/a": "other body"}
    env = {"OTHER": "preserved", "BEADS_MEMORY_INDEX": "/unrelated/index"}
    result = runtime.prepare_catalog(tmp_path, before, "indexed", env)
    assert result == {"keys": ["project/a", "project/é"]}
    assert json.loads(Path(env["BEADS_MEMORY_INDEX"]).read_text()) == result
    assert "private full body" not in Path(env["BEADS_MEMORY_INDEX"]).read_text()
    assert before == {"project/é": "private full body", "project/a": "other body"}
    assert env["OTHER"] == "preserved"
    with pytest.raises(FileExistsError):
        runtime.prepare_catalog(tmp_path, {}, "indexed", env)


@pytest.mark.parametrize("mode", ["none", "search-only"])
def test_unindexed_launch_cannot_inherit_an_external_catalog(tmp_path: Path, mode: str) -> None:
    env = {"BEADS_MEMORY_INDEX": "/unrelated/index"}
    assert runtime.prepare_catalog(tmp_path, {"actual/key": "body"}, mode, env) is None
    assert "BEADS_MEMORY_INDEX" not in env
    assert not (tmp_path / "memory-catalog.json").exists()


@pytest.mark.parametrize("kind", ["symlink", "fifo"])
def test_catalog_evidence_does_not_follow_links_or_block_on_special_files(
    tmp_path: Path, kind: str
) -> None:
    catalog = tmp_path / "memory-catalog.json"
    if kind == "symlink":
        outside = tmp_path / "outside.txt"
        outside.write_text("unrelated private contents")
        catalog.symlink_to(outside)
    else:
        os.mkfifo(catalog)
    evidence = runtime.catalog_evidence(catalog)
    assert evidence["text"] is None
    assert "read_error" in evidence


def test_frozen_input_tree_detects_new_unreviewed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "task.json").write_text("original")
    monkeypatch.setattr(runtime.base, "REPO", tmp_path)
    monkeypatch.setattr(runtime.e2e, "assert_frozen", lambda _: None)
    monkeypatch.setattr(runtime, "profile_hashes", lambda: {})
    manifest = {
        "profile_sha256": {},
        "input_tree_sha256": {"corpus": {"corpus/task.json": runtime.base.sha(root / "task.json")}},
    }
    runtime.assert_frozen(manifest)
    (root / "new-instructions.md").write_text("unreviewed")
    with pytest.raises(runtime.FrozenInputsChangedError, match="input tree"):
        runtime.assert_frozen(manifest)


def test_new_phase_requires_review_of_exact_prior_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = {"slots": [], "require_phase_review": True}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    prior = tmp_path / "phases/phase1"
    prior.mkdir(parents=True)
    (prior / "completed.json").write_text('{"assessed":80}')
    monkeypatch.setattr(runtime, "assert_frozen", lambda _: None)
    with pytest.raises(ValueError, match="explicit review"):
        runtime.run_phase(tmp_path, "phase2", phases=policy.PHASES)
    assert not (tmp_path / "phases/phase2").exists()
    (prior / "reviewed.json").write_text('{"approved":true,"summary_sha256":"stale"}')
    with pytest.raises(ValueError, match="exact final summary"):
        runtime.run_phase(tmp_path, "phase2", phases=policy.PHASES)
    assert not (tmp_path / "phases/phase2").exists()
    (prior / "reviewed.json").write_text(
        json.dumps({"approved": True, "summary_sha256": runtime.base.sha(prior / "completed.json")})
    )
    monkeypatch.setattr(runtime.hosts, "MODELS", {})
    runtime.run_phase(tmp_path, "phase2", phases=policy.PHASES)
    assert (tmp_path / "phases/phase2/completed.json").is_file()


def test_review_coverage_includes_transitive_guidance_and_external_admission() -> None:
    required = policy.review_paths()
    assert "memory-bench/fixtures/memory-unprompted-package/memory.md" in required
    assert "specs/plans/0006-policy-handoff-model-sweep.md" in required
    assert any(p.endswith("qualification-admission.json") for p in required)


def test_profile_session_uses_actual_before_keys_and_explicit_model_through_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No agent process or Beads command is launched. The orchestration seam is
    # exercised with a deterministic process/adapter fixture and real snapshots.
    scratch = tmp_path / "scratch"
    workspace = scratch / "work"
    workspace.mkdir(parents=True)
    (workspace / "main.py").write_text("# ordinary starter\n")
    store = scratch / "store"
    store.mkdir()
    family = tmp_path / "corpus/finance/account-first"
    family.mkdir(parents=True)
    (family / "manifest.json").write_text('{"entrypoint":"main.py"}')
    (family / "tasks.json").write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "stage": 1,
                        "title": "Business task",
                        "prompt": "Return the requested statement.",
                    }
                ]
            }
        )
    )
    state = {
        "scratch": str(scratch),
        "workspace": str(workspace),
        "store": str(store),
        "env": {},
        "package": {"files": {}},
    }
    row = {
        "slot": "codex-sol-finance-generic-isolated-1",
        "lifecycle": "codex-sol-finance-generic-isolated",
        "host": "codex",
        "profile_id": "codex-sol",
        "family": "finance",
        "corpus_family": "finance/account-first",
        "arm": "generic",
        "mode": "isolated",
        "stage": 1,
        "catalog_mode": "indexed",
    }
    evidence_parent = tmp_path / "cohort/cases" / row["lifecycle"]
    evidence_parent.mkdir(parents=True)
    calls = []
    monkeypatch.setattr(runtime, "setup", lambda *_, **__: state)
    monkeypatch.setattr(runtime.e2e, "create_task", lambda *_: {"id": "actual-123"})
    monkeypatch.setattr(
        runtime.e2e, "all_tasks", lambda *_: [{"id": "actual-123", "status": "closed"}]
    )
    monkeypatch.setattr(
        runtime.base, "memories", lambda *_: {"actual/key": "Never inject this body"}
    )
    monkeypatch.setattr(runtime.receipts, "prepare", lambda *_, **__: (tmp_path / "log", None))
    monkeypatch.setattr(runtime.receipts, "read", lambda *_: [])
    monkeypatch.setattr(
        runtime.receipts, "assess", lambda *_, **__: {"executions": [], "unknown_execution": False}
    )
    monkeypatch.setattr(runtime, "experiment_env", lambda *_: {})
    monkeypatch.setattr(runtime, "shell_environment", lambda _, env: env)
    monkeypatch.setattr(runtime, "make_profile", lambda path, *_: path)
    monkeypatch.setattr(runtime.smoke, "secret_values", lambda *_: [])
    monkeypatch.setattr(runtime.smoke, "sanitize", lambda text, _: (text, False))
    monkeypatch.setattr(
        runtime, "grade", lambda *_, **__: {"passed": True, "correct": 1, "total": 1, "cases": []}
    )

    def prepare(
        profile: str, local: Path, env: dict[str, str], prompt: str, *args: Any
    ) -> HostLaunch:
        calls.append(("prepare", profile))
        assert prompt == "Work on actual-123."
        assert json.loads(Path(env["BEADS_MEMORY_INDEX"]).read_text()) == {"keys": ["actual/key"]}
        assert "account-first" not in str(local)
        return HostLaunch(["fake-agent"], env)

    def observe(profile: str, *_: Any) -> HostObservation:
        calls.append(("observe", profile))
        return HostObservation("session-1", ["gpt-5.6-sol"], [], True, True)

    monkeypatch.setattr(runtime.model_profiles, "prepare", prepare)
    monkeypatch.setattr(runtime.model_profiles, "observe", observe)
    monkeypatch.setattr(
        runtime.model_profiles,
        "export_evidence",
        lambda profile, *_: calls.append(("export", profile)),
    )

    class Process:
        pid = 987654321

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs["stdout"].write("{}\n")
            kwargs["stdout"].flush()

        def wait(self, **kwargs: Any) -> int:
            return 0

    monkeypatch.setattr(runtime.subprocess, "Popen", Process)
    result = runtime.run_session(tmp_path / "cohort", row, None, corpus_root=tmp_path / "corpus")
    assert calls == [("prepare", "codex-sol"), ("observe", "codex-sol"), ("export", "codex-sol")]
    assert result["model_requested"] == "gpt-5.6-sol"
    assert result["infrastructure_fault"] is False
    assert result["artifact_passed"] is True
    evidence = runtime.session_path(tmp_path / "cohort", row)
    assert json.loads((evidence / "memory-catalog-before.json").read_text()) == {
        "keys": ["actual/key"]
    }
    assert json.loads((evidence / "memory-before.json").read_text()) == {
        "actual/key": "Never inject this body"
    }


@pytest.mark.skipif(sys.platform != "darwin", reason="Real macOS read-only grader sandbox")
@pytest.mark.parametrize(
    "kind",
    ["valid", "escape", "absolute", "symlink", "parent_symlink", "fifo", "boolean", "duplicate"],
)
def test_artifact_grading_uses_safe_readonly_json_path(tmp_path: Path, kind: str) -> None:
    workspace, local, hidden = (tmp_path / n for n in ("work", "local", "hidden/world"))
    for p in (workspace, local, hidden):
        p.mkdir(parents=True)
    (hidden / "graders").mkdir()
    (hidden / "manifest.json").write_text('{"entrypoint":"main.py"}')
    (hidden / "tasks.json").write_text('{"tasks":[]}')
    outside = tmp_path / "outside.json"
    outside.write_text('{"value":7}')
    path = "support/output.json"
    (workspace / "support").mkdir()
    target = workspace / path
    if kind == "escape":
        path = "../outside.json"
    elif kind == "absolute":
        path = str(outside)
    elif kind == "symlink":
        target.symlink_to(outside)
    elif kind == "parent_symlink":
        (workspace / "link").symlink_to(tmp_path)
        path = "link/outside.json"
    elif kind == "fifo":
        os.mkfifo(target)
    elif kind == "boolean":
        target.write_text('{"value":true}')
    elif kind == "duplicate":
        target.write_text('{"value":0,"value":7}')
    else:
        target.write_text('{"value":7}')
    (hidden / "graders/stage-6.json").write_text(
        json.dumps([{"name": "artifact", "artifact_json_path": path, "expected": {"value": 7}}])
    )
    result = runtime.grade(
        workspace,
        local,
        {"family": "logical", "corpus_family": "world", "stage": 6},
        corpus_root=tmp_path / "hidden",
    )
    assert result["passed"] is (kind == "valid")
    assert outside.read_text() == '{"value":7}'
