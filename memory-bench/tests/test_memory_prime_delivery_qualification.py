"""Interface access, delivery and diagnostic compliance are distinct outcomes."""

import json
from pathlib import Path
from typing import Any

import pytest

from membench.runner import memory_prime_delivery_package as package
from scripts import memory_prime_delivery_qualification as qualification
from scripts import memory_prime_delivery_runtime as delivery


def fixture_result(tmp_path: Path, arm: str) -> dict[str, Any]:
    task = "Work on trial-diagnostic."
    prompt = delivery.compose_prompt(arm, task, package.briefing())
    (tmp_path / "task-prompt.txt").write_text(task)
    (tmp_path / "launch-prompt.txt").write_text(prompt)
    (tmp_path / "tool-calls.json").write_text("[]")
    return {
        "arm": arm,
        "profile_id": "codex-astra",
        "models_observed": ["gpt-6-astra"],
        "session_id": "actual-session",
        "host_success": True,
        "exit_code": 0,
        "infrastructure_fault": False,
        "timed_out": False,
        "artifact_passed": True,
        "receipt_assessment": {"executions": [], "unknown_execution": False},
    }


def test_working_interface_without_prime_compliance_is_not_excluded(tmp_path: Path) -> None:
    result = fixture_result(tmp_path, "rich-prime")
    assessed = qualification.assess_session(result, tmp_path)
    assert assessed["interface_passed"] is True
    assert assessed["diagnostic_passed"] is False
    assert assessed["agent_prime_full_output_visible"] is False


def test_raw_complete_prime_is_not_model_visible_after_truncation(tmp_path: Path) -> None:
    result = fixture_result(tmp_path, "rich-prime")
    result["receipt_assessment"]["executions"] = [
        {"command": "prime", "returncode": 0, "stdout": package.briefing()}
    ]
    (tmp_path / "tool-calls.json").write_text(
        json.dumps([{"result": package.briefing()[:90], "is_error": False}])
    )
    assessed = qualification.assess_session(result, tmp_path)
    assert assessed["agent_prime_exact_output"] is True
    assert assessed["agent_prime_full_output_visible"] is False
    assert assessed["diagnostic_passed"] is False


def test_startup_transport_and_thin_prime_are_separately_verified(tmp_path: Path) -> None:
    result = fixture_result(tmp_path, "startup-briefing")
    result["receipt_assessment"]["executions"] = [
        {"command": "prime", "returncode": 0, "stdout": package.thin_prime()}
    ]
    (tmp_path / "tool-calls.json").write_text(
        json.dumps([{"result": package.thin_prime(), "is_error": False}])
    )
    assessed = qualification.assess_session(result, tmp_path)
    assert assessed["diagnostic_passed"] is True
    assert assessed["startup_briefing_submitted"] is True
    assert assessed["rich_prime_model_output_visible"] is False


def test_model_mismatch_cannot_pass_interface(tmp_path: Path) -> None:
    result = fixture_result(tmp_path, "startup-briefing")
    result["models_observed"] = ["different-model"]
    assert qualification.assess_session(result, tmp_path)["interface_passed"] is False


def test_generated_corpus_is_single_explicit_diagnostic_and_exclusive(tmp_path: Path) -> None:
    qualification.create_corpus(tmp_path / "corpus")
    task = json.loads((tmp_path / "corpus/diagnostic/tasks.json").read_text())["tasks"][0]
    assert task["stage"] == 1
    assert "bd prime --no-memories" in task["prompt"]
    cases = json.loads((tmp_path / "corpus/diagnostic/graders/stage-1.json").read_text())
    assert cases[0]["artifact_json_path"] == "delivery-receipt.json"
    with pytest.raises(FileExistsError):
        qualification.create_corpus(tmp_path / "corpus")


def test_existing_qualification_is_never_restarted(tmp_path: Path) -> None:
    (tmp_path / "keep.txt").write_text("preserved")
    with pytest.raises(FileExistsError):
        qualification.run(tmp_path)
    assert (tmp_path / "keep.txt").read_text() == "preserved"
