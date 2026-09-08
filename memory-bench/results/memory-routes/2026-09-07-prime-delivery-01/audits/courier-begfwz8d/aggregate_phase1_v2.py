"""Append a phase-1 aggregate of manually adjudicated Courier stage evidence."""
import hashlib
import json
import time
from pathlib import Path
A = Path(__file__).resolve().parent
C = A.parents[1]
manifest = json.loads((C / "manifest.json").read_text())
rows = [r for r in manifest["slots"] if r["family"] == "webhooks"]
all_audits = {}
for row in rows:
    path = A / (row["slot"] + ".json")
    if path.exists():
        value = json.loads(path.read_text())
        if value.get("schema") == "prime-courier-stage-audit.v1":
            for count_key in ("record_count_before", "record_count_after"):
                if count_key not in value:
                    value[count_key] = value["capture"][count_key]
            all_audits[row["slot"]] = value
censored = "codex-luna-webhooks-thin-prime-isolated"
lifecycles = []
for life in sorted({r["lifecycle"] for r in rows}):
    planned = [r for r in rows if r["lifecycle"] == life]
    observed = {r["stage"]: all_audits[r["slot"]] for r in planned if r["slot"] in all_audits}
    base = planned[0]
    missing_status = "censored_original_prelaunch_claim" if life == censored else "pending"
    initial = observed.get(1)
    uses = []
    for stage in (2, 4, 5):
        item = observed.get(stage)
        if item is None:
            uses.append({"stage": stage, "status": missing_status, "route": None, "primary_preparatory": None, "secondary_informed": None, "applicable_entry": None, "entry_faithful": None, "required_agreement_entry_sensitivity": None})
            continue
        use = dict(item["eligible_use"])
        use["status"] = "assessed"
        use["evidence_path"] = str((A / (item["slot"] + ".json")).relative_to(C))
        use.setdefault("entry_faithful", bool(use.get("entry_complete_for_required_facts")))
        use.setdefault("entry_scope_status", "complete_provider_agreement" if use["entry_faithful"] else "no_prior_entry")
        use.setdefault("required_agreement_entry_sensitivity", bool(use["primary_preparatory"] and use["entry_faithful"]))
        use.setdefault("required_current_task_identity_entry_sensitivity", bool(use["primary_preparatory"] and use["entry_faithful"]))
        uses.append(use)
    lifecycles.append({
        **{key: base[key] for key in ("lifecycle", "profile_id", "family", "arm", "catalog_mode", "corpus_family")},
        "status": "censored" if life == censored else "phase1_assessed" if set(observed) >= {1, 2} else "phase1_pending",
        "planned_sessions": 6,
        "assessed_sessions": len(observed),
        "initial_faithful": initial["capture"]["faithful_complete_agreement"] if initial else None,
        "initial_capture_status": initial["capture"]["status"] if initial else missing_status,
        "initial_capture_count": initial["record_count_after"] if initial else None,
        "initial_capture_trigger_limit": "The provider agreement was already a durable project document; missing keyed handoff is not automatically disobedience of newly-approved-knowledge wording.",
        "records_stage_3_5_6_faithful": None,
        "records_stage_3_5_6_details": [{"stage": stage, "faithful": None, "status": missing_status} for stage in (3, 5, 6)],
        "artifact_all_correct": None,
        "artifact_observed_all_correct": all(x["artifact"]["passed"] for x in observed.values()) if observed else None,
        "unsupported_standing_or_history_mutation": None,
        "unsupported_standing_or_history_mutation_observed": any(x["unsupported_standing_or_history_mutation"] for x in observed.values()) if observed else None,
        "unsupported_standing_extension_observed": any(x.get("unsupported_standing_extension", False) for x in observed.values()) if observed else None,
        "duplicate_control": None,
        "duplicate_control_opportunity": False,
        "duplicate_control_status": missing_status,
        "eligible_uses": uses,
        "strict_core_primary": None,
        "strict_core_secondary": None,
        "strict_core_observed_failure": bool(initial is not None and not initial["capture"]["faithful_complete_agreement"] or any(not x["artifact"]["passed"] for x in observed.values())),
        "saved_claim_findings": [{"stage": stage, **finding} for stage, x in observed.items() for finding in x["saved_claim_findings"]],
        "stages": [{"stage": stage, "status": "assessed", "audit_path": str((A / (x["slot"] + ".json")).relative_to(C)), "artifact": x["artifact"], "capture": x["capture"], "exposure": x["exposure"]} for stage, x in sorted(observed.items())],
    })
phase1 = [a for a in all_audits.values() if a["stage"] in (1, 2)]
initials = [a for a in phase1 if a["stage"] == 1]
uses = [u for life in lifecycles for u in life["eligible_uses"] if u["status"] == "assessed"]
summary = {
    "planned_lifecycles": 18, "planned_sessions": 108, "planned_eligible_uses": 54,
    "phase1_planned": 36, "phase1_assessable": 34, "phase1_assessed": len(phase1),
    "phase1_artifact_passes": sum(a["artifact"]["passed"] for a in phase1),
    "initial_assessed": len(initials), "initial_faithful": sum(a["capture"]["faithful_complete_agreement"] for a in initials),
    "initial_any_capture": sum(a["record_count_after"] > 0 for a in initials),
    "initial_incomplete_capture": sum(a["record_count_after"] > 0 and not a["capture"]["faithful_complete_agreement"] for a in initials),
    "initial_no_capture": sum(a["record_count_after"] == 0 for a in initials),
    "eligible_use_assessed": len(uses), "primary_preparatory_broad_applicability": sum(u["primary_preparatory"] for u in uses),
    "primary_complete_faithful_entry": sum(u["primary_preparatory"] and u["entry_faithful"] for u in uses),
    "primary_incomplete_entry": sum(u["primary_preparatory"] and not u["entry_faithful"] for u in uses),
    "strict_required_agreement_entry_sensitivity": sum(u["required_agreement_entry_sensitivity"] for u in uses),
    "stage2_late_capture": sum(a["stage"] == 2 and a["record_count_before"] == 0 and a["record_count_after"] > 0 for a in phase1),
    "actual_rich_prime_full": sum(bool(a["exposure"].get("actual_rich_prime_full")) for a in phase1),
    "startup_submitted": sum(bool(a["exposure"].get("startup_submitted")) for a in phase1),
    "startup_raw_observed": sum(a["exposure"].get("startup_observed") is True for a in phase1),
    "prime_misrouted_to_native_skill": sum(bool(a["exposure"].get("misrouted_prime_to_skill")) for a in phase1),
}
value = {"schema": "prime-courier-lifecycle-audit.v1", "status": "phase1_final" if len(phase1) == 34 else "phase1_partial", "created_ns": time.time_ns(), "manifest_sha256": hashlib.sha256((C / "manifest.json").read_bytes()).hexdigest(), "summary": summary, "lifecycles": lifecycles, "audit_sha256": {str((A / (slot + ".json")).relative_to(C)): hashlib.sha256((A / (slot + ".json")).read_bytes()).hexdigest() for slot in all_audits}, "limits": ["Phase2 unassessed; no completed lifecycle/core conclusion.", "Broad note applicability includes Sonnet rich version-only note; strict complete required-agreement sensitivity excludes it and other partial records.", "Current artifact scores do not certify latent winner/presentation logic, saved prose or provenance.", "No new inference, repairs or frozen input edits during audit."]}
output = A / ("phase1-lifecycles-" + str(time.time_ns()) + ".json")
with output.open("x") as handle:
    json.dump(value, handle, indent=2)
    handle.write("\n")
print(output)
print(json.dumps(summary))
