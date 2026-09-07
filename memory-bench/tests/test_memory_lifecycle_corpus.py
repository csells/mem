from __future__ import annotations

import json
import re
from dataclasses import asdict

import pytest

from membench.runner.memory_lifecycle_corpus import build_lifecycles
from membench.runner.memory_routes_corpus import build_tasks


def test_lifecycle_reuses_original_contract_and_revises_exactly_one_typed_field():
    original = {task.domain: task for task in build_tasks(20260907)}
    lifecycles = build_lifecycles()
    assert [case.domain for case in lifecycles] == [
        "cache",
        "csv_export",
        "image_export",
        "logging",
    ]
    for case in lifecycles:
        assert case.task == original[case.domain]
        assert case.initial_config == original[case.domain].expected_config
        assert case.key == case.task.key
        assert case.historical_key == case.key + ".v1"
        assert [stage.name for stage in case.stages] == [
            "establish",
            "direct",
            "search",
            "revise",
            "revised_direct",
            "revised_search",
            "supplied",
            "historical",
        ]
        assert [stage.expected_version for stage in case.stages] == [
            "v1",
            "v1",
            "v1",
            "v2",
            "v2",
            "v2",
            "v2",
            "v1",
        ]
        assert case.revised_config["project"] == case.initial_config["project"]
        before = case.initial_config[case.domain]
        after = case.revised_config[case.domain]
        assert after.keys() == before.keys()
        changed = [field for field in before if before[field] != after[field]]
        assert len(changed) == 1
        assert case.revision_patch == {case.domain: {changed[0]: after[changed[0]]}}
        assert all(type(before[field]) is type(after[field]) for field in before)
        for stage in case.stages:
            expected = (
                case.initial_config if stage.expected_version == "v1" else case.revised_config
            )
            assert stage.expected_config == expected


def json_blocks(text):
    return [json.loads(value) for value in re.findall(r"```json\n(.*?)\n```", text, re.S)]


@pytest.mark.parametrize("seed", [0, 20260907, 20260908])
def test_missing_information_stays_out_of_prompts_and_revision_supplies_only_its_patch(seed):
    for case in build_lifecycles(seed):
        stages = {stage.name: stage for stage in case.stages}
        assert json_blocks(stages["establish"].prompt) == [case.initial_config]
        assert json_blocks(stages["supplied"].prompt) == [case.revised_config]
        assert json_blocks(stages["revise"].prompt) == [case.revision_patch]
        [changed] = case.revision_patch[case.domain]
        for name, stage in stages.items():
            assert "config.json" in stage.prompt
            if name not in {"establish", "supplied", "revise"}:
                assert not json_blocks(stage.prompt)
            if name in {"establish", "supplied"}:
                continue
            for field, value in case.initial_config[case.domain].items():
                # A JSON contract pair cannot be supplied accidentally in any
                # missing-information prompt, except the explicit revision patch.
                if name == "revise" and field == changed:
                    continue
                literal_pair = f"{json.dumps(field)}: {json.dumps(value)}"
                assert literal_pair not in stage.prompt
                assert f"`{field}`" not in stage.prompt
        for name in ("search", "revised_search"):
            assert case.initial_config["project"] in stages[name].prompt.lower().replace(" ", "-")
            assert case.key not in stages[name].prompt
            assert case.historical_key not in stages[name].prompt
            assert stages[name].lookup_key is None


def test_public_workflow_requirements_distinguish_capture_retrieval_and_reproduction():
    for case in build_lifecycles():
        for stage in case.stages:
            assert stage.capture_required is (stage.name in {"establish", "revise"})
            assert stage.retrieval_required is (stage.name not in {"establish", "supplied"})
            if stage.name == "establish":
                assert stage.required_write_keys == (case.key, case.historical_key)
                assert all(key in stage.prompt for key in stage.required_write_keys)
                assert stage.source_label in stage.prompt
            elif stage.name == "revise":
                assert stage.required_write_keys == (case.key,)
                assert stage.lookup_key == case.key
                assert f"at `{case.historical_key}` unchanged" in stage.prompt
                assert stage.source_label in stage.prompt
            else:
                assert stage.required_write_keys == ()
                assert "ordinary reproduction of an existing approval" in stage.prompt
        direct = [stage for stage in case.stages if stage.name in {"direct", "revised_direct"}]
        assert all(stage.lookup_key == case.key for stage in direct)
        historical = case.stages[-1]
        assert historical.lookup_key == case.historical_key
        assert case.historical_key in historical.prompt
        assert historical.expected_config != case.stages[-2].expected_config
        assert "permanent current agreement remains version v2" in historical.prompt


def test_corpus_is_deterministic_and_keeps_source_task_and_version_objects_separate():
    first = build_lifecycles()
    assert [asdict(case) for case in first] == [asdict(case) for case in build_lifecycles(20260907)]
    second = build_lifecycles(20260908)
    assert len({case.id for case in first + second}) == 8
    for left, right in zip(first, second, strict=True):
        assert left.key == right.key
        assert left.initial_config != right.initial_config
        assert left.revised_config is not left.initial_config
        assert left.initial_config is not left.task.expected_config
        assert len({id(stage.expected_config) for stage in left.stages}) == 8
        assert left.key not in left.task.decoys
        assert left.historical_key not in left.task.decoys


def test_revision_keeps_boolean_and_fractional_contract_types():
    for seed in range(20):
        cases = {case.domain: case for case in build_lifecycles(seed)}
        image = cases["image_export"]
        assert type(image.revision_patch["image_export"]["strip_metadata"]) is bool
        assert (
            image.initial_config["image_export"]["strip_metadata"]
            is not image.revised_config["image_export"]["strip_metadata"]
        )
        logging = cases["logging"]
        rate = logging.revision_patch["logging"]["sample_rate"]
        assert type(rate) is float
        assert 0 < rate < 1
        assert not rate.is_integer()
        for case in cases.values():
            for config in (case.initial_config, case.revised_config):
                assert json.loads(json.dumps(config)) == config
                if case.domain != "csv_export":
                    assert any(type(value) is bool for value in config[case.domain].values())


@pytest.mark.parametrize("seed", [-1, True, 1.5, "20260907"])
def test_rejects_invalid_seeds(seed):
    with pytest.raises(ValueError, match="nonnegative integer"):
        build_lifecycles(seed)
