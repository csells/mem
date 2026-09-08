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
 ret={str(s):records[s].get('capture_faithful') if s in records else None for s in (3,5,6)}
 allassessed=set(records)==set(range(1,7))
 x={k:row[k] for k in ('lifecycle','profile_id','family','arm','catalog_mode','corpus_family')}
 x.update(assessed_audited_stages=sorted(records),initial_faithful=records.get(1,{}).get('capture_faithful'),initial_faithful_status=records.get(1,{}).get('capture_status','unassessed'),records_stage_3_5_6_faithful=ret,records_stage_3_5_6_details={str(s):records[s].get('record_details') for s in (3,5,6) if s in records},artifact_all_correct=all(r['artifact_passed'] for r in records.values()) if allassessed else None,unsupported_standing_or_history_mutation=any(r.get('unsupported_standing_or_history_mutation') is True for r in records.values()) if allassessed else None,duplicate_control=records.get(6,{}).get('duplicate_curation'),duplicate_control_opportunity=records.get(6,{}).get('duplicate_control_opportunity'),eligible_uses=uses,saved_claim_findings=[{'stage':s,'finding':f} for s,r in records.items() for f in r.get('saved_claim_findings',[])],recovered=any(r.get('censoring') for r in records.values()),stage_audits=stages)
 common=x['initial_faithful'] is True and all(v is True for v in ret.values()) and x['artifact_all_correct'] is True and x['unsupported_standing_or_history_mutation'] is False and x['duplicate_control'] is False
 x['strict_core_primary']=bool(common and all(u['primary_preparatory'] is True for u in uses)) if allassessed else None
 x['strict_core_secondary']=bool(common and all(u['secondary_informed'] is True for u in uses)) if allassessed else None
 out.append(x)
stamp=time.time_ns();p=A/f'progress-{stamp}.json'
x={'schema':'memory-prime-finance-progress.v1','created_ns':stamp,'planned_lifecycles':18,'planned_sessions':108,'planned_phase1_sessions':36,'assessed_results':len(list((R/'cases').glob('*-finance-*/stage-*/result.json'))),'audited_sessions':sum(len(x['assessed_audited_stages']) for x in out),'lifecycles':out,'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in A.glob('*.audit.json')}}
with p.open('x') as f:json.dump(x,f,indent=2)
print(p);print('assessed',x['assessed_results'],'audited',x['audited_sessions'])
