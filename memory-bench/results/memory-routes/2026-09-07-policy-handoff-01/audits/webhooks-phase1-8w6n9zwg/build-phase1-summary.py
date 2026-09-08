"""Aggregate manually reviewed judgments; never classify semantic fidelity from counters."""
from pathlib import Path
import hashlib
import json

A = Path(__file__).resolve().parent
R = A.parents[1]
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
rows = read(A / "scope.json")["scheduled_rows"]
assert len(rows) == 40
results = {r["slot"]: read(R / "cases" / r["lifecycle"] / f"stage-{r['stage']}" / "result.json") for r in rows}
assert all((A / (slot + ".json")).is_file() for slot in results)
faithful = {"codex-astra/occasions", "claude-fable/generic", "claude-fable/occasions", "claude-opus/occasions"}
censored = {"codex-luna/generic", "codex-luna/occasions", "codex-terra/generic", "codex-terra/occasions"}
partial = "zcode-glm/generic"
late_good = {"codex-astra/generic", "claude-sonnet/generic"}
late_false = "claude-sonnet/occasions"
timing = {
 "codex-astra/occasions": {"route": "search", "reference_tool": 4, "full_body_tool": 5, "edit_tool": 6},
 "claude-fable/generic": {"route": "direct", "reference_tool": 2, "full_body_tool": 3, "edit_tool": 4},
 "claude-fable/occasions": {"route": "direct", "reference_tool": 2, "full_body_tool": 3, "edit_tool": 5},
 "claude-opus/occasions": {"route": "search", "reference_tool": 9, "full_body_tool": 10, "edit_tool": 14},
 "zcode-glm/generic": {"route": "search", "route_subtype": "list_then_full", "reference_tool": 21, "full_body_tool": 24, "edit_tool": 16},
}
validation_concerns = {
 "opencode-qwen/generic": ["Stages 1 and 2 source/prose claim UTC representative selection, but unused helper sorts raw timestamp strings. Stage 1 broad test claim includes commands that failed or ran zero tests; actual public counts pass."],
 "opencode-qwen/occasions": ["Stage 1 source retains unused raw-timestamp selection despite UTC requirement. Stage 2 is a literal tool-call-shaped text response with zero actual tools; no evidence of provider unavailability."],
 "codex-terra/occasions": ["Stage 1 targeted-selector-coverage claim precedes a blocked heredoc; those assertions never ran. Provider quota subsequently interrupts completion; classify these separately."],
 "claude-haiku/generic": ["Stage 1 claims tie-break verification from scalar count cases, which cannot identify the chosen receipt."],
 "claude-sonnet/occasions": ["Stage 1 final tie-check claim is stronger than the actual unequal-instant manual case. Stage 2 invented scope and its manual expected total contradict the available provider contract."],
}
life = []
for r in rows:
 if r["stage"] != 1:
  continue
 key = r["profile_id"] + "/" + r["arm"]
 d1 = results[r["lifecycle"] + "-1"]
 d2 = results[r["lifecycle"] + "-2"]
 initial = True if key in faithful else None if key in censored else False
 if key in faithful:
  capture_status = "faithful_complete"
 elif key in censored:
  capture_status = "provider_censored_no_record"
 elif key == partial:
  capture_status = "dispatch_only_record_missing_provider_agreement"
 else:
  capture_status = "omitted_after_completed_work"
 broad = key in faithful or key == partial
 t = timing.get(key, {"route": "none"})
 future = {"status": "unverified", "reason": "Phase 1 covers stages 1 and 2 only; assess after publication."}
 reasons = []
 if initial is False:
  reasons.append("Initial required agreement was not faithfully captured by the end of stage 1; later capture cannot repair this component.")
 for d in [d1, d2]:
  if not d["artifact_passed"]:
   reasons.append(f"Stage {d['stage']} frozen artifact failed ({d['artifact_correct']}/{d['artifact_total']}).")
 if key == late_false:
  reasons.append("Stage 2 created an unsupported standing protocol-1 policy contradicting the provider.")
 if key == partial:
  reasons.append("Saved future-error-shape stability advice is an agent choice, not an approved valid-input requirement; required provider facts are absent.")
 concerns = validation_concerns.get(key, [])
 life.append({
  "lifecycle": r["lifecycle"], "profile_id": r["profile_id"], "arm": r["arm"], "private_world": r["corpus_family"], "catalog_mode": r["catalog_mode"],
  "initial_capture_faithful": initial, "initial_capture_status": capture_status,
  "phase1_provider_availability": [{"stage": d["stage"], "failed": not d["host_success"], "errors": d["errors"], "frozen_infrastructure_fault": d.get("infrastructure_fault"), "interpretation": "Provider quota before all task tools or after partial work; not voluntary capture failure."} for d in [d1,d2] if not d["host_success"]],
  "current_and_historical_faithful": {str(s): dict(future) for s in [3,5,6]},
  "retrieval_legs": {
   "2": {"applicable_prior_record_at_entry": broad, "applicability_scope": "complete_provider_agreement" if key in faithful else "protocol_dispatch_only; provider identity/order absent" if key == partial else "none", "complete_required_provider_agreement_at_entry": key in faithful,
         "full_prior_body_read": broad, "full_required_provider_agreement_read": key in faithful, **t,
         "pre_edit_or_informed_use": key in faithful, "read_timing": "pre_edit" if key in faithful else "after_edit_and_tests" if key == partial else "none",
         "artifact_correct": d2["artifact_passed"], "successful_prior_record_use": key in faithful,
         "evidence": str((A/(d2['slot']+'.json')).relative_to(R))},
   "4": dict(future), "5": dict(future)},
  "stage2_capture": "faithful_late_first_capture" if key in late_good else "false_late_first_capture" if key == late_false else "same_key_source_pointer_update_preserves_facts" if key == "claude-fable/generic" else "no_write",
  "stage2_required_agreement_faithful": key in faithful or key in late_good,
  "unsupported_standing_or_historical_mutation": key in {partial,late_false},
  "unsupported_standing_detail": "Creates false account-local protocol-1 policy and future-consumer instruction." if key == late_false else "Agent-authored future-error-shape stability advice outside approved contract; accurate implementation context retained separately." if key == partial else None,
  "older_issue_or_provider_document_mutation": False,
  "stage6_control": {"duplicate_curation": None, "evidenced_new_finding": None, **future},
  "verification_and_provenance_concerns": concerns,
  "qualification_of_other_notes": "Provider allocation rationale omitted from compact note, while all frozen required facts survive." if key == "claude-fable/generic" else "Stage 1 source/test references accurate, but scalar verification alone cannot certify selector details; see detailed audit." if key == "claude-fable/occasions" else None,
  "artifact_results": [{"stage": d["stage"], "passed": d["artifact_passed"], "correct": d["artifact_correct"], "total": d["artifact_total"]} for d in [d1,d2]],
  "strict_six_stage_intersection": {"status": "false" if reasons else "unverified", "reasons": reasons or ["Initial capture and stage-2 use/artifact pass; stages 3-6 remain unaudited/unrun at this checkpoint."]},
  "detailed_evidence": [str((A/(d['slot']+'.json')).relative_to(R)) for d in [d1,d2]]
 })
normal = {
 "schema": "webhooks-manual-lifecycle-phase1.v1", "phase": "phase1", "method": "Manual semantic judgments normalized from 40 detailed audits, exact memory bodies, actual model-facing tool delivery, source, and issue-history snapshots. No semantic inference from action counters.",
 "tri_state": "true/false are observed components; null or status unverified means censored/not yet assessed. Strict false may be established by an artifact failure even when memory adherence is provider-censored.",
 "denominator_note": "Broad applicable prior record includes GLM's related dispatch-only record; complete governing provider agreement is a separate narrower denominator. Full body means all of the actual saved record, not that the saved record contains all required facts.",
 "lifecycles": life,
 "audit_hashes": {str((A/(d['slot']+'.json')).relative_to(R)): sha(A/(d['slot']+'.json')) for d in results.values()},
 "codex_visibility_correction": {str((A/f'codex-delivery-supplement-0{s}.json').relative_to(R)): sha(A/f'codex-delivery-supplement-0{s}.json') for s in [1,2,3]},
}
assert len(life)==20
assert sum(x['initial_capture_faithful'] is True for x in life)==4
assert sum(x['retrieval_legs']['2']['successful_prior_record_use'] for x in life)==4
assert sum(x['strict_six_stage_intersection']['status']=='unverified' for x in life)==4
with (A/'normalized-lifecycles-phase1.json').open('x') as f:
 json.dump(normal,f,indent=2,ensure_ascii=False)
summary = {
 "verdict": "PASS_FOR_UNCHANGED_CONTINUATION_WITH_REPORTED_LIMITS", "scope": "Semantic audit of webhooks phase1; no new task delivery, isolation, oracle, or source integrity blocker identified. Provider availability faults are measured separately.",
 "planned_and_assessed_slots": 40, "detailed_manual_audits": 40,
 "frozen_artifacts": {"passed": sum(d['artifact_passed'] for d in results.values()), "correct_cases": sum(d['artifact_correct'] for d in results.values()), "total_cases": sum(d['artifact_total'] for d in results.values())},
 "by_arm": {arm: {"slots":20,"artifact_passed":sum(d['artifact_passed'] for d in results.values() if d['arm']==arm),"case_correct":sum(d['artifact_correct'] for d in results.values() if d['arm']==arm),"case_total":700,"initial_faithful":sum(x['initial_capture_faithful'] is True for x in life if x['arm']==arm),"initial_planned":10,"initial_behaviorally_complete":8,"pre_edit_successful_use":sum(x['retrieval_legs']['2']['successful_prior_record_use'] for x in life if x['arm']==arm),"retrieval_planned":10} for arm in ['generic','occasions']},
 "provider_availability": {"quota_failed_slots":9,"before_any_tool":7,"after_partial_work":2,"stage1_completion_censored":4,"stage2_completion_censored":5,"narrow_frozen_infrastructure_fault": "Preserved; false does not erase explicit provider quota errors.","no_retries":True},
 "initial_capture": {"faithful":4,"all_planned":20,"behaviorally_completed":16,"dispatch_only_partial":1,"completed_omissions":11,"provider_censored_no_record":4},
 "eligible_stage2": {"all_planned":20,"complete_provider_agreement_at_entry":4,"related_dispatch_only_at_entry":1,"broad_applicable_at_entry":5,"full_preexisting_body_delivered":5,"full_required_provider_body_delivered":4,"pre_edit_successful_use":4,"direct_successful":2,"search_successful":2,"list_then_full_after_edit_and_tests_related_only":1,"no_successful_prior_use":16,"artifact_pass_without_prior_use":10,"artifact_pass_without_prior_use_in_completed_host_turn":9},
 "capture_verification": {"full_same_session_saved_body_reads":9,"initial_faithful":4,"initial_dispatch_only":1,"stage2_first_faithful":2,"stage2_first_false":1,"stage2_same_key_pointer_update":1,"distinction":"Complete readback confirms stored bytes, not truth or prior reuse."},
 "stage2_retained": {"complete_faithful_agreements":6,"partial_dispatch_only":1,"false_agreement":1,"no_record":12},
 "strict_six_stage_intersection_at_checkpoint": {"false":16,"unverified":4,"true":0},
 "actual_blockers": [],
 "normalized_lifecycles": "normalized-lifecycles-phase1.json", "normalized_sha256":sha(A/'normalized-lifecycles-phase1.json'),
 "important_limits": ["Single synthetic lifecycle per profile/arm; world and catalog are paired within profile/family but confounded across profiles. No model-strength causal ranking.","No retry or recoding of the provider quota burst. Capture adherence unknown when provider terminated the opportunity.","Vendor docs, issues, source and history remained available. Pre-edit memory reads plus correct behavior do not prove exclusive causal reliance on memory.","Codex normalized outputs omit some delivered prefixes. Retained native rollouts resolve actual visibility; normalized counters are lower bounds. Supplement03 corrects incomplete earlier supplement parsing without rewriting earlier evidence.","Stage1/2 scalar outputs cannot certify representative selection. Latent source/helper defects and unsupported test claims remain separate from frozen artifact grades.","No stage3/5/6 historical fidelity or stage6 duplicate-control outcome yet; no favorable inference from phase1."],
}
assert summary['frozen_artifacts']=={'passed':31,'correct_cases':1124,'total_cases':1400}
with (A/'phase1-aggregate-final.json').open('x') as f:
 json.dump(summary,f,indent=2,ensure_ascii=False)
print(json.dumps({"summary":str(A/'phase1-aggregate-final.json'),"sha256":sha(A/'phase1-aggregate-final.json'),"normalized":str(A/'normalized-lifecycles-phase1.json'),"normalized_sha256":sha(A/'normalized-lifecycles-phase1.json')}))
