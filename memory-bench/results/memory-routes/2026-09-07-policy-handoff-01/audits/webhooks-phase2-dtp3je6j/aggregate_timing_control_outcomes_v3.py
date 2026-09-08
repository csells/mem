"""Additional counts from completed manual audits; no candidate execution."""
import hashlib
import json
from collections import Counter
from pathlib import Path

A = Path(__file__).resolve().parent
R = A.parents[1]
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def timing(stage, leg):
    if leg.get("full_prior_body_read") is not True:
        return "no_full_prior_body"
    if stage == "2":
        return {"pre_edit": "pre_behavior_edit", "after_edit_and_tests": "after_work"}[leg["read_timing"]]
    if leg.get("first_behavior_edit_tool") is not None:
        assert leg["pre_edit_or_informed_use"] is True
        return "pre_behavior_edit"
    if leg.get("pre_edit_or_informed_use") is True:
        assert any(leg.get(k) for k in ["timing", "timing_classification"]), leg
        return "informed_validation_of_existing_behavior"
    raise AssertionError((stage, leg))


def state(leg):
    if leg.get("complete_required_agreement_at_entry", leg.get("complete_required_provider_agreement_at_entry")) is True:
        return "complete"
    if leg.get("applicable_prior_record_at_entry") is True:
        return "applicable_incomplete"
    if leg.get("related_prior_record_at_entry") is True or leg.get("full_prior_body_read") is True:
        return "related_but_not_applicable"
    return "no_applicable_record"


def counts(legs):
    return {
        "planned": len(legs),
        "prior_state": dict(Counter(x["prior_record_state"] for x in legs)),
        "full_body_timing": dict(Counter(x["timing"] for x in legs)),
        "full_body_routes": dict(Counter(x["route"] for x in legs if x["full_prior_body_read"])),
        "successful_use_timing": dict(Counter(x["timing"] for x in legs if x["successful_use"])),
        "successful_use_routes": dict(Counter(x["route"] for x in legs if x["successful_use"])),
        "successful_use": sum(x["successful_use"] for x in legs),
    }


if __name__ == "__main__":
    paths = sorted((A / "lifecycles-final-outcomes-v3").glob("*.json"))
    assert len(paths) == 20
    rows = [read(p) for p in paths]
    legs = []
    controls = []
    for row in rows:
        for stage, leg in row["retrieval_legs"].items():
            legs.append({
                "slot": row["lifecycle"] + "-" + stage,
                "profile_id": row["profile_id"], "arm": row["arm"], "stage": stage,
                "prior_record_state": state(leg),
                "full_prior_body_read": leg.get("full_prior_body_read") is True,
                "route": leg.get("route"), "timing": timing(stage, leg),
                "successful_use": leg.get("successful_use", leg.get("successful_prior_record_use")) is True,
            })
        folder = R / "cases" / row["lifecycle"] / "stage-6"
        receipts = read(folder / "raw-receipts.json")
        memory_invocations = [x for x in receipts if x.get("event") == "finish" and x.get("operation_argv", [None])[0] in {"remember", "recall", "memories", "forget", "memory"}]
        detail = read(A / (row["lifecycle"] + "-6.json"))
        control = row["stage6_control"]
        controls.append({
            "slot": row["lifecycle"] + "-6", "profile_id": row["profile_id"], "arm": row["arm"],
            "duplicate_curation": row["stage6_duplicate_curation"],
            "evidenced_new_finding": row["stage6_evidenced_new_finding"],
            "finding_scope": control.get("finding_kind", "durable_project_finding" if row["stage6_evidenced_new_finding"] else "none"),
            "wrapped_memory_invocations": [{"argv": x["operation_argv"], "returncode": x.get("returncode")} for x in memory_invocations],
            "no_wrapped_memory_invocations": not memory_invocations,
            "successful_record_writes": sum(x["operation_argv"][0] in {"remember", "forget"} and x.get("returncode") == 0 for x in memory_invocations),
            "full_prior_body_delivered": (detail["findings"].get("retrieval", {}).get("full_prior_body_read") is True or detail["findings"].get("additional_prior_body_read", {}).get("full_body_delivered") is True),
            "attachment_correct": next(x["independently_passed"] for x in detail["saved_output_oracle_recheck"]["observations"] if x["name"] == "support_attachment"),
            "whole_artifact_correct": detail["metadata"]["artifact_passed"],
        })
    data = {
        "method": "Mechanical timing categories over manually adjudicated full-body delivery and source/work chronology; raw wrapped invocations establish command activity only, not model visibility.",
        "overall": counts(legs),
        "by_stage": {s: counts([x for x in legs if x["stage"] == s]) for s in ["2", "4", "5"]},
        "by_arm": {s: counts([x for x in legs if x["arm"] == s]) for s in ["generic", "occasions"]},
        "by_profile": {s: counts([x for x in legs if x["profile_id"] == s]) for s in sorted({x["profile_id"] for x in legs})},
        "legs": legs, "controls": controls,
        "control_totals": {
            "planned": len(controls),
            "duplicate_curation": sum(x["duplicate_curation"] is True for x in controls),
            "no_wrapped_memory_invocations": sum(x["no_wrapped_memory_invocations"] for x in controls),
            "full_prior_body_delivered": sum(x["full_prior_body_delivered"] for x in controls),
            "successful_record_writes": sum(x["successful_record_writes"] for x in controls),
            "attachment_correct": sum(x["attachment_correct"] for x in controls),
            "whole_artifact_correct": sum(x["whole_artifact_correct"] for x in controls),
            "new_findings_by_scope": dict(Counter(x["finding_scope"] for x in controls)),
        },
        "input_hashes": {str(p.relative_to(R)): sha(p) for p in paths},
        "limits": [
            "A full related but inaccurate body may precede edits without supplying a correct governing agreement.",
            "Applicable incomplete includes a useful narrow engineering convention; it does not imply complete provider policy.",
            "No wrapped memory invocation is narrower than no memory work: catalogs and procedures can still be read.",
            "Raw full recall receipt alone does not establish full model delivery; that judgment comes from detailed manual traces.",
            "Informed validation means subsequent testing or test creation after receipt of the body, with behavior already implemented.",
        ],
    }
    with (A / "WEBHOOKS-TIMING-CONTROL.json").open("x") as out:
        json.dump(data, out, indent=2, ensure_ascii=False)
    print(json.dumps({"overall": data["overall"], "controls": data["control_totals"]}, indent=2))
