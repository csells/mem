"""Aggregate existing auditor judgments without new semantic inference."""
from pathlib import Path
import json,time,hashlib
A=Path(__file__).resolve().parent;R=A.parents[1]
def j(p):return json.loads(p.read_text())
m=j(R/'manifest.json');life={r['lifecycle']:r for r in m['slots'] if r['family']=='finance'}
out=[]
for name,row in sorted(life.items()):
 records={int(p.name.rsplit('-',1)[-1].split('.')[0]):j(p) for p in A.glob(name+'-*.audit.json')}
 stages={str(s):r for s,r in records.items()}
 uses=[records[s]['eligible_use'] if s in records and 'eligible_use' in records[s] else {'stage':s,'status':'unassessed','route':None,'primary_preparatory':None,'secondary_informed':None,'applicable_entry':None} for s in (2,4,5)]
 for use in uses:
  stage=use['stage']
  if use.get('status')=='unassessed':
   use.update(entry_faithful=None,entry_scope_status='unassessed',required_agreement_entry_sensitivity=None)
  else:
   faithful=use.get('entry_faithful')
   if faithful is None and stage==2:faithful=records.get(1,{}).get('capture_faithful')
   use.update(entry_faithful=faithful,entry_scope_status=use.get('entry_scope_status',('full_applicable_agreement' if faithful is True and use['applicable_entry'] else 'absent' if not use['applicable_entry'] else 'partial_applicable_agreement')),required_agreement_entry_sensitivity=use.get('required_agreement_entry_sensitivity',faithful is True and use['applicable_entry']))
 for stage,rec in records.items():
  proof=A/f'{name}-{stage}.startup-host-user.json'
  if proof.exists():
   doc=j(proof)
   if 'exact_launch_match' in doc:seen=doc['exact_launch_match']
   else:seen=any(t.get('launch_contained') for t in doc.get('user_messages',[]))
   rec['guidance_exposure']['startup_observed_in_host_user_record']=seen
   rec['guidance_exposure']['host_user_delivery_supplement']=str(proof)
 ret={str(s):records[s].get('capture_faithful') if s in records else None for s in (3,5,6)}
 allassessed=set(records)==set(range(1,7))
 x={k:row[k] for k in ('lifecycle','profile_id','family','arm','catalog_mode','corpus_family')}
 x.update(assessed_audited_stages=sorted(records),initial_faithful=records.get(1,{}).get('capture_faithful'),initial_faithful_status=records.get(1,{}).get('capture_status','unassessed'),records_stage_3_5_6_faithful=ret,records_stage_3_5_6_details={str(s):records[s].get('record_details') for s in (3,5,6) if s in records},artifact_all_correct=all(r['artifact_passed'] for r in records.values()) if allassessed else None,unsupported_standing_or_history_mutation=any(r.get('unsupported_standing_or_history_mutation') is True for r in records.values()) if allassessed else None,duplicate_control=records.get(6,{}).get('duplicate_curation'),duplicate_control_opportunity=records.get(6,{}).get('duplicate_control_opportunity'),eligible_uses=uses,saved_claim_findings=[{'stage':s,'finding':f} for s,r in records.items() for f in r.get('saved_claim_findings',[])],recovered=any(r.get('censoring') for r in records.values()),stage_audits=stages)
 common=x['initial_faithful'] is True and all(v is True for v in ret.values()) and x['artifact_all_correct'] is True and x['unsupported_standing_or_history_mutation'] is False and x['duplicate_control'] is False
 x['strict_core_primary']=bool(common and all(u['primary_preparatory'] is True for u in uses)) if allassessed else None
 x['strict_core_secondary']=bool(common and all(u['secondary_informed'] is True for u in uses)) if allassessed else None
 x['unsupported_saved_prose_mutation_observed']=any(r.get('unsupported_saved_prose_mutation') is True for r in records.values())
 x['all_saved_prose_faithful_sensitivity']=False if x['saved_claim_findings'] or x['unsupported_saved_prose_mutation_observed'] else True if allassessed else None
 x['strict_core_primary_no_flagged_claims_sensitivity']=bool(x['strict_core_primary'] and x['all_saved_prose_faithful_sensitivity']) if allassessed else None
 x['agreement_vs_prose_definition']='Inherited agreement-core criterion excludes verification-only prose changes; all saved-claim flags and stricter sensitivity remain separate. See courier-begfwz8d/core-prose-interpretation-review-1788826926849110000.json.'
 if name=='claude-sonnet-finance-rich-prime-isolated':
  x['initial_faithful_status']='censored_prelaunch_claim_no_model_session'
  x['censored_planned_stages']=[1,2,3,4,5,6]
  for use in uses:
   use['status']='censored_lifecycle';use['entry_scope_status']='censored_lifecycle'

 out.append(x)
stamp=time.time_ns();p=A/f'progress-{stamp}.json'
x={'schema':'memory-prime-finance-progress.v3','created_ns':stamp,'planned_lifecycles':18,'planned_sessions':108,'planned_phase1_sessions':36,'assessed_results':len(list((R/'cases').glob('*-finance-*/stage-*/result.json'))),'audited_sessions':sum(len(x['assessed_audited_stages']) for x in out),'lifecycles':out,'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in A.glob('*.audit.json')}}
with p.open('x') as f:json.dump(x,f,indent=2)
print(p);print('assessed',x['assessed_results'],'audited',x['audited_sessions'])
