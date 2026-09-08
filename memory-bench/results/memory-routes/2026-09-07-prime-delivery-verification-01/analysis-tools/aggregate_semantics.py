"""Combine independently audited judgments without inferring new semantic facts."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(rows):
    uses = [use for row in rows for use in row["eligible_uses"]]
    return {
        "planned_lifecycles": len(rows), "planned_sessions": len(rows) * 6,
        "audited_sessions": sum(len(row["assessed_audited_stages"]) for row in rows),
        "complete_lifecycles": sum(len(row["assessed_audited_stages"]) == 6 for row in rows),
        "strict_core_primary": sum(row["strict_core_primary"] is True for row in rows),
        "strict_core_primary_without_flagged_saved_claims": sum(row["strict_core_primary"] is True and not row["saved_claim_findings"] for row in rows),
        "strict_core_secondary": sum(row["strict_core_secondary"] is True for row in rows),
        "all_artifacts_correct": sum(row["artifact_all_correct"] is True for row in rows),
        "initial_capture_audited": sum(1 in row["assessed_audited_stages"] for row in rows),
        "initial_capture_faithful": sum(row["initial_faithful"] is True for row in rows),
        "initial_no_record_retained": sum(row.get("initial_record_present") is False for row in rows),
        "initial_record_present_but_not_faithful": sum(row.get("initial_record_present") is True and row["initial_faithful"] is False for row in rows),
        "retention": {
            str(stage): {"planned": len(rows),
                         "audited": sum(stage in row["assessed_audited_stages"] for row in rows),
                         "faithful": sum(row["records_stage_3_5_6_faithful"].get(str(stage)) is True for row in rows)}
            for stage in (3, 5, 6)
        },
        "eligible_use_planned": len(uses),
        "eligible_use_audited": sum(use["stage"] in row["assessed_audited_stages"] for row in rows for use in row["eligible_uses"]),
        "applicable_entry": sum(use.get("applicable_entry") is True for use in uses),
        "faithful_entry": sum(use.get("entry_faithful") is True for use in uses),
        "primary_preparatory": sum(use["primary_preparatory"] is True for use in uses),
        "primary_with_faithful_entry": sum(use["primary_preparatory"] is True and use.get("entry_faithful") is True for use in uses),
        "primary_with_incomplete_or_wrong_entry": sum(use["primary_preparatory"] is True and use.get("entry_faithful") is False for use in uses),
        "primary_entry_fidelity_unclassified": sum(use["primary_preparatory"] is True and use.get("entry_faithful") is None for use in uses),
        "secondary_informed": sum(use["secondary_informed"] is True for use in uses),
        "primary_by_route": {route: sum(use.get("route") == route and use["primary_preparatory"] is True for use in uses) for route in ("direct", "search_then_recall")},
        "unsupported_standing_or_history_mutation": sum(row["unsupported_standing_or_history_mutation"] is True for row in rows),
        "control_audited": sum(6 in row["assessed_audited_stages"] for row in rows),
        "duplicate_control": sum(row["duplicate_control"] is True for row in rows),
        "control_had_record_opportunity": sum(row.get("duplicate_control_opportunity") is True for row in rows),
        "saved_claim_findings": sum(len(row["saved_claim_findings"]) for row in rows),
        "lifecycles_with_saved_claim_findings": sum(bool(row["saved_claim_findings"]) for row in rows),
    }


def validate(manifest, rows):
    expected = {slot["lifecycle"]: slot for slot in manifest["slots"]}
    identities = [row["lifecycle"] for row in rows]
    if len(set(identities)) != len(identities) or set(identities) != set(expected):
        raise ValueError("Audits must cover every planned lifecycle exactly once")
    for row in rows:
        frozen = expected[row["lifecycle"]]
        if any(row[key] != frozen[key] for key in ("profile_id", "family", "arm", "catalog_mode")):
            raise ValueError("Audit identity differs from frozen manifest")
        stages = row["assessed_audited_stages"]
        if len(stages) != len(set(stages)) or not set(stages) <= set(range(1, 7)):
            raise ValueError("Invalid audited stages")
        if sorted(use["stage"] for use in row["eligible_uses"]) != [2, 4, 5]:
            raise ValueError("Every lifecycle needs all three planned eligible legs")
        for use in row["eligible_uses"]:
            if use["stage"] not in stages and any(use.get(key) is not None for key in ("primary_preparatory", "secondary_informed", "applicable_entry")):
                raise ValueError("An unassessed leg cannot carry an observed use outcome")
            if any(use.get(key) is True for key in ("primary_preparatory", "secondary_informed")) and (use.get("route") not in ("direct", "search_then_recall") or use.get("applicable_entry") is not True):
                raise ValueError("Successful use requires a tested route and applicable prior entry")
        complete = len(stages) == 6
        common = (row["artifact_all_correct"] is True and row["initial_faithful"] is True
                  and all(row["records_stage_3_5_6_faithful"].get(str(stage)) is True for stage in (3, 5, 6))
                  and row["unsupported_standing_or_history_mutation"] is False
                  and row["duplicate_control"] is False)
        for kind, use_key in (("primary", "primary_preparatory"), ("secondary", "secondary_informed")):
            correct = bool(common and all(use[use_key] is True for use in row["eligible_uses"])) if complete else None
            if row[f"strict_core_{kind}"] is not correct:
                raise ValueError("Reported strict intersection disagrees with audited components")


def combine(root, audit_paths):
    manifest = read(root / "manifest.json")
    rows = [row for path in audit_paths for row in read(path)["lifecycles"]]
    validate(manifest, rows)
    for row in rows:
        actual = []
        for stage in range(1, 7):
            path = root / "cases" / row["lifecycle"] / f"stage-{stage}" / "result.json"
            if path.exists():
                actual.append((stage, read(path)))
        initial = root / "cases" / row["lifecycle"] / "stage-1"
        row["initial_record_present"] = bool(read(initial / "memory-after.json")) if (initial / "result.json").exists() else None
        if [stage for stage, _ in actual] != sorted(row["assessed_audited_stages"]):
            raise ValueError("Semantic audit does not cover exactly the assessed stages")
        correct = all(result["artifact_passed"] for _, result in actual) if len(actual) == 6 else None
        if row["artifact_all_correct"] is not correct:
            raise ValueError("Semantic artifact verdict disagrees with independent hidden grades")
        grades = {stage: result["artifact_passed"] for stage, result in actual}
        for use in row["eligible_uses"]:
            if any(use.get(key) is True for key in ("primary_preparatory", "secondary_informed")) and grades.get(use["stage"]) is not True:
                raise ValueError("Successful use requires correct subsequent work")
    excluded = {("claude-sonnet", "finance"), ("codex-luna", "webhooks")}
    matched = [row for row in rows if (row["profile_id"], row["family"]) not in excluded]
    without_recovery = [row for row in matched if (row["profile_id"], row["family"]) != ("codex-astra", "finance")]
    result = {
        "schema": "prime-delivery-semantic-summary.v1", "created_ns": time.time_ns(),
        "manifest_sha256": digest(root / "manifest.json"),
        "audit_sha256": {str(path): digest(path) for path in audit_paths},
        "overall": metrics(rows), "lifecycles": rows,
        "predeclared_complete_cells": metrics(matched),
        "predeclared_complete_cells_without_recovered_cell": metrics(without_recovery),
        "limits": ["Counts inherit the explicitly recorded independent semantic judgments.",
                   "Planned denominators retain infrastructure-censored slots.",
                   "Complete-cell sensitivity is interpretable only with its assessed/complete counts.",
                   "Strict core does not certify every saved prose or provenance claim."],
    }
    for field in ("arm", "profile_id", "family", "catalog_mode"):
        result[field] = {value: metrics([row for row in rows if row[field] == value]) for value in dict.fromkeys(row[field] for row in rows)}
    result["profile_arm"] = {f"{profile}/{arm}": metrics([row for row in rows if row["profile_id"] == profile and row["arm"] == arm]) for profile in manifest["admitted_profile_ids"] for arm in ("thin-prime", "rich-prime", "startup-briefing")}
    result["matched_arm"] = {arm: metrics([row for row in matched if row["arm"] == arm]) for arm in ("thin-prime", "rich-prime", "startup-briefing")}
    result["matched_without_recovered_arm"] = {arm: metrics([row for row in without_recovery if row["arm"] == arm]) for arm in ("thin-prime", "rich-prime", "startup-briefing")}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--audit", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = combine(args.root, args.audit)
    with args.out.open("x") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print(json.dumps(result["overall"], indent=2))
