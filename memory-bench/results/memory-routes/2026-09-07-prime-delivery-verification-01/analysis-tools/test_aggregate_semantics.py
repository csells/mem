"""Guard the planned denominators and strict intersection without model calls."""
import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("aggregate", Path(__file__).with_name("aggregate_semantics.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    identity = {"lifecycle": "example", "profile_id": "model", "family": "finance", "arm": "thin-prime", "catalog_mode": "indexed"}
    row = {**identity, "assessed_audited_stages": list(range(1, 7)),
           "artifact_all_correct": True, "initial_faithful": True,
           "records_stage_3_5_6_faithful": {"3": True, "5": True, "6": True},
           "unsupported_standing_or_history_mutation": False, "duplicate_control": False,
           "saved_claim_findings": [], "strict_core_primary": True, "strict_core_secondary": True,
           "eligible_uses": [{"stage": stage, "route": "direct", "primary_preparatory": True, "secondary_informed": True, "applicable_entry": True} for stage in (2, 4, 5)]}
    return {"slots": [identity]}, row


def test_missing_or_duplicate_planned_lifecycle_is_rejected():
    manifest, row = fixture()
    for rows in ([], [row, copy.deepcopy(row)]):
        with pytest.raises(ValueError, match="every planned lifecycle"):
            module.validate(manifest, rows)


def test_censored_lifecycle_keeps_planned_denominator_and_cannot_be_success():
    manifest, row = fixture()
    row["assessed_audited_stages"] = []
    with pytest.raises(ValueError, match="unassessed leg"):
        module.validate(manifest, [row])
    for key in ("artifact_all_correct", "initial_faithful", "unsupported_standing_or_history_mutation", "duplicate_control", "strict_core_primary", "strict_core_secondary"):
        row[key] = None
    row["records_stage_3_5_6_faithful"] = {str(stage): None for stage in (3, 5, 6)}
    for use in row["eligible_uses"]:
        use.update(route=None, primary_preparatory=None, secondary_informed=None, applicable_entry=None)
    module.validate(manifest, [row])
    counts = module.metrics([row])
    assert counts["planned_sessions"] == 6
    assert counts["eligible_use_planned"] == 3
    assert counts["audited_sessions"] == counts["eligible_use_audited"] == counts["strict_core_primary"] == 0


def test_late_confirmation_is_secondary_only_even_with_correct_artifacts():
    manifest, row = fixture()
    row["eligible_uses"][0]["primary_preparatory"] = False
    with pytest.raises(ValueError, match="strict intersection"):
        module.validate(manifest, [row])
    row["strict_core_primary"] = False
    module.validate(manifest, [row])
    counts = module.metrics([row])
    assert counts["strict_core_primary"] == 0
    assert counts["strict_core_secondary"] == 1
    assert counts["primary_preparatory"] == 2


@pytest.mark.parametrize("component", ["initial_faithful", "artifact_all_correct"])
def test_component_failure_cannot_be_hidden_by_successful_command_use(component):
    manifest, row = fixture()
    row[component] = False
    with pytest.raises(ValueError, match="strict intersection"):
        module.validate(manifest, [row])


@pytest.mark.parametrize("change", [{"route": "bulk_or_other"}, {"applicable_entry": False}])
def test_bulk_or_inapplicable_record_cannot_earn_tested_route_credit(change):
    manifest, row = fixture()
    row["eligible_uses"][0].update(change)
    with pytest.raises(ValueError, match="tested route and applicable"):
        module.validate(manifest, [row])
