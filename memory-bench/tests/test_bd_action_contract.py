"""The endpoint must witness the requested artifact, not token echoes in tool metadata."""

import json
from pathlib import Path

import pytest

from membench.runner.e1_reliability import reliability_report, score_bd_leg
from membench.schemas.trace import ToolCall
from tests.test_e1_reliability import _identified, _receipt, _row
from tests.toolreq_helpers import corpus_one


def score(task, calls, *, cwd=None, receipts=None):
    return score_bd_leg(
        task,
        calls,
        leg=1,
        role="goal",
        status="ok",
        config_dir=None,
        cwd=cwd,
        receipts=receipts,
        expected_leg_id="leg" if receipts is not None else None,
    )


def write(path, content, *, use=4, result="written", error=False):
    return ToolCall(
        name="Write",
        arguments={"file_path": path, "content": content},
        result=result,
        is_error=error,
        tool_use_index=use,
        tool_result_index=use + 1,
    )


@pytest.mark.parametrize(
    "case",
    [
        "filename",
        "wrong_name",
        "wrong_directory",
        "key_only",
        "plain_text",
        "duplicate_keys",
        "nan",
        "missing_content",
        "failed",
        "unanswered",
        "forbidden",
    ],
)
def test_non_artifact_writes_are_definite_failure(tmp_path, case):
    _, tasks = corpus_one(tmp_path)
    task = tasks[0]
    token = task.current_opaque_values[0]
    old = task.goal_step.outcome_checks[0].requires_action[0].forbidden_values[0]
    path = "config.json"
    content = json.dumps({"value": token})
    result = "written"
    error = False
    if case == "filename":
        path = token
        content = "{}"
    elif case == "wrong_name":
        path = "applied-config.json"
    elif case == "wrong_directory":
        path = "/wrong/config.json"
    elif case == "key_only":
        content = json.dumps({token: 0})
    elif case == "plain_text":
        content = token
    elif case == "duplicate_keys":
        content = '{"v":' + json.dumps(token) + ',"v":' + json.dumps(token) + "}"
    elif case == "nan":
        content = '{"v":' + json.dumps(token) + ',"n":NaN}'
    elif case == "missing_content":
        content = None
    elif case == "failed":
        error = True
    elif case == "unanswered":
        result = None
    elif case == "forbidden":
        content = json.dumps([token, old])
    evidence = score(task, [write(path, content, result=result, error=error)], cwd=Path("/work"))
    assert evidence.goal_action_success is False
    assert evidence.bd_recall_before_action is False


@pytest.mark.parametrize(
    "path,cwd,expected",
    [
        ("config.json", None, True),
        ("./config.json", None, True),
        ("/work/config.json", Path("/work"), True),
        ("/work/config.json", None, None),
        ("/work/wrong.json", None, False),
        ("../config.json", None, False),
    ],
)
def test_destination_knowledge_is_explicit(tmp_path, path, cwd, expected):
    _, tasks = corpus_one(tmp_path)
    task = tasks[0]
    content = json.dumps(task.current_opaque_values).replace("toolreq", "\\u0074oolreq")
    evidence = score(task, [write(path, content)], cwd=cwd)
    assert evidence.goal_action_success is expected
    if expected is None:
        assert evidence.bd_recall_before_action is None


def test_unrelated_later_write_cannot_move_action_after_recall(tmp_path):
    _, tasks = corpus_one(tmp_path)
    task = tasks[0]
    token = task.current_opaque_values[0]
    calls = [
        write("config.json", json.dumps(token), use=0),
        _identified("bd recall k", token, use=2, delivered=3),
        write("notes.txt", '"done"'),
    ]
    evidence = score(task, calls, receipts=_receipt("read", ["recall", "k"], token))
    assert evidence.goal_action_success is True
    assert evidence.bd_recall_before_action is False


def test_ambiguous_legacy_destination_preserves_handoff_uncertainty(tmp_path):
    _, tasks = corpus_one(tmp_path)
    task = tasks[0]
    token = task.current_opaque_values[0]
    evidence = score(
        task,
        [_identified("bd recall k", token), write("/vanished/config.json", json.dumps(token))],
        receipts=_receipt("read", ["recall", "k"], token),
    )
    establish = evidence.model_copy(
        update={"leg": 0, "role": "establish", "bd_capture_complete": True}
    )
    report = reliability_report([_row([establish, evidence])])
    assert report["groups"][0]["pairs"]["rate_bounds"] == [0, 1]
    assert report["status"] == "partial"


@pytest.mark.parametrize("delivered,expected", [(1, True), (6, False), (None, None)])
def test_receipt_free_recall_order_uses_delivery_events(tmp_path, delivered, expected):
    _, tasks = corpus_one(tmp_path)
    task = tasks[0]
    token = task.current_opaque_values[0]
    evidence = score(
        task,
        [
            _identified("bd recall k", token, delivered=delivered),
            write("config.json", json.dumps(token), use=2),
        ],
    )
    assert evidence.bd_recall_before_action is expected
    if expected is None:
        establish = evidence.model_copy(
            update={"leg": 0, "role": "establish", "bd_capture_complete": True}
        )
        report = reliability_report([_row([establish, evidence])])
        assert report["status"] == "partial"
        assert report["groups"][0]["pairs"]["measurement_incomplete"] == 1


def test_unversioned_cached_action_scores_are_not_upgraded_to_strict_success(tmp_path):
    _, tasks = corpus_one(tmp_path)
    task = tasks[0]
    token = task.current_opaque_values[0]
    goal = score(task, [_identified("bd recall k", token), write("config.json", json.dumps(token))])
    establish = goal.model_copy(update={"leg": 0, "role": "establish", "bd_capture_complete": True})
    strict = _row([establish, goal])
    old = {
        **strict,
        "work_id": "legacy",
        "bd_evidence": [
            {key: value for key, value in row.items() if key != "scoring_version"}
            for row in strict["bd_evidence"]
        ],
    }
    original = json.dumps(old, sort_keys=True)
    report = reliability_report([strict, old])
    assert report["evidence_versions"] == [0, 3]
    assert report["groups"][0]["pairs"]["rate_bounds"] == [0.5, 1]
    assert report["groups"][0]["roles"]["goal"]["legacy_goal_action_success_legs"] == 1
    assert report["groups"][0]["roles"]["goal"]["goal_action_success_legs"] == 1
    assert report["status"] == "partial"
    assert json.dumps(old, sort_keys=True) == original
