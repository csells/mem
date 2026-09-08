"""Append-only final finance audit aggregate. Never executes candidate/model code."""
from pathlib import Path
import json,time,hashlib,collections,copy
A=Path(__file__).resolve().parent
C=A.parents[1]
P1=A.parent/'finance-phase1-lxa0y1o5'
reviews={p.name.removesuffix('.audit.json'):json.loads(p.read_text()) for p in A.glob('*.audit.json')}
assert len(reviews)==80, f"Only {len(reviews)}/80 audited"
for p in sorted(A.glob('*adjudication*.json')):
 o=json.loads(p.read_text())
 if o.get('schema')!='finance-semantic-adjudication.v1':continue
 for slot in o['slots']:
  for dotted,value in o['field_overrides'].items():
   target=reviews[slot];parts=dotted.split('.')
   for part in parts[:-1]:target=target.setdefault(part,{})
   target[parts[-1]]=value
extracts={p.name.removesuffix('.extraction.json'):json.loads(p.read_text()) for p in A.glob('*.extraction.json')}
latest=lambda pattern:max(A.glob(pattern),key=lambda p:int(p.stem.rsplit('-',1)[1]))
pp=latest('progress-*.json');bp=latest('breakdowns-*.json');tp=latest('eligible-use-timing-*.json');sp=latest('support-snapshot-check-*.json')
progress=json.loads(pp.read_text());breakdowns=json.loads(bp.read_text());timing=json.loads(tp.read_text());support=json.loads(sp.read_text())
assert progress['audited']==80 and progress['published']==80
states=lambda vals:dict(collections.Counter('faithful' if x is True else 'false' if x is False else 'unverified' for x in vals))
policy={}
for arm in ('generic','occasions'):
 policy[arm]={}
 for stage in (3,5,6):
  rr=[r for r in reviews.values() if r['arm']==arm and r['stage']==stage]
  policy[arm][str(stage)]={which:states([r['policy'].get(which,{}).get('faithful') for r in rr]) for which in ('current','historical')}
  policy[arm][str(stage)]['combined']=states([r['policy'].get('current_and_historical_faithful') for r in rr])
legs=[]
for life in progress['lifecycle_summaries']:
 for stage,leg in life['retrieval_legs'].items():legs.append({'lifecycle':life['lifecycle'],'arm':life['arm'],'stage':int(stage),**leg})
route_counts={}
for arm in ('generic','occasions'):
 ll=[l for l in legs if l['arm']==arm]
 route_counts[arm]={'planned':30,'applicable_prior_at_entry':sum(l['applicable_prior_record_at_entry'] is True for l in ll),'full_applicable_reads':sum(l['full_prior_body_read'] is True for l in ll),'successful_use_correct_artifact':sum(all(l[k] is True for k in ('applicable_prior_record_at_entry','full_prior_body_read','pre_edit_or_informed_use','artifact_correct')) for l in ll),'full_read_routes':dict(collections.Counter(l['route'] for l in ll if l['full_prior_body_read'] is True)),'read_omissions_despite_applicable_record':[l['lifecycle']+'-'+str(l['stage']) for l in ll if l['applicable_prior_record_at_entry'] is True and l['full_prior_body_read'] is not True]}
controls=[]
for r in sorted(reviews.values(),key=lambda r:r['slot']):
 if r['stage']!=6:continue
 x=extracts[r['slot']];controls.append({'slot':r['slot'],'arm':r['arm'],'catalog_mode':r['catalog_mode'],'before_keys':list(x['memory_before']),'artifact_correct':x['artifact_passed'],**r['curation']})
execution=[]
for r in sorted(reviews.values(),key=lambda r:r['slot']):
 if r['execution_outcome'].get('host_success') is not True:execution.append({'slot':r['slot'],'availability':r['availability'],'execution_outcome':r['execution_outcome'],'execution_integrity':r.get('execution_integrity',[]),'audit':r['slot']+'.audit.json'})
report={'schema':'finance-phase2-final.v1','status':'complete80/80','reviewer':'billing_tasks; finance corpus author unblinded, semantic reviewer agent, not independent human','constraints':'Offline read-only source/evidence review; no candidate reruns, models, memory CLI or frozen evidence edits. Saved outputs and actual support artifact files independently checked.','phase2_sessions':80,'phase2_artifact_passes':sum(x['artifact_passed'] for x in extracts.values()),'phase2_cases_correct':sum(x['artifact_correct'] for x in extracts.values()),'phase2_cases_total':sum(x['artifact_total'] for x in extracts.values()),'initial_faithful':sum(l['initial_capture_faithful'] is True for l in progress['lifecycle_summaries']),'initial_planned':20,'initial_actual_approval_views':sum(l['initial_approval_actually_viewed'] is True for l in progress['lifecycle_summaries']),'late_first_capture_stage2':[l['lifecycle'] for l in progress['lifecycle_summaries'] if l['late_first_capture_stage2']],'policy_states':policy,'routes':route_counts,'timing':{k:v for k,v in timing.items() if k!='rows'},'strict_intersections':progress['strict_intersections'],'strict_true_lifecycles':[l['lifecycle'] for l in progress['lifecycle_summaries'] if l['strict_six_stage_intersection'] is True],'control_rows':controls,'frozen_unsuccessful_hosts':execution,'all_oracle_verdicts_agree':progress['all_saved_oracle_verdicts_agree'],'reference_files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (pp,bp,tp,sp)},'phase1_source':progress['phase1_source'],'phase1_source_sha256':progress['phase1_source_sha256'],'qualification_files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(A.glob('*.json')) if any(s in p.name for s in ('adjudication','supplement','addendum','qualification'))},'limits':['Strict core fact/route/artifact intersection is not clean provenance or comprehensive validation. Exact claim qualifications remain in source audits and append-only supplements.','Successful read-and-correct-artifact evidence is observational. Complete policies in code and retained approval issues were legitimate alternatives; no memory necessity or exclusive causality is established.','World and route differ across profiles; model sweep is coverage/screen, not controlled causal strength ranking.','All planned denominators retained. Provider quota failures in phase1, bounded completion failures and observer limitations differ from meaningful capture/read omissions.','Zero duplicate writes does not mean zero memory-related work. Shared index orientation, procedure reads, invalid commands and full bodies are reported separately.']}
p=A/f'phase2-final-{time.time_ns()}.json'
with p.open('x') as f:json.dump(report,f,indent=2)
print(p)
print(json.dumps({k:report[k] for k in ('phase2_sessions','phase2_artifact_passes','phase2_cases_correct','phase2_cases_total','strict_intersections')},indent=2))
