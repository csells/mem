"""Append-only semantic component summary for four fresh normal finance lifecycles."""
from pathlib import Path
import json,time,collections,hashlib
A=Path(__file__).resolve().parent
scope=json.loads((A/'scope.json').read_text());reviews={p.name.removesuffix('.audit.json'):json.loads(p.read_text()) for p in A.glob('*.audit.json')};extracts={p.name.removesuffix('.extraction.json'):json.loads(p.read_text()) for p in A.glob('*.extraction.json')}
lives=[]
for lifecycle in sorted(set(r['lifecycle'] for r in scope['rows'])):
 rr={str(s):reviews.get(lifecycle+'-'+str(s)) for s in range(1,7)};row=next(r for r in scope['rows'] if r['lifecycle']==lifecycle);initial=rr['1'];capture=initial.get('capture',{}) if initial else {}
 l={'lifecycle':lifecycle,'profile_id':row['profile_id'],'arm':row['arm'],'catalog_mode':row['catalog_mode'],'initial_capture_faithful':capture.get('initial_capture_faithful'),'initial_approval_actually_viewed':capture.get('approval_actually_viewed'),'current_and_historical_faithful':{'stage'+s:rr[s]['policy'].get('current_and_historical_faithful') if rr[s] else None for s in ('3','5','6')},'retrieval_legs':{},'artifacts':{s:extracts[r['slot']]['artifact_passed'] if r else None for s,r in rr.items()},'native_memory':{s:r.get('native_memory') if r else None for s,r in rr.items()},'primary_audits':[r['slot']+'.audit.json' for r in rr.values() if r]}
 for s in ('2','4','5'):
  r=rr[s];leg=r.get('retrieval',{}) if r else {};l['retrieval_legs'][s]={k:leg.get(k) for k in ('applicable_prior_record_at_entry','full_prior_body_read','route','pre_edit_or_informed_use','timing_class')};l['retrieval_legs'][s]['artifact_correct']=l['artifacts'][s];l['retrieval_legs'][s]['route_detail']=leg
 l['stage6']=rr['6'].get('curation',{}) if rr['6'] else {};mut=[r['policy'].get('unsupported_standing_or_historical_mutation') for r in rr.values() if r];l['unsupported_standing_or_historical_mutation']=True if any(v is True for v in mut) else False if len(mut)==6 and all(v is False for v in mut) else None
 components={'initial_capture':l['initial_capture_faithful'],**{'artifact'+s:v for s,v in l['artifacts'].items()},**l['current_and_historical_faithful']}
 for s,leg in l['retrieval_legs'].items():
  for k in ('applicable_prior_record_at_entry','full_prior_body_read','pre_edit_or_informed_use'):components['retrieval'+s+'.'+k]=leg[k]
 components['no_unsupported_mutation']=None if l['unsupported_standing_or_historical_mutation'] is None else not l['unsupported_standing_or_historical_mutation'];duplicate=l['stage6'].get('duplicate_curation');components['no_duplicate_control']=None if duplicate is None else not duplicate
 failed=[k for k,v in components.items() if v is False];unknown=[k for k,v in components.items() if v is None];l['strict_six_stage_intersection']=False if failed else 'unverified' if unknown else True;l['strict_intersection_reasons']=failed;l['remaining_unknown_components']=unknown;lives.append(l)
report={'schema':'finance-normal-progress-and-lifecycles.v1','planned':24,'published':len(extracts),'audited':len(reviews),'artifact_passes':sum(extracts[r['slot']]['artifact_passed'] for r in reviews.values()),'correct_cases':sum(extracts[r['slot']]['artifact_correct'] for r in reviews.values()),'assessed_cases':sum(extracts[r['slot']]['artifact_total'] for r in reviews.values()),'lifecycle_summaries':lives,'strict_intersections':dict(collections.Counter('true' if l['strict_six_stage_intersection'] is True else 'false' if l['strict_six_stage_intersection'] is False else 'unverified' for l in lives)),'audit_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(A.glob('*.audit.json'))},'limits':'Four fresh matched anchor lifecycles, not pooled with main. Native files/settings are not native use; actual field adjudication required. Prior body read timing separate from save readback.'}
p=A/f'progress-{time.time_ns()}.json'
with p.open('x') as f:json.dump(report,f,indent=2)
print(p);print(json.dumps({k:report[k] for k in ('published','audited','artifact_passes','correct_cases','assessed_cases','strict_intersections')}))
