"""Append aggregation of already-manually-adjudicated Courier evidence, without inference."""
import hashlib
import json
import time
from pathlib import Path
A = Path(__file__).resolve().parent
C = A.parents[1]
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
manifest = read(C / "manifest.json")
rows = [r for r in manifest["slots"] if r["family"] == "webhooks"]
normalization = A / "provider-no-generation-normalization-1788828367643612000.json"
overrides = {r["slot"]: r for r in read(normalization)["stage_overrides"]}
audits = {}
for row in rows:
    p = A / (row["slot"] + ".json")
    if not p.exists(): continue
    a = read(p)
    for k in ("record_count_before", "record_count_after"):
        if k not in a: a[k] = a["capture"][k]
    o = overrides.get(row["slot"])
    if o:
        assert sha(p) == o["original_stage_audit_sha256"]
        a["status"] = o["status"]
        a["agent_interaction_opportunity"] = False
        a["operational_failure"] = o["operational_failure"]
        if "eligible_use_overrides" in o: a["eligible_use"].update(o["eligible_use_overrides"])
        a.update(o.get("control_overrides", {}))
    audits[row["slot"]] = a

claim_normalization = A / 'claim-location-normalization-1788829081757169000.json'
for o in read(claim_normalization)["stage_overrides"]:
    p = A / (o["slot"] + ".json")
    assert sha(p) == o["original_sha256"]
    if o["slot"] in audits:
        audits[o["slot"]]["saved_claim_findings"] = o["saved_claim_findings"]
        audits[o["slot"]]["transient_claim_findings"] = o["transient_claim_findings"]

def missing_status(life, stage):
    if life == "codex-luna-webhooks-thin-prime-isolated": return "censored_original_prelaunch_claim" if stage == 1 else "censored_original_predecessor"
    if life == "codex-astra-webhooks-startup-briefing-isolated" and stage >= 5:
        return "censored_authentication_setup_before_host_launch" if stage == 5 else "censored_authentication_failed_predecessor"
    return "pending_or_not_yet_audited"

lifecycles = []
for life in sorted({r["lifecycle"] for r in rows}):
    planned = [r for r in rows if r["lifecycle"] == life]
    base = planned[0]
    observed = {r["stage"]: audits[r["slot"]] for r in planned if r["slot"] in audits}
    complete = len(observed) == 6
    initial = observed.get(1)
    uses = []
    for stage in (2, 4, 5):
        a = observed.get(stage)
        if a is None:
            uses.append({"stage": stage, "status": missing_status(life, stage), "route": None, "primary_preparatory": None, "secondary_informed": None, "applicable_entry": None, "entry_faithful": None, "required_agreement_entry_sensitivity": None})
            continue
        u = dict(a["eligible_use"])
        u.setdefault("status", a["status"])
        u["evidence_path"] = str((A / (a["slot"] + ".json")).relative_to(C))
        u.setdefault("entry_faithful", bool(u.get("entry_complete_for_required_facts")))
        u.setdefault("entry_scope_status", "complete_required_agreement" if u["entry_faithful"] else "no_prior_entry")
        u.setdefault("required_agreement_entry_sensitivity", bool(u["primary_preparatory"] and u["entry_faithful"]))
        uses.append(u)
    faithful = {str(s): observed[s]["capture"]["faithful_complete_agreement"] if s in observed else None for s in (3,5,6)}
    mutation_observed = any(a["unsupported_standing_or_history_mutation"] for a in observed.values())
    mutation = mutation_observed if complete or mutation_observed else None
    control = observed.get(6)
    duplicate = control.get("duplicate_control") if control else None
    correct = all(a["artifact"]["passed"] for a in observed.values()) if complete else None
    common = correct is True and initial["capture"]["faithful_complete_agreement"] is True and all(v is True for v in faithful.values()) and mutation is False and duplicate is False
    life_row = {
        **{k: base[k] for k in ("lifecycle", "profile_id", "family", "arm", "catalog_mode", "corpus_family")},
        "status": "complete_assessed" if complete else "incomplete_with_censoring" if any(missing_status(life,s).startswith("censored") for s in range(1,7) if s not in observed) else "partial",
        "planned_sessions":6, "assessed_sessions": len(observed), "assessed_audited_stages": sorted(observed),
        "initial_faithful": initial["capture"]["faithful_complete_agreement"] if initial else None,
        "initial_record_present": bool(initial["record_count_after"]) if initial else None,
        "initial_capture_count": initial["record_count_after"] if initial else None,
        "initial_capture_status": initial["capture"]["status"] if initial else missing_status(life,1),
        "initial_capture_trigger_limit": "Provider agreement already existed in a durable project document; missing keyed initial handoff is not automatically disobedience of newly-approved-knowledge wording.",
        "records_stage_3_5_6_faithful": faithful,
        "records_stage_3_5_6_all_faithful": all(v is True for v in faithful.values()) if all(v is not None for v in faithful.values()) else None,
        "records_stage_3_5_6_details": [{"stage":s, "faithful":faithful[str(s)], "status":observed[s]["status"] if s in observed else missing_status(life,s), "capture":observed[s]["capture"] if s in observed else None} for s in (3,5,6)],
        "artifact_all_correct":correct,
        "artifact_observed_all_correct":all(a["artifact"]["passed"] for a in observed.values()) if observed else None,
        "unsupported_standing_or_history_mutation":mutation,
        "unsupported_standing_or_history_mutation_observed":mutation_observed,
        "unsupported_saved_prose_mutation_observed":any(a.get("unsupported_saved_prose_mutation",False) for a in observed.values()),
        "duplicate_control":duplicate,
        "duplicate_control_opportunity":bool(control.get("duplicate_control_opportunity",control.get("record_count_before",0)>0)) if control else None,
        "agent_control_opportunity":control.get("agent_control_opportunity",True) if control else None,
        "duplicate_control_status":control.get("control_status",control["status"]) if control else missing_status(life,6),
        "eligible_uses":uses,
        "strict_core_primary":bool(common and all(u["primary_preparatory"] is True for u in uses)) if complete else None,
        "strict_core_secondary":bool(common and all(u["secondary_informed"] is True for u in uses)) if complete else None,
        "saved_claim_findings":[{"stage":s, **finding} for s,a in observed.items() for finding in a["saved_claim_findings"]],
        "stages":[{"stage":s, "status":observed[s]["status"], "audit_path":str((A/(observed[s]["slot"]+".json")).relative_to(C)), "artifact":observed[s]["artifact"], "capture":observed[s]["capture"], "exposure":observed[s]["exposure"]} if s in observed else {"stage":s,"status":missing_status(life,s),"audit_path":None} for s in range(1,7)],
    }
    lifecycles.append(life_row)
summary = {"planned_lifecycles":18,"planned_sessions":108,"planned_eligible_uses":54,"assessed_audited":len(audits),"artifact_correct":sum(a["artifact"]["passed"] for a in audits.values()),"complete_lifecycles":sum(len(x["assessed_audited_stages"])==6 for x in lifecycles),"provider_blocked_no_generation":sum(a["status"]=="provider_blocked_no_generation" for a in audits.values()),"primary_preparatory":sum(u["primary_preparatory"] is True for x in lifecycles for u in x["eligible_uses"]),"primary_faithful_entry":sum(u["primary_preparatory"] is True and u["entry_faithful"] is True for x in lifecycles for u in x["eligible_uses"]),"strict_core_primary":sum(x["strict_core_primary"] is True for x in lifecycles)}
value={"schema":"prime-courier-lifecycle-audit.v2","created_ns":time.time_ns(),"status":"incremental","manifest_sha256":sha(C/"manifest.json"),"summary":summary,"lifecycles":lifecycles,"audit_sha256":{str((A/(slot+".json")).relative_to(C)):sha(A/(slot+".json")) for slot in audits},"normalization_sha256":{str(normalization.relative_to(C)):sha(normalization),str(claim_normalization.relative_to(C)):sha(claim_normalization)},"limits":["Only existing manually adjudicated stages aggregated; pending and censored stages carry no observed cognitive verdict.","Artifact correctness does not certify all retained prose or provenance.","No inference, reruns, repairs, or frozen input edits during audit.","Broad applicability includes useful partial records; required-agreement sensitivity requires faithful full facts."]}
out=A/("lifecycles-progress-"+str(time.time_ns())+".json")
with out.open("x") as handle: json.dump(value,handle,indent=2);handle.write("\n")
print(out)
print(json.dumps(summary))
