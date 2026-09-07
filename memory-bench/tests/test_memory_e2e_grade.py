from __future__ import annotations

import json

from membench.runner.memory_e2e_corpus import build_e2e_case
from membench.runner.memory_e2e_grade import grade_retained


def record(case, version="v1", policy=None, source=None, rationale=None):
    contract = getattr(case, f"{version}_policy") if policy is None else policy
    origin = getattr(case, f"{version}_source") if source is None else source
    why = getattr(case, f"{version}_rationale") if rationale is None else rationale
    return (
        "Readable response-cache agreement.\n\n```json\n"
        + json.dumps(contract, indent=2)
        + f"\n```\n\nSOURCE: {origin}\nRATIONALE: {why}\n"
    )


def test_actual_arbitrary_keys_capture_complete_records_without_inferred_roles():
    case = build_e2e_case()
    after = {"agents-choice": record(case), "original-approval": record(case)}
    grade = grade_retained(case.decoys, {**case.decoys, **after}, case, case.stages[0])
    assert grade["current_exact_keys"] == ["agents-choice", "original-approval"]
    assert grade["history_exact_keys"] == ["agents-choice", "original-approval"]
    assert grade["standing_identity"]["passed"] is None
    assert grade["historical_bodies"]["passed"] is None
    assert grade["incomplete_keys"] == []
    assert grade["surrounding_prose"] == "not_assessed"
    assert grade["duplicate_content_groups"] == {"v1": ["agents-choice", "original-approval"]}
    assert grade["duplicate_content_groups_are_definite_duplicates"] is False


def test_no_capture_is_not_repaired_or_treated_as_unknown_success():
    case = build_e2e_case()
    grade = grade_retained(case.decoys, case.decoys, case, case.stages[0])
    assert grade["current_exact_keys"] == []
    assert grade["history_exact_keys"] == []
    assert not grade["current_content_available"]
    assert grade["changes"] == {"created": [], "updated": [], "removed": []}


def test_partial_config_and_wrong_but_self_consistent_record_fail_hidden_oracle():
    case = build_e2e_case()
    wrong = json.loads(json.dumps(case.v1_policy))
    wrong["cache"]["ttl_seconds"] = 999
    partial = {"project": "catalog-api", "cache": {"ttl_seconds": 600}}
    after = {"wrong": record(case, policy=wrong), "partial": record(case, policy=partial)}
    grade = grade_retained({}, after, case, case.stages[0])
    assert grade["current_exact_keys"] == []
    assert grade["incomplete_keys"] == ["partial", "wrong"]
    assert not grade["records"]["wrong"]["v1"]["policy"]["passed"]


def test_json_boolean_is_not_interchangeable_with_integer():
    case = build_e2e_case()
    wrong = json.loads(json.dumps(case.v1_policy))
    wrong["cache"]["cache_misses"] = 1
    grade = grade_retained({}, {"key": record(case, policy=wrong)}, case, case.stages[0])
    assert grade["records"]["key"]["v1"]["policy"]["reason"] == "type_mismatch"
    assert grade["current_exact_keys"] == []


def test_source_and_rationale_are_separate_from_exact_policy():
    case = build_e2e_case()
    after = {
        "no-source": record(case, source="Agent guessed"),
        "no-rationale": record(case, rationale="Because it is faster"),
    }
    grade = grade_retained({}, after, case, case.stages[0])
    assert grade["current_policy_exact_keys"] == ["no-rationale", "no-source"]
    assert grade["current_exact_keys"] == []
    source = grade["records"]["no-source"]["v1"]
    assert source["policy"]["passed"]
    assert not source["source"]["passed"]
    assert source["rationale"]["passed"]


def test_unsupported_prose_is_unknown_representation_not_proven_information_loss():
    case = build_e2e_case()
    after = {"prose": "Cache catalog API replies for ten minutes, including misses."}
    grade = grade_retained({}, after, case, case.stages[0])
    assert grade["unassessed_representation_keys"] == ["prose"]
    assert grade["records"]["prose"]["v1"]["policy"]["passed"] is None
    assert grade["incomplete_keys"] == []


def test_duplicate_reproduction_capture_and_historical_body_mutation_are_visible():
    case = build_e2e_case()
    before = {"standing": record(case), "snapshot": record(case)}
    after = {**before, "another-copy": before["standing"], "snapshot": before["snapshot"] + "Extra"}
    grade = grade_retained(
        before, after, case, case.stages[1], standing_keys=["standing"], history_keys=["snapshot"]
    )
    assert grade["new_exact_copy_keys"] == ["another-copy"]
    assert grade["reproduction_changes"] == {
        "created": ["another-copy"],
        "updated": ["snapshot"],
        "removed": [],
    }
    assert grade["historical_bodies"]["mutated"] == ["snapshot"]
    assert not grade["historical_bodies"]["passed"]
    assert grade["records"]["snapshot"]["v1"]["complete"]


def test_revision_of_identified_standing_key_does_not_count_as_historical_mutation():
    case = build_e2e_case()
    before = {"standing": record(case), "snapshot": record(case)}
    after = {"standing": record(case, "v2"), "snapshot": before["snapshot"]}
    grade = grade_retained(
        before, after, case, case.stages[3], standing_keys=["standing"], history_keys=["snapshot"]
    )
    assert grade["current_exact_keys"] == ["standing"]
    assert grade["history_exact_keys"] == ["snapshot"]
    assert grade["standing_identity"]["passed"]
    assert grade["standing_identity"]["all_match_current"]
    assert grade["historical_bodies"]["passed"]
    assert grade["reproduction_changes"] is None


def test_new_current_key_is_separate_from_retention_of_original_identity():
    case = build_e2e_case()
    before = {"standing": record(case), "snapshot": record(case)}
    after = {"replacement": record(case, "v2"), "snapshot": before["snapshot"]}
    grade = grade_retained(
        before, after, case, case.stages[3], standing_keys=["standing"], history_keys=["snapshot"]
    )
    assert grade["current_content_available"]
    assert grade["current_exact_keys"] == ["replacement"]
    assert not grade["standing_identity"]["passed"]
    assert grade["standing_identity"]["missing"] == ["standing"]
    assert grade["changes"]["removed"] == ["standing"]


def test_historical_reproduction_still_requires_standing_v2():
    case = build_e2e_case()
    before = {"standing": record(case, "v2"), "snapshot": record(case)}
    after = {"standing": record(case), "snapshot": before["snapshot"]}
    grade = grade_retained(before, after, case, case.stages[-1])
    assert grade["standing_version"] == "v2"
    assert grade["history_content_available"]
    assert not grade["current_content_available"]


def test_decoys_are_excluded_by_identity_only_and_decoy_mutation_is_still_visible():
    case = build_e2e_case()
    key = next(iter(case.decoys))
    after = {**case.decoys, key: record(case), "actual": record(case)}
    grade = grade_retained(case.decoys, after, case, case.stages[0])
    assert grade["current_exact_keys"] == ["actual"]
    assert key not in grade["records"]
    assert key in grade["changes"]["updated"]


def test_deleted_history_and_unknown_baselines_are_not_credited():
    case = build_e2e_case()
    before = {"snapshot": record(case)}
    removed = grade_retained(before, {}, case, case.stages[1], history_keys=["snapshot"])
    assert not removed["historical_bodies"]["passed"]
    assert removed["historical_bodies"]["missing_after"] == ["snapshot"]
    unknown = grade_retained({}, before, case, case.stages[0], history_keys=["snapshot"])
    assert unknown["historical_bodies"]["passed"] is None
    assert unknown["historical_bodies"]["missing_baseline"] == ["snapshot"]
