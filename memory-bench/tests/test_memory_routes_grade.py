from __future__ import annotations

import copy
import json

import pytest

from membench.runner.memory_routes_grade import grade_artifact, grade_capture

CONFIG = {
    "service": "billing",
    "deploy": {"timeout_seconds": 91, "dry_run": False},
    "regions": ["east", "west"],
    "fallback": None,
}


def test_final_artifact_exact_nested_config(tmp_path):
    artifact = tmp_path / "config.json"
    artifact.write_text(json.dumps(CONFIG, sort_keys=True))
    assert grade_artifact(artifact, CONFIG) == {"passed": True, "reason": "exact_match"}


@pytest.mark.parametrize(
    "actual,reason",
    [
        ({**CONFIG, "deploy": {"timeout_seconds": "91", "dry_run": False}}, "type_mismatch"),
        ({**CONFIG, "deploy": {"timeout_seconds": 91.0, "dry_run": False}}, "type_mismatch"),
        ({**CONFIG, "deploy": {"timeout_seconds": 91, "dry_run": 0}}, "type_mismatch"),
        ({**CONFIG, "deploy": {"timeout_seconds": 90, "dry_run": False}}, "value_mismatch"),
        ({**CONFIG, "deploy": {"timeout_ms": 91, "dry_run": False}}, "object_keys_mismatch"),
        ({**CONFIG, "extra": "not requested"}, "object_keys_mismatch"),
        ({**CONFIG, "regions": ["west", "east"]}, "value_mismatch"),
        ({**CONFIG, "regions": ["east"]}, "array_length_mismatch"),
        ({"config": CONFIG}, "object_keys_mismatch"),
        ([CONFIG], "type_mismatch"),
    ],
)
def test_wrong_final_artifacts_fail(tmp_path, actual, reason):
    artifact = tmp_path / "config.json"
    artifact.write_text(json.dumps(actual))
    result = grade_artifact(artifact, CONFIG)
    assert result["passed"] is False
    assert result["reason"] == reason


def test_booleans_do_not_satisfy_integer_facts(tmp_path):
    artifact = tmp_path / "config.json"
    artifact.write_text('{"retries": true}')
    assert grade_artifact(artifact, {"retries": 1})["reason"] == "type_mismatch"


def test_final_state_overrules_an_earlier_correct_write(tmp_path):
    artifact = tmp_path / "config.json"
    artifact.write_text(json.dumps(CONFIG))
    assert grade_artifact(artifact, CONFIG)["passed"]
    stale = copy.deepcopy(CONFIG)
    stale["deploy"]["timeout_seconds"] = 30
    artifact.write_text(json.dumps(stale))
    assert grade_artifact(artifact, CONFIG) == {
        "passed": False,
        "reason": "value_mismatch",
        "path": "$/deploy/timeout_seconds",
    }


@pytest.mark.parametrize(
    "body",
    [
        "",
        "{",
        '{"x": 1, "x": 2}',
        '{"x": NaN}',
        '{"x": Infinity}',
        '{"x": -Infinity}',
        '{"x": 1e999}',
    ],
)
def test_malformed_json_is_never_accepted(tmp_path, body):
    artifact = tmp_path / "config.json"
    artifact.write_text(body)
    assert grade_artifact(artifact, {"x": 2})["reason"] == "malformed_json"


def test_missing_directory_symlink_and_invalid_utf8_fail(tmp_path):
    artifact = tmp_path / "config.json"
    assert grade_artifact(artifact, CONFIG)["reason"] == "artifact_missing"
    assert grade_artifact(tmp_path, CONFIG)["reason"] == "artifact_not_file"
    artifact.write_text(json.dumps(CONFIG))
    linked = tmp_path / "linked.json"
    linked.symlink_to(artifact)
    assert grade_artifact(linked, CONFIG)["reason"] == "artifact_symlink"
    artifact.write_bytes(b"\xff")
    assert grade_artifact(artifact, CONFIG)["reason"] == "malformed_json"


@pytest.mark.parametrize("label", [None, "json", "", "JSON"])
def test_literal_capture_accepts_plain_or_fenced_json(label):
    body = json.dumps(CONFIG)
    if label is not None:
        body = f"# Billing policy\nSource: release decision.\n\n```{label}\n{body}\n```\n"
    memories = {"billing-policy": body, "unrelated": "other fact"}
    assert grade_capture(memories, "billing-policy", CONFIG) == {
        "passed": True,
        "reason": "exact_match",
        "matched_key": "billing-policy",
    }


def test_capture_requires_exact_key_not_a_matching_fact_elsewhere():
    assert grade_capture({"other": json.dumps(CONFIG)}, "billing-policy", CONFIG)["reason"] == (
        "memory_key_missing"
    )


@pytest.mark.parametrize(
    "body,reason",
    [
        ('```json\n{"x": 1, "x": 1}\n```', "memory_json_malformed"),
        ('```json\n{"x": NaN}\n```', "memory_json_malformed"),
        ('```json\n{"x": 1}\n```\n```json\n{"x": 2}\n```', "memory_json_ambiguous"),
        ('```json\n{"x": 1}\n```\n```json\n{"x": 1}\n```', "memory_json_ambiguous"),
        ('{"x": "1"}', "type_mismatch"),
        ('{"x": 2}', "value_mismatch"),
        ('{"config": {"x": 1}}', "object_keys_mismatch"),
        ('{"x": 1, "stale_x": 2}', "object_keys_mismatch"),
    ],
)
def test_capture_rejects_ambiguous_malformed_and_wrong_records(body, reason):
    result = grade_capture({"policy": body}, "policy", {"x": 1})
    assert result["passed"] is False
    assert result["reason"] == reason


def test_capture_prose_is_unchecked_not_a_semantic_failure():
    result = grade_capture({"policy": "The timeout is 91 seconds."}, "policy", CONFIG)
    assert result == {"passed": None, "reason": "unsupported_capture_representation"}


def test_invalid_expected_is_an_oracle_error(tmp_path):
    with pytest.raises(ValueError, match="non-finite"):
        grade_artifact(tmp_path / "missing", {"x": float("nan")})
    with pytest.raises(ValueError, match="only JSON"):
        grade_capture({}, "k", {"x": (1, 2)})
    with pytest.raises(ValueError, match="string object keys"):
        grade_artifact(tmp_path / "missing", {1: "x"})
