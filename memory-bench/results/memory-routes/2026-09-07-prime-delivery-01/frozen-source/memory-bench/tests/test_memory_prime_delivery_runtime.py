"""Startup delivery preserves ordinary task text and frozen-session evidence."""

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from membench.runner import memory_model_profiles as models
from membench.runner.memory_host_types import HostLaunch, HostObservation
from membench.runner.memory_routes_runtime import experiment_env
from scripts import memory_prime_delivery_runtime as runtime
from scripts import memory_routes_experiment as base
from scripts.memory_unprompted_experiment import session_path


def test_startup_briefing_preserves_literal_guidance_and_separate_ordinary_task() -> None:
    task = "Work on trial-417."
    guidance = "Keep `quotes`, $HOME and Unicode → unchanged.\n"
    assert runtime.compose_prompt("startup-briefing", task, guidance) == (
        "# Project startup briefing\n\n"
        "Keep `quotes`, $HOME and Unicode → unchanged.\n"
        "\n# Task\n\nWork on trial-417."
    )


@pytest.mark.parametrize("arm", ["thin-prime", "rich-prime", "startup-briefing"])
def test_delivery_evidence_distinguishes_task_startup_and_actual_prime(
    tmp_path: Path, arm: str
) -> None:
    task = "Work on trial-417."
    briefing = "Preserve approved decisions.\n"
    thin = "Read AGENTS.md.\n"
    prime = briefing if arm == "rich-prime" else thin
    delivery = runtime.record_delivery(tmp_path, arm, task, briefing, prime, prime)
    assert (tmp_path / "prompt.txt").read_text() == task
    assert (tmp_path / "task-prompt.txt").read_text() == task
    assert (tmp_path / "startup-briefing.txt").read_text() == briefing
    launched = (tmp_path / "launch-prompt.txt").read_text()
    assert launched == (
        task if arm != "startup-briefing" else runtime.compose_prompt(arm, task, briefing)
    )
    assert delivery["startup_briefing_injected"] is (arm == "startup-briefing")
    assert delivery["task_prompt_sha256"] == hashlib.sha256(task.encode()).hexdigest()
    assert delivery["launch_prompt_sha256"] == hashlib.sha256(launched.encode()).hexdigest()
    assert delivery["actual_prime_sha256"] == hashlib.sha256(prime.encode()).hexdigest()
    assert delivery["actual_prime_equals_briefing"] is (arm == "rich-prime")
    assert json.loads((tmp_path / "delivery.json").read_text()) == delivery


def test_unmatched_prime_is_rejected_before_publishing_delivery(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Actual prime output"):
        runtime.record_delivery(
            tmp_path, "rich-prime", "Work on trial-417.", "rich", "wrong", "rich"
        )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("completed", [False, True])
def test_claimed_slots_are_preserved_without_launching_again(
    tmp_path: Path, completed: bool
) -> None:
    row = {"slot": "example-1", "lifecycle": "example", "stage": 1}
    evidence = tmp_path / "cases/example/stage-1"
    evidence.mkdir(parents=True)
    prior = {"slot": "example-1", "artifact_passed": False}
    if completed:
        (evidence / "result.json").write_text(json.dumps(prior))
        assert runtime.run_session(tmp_path, row, None) == prior
    else:
        (evidence / "process.json").write_text('{"pid": 12345}')
        with pytest.raises(RuntimeError, match="cannot be rerun"):
            runtime.run_session(tmp_path, row, None)
        assert (evidence / "process.json").read_text() == '{"pid": 12345}'


@pytest.mark.skipif(sys.platform != "darwin", reason="Real sandbox-exec and bd scratch integration")
@pytest.mark.parametrize("arm", ["thin-prime", "rich-prime", "startup-briefing"])
def test_real_scratch_session_preserves_task_and_sends_only_its_assigned_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arm: str
) -> None:
    """Replace only the paid host boundary; run actual setup, subprocess and grading."""
    from membench.runner import memory_prime_delivery_package as package

    family = tmp_path / "corpus/business"
    (family / "starter").mkdir(parents=True)
    (family / "graders").mkdir()
    (family / "starter/main.py").write_text("print('\"fixture-result\"')\n")
    (family / "manifest.json").write_text('{"entrypoint":"main.py"}')
    (family / "tasks.json").write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "stage": 1,
                        "title": "Print a fixture",
                        "prompt": "Print the requested fixture.",
                    }
                ]
            }
        )
    )
    (family / "graders/stage-1.json").write_text(
        json.dumps([{"name": "fixture", "stdin": "", "expected": "fixture-result"}])
    )
    received: list[str] = []

    def prepare(
        profile: str, local: Path, env: dict[str, str], prompt: str, mode: str, budget: float
    ) -> HostLaunch:
        assert profile == "codex-sol" and mode == "isolated" and budget == 1.50
        received.append(prompt)
        fake_cli = local / "config/fake_cli.py"
        fake_cli.write_text(
            "import json, sys\n"
            "from pathlib import Path\n"
            "Path('received.json').write_text(json.dumps({'prompt': sys.argv[1]}))\n"
            "print('{}')\n"
        )
        return HostLaunch([str(base.PYTHON), str(fake_cli), prompt], env)

    monkeypatch.setattr(models, "prepare", prepare)
    monkeypatch.setattr(
        models,
        "observe",
        lambda *_: HostObservation("fixture-session", ["gpt-5.6-sol"], [], True, True),
    )
    monkeypatch.setattr(models, "export_evidence", lambda *_: None)

    def install(work: Path, store: Path, selected_arm: str) -> dict[str, Any]:
        # Deliberate unit-test scaffolding proves retained bodies and keys do not
        # enter the launch prompt. Scored experiment setup never seeds records.
        installed = package.install(work, store, selected_arm)
        admin = store.parent / "admin"
        env = experiment_env(admin / "config", admin / "tmp", admin / "bin")
        base.checked_bd(
            [
                "remember",
                "Unrelated retained body: do not inject me.",
                "--key",
                "sentinel/live-key",
            ],
            store,
            env,
        )
        return installed

    row: dict[str, Any] = {
        "slot": f"fixture-{arm}-1",
        "lifecycle": f"fixture-{arm}",
        "stage": 1,
        "host": "codex",
        "profile_id": "codex-sol",
        "family": "business",
        "arm": arm,
        "mode": "isolated",
        "catalog_mode": "indexed",
    }
    out = tmp_path / "cohort"
    result = runtime.run_session(
        out, row, None, corpus_root=tmp_path / "corpus", package_installer=install
    )
    evidence = session_path(out, row)
    task = json.loads((evidence / "task.json").read_text())
    exact_task = f"Work on {task['id']}."
    assert (evidence / "prompt.txt").read_text() == exact_task
    assert (evidence / "task-prompt.txt").read_text() == exact_task
    assert "remember" not in json.dumps(task)
    assert "recall" not in json.dumps(task)
    assert "memory" not in json.dumps(task)
    launched = json.loads((evidence / "workspace-after/received.json").read_text())["prompt"]
    assert launched == received[0] == (evidence / "launch-prompt.txt").read_text()
    assert launched == runtime.compose_prompt(arm, exact_task, package.briefing())
    assert "sentinel/live-key" not in launched
    assert "Unrelated retained body" not in launched
    assert json.loads((evidence / "memory-catalog-before.json").read_text()) == {
        "keys": ["sentinel/live-key"]
    }
    assert json.loads((evidence / "memory-before.json").read_text()) == {
        "sentinel/live-key": "Unrelated retained body: do not inject me."
    }
    assert result["delivery"]["actual_prime_equals_briefing"] is (arm == "rich-prime")
    assert result["infrastructure_fault"] is False
    assert result["administrative_memory_reads"] == 2
    assert result["artifact_passed"] is True
