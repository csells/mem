from __future__ import annotations

import json
import re
from dataclasses import asdict

import pytest

from membench.runner.memory_routes_corpus import build_tasks


def json_blocks(text):
    return [json.loads(value) for value in re.findall(r"```json\n(.*?)\n```", text, re.S)]


def leaves(value, path=()):
    if isinstance(value, dict):
        return {
            key: leaf
            for name, child in value.items()
            for key, leaf in leaves(child, (*path, name)).items()
        }
    return {path: value}


def test_corpus_reproduces_and_changes_with_seed():
    first = build_tasks(17)
    assert [asdict(task) for task in first] == [asdict(task) for task in build_tasks(17)]
    second = build_tasks(18)
    assert len(first) == len(second) == 8
    assert {task.domain for task in first} == {
        "deployment",
        "csv_export",
        "retry_queue",
        "image_export",
        "logging",
        "backups",
        "report_format",
        "cache",
    }
    assert len({task.key for task in first}) == 8
    assert len({task.id for task in first}) == 8
    for left, right in zip(first, second, strict=True):
        assert left.key == right.key
        assert left.expected_config != right.expected_config


@pytest.mark.parametrize("seed", [0, 1, 42, 1031])
def test_source_and_supplied_control_have_exact_config_but_recall_goals_do_not(seed):
    for task in build_tasks(seed):
        assert json_blocks(task.context_note) == [task.expected_config]
        assert task.context_note in task.establish_prompt
        assert json_blocks(task.goal_prompt_unnecessary) == [task.expected_config]
        assert task.key in task.goal_prompt_direct
        assert task.key not in task.goal_prompt_search
        assert not json_blocks(task.goal_prompt_direct)
        assert not json_blocks(task.goal_prompt_search)
        assert json.dumps(task.expected_config) not in task.goal_prompt_search
        for prompt in (
            task.establish_prompt,
            task.goal_prompt_direct,
            task.goal_prompt_search,
            task.goal_prompt_unnecessary,
        ):
            assert "config.json" in prompt


@pytest.mark.parametrize("seed", [0, 42, 1031])
def test_decoys_cannot_supply_target_values_or_target_address(seed):
    for task in build_tasks(seed):
        target = leaves(task.expected_config)
        assert len(task.decoys) == 5
        assert task.key not in task.decoys
        for key, body in task.decoys.items():
            assert task.key not in body
            assert key in body
            [decoy] = json_blocks(body)
            candidate = leaves(decoy)
            assert candidate.keys() == target.keys()
            assert all(candidate[path] != value for path, value in target.items())


def test_configuration_values_keep_meaningful_types_and_ranges():
    for seed in range(20):
        for task in build_tasks(seed):
            payload = task.expected_config[task.domain]
            assert isinstance(task.expected_config["project"], str)
            assert any(type(value) is int for value in payload.values())
            assert all(value > 0 for value in payload.values() if type(value) is int)
            if task.domain == "deployment":
                assert payload["timeout_seconds"] <= 120
                assert payload["health_path"].startswith("/")
            elif task.domain == "image_export":
                assert 1 <= payload["quality"] <= 100
                assert payload["format"] in {"webp", "jpeg", "avif"}
            elif task.domain == "backups":
                assert 0 <= payload["utc_hour"] <= 23
            elif task.domain == "logging":
                assert 0 < payload["sample_rate"] <= 1
                assert type(payload["sample_rate"]) is float
                assert not payload["sample_rate"].is_integer()


@pytest.mark.parametrize("seed", [-1, True, 1.5, "1"])
def test_rejects_invalid_seed(seed):
    with pytest.raises(ValueError, match="nonnegative integer"):
        build_tasks(seed)
