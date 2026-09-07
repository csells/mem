"""Independent checks of route evidence and cross-session carryover boundaries."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from membench.runner.memory_routes_corpus import build_tasks
from membench.schemas.trace import ToolCall
from tests.test_bd_real_metrics import call, receipts, score

SPEC = importlib.util.spec_from_file_location(
    "memory_routes_experiment", Path(__file__).parents[1] / "scripts/memory_routes_experiment.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

EXPECTED = {"project": "billing", "deploy": {"timeout_seconds": 91, "dry_run": False}}


def observed(body, *, verb="recall", visible=True, code=0, result_index=3):
    if verb == "recall":
        argv = ["recall", "billing-policy", "--json"]
        payload = {"schema_version": 1, "found": True, "key": "billing-policy", "value": body}
    else:
        argv = ["memories", "billing", "--json"]
        payload = {"schema_version": 1, "billing-policy": body}
    output = json.dumps(payload)
    tool = call("bd " + " ".join(argv), output if visible else "unrelated output")
    tool = tool.model_copy(update={"tool_result_index": result_index})
    return score(receipts(argv, output, code), [tool]).model_dump(mode="json"), [tool]


def write(path: Path, index=5):
    return ToolCall(
        name="Write",
        arguments={"file_path": str(path), "content": json.dumps(EXPECTED)},
        result="File written successfully",
        tool_use_id="write",
        tool_use_index=index,
        tool_result_index=index + 1,
    )


@pytest.mark.parametrize("verb", ["recall", "memories"])
def test_correct_payload_is_observed_on_the_actual_route(tmp_path, verb):
    observation, calls = observed(json.dumps(EXPECTED), verb=verb)
    artifact = tmp_path / "config.json"
    result = MODULE.route_summary(observation, [*calls, write(artifact)], artifact, EXPECTED)
    assert result["bd_correct_payload_observed"] is True
    assert result["bd_correct_payload_via_direct"] is (verb == "recall")
    assert result["bd_correct_payload_via_search"] is (verb == "memories")
    assert result["bd_correct_payload_before_first_config_write"] is True


@pytest.mark.parametrize("verb", ["recall", "memories"])
def test_decoy_read_does_not_count_as_useful_retrieval(tmp_path, verb):
    decoy = {**EXPECTED, "project": "unrelated"}
    observation, calls = observed(json.dumps(decoy), verb=verb)
    artifact = tmp_path / "config.json"
    result = MODULE.route_summary(observation, [*calls, write(artifact)], artifact, EXPECTED)
    assert result["bd_correct_payload_observed"] is False
    assert result["bd_correct_payload_via_direct"] is False
    assert result["bd_correct_payload_via_search"] is False
    assert result["bd_correct_payload_before_first_config_write"] is False


def test_explicit_lookup_miss_is_not_a_useful_payload(tmp_path):
    output = json.dumps({"schema_version": 1, "found": False, "key": "billing-policy"})
    tool = call("bd recall billing-policy --json", output)
    observation = score(
        receipts(["recall", "billing-policy", "--json"], output), [tool]
    ).model_dump(mode="json")
    artifact = tmp_path / "config.json"
    result = MODULE.route_summary(observation, [tool, write(artifact)], artifact, EXPECTED)
    assert result["bd_correct_payload_observed"] is False
    assert result["bd_correct_payload_before_first_config_write"] is False


@pytest.mark.parametrize("visible,code", [(False, 0), (True, 1)])
def test_hidden_or_failed_return_cannot_establish_useful_delivery(tmp_path, visible, code):
    observation, calls = observed(json.dumps(EXPECTED), visible=visible, code=code)
    artifact = tmp_path / "config.json"
    result = MODULE.route_summary(observation, [*calls, write(artifact)], artifact, EXPECTED)
    assert result["bd_correct_payload_observed"] is False
    assert result["bd_correct_payload_before_first_config_write"] is False


def test_prose_payload_remains_semantically_unchecked(tmp_path):
    observation, calls = observed("Billing deploy timeout is 91 seconds; dry-run is off.")
    artifact = tmp_path / "config.json"
    result = MODULE.route_summary(observation, [*calls, write(artifact)], artifact, EXPECTED)
    assert result["bd_correct_payload_observed"] is None
    assert result["bd_correct_payload_before_first_config_write"] is None


@pytest.mark.parametrize("wrong_path", ["other/config.json", "not-config.json"])
def test_timing_requires_the_exact_configuration_path(tmp_path, wrong_path):
    observation, calls = observed(json.dumps(EXPECTED))
    artifact = tmp_path / "config.json"
    result = MODULE.route_summary(
        observation, [*calls, write(tmp_path / wrong_path)], artifact, EXPECTED
    )
    assert result["bd_read_before_first_config_write"] is None
    assert result["bd_correct_payload_before_first_config_write"] is None


def test_bash_artifact_write_does_not_fabricate_write_tool_timing(tmp_path):
    observation, calls = observed(json.dumps(EXPECTED))
    bash = ToolCall(
        name="Bash",
        arguments={"command": "printf '%s' '{}' > config.json"},
        result="",
        tool_use_id="bash-write",
        tool_use_index=5,
        tool_result_index=6,
    )
    result = MODULE.route_summary(observation, [*calls, bash], tmp_path / "config.json", EXPECTED)
    assert result["bd_read_before_first_config_write"] is None
    assert result["bd_correct_payload_before_first_config_write"] is None


@pytest.mark.parametrize("read_result_index", [5, 7])
def test_correct_read_delivered_too_late_is_not_before_action(tmp_path, read_result_index):
    observation, calls = observed(json.dumps(EXPECTED), result_index=read_result_index)
    artifact = tmp_path / "config.json"
    result = MODULE.route_summary(observation, [*calls, write(artifact, 5)], artifact, EXPECTED)
    assert result["bd_correct_payload_observed"] is True
    assert result["bd_correct_payload_before_first_config_write"] is False


def init(**changes):
    return {
        "type": "system",
        "subtype": "init",
        "model": MODULE.MODEL,
        "session_id": "session-1",
        **changes,
    }


def test_session_identity_requires_one_pinned_init():
    event = init()
    assert MODULE.session_event(json.dumps(event))["session_id"] == "session-1"


@pytest.mark.parametrize(
    "events",
    [
        [],
        [init(), init()],
        [init(model="other-model")],
        [init(session_id="")],
        [init(session_id="  ")],
        [init(session_id=None)],
    ],
)
def test_invalid_session_identity_refuses(events):
    with pytest.raises((ValueError, RuntimeError)):
        MODULE.session_event("\n".join(json.dumps(event) for event in events))


@pytest.mark.parametrize("capture_target", [False, True])
def test_goal_branches_transfer_actual_memories_without_task_or_workspace_answers(
    tmp_path, monkeypatch, capture_target
):
    task = build_tasks(20260906)[0]
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(MODULE.tempfile, "mkdtemp", lambda **kwargs: str(scratch))
    monkeypatch.setattr(MODULE, "experiment_env", lambda *args: {})
    states = {}
    seen = []

    def initialize(store, env, evidence):
        store.mkdir()
        states[store] = {}
        MODULE.new_json(evidence, {"returncode": 0})

    def checked(args, store, env):
        assert args[0] == "remember" and args[2] == "--key"
        states[store][args[3]] = args[1]
        return "Remembered"

    def leg(**kwargs):
        name, store = kwargs["leg"], kwargs["store"]
        seen.append(name)
        if name == "establish":
            workspace = scratch / "establish" / "work"
            workspace.mkdir(parents=True)
            (workspace / "config.json").write_text(json.dumps(task.expected_config))
            (store / "private-task-history.txt").write_text(json.dumps(task.expected_config))
            if capture_target:
                states[store][task.key] = task.context_note
            states[store]["additional-agent-memory"] = "An actual extra agent record."
            native = scratch / "establish-native"
            native.mkdir()
        else:
            assert not (store / "private-task-history.txt").exists()
            assert not (scratch / name / "work" / "config.json").exists()
            assert kwargs["native_from"] is None
            assert (task.key in states[store]) is capture_target
            assert states[store]["additional-agent-memory"] == "An actual extra agent record."
            assert "goal-only-mutation" not in states[store]
            states[store]["goal-only-mutation"] = name
            native = scratch / "unused-native"
        return {"leg": name}, native

    monkeypatch.setattr(MODULE, "initialize_store", initialize)
    monkeypatch.setattr(MODULE, "checked_bd", checked)
    monkeypatch.setattr(MODULE, "memories", lambda store, env: dict(states[store]))
    monkeypatch.setattr(MODULE, "run_leg", leg)
    out = tmp_path / "out"
    MODULE.run_case(out, task, "examples", 0.5)
    assert seen == ["establish", "direct", "search", "unnecessary"]
    directory = out / "cases" / f"{task.id}-examples"
    transferred = [
        json.loads((directory / f"transferred-{route}.json").read_text())
        for route in ("direct", "search", "unnecessary")
    ]
    assert transferred[0] == transferred[1] == transferred[2]
    assert (task.key in transferred[0]) is capture_target
    result = json.loads((directory / "result.json").read_text())
    assert result["capture"]["passed"] is capture_target
    # A duplicate invocation cannot overwrite evidence or purchase more legs.
    with pytest.raises(FileExistsError):
        MODULE.run_case(out, task, "examples", 0.5)
    assert len(seen) == 4
