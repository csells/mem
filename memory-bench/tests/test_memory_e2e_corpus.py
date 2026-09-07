from __future__ import annotations

import json
import sys
from dataclasses import asdict

import pytest

from membench.runner.memory_e2e_corpus import (
    build_e2e_case,
    find_successor_task,
    grade_component,
    initial_scaffold,
    stage_task,
)


def materialize(tmp_path, case):
    for name, content in initial_scaffold(case).items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def write_component(tmp_path, stage, case, policy=None, implementation=None, source=None):
    version = stage.expected_version
    contract = policy if policy is not None else getattr(case, f"{version}_policy")
    provenance = source if source is not None else getattr(case, f"{version}_source")
    rationale = getattr(case, f"{version}_rationale")
    (tmp_path / stage.component).write_text(
        "from cache_engine import ResponseCache\n"
        + f"POLICY = {contract!r}\nSOURCE = {provenance!r}\nRATIONALE = {rationale!r}\n"
        + (
            implementation
            if implementation is not None
            else "def create_cache(clock):\n    return ResponseCache(POLICY['cache'], clock)\n"
        )
    )


def test_eight_real_tasks_and_only_agent_authored_direct_handoffs():
    case = build_e2e_case()
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
    assert [stage.name for stage in case.stages if stage.authored_task] == [
        "direct",
        "revised_direct",
    ]
    assert len({stage.component for stage in case.stages}) == 8
    assert json.loads(json.dumps(asdict(case)))["id"] == case.id
    for stage in case.stages:
        task = stage_task(case, stage)
        assert stage.component in task["body"]
        assert "create_cache" in task["body"]
        assert task["title"]
    for name in ("establish", "revise"):
        body = stage_task(case, next(stage for stage in case.stages if stage.name == name))["body"]
        assert "follow-up issue" in body
        assert "usable reference" in body


def test_missing_agreements_are_not_in_scaffold_or_retrieval_task_bodies():
    case = build_e2e_case()
    assert case.v1_policy != case.v2_policy
    public_scaffold = "\n".join(initial_scaffold(case).values())
    assert case.v1_source not in public_scaffold
    assert case.v1_rationale not in public_scaffold
    assert '"ttl_seconds": 600' not in public_scaffold
    for stage in case.stages:
        body = stage_task(case, stage)["body"]
        if stage.name not in {"establish", "supplied"}:
            assert json.dumps(case.v1_policy, indent=2) not in body
            assert json.dumps(case.v2_policy, indent=2) not in body
            assert '"max_entries": 3' not in body
        if stage.name == "revise":
            assert '"ttl_seconds": 300' in body
            assert "bd recall" not in body
            assert "memory key" not in body
        if stage.name in {"search", "revised_search", "historical"}:
            assert "bd recall" not in body
    assert all("catalog-response" not in body for body in case.decoys.values())


def test_actual_successor_is_selected_unchanged_without_repair():
    title = "Implement catalog_detail_cache component"
    task = {"id": "test-42", "title": title, "description": "Use bd recall actual.agent.key"}
    selected = find_successor_task([task], title)
    assert selected == {"status": "selected", "task": task, "matches": ["test-42"]}
    assert selected["task"] is task
    assert find_successor_task([], title) == {"status": "missing", "task": None, "matches": []}
    duplicate = {**task, "id": "test-43"}
    ambiguous = find_successor_task([task, duplicate], title)
    assert ambiguous["status"] == "ambiguous"
    assert ambiguous["task"] is None
    no_reference = {**task, "description": "I forgot the reference."}
    assert find_successor_task([no_reference], title)["task"] == no_reference


@pytest.mark.parametrize("stage_index", range(8))
def test_real_feature_passes_both_versions(tmp_path, stage_index):
    case = build_e2e_case()
    stage = case.stages[stage_index]
    materialize(tmp_path, case)
    write_component(tmp_path, stage, case)
    grade = grade_component(tmp_path, stage, case)
    assert grade["passed"], grade
    assert grade["behavior"]["passed"]
    assert grade["policy"]["passed"]
    assert grade["source"]["passed"]
    assert grade["rationale"]["passed"]
    assert grade["surrounding_prose"] == "not_assessed"
    assert not list(tmp_path.rglob("__pycache__"))


def test_wrong_but_consistent_artifact_and_memory_cannot_pass(tmp_path):
    case = build_e2e_case()
    stage = case.stages[0]
    materialize(tmp_path, case)
    wrong = json.loads(json.dumps(case.v1_policy))
    wrong["cache"]["ttl_seconds"] = 300
    write_component(tmp_path, stage, case, policy=wrong)
    (tmp_path / "remembered-agreement.json").write_text(json.dumps(wrong))
    grade = grade_component(tmp_path, stage, case)
    assert not grade["passed"]
    assert not grade["policy"]["passed"]
    assert not grade["behavior"]["checks"]["ttl_boundary"]


def test_runtime_behavior_is_checked_even_with_exact_policy(tmp_path):
    case = build_e2e_case()
    stage = case.stages[0]
    materialize(tmp_path, case)
    write_component(
        tmp_path,
        stage,
        case,
        implementation=(
            "def create_cache(clock):\n"
            "    return ResponseCache({**POLICY['cache'], 'max_entries': 9}, clock)\n"
        ),
    )
    grade = grade_component(tmp_path, stage, case)
    assert grade["policy"]["passed"]
    assert not grade["behavior"]["checks"]["fifo_capacity"]
    assert not grade["passed"]


def test_source_fidelity_is_separate_from_correct_runtime_behavior(tmp_path):
    case = build_e2e_case()
    stage = case.stages[0]
    materialize(tmp_path, case)
    write_component(tmp_path, stage, case, source="Agent inferred this approval")
    grade = grade_component(tmp_path, stage, case)
    assert grade["behavior"]["passed"]
    assert grade["policy"]["passed"]
    assert not grade["source"]["passed"]
    assert not grade["passed"]


@pytest.mark.parametrize(
    ("changed", "dimension"),
    [("'namespace': 'wrong'", "namespace"), ("'cache_misses': False", "cached_misses")],
)
def test_runtime_settings_cannot_hide_behind_correct_exported_policy(tmp_path, changed, dimension):
    case = build_e2e_case()
    stage = case.stages[0]
    materialize(tmp_path, case)
    write_component(
        tmp_path,
        stage,
        case,
        implementation=(
            "def create_cache(clock):\n"
            + "    return ResponseCache({**POLICY['cache'], "
            + changed
            + "}, clock)\n"
        ),
    )
    grade = grade_component(tmp_path, stage, case)
    assert grade["policy"]["passed"]
    assert not grade["behavior"]["checks"][dimension]


def test_normal_python_dataclass_component_is_importable(tmp_path):
    case = build_e2e_case()
    stage = case.stages[0]
    materialize(tmp_path, case)
    write_component(tmp_path, stage, case)
    path = tmp_path / stage.component
    path.write_text(
        "from __future__ import annotations\nfrom dataclasses import dataclass\n"
        "@dataclass\nclass Metadata:\n    label: str = 'cache'\n" + path.read_text()
    )
    grade = grade_component(tmp_path, stage, case)
    assert grade["passed"], grade


def test_missing_broken_and_timed_out_components_fail_with_evidence(tmp_path):
    case = build_e2e_case()
    stage = case.stages[0]
    assert grade_component(tmp_path, stage, case)["reason"] == "artifact_missing"
    materialize(tmp_path, case)
    (tmp_path / stage.component).write_text("raise RuntimeError('broken component')\n")
    grade = grade_component(tmp_path, stage, case)
    assert grade["reason"] == "probe_failed"
    assert "broken component" in grade["stderr"]
    (tmp_path / stage.component).write_text("while True: pass\n")
    timed = grade_component(tmp_path, stage, case, timeout_seconds=0.1)
    assert timed["reason"] == "probe_timeout"


def test_boolean_type_mismatch_is_not_equal_to_integer(tmp_path):
    case = build_e2e_case()
    stage = case.stages[0]
    materialize(tmp_path, case)
    wrong = json.loads(json.dumps(case.v1_policy))
    wrong["cache"]["cache_misses"] = 1
    write_component(tmp_path, stage, case, policy=wrong)
    assert not grade_component(tmp_path, stage, case)["policy"]["passed"]


def test_process_prefix_really_executes_probe_without_inherited_credentials(tmp_path, monkeypatch):
    case = build_e2e_case()
    stage = case.stages[0]
    materialize(tmp_path, case)
    write_component(tmp_path, stage, case)
    receipt = tmp_path / "prefix-receipt.json"
    wrapper = tmp_path / "prefix.py"
    wrapper.write_text(
        "import json, os, pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text(json.dumps({"
        "'argv': sys.argv[2:], 'environment': dict(os.environ)}))\n"
        "os.execv(sys.argv[2], sys.argv[2:])\n"
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-no-real-credential")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "another-test-only-value")
    grade = grade_component(
        tmp_path,
        stage,
        case,
        process_prefix=[sys.executable, "-I", "-B", str(wrapper), str(receipt)],
        python_executable=sys.executable,
    )
    assert grade["passed"], grade
    actual = json.loads(receipt.read_text())
    assert actual["argv"][0] == sys.executable
    assert actual["argv"][-1] == stage.component
    assert "OPENAI_API_KEY" not in actual["environment"]
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in actual["environment"]
    assert actual["environment"]["PATH"] == ""
