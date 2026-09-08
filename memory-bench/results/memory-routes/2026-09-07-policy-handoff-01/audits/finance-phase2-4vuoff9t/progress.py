"""Combine explicit semantic components; missing later assessments stay unknown."""
from pathlib import Path
import json,time,hashlib,copy
A=Path(__file__).resolve().parent
P1=A.parent/'finance-phase1-lxa0y1o5/phase1-lifecycles-1788808529862145000.json'
lifecycles=copy.deepcopy(json.loads(P1.read_text())['lifecycles'])
reviews={p.name.removesuffix('.audit.json'):json.loads(p.read_text()) for p in A.glob('*.audit.json')}
extracts={p.name.removesuffix('.extraction.json'):json.loads(p.read_text()) for p in A.glob('*.extraction.json')}
for life in lifecycles:
 life['phase2_primary_audits']=[];life['phase2_provenance_verification']={};bad_mutations=[];mutation_unknown=False
 for stage in range(3,7):
  slot=life['lifecycle']+'-'+str(stage);r=reviews.get(slot)
  if r is None:mutation_unknown=True;continue
  x=extracts[slot];life['phase2_primary_audits'].append(slot+'.audit.json');life['artifacts'][str(stage)]=x['artifact_passed']
  policy=r.get('policy',{});mutated=policy.get('unsupported_standing_or_historical_mutation')
  if mutated is True:bad_mutations.append(slot)
  if mutated is None:mutation_unknown=True
  if stage in (3,5,6):life['current_and_historical_faithful']['stage'+str(stage)]=policy.get('current_and_historical_faithful')
  if stage in (4,5):
   retrieval=r.get('retrieval',{})
   life['retrieval_legs'][str(stage)]={k:retrieval.get(k) for k in ('applicable_prior_record_at_entry','full_prior_body_read','route','pre_edit_or_informed_use')}
   life['retrieval_legs'][str(stage)]['artifact_correct']=x['artifact_passed'];life['retrieval_legs'][str(stage)]['route_detail']=retrieval
  if stage==6:
   curation=r.get('curation',{});life['stage6']={k:curation.get(k) for k in ('duplicate_curation','evidenced_new_finding','catalog_orientation','full_body_reads')}
  life['phase2_provenance_verification'][str(stage)]={k:r.get(k) for k in ('provenance_and_verification','unsupported_commentary','uncertainties')}
 life['unsupported_standing_or_historical_mutation']['complete_lifecycle']=True if bad_mutations else None if mutation_unknown else False
 reasons=[];unknown=[]
 if life['initial_capture_faithful'] is not True:reasons.append('Initial faithful capture absent; later capture cannot repair it.')
 for stage,value in life['artifacts'].items():
  if value is False:reasons.append('Artifact stage'+stage+' incorrect.')
  elif value is None:unknown.append('Artifact stage'+stage+' unassessed.')
 for stage,value in life['current_and_historical_faithful'].items():
  if value is False:reasons.append(stage+' current/history fidelity fails.')
  elif value is None:unknown.append(stage+' current/history unassessed.')
 for stage,leg in life['retrieval_legs'].items():
  for field in ('applicable_prior_record_at_entry','full_prior_body_read','pre_edit_or_informed_use','artifact_correct'):
   if leg[field] is False:reasons.append('Retrieval stage'+stage+': '+field+' false.')
   elif leg[field] is None:unknown.append('Retrieval stage'+stage+': '+field+' unassessed.')
 if bad_mutations:reasons.append('Unsupported standing/history mutation: '+','.join(bad_mutations))
 elif mutation_unknown:unknown.append('Complete mutation assessment unavailable.')
 if life['stage6']['duplicate_curation'] is True:reasons.append('Stage6 duplicate curation.')
 elif life['stage6']['duplicate_curation'] is None:unknown.append('Stage6 curation unassessed.')
 life['strict_six_stage_intersection']=False if reasons else 'unverified' if unknown else True
 life['strict_intersection_reasons']=reasons;life['remaining_unknown_components']=unknown
by_stage={}
for stage in range(3,7):
 rr=[r for r in reviews.values() if r['stage']==stage]
 by_stage[str(stage)]={'planned':20,'audited':len(rr),'artifact_passes':sum(extracts[r['slot']]['artifact_passed'] for r in rr),'correct_cases':sum(extracts[r['slot']]['artifact_correct'] for r in rr),'total_cases_assessed':sum(extracts[r['slot']]['artifact_total'] for r in rr),'current_and_historical_faithful':sum(r.get('policy',{}).get('current_and_historical_faithful') is True for r in rr),'applicable_prior_records':sum(r.get('retrieval',{}).get('applicable_prior_record_at_entry') is True for r in rr),'full_prior_body_reads':sum(r.get('retrieval',{}).get('full_prior_body_read') is True for r in rr),'pre_edit_or_informed_use':sum(r.get('retrieval',{}).get('pre_edit_or_informed_use') is True for r in rr)}
report={'schema':'finance-phase2-progress-and-lifecycles.v1','planned_phase2_sessions':80,'published':len(extracts),'audited':len(reviews),'by_stage':by_stage,'all_saved_oracle_verdicts_agree':all(x['independent_artifact_check']['all_expected_agree'] and x['independent_artifact_check']['all_verdicts_agree'] for x in extracts.values()),'phase1_source':str(P1),'phase1_source_sha256':hashlib.sha256(P1.read_bytes()).hexdigest(),'lifecycle_summaries':lifecycles,'strict_intersections':{'true':sum(l['strict_six_stage_intersection'] is True for l in lifecycles),'false':sum(l['strict_six_stage_intersection'] is False for l in lifecycles),'unverified':sum(l['strict_six_stage_intersection']=='unverified' for l in lifecycles)},'claims':'Component totals summarize explicit semantic judgments, not command counts. Stage3 reads are preservation/revision events, not eligible retrieval legs. Any conditional subset must retain planned denominators.','audit_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(A.glob('*.json'))}}
dest=A/f'progress-{time.time_ns()}.json'
with dest.open('x') as f:json.dump(report,f,indent=2)
print(dest)
print(json.dumps({k:report[k] for k in ('published','audited','by_stage','strict_intersections')},indent=2))
