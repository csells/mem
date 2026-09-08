"""Lossless canonical bridge of explicit human assessments; no semantic scoring from counts."""
from pathlib import Path
import json,time,hashlib,copy
A=Path(__file__).resolve().parent
source=max(A.glob('progress-*.json'))
p=json.loads(source.read_text())
reviews={f.name.removesuffix('.audit.json'):json.loads(f.read_text()) for f in A.glob('*.audit.json')}
qualifications=[f for pattern in ('*supplement*.json','*addendum*.json','*qualification*.json') for f in A.glob(pattern)]
rows=[]
for old in p['lifecycle_summaries']:
 life=copy.deepcopy(old)
 vals=list(life['artifacts'].values())
 life['all_six_artifacts']=False if False in vals else True if all(v is True for v in vals) else None
 life['current_and_historical_faithful']={k.removeprefix('stage'):v for k,v in life['current_and_historical_faithful'].items()}
 status=life.pop('strict_six_stage_intersection')
 life['strict_six_stage_intersection']={'status':str(status).lower(),'failed_components':life.pop('strict_intersection_reasons'),'unverified_components':life.pop('remaining_unknown_components')}
 life['stage6_duplicate_curation']=life['stage6']['duplicate_curation']
 life['unsupported_mutation_detail']=life.pop('unsupported_standing_or_historical_mutation')
 md=life['unsupported_mutation_detail']; life['unsupported_standing_or_historical_mutation']=True if any(v is True for v in md.values()) else None if any(v is None for v in md.values()) else False
 life['later_session_evidence']={}
 for stage in (3,4,5,6):
  review=reviews.get(life['lifecycle']+'-'+str(stage))
  life['later_session_evidence'][str(stage)]={k:review.get(k) for k in ('availability','execution_outcome','revision','retrieval','curation','alternative_sources','provenance_and_verification','unsupported_commentary','uncertainties','execution_integrity')} if review else None
 life['qualification_refs']=[f.name for f in qualifications if ('astra' in f.name and life['lifecycle']=='codex-astra-finance-occasions-isolated') or ('qwen4' in f.name and life['lifecycle']=='opencode-qwen-finance-occasions-isolated') or ('sol6' in f.name and life['lifecycle']=='codex-sol-finance-generic-isolated')]
 life['interpretation_limits']=['Core intersection does not erase separate unsupported verification/provenance claims.','Actual source alternatives and preimplemented product behavior remain meaningful distinctions; read plus correct artifact does not establish exclusive memory causality.']
 if life['lifecycle']=='codex-astra-finance-occasions-isolated':
  life['interpretation_limits'].append('Earlier notes characterizing implementation wording as definitely stale are qualified: quote/total-specific assertion remains true; broader implementation statement is ambiguous and historically sourced. It is not counted as proven false policy or unsupported historical claim. See qualification_refs.')
 rows.append(life)
output={'schema':'finance-normalized-lifecycles.v2','status':'complete' if p['audited']==80 else 'partial','planned_lifecycles':20,'planned_phase2_sessions':80,'published_phase2_sessions':p['published'],'audited_phase2_sessions':p['audited'],'source':source.name,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'lifecycle_summaries':rows,'qualification_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in qualifications},'scope':'Semantic audit of actual captured records, outputs and model-facing delivery; no candidate reruns or model calls. Original reports unchanged; this bridge adds no new automatic semantic judgments.'}
f=A/f'normalized-lifecycles-{time.time_ns()}.json'
with f.open('x') as o:json.dump(output,o,indent=2)
print(f)
