"""Append-only finance terminal export from already audited judgments."""
import collections,hashlib,json,re,sys,time
from pathlib import Path
A=Path(__file__).resolve().parent
source=Path(sys.argv[1]);d=json.loads(source.read_text());controls=[]
for life in d['lifecycles']:
 for stage,row in life['stage_audits'].items():
  row.setdefault('model_generation_observed', True)
  row.setdefault('behavioral_status','observed_generation' if row['model_generation_observed'] else 'provider_blocked_no_generation')
  if stage!='6':continue
  ex_path=A/(life['lifecycle']+'-6.extraction.json');ex=json.loads(ex_path.read_text())
  calls=[]
  for i,c in enumerate(ex['calls']):
   command=c.get('arguments',{}).get('command','')
   if re.search(r'bd (?:memories|recall)\b',command):
    calls.append({'call':i,'command':command,'search_invocations':len(re.findall(r'bd memories\b',command)),'recall_invocations':len(re.findall(r'bd recall\b',command)), 'full_before_bodies_observed':[key for key,body in ex['memory_before'].items() if body and body in str(c.get('result',''))]})
  generated=row['model_generation_observed']
  control={'lifecycle':life['lifecycle'],'profile_id':life['profile_id'],'arm':life['arm'],'model_generation_observed':generated,'status':row['behavioral_status'],'existing_record_opportunity':bool(ex['memory_before']),'retained_record_count':len(ex['memory_before']),'support_artifact_correct':row.get('support_artifact_correct'),'accumulated_artifact_correct':row['artifact_passed'],'duplicate_capture':row.get('duplicate_curation'),'any_unnecessary_memory_query_or_read':bool(calls) if generated else None,'memory_search_invocations':sum(c['search_invocations'] for c in calls) if generated else None,'memory_recall_invocations':sum(c['recall_invocations'] for c in calls) if generated else None,'full_before_record_read_observed':any(c['full_before_bodies_observed'] for c in calls) if generated else None,'calls':calls,'evidence':str(ex_path)}
  controls.append(control);life['supplied_control_audit']=control
  if 'product_unchanged' in row and 'product_changed_in_control' not in row:row['product_changed_in_control']=not row['product_unchanged']
 dups=[v for v in life['stage_audits'].values() if v.get('provenance_caveats')]
 life['provenance_metadata_caveats']=[c for r in dups for c in r.get('provenance_caveats',[])]
 life['final_response_only_claim_findings']=[{'stage':int(s),'findings':r['final_claim_findings']} for s,r in life['stage_audits'].items() if r.get('final_claim_findings')]
allrows=[r for l in d['lifecycles'] for r in l['stage_audits'].values()];uses=[u for l in d['lifecycles'] for u in l['eligible_uses']];generated=[c for c in controls if c['model_generation_observed']]
summary={'planned_sessions':108,'assessed_sessions':len(allrows),'correct_accumulated_artifacts':sum(r['artifact_passed'] for r in allrows),'provider_blocked_no_generation':sum(r['model_generation_observed'] is False for r in allrows),'observed_generated_sessions':sum(r['model_generation_observed'] is True for r in allrows),'planned_lifecycles':18,'complete_assessed_lifecycles':sum(len(l['stage_audits'])==6 for l in d['lifecycles']),'strict_primary':sum(l['strict_core_primary'] is True for l in d['lifecycles']),'strict_secondary':sum(l['strict_core_secondary'] is True for l in d['lifecycles']),'strict_primary_no_flagged_saved_claims':sum(l['strict_core_primary_no_flagged_claims_sensitivity'] is True for l in d['lifecycles']),'initial_faithful':sum(l['initial_faithful'] is True for l in d['lifecycles']),'planned_eligible_uses':54,'primary_uses':sum(u['primary_preparatory'] is True for u in uses),'primary_uses_full_required_entry':sum(u['primary_preparatory'] is True and u['entry_faithful'] is True for u in uses),'primary_uses_partial_or_current_preservation':sum(u['primary_preparatory'] is True and u['entry_faithful'] is False for u in uses),'generated_controls':len(generated),'generated_controls_existing_record_opportunity':sum(c['existing_record_opportunity'] for c in generated),'generated_controls_correct_support':sum(c['support_artifact_correct'] is True for c in generated),'generated_controls_correct_accumulated':sum(c['accumulated_artifact_correct'] is True for c in generated),'generated_controls_duplicate_capture':sum(c['duplicate_capture'] is True for c in generated),'generated_controls_any_unnecessary_memory_query_or_read':sum(c['any_unnecessary_memory_query_or_read'] is True for c in generated),'generated_controls_full_before_record_read':sum(c['full_before_record_read_observed'] is True for c in generated),'generated_controls_memory_search_invocations':sum(c['memory_search_invocations'] for c in generated),'generated_controls_memory_recall_invocations':sum(c['memory_recall_invocations'] for c in generated)}
for stage in (3,5,6):summary['faithful_records_stage_'+str(stage)]=sum(l['records_stage_3_5_6_faithful'][str(stage)] is True for l in d['lifecycles'])
stamp=time.time_ns();d.update(schema='memory-prime-finance-terminal-export.v4',created_ns=stamp,derived_from={'path':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()},summary=summary,controls=controls,control_derivation_note='Model calls and linked outputs only. Fully supplied tasks define query/read as unnecessary work; duplicate capture is independent. Administrative snapshot reads excluded. No-generation controls retain null behavior, not negative observations. No flagged claim sensitivity does not certify all prose or ambiguous metadata.')
p=A/f'normalized-final-{stamp}.json'
with p.open('x') as f:json.dump(d,f,indent=2)
print(p);print(json.dumps(summary,indent=2))
