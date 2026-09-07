from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from membench.runner.memory_lifecycle_gate import evaluate_gate
from membench.runner.memory_routes_grade import grade_artifact

CONFIG = {"project": "maple", "cache": {"ttl_seconds": 300, "enabled": False}}
BODY = "Approved project contract.\n```json\n" + json.dumps(CONFIG) + "\n```"


def receipt(argv, output, index, code=0):
    start = {
        "event": "start",
        "invocation_id": f"inv-{index}",
        "tool_use_id": f"tool-{index}",
        "session_id": "session",
        "leg_id": "establish",
        "operation_argv": argv,
        "argv": ["/bin/bd", "-C", "/store", *argv],
        "start_monotonic_ns": index * 10,
    }
    return [
        start,
        dict(
            start,
            event="finish",
            returncode=code,
            stdout=output,
            stderr="",
            stdout_base64=base64.b64encode(output.encode()).decode(),
            stderr_base64="",
            end_monotonic_ns=index * 10 + 1,
        ),
    ]


def artifact(tmp_path: Path, config=CONFIG):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    return path


def test_missing_required_write_is_denied(tmp_path):
    result = evaluate_gate(artifact(tmp_path), {"decision": BODY}, [], ["decision"], False)
    assert result["passed"] is False
    assert "missing_write:decision" in result["reasons"]


def test_acknowledged_write_and_exact_readback_pass(tmp_path):
    rows = receipt(["remember", BODY, "--key", "decision"], "Remembered [decision]: Approved", 1)
    rows += receipt(["recall", "decision"], BODY + "\n", 2)
    assert evaluate_gate(artifact(tmp_path), {"decision": BODY}, rows, ["decision"], False) == {
        "passed": True,
        "reasons": [],
    }


def test_later_success_without_acknowledgment_invalidates_old_verification(tmp_path):
    rows = receipt(["remember", BODY, "--key", "decision"], "Remembered [decision]: Approved", 1)
    rows += receipt(["recall", "decision"], BODY + "\n", 2)
    rows += receipt(["remember", BODY, "--key", "decision"], "", 3)
    assert (
        evaluate_gate(artifact(tmp_path), {"decision": BODY}, rows, ["decision"], False)["passed"]
        is False
    )


def chain(key="decision", body=BODY, start=1):
    return receipt(
        ["remember", body, "--key", key], f"Remembered [{key}]: Approved", start
    ) + receipt(["recall", key], body + "\n", start + 1)


def test_establish_requires_both_current_and_original_records(tmp_path):
    path = artifact(tmp_path)
    memories = {"decision": BODY, "decision.v1": BODY}
    rows = chain()
    assert evaluate_gate(path, memories, rows, list(memories), False)["passed"] is False
    rows += chain("decision.v1", start=3)
    assert evaluate_gate(path, memories, rows, list(memories), False)["passed"] is True


@pytest.mark.parametrize("mode", ["absent", "earlier", "truncated", "failed", "wrong_key"])
def test_readback_must_be_successful_exact_and_after_write(tmp_path, mode):
    rows = chain()
    if mode == "absent":
        rows = rows[:2]
    elif mode == "earlier":
        rows = receipt(["recall", "decision"], BODY + "\n", 1) + receipt(
            ["remember", BODY, "--key", "decision"], "Updated [decision]: Approved", 2
        )
    elif mode == "truncated":
        rows = rows[:2] + receipt(["recall", "decision"], BODY[:35] + "...", 2)
    elif mode == "failed":
        rows = rows[:2] + receipt(["recall", "decision"], BODY + "\n", 2, code=1)
    else:
        rows = rows[:2] + receipt(["recall", "other"], BODY + "\n", 2)
    result = evaluate_gate(artifact(tmp_path), {"decision": BODY}, rows, ["decision"], False)
    assert result["passed"] is False
    assert "missing_readback:decision" in result["reasons"]


def test_readback_before_latest_acknowledged_write_does_not_count(tmp_path):
    rows = chain() + receipt(["remember", BODY, "--key", "decision"], "Updated [decision]: ok", 3)
    assert (
        evaluate_gate(artifact(tmp_path), {"decision": BODY}, rows, ["decision"], False)["passed"]
        is False
    )


@pytest.mark.parametrize("body", ["truncated", "```json\n{bad}\n```", '{"project":true}'])
def test_capture_requires_complete_json_matching_actual_artifact(tmp_path, body):
    assert (
        evaluate_gate(
            artifact(tmp_path), {"decision": body}, chain(body=body), ["decision"], False
        )["passed"]
        is False
    )


def test_surviving_body_must_match_acknowledged_write(tmp_path):
    assert (
        evaluate_gate(
            artifact(tmp_path), {"decision": "Replaced\n" + BODY}, chain(), ["decision"], False
        )["passed"]
        is False
    )


def test_reuse_accepts_any_surviving_key_without_hidden_target(tmp_path):
    rows = receipt(["recall", "agent-chosen-alias"], BODY + "\n", 1)
    assert (
        evaluate_gate(artifact(tmp_path), {"agent-chosen-alias": BODY}, rows, [], True)["passed"]
        is True
    )


@pytest.mark.parametrize("kind", ["no_read", "missing_record", "wrong_content", "search_only"])
def test_reuse_requires_actual_exact_recall_of_surviving_record(tmp_path, kind):
    memories = {"decision": BODY}
    rows = receipt(["recall", "decision"], BODY + "\n", 1)
    if kind == "no_read":
        rows = []
    elif kind == "missing_record":
        memories = {}
    elif kind == "wrong_content":
        rows = receipt(["recall", "decision"], "some other fact\n", 1)
    else:
        rows = receipt(["memories", "maple"], BODY + "\n", 1)
    assert evaluate_gate(artifact(tmp_path), memories, rows, [], True)["passed"] is False


def test_revision_requires_old_read_before_write_but_not_old_values_in_new_artifact(tmp_path):
    old_body = BODY.replace("300", "600")
    rows = receipt(["recall", "decision"], old_body + "\n", 1) + chain(start=2)
    result = evaluate_gate(artifact(tmp_path), {"decision": BODY}, rows, ["decision"], True, False)
    assert result["passed"] is True
    result = evaluate_gate(
        artifact(tmp_path), {"decision": BODY}, chain(), ["decision"], True, False
    )
    assert "missing_prior_read:decision" in result["reasons"]


def test_unrelated_prior_recall_cannot_verify_revision_source(tmp_path):
    rows = receipt(["recall", "other"], BODY + "\n", 1) + chain(start=2)
    assert (
        evaluate_gate(artifact(tmp_path), {"decision": BODY}, rows, ["decision"], True, False)[
            "passed"
        ]
        is False
    )


def test_wrong_but_consistent_config_passes_gate_and_fails_independent_oracle(tmp_path):
    wrong = {"project": "maple", "cache": {"ttl_seconds": 900, "enabled": False}}
    body = json.dumps(wrong)
    path = artifact(tmp_path, wrong)
    assert (
        evaluate_gate(path, {"decision": body}, chain(body=body), ["decision"], False)["passed"]
        is True
    )
    assert grade_artifact(path, CONFIG)["passed"] is False


def test_json_acknowledgment_and_read_payload(tmp_path):
    rows = receipt(
        ["remember", BODY, "--key", "decision", "--json"],
        json.dumps({"action": "updated", "key": "decision"}),
        1,
    )
    rows += receipt(
        ["recall", "decision", "--json"],
        json.dumps({"found": True, "key": "decision", "value": BODY}),
        2,
    )
    assert (
        evaluate_gate(artifact(tmp_path), {"decision": BODY}, rows, ["decision"], False)["passed"]
        is True
    )


@pytest.mark.parametrize(
    "ack", ["Remembered [other]: Approved", "", '{"action":"updated","key":"other"}']
)
def test_acknowledgment_cannot_claim_another_key(tmp_path, ack):
    args = ["remember", BODY, "--key", "decision"] + (["--json"] if ack.startswith("{") else [])
    rows = receipt(args, ack, 1) + receipt(["recall", "decision"], BODY + "\n", 2)
    assert (
        evaluate_gate(artifact(tmp_path), {"decision": BODY}, rows, ["decision"], False)["passed"]
        is False
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("invocation_id", "another"),
        ("tool_use_id", "another"),
        ("argv", ["/evil"]),
        ("returncode", True),
        ("end_monotonic_ns", 0),
        ("stdout", "forged"),
        ("stdout_base64", "!!!"),
        ("operation_argv", ["recall", "wrong"]),
    ],
)
def test_malformed_receipt_pairs_are_rejected(tmp_path, field, value):
    rows = chain()
    rows[1][field] = value
    result = evaluate_gate(artifact(tmp_path), {"decision": BODY}, rows, ["decision"], False)
    assert result == {"passed": False, "reasons": ["invalid_receipts"]}


@pytest.mark.parametrize(
    "mode", ["unfinished", "duplicate", "different_session", "different_leg", "different_store"]
)
def test_receipts_must_be_complete_and_from_one_context(tmp_path, mode):
    rows = chain()
    if mode == "unfinished":
        rows.pop()
    elif mode == "duplicate":
        rows.append(dict(rows[1]))
    else:
        for row in rows[-2:]:
            if mode == "different_store":
                row["argv"] = ["/bin/bd", "-C", "/other", *row["operation_argv"]]
            else:
                row["session_id" if mode == "different_session" else "leg_id"] = "other"
    assert (
        evaluate_gate(artifact(tmp_path), {"decision": BODY}, rows, ["decision"], False)["passed"]
        is False
    )


@pytest.mark.parametrize("text", ["{bad}", "[]", '{"x":true,"x":1}', '{"x":NaN}', '{"x":1e999}'])
def test_invalid_artifact_is_denied_even_without_memory_requirements(tmp_path, text):
    path = tmp_path / "config.json"
    path.write_text(text)
    assert evaluate_gate(path, {}, [], [], False) == {
        "passed": False,
        "reasons": ["invalid_artifact"],
    }


def test_supplied_replay_requires_no_memory_calls(tmp_path):
    assert evaluate_gate(artifact(tmp_path), {}, [], [], False)["passed"] is True
