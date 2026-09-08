"""Normalize completed manual lifecycle reviews; never judges semantic fidelity from counters."""
from pathlib import Path
import hashlib
import json
A=Path(__file__).resolve().parent
R=A.parents[1]
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
initial_file=R/'audits/webhooks-phase1-8w6n9zwg/normalized-lifecycles-phase1.json'
phase1=read(initial_file)['lifecycles']
output=A/'lifecycles-final-v2'
output.mkdir(exist_ok=True)
for first in phase1:
 life=first['lifecycle']
 path=output/(life+'.json')
 if path.exists():
  continue
 files=[A/(life+f'-{stage}.json') for stage in range(3,7)]
 if not all(p.exists() for p in files):
  continue
 audits={stage:read(p) for stage,p in zip(range(3,7),files)}
 facts={stage:d['findings'] for stage,d in audits.items()}
 interpretation_files=[A/'initial-capture-trigger-interpretation.json']
 if life == 'codex-sol-webhooks-generic-isolated':
  interpretation_files.append(A/'sol-generic4-source-wording-supplement.json')
  facts[4]['verification_and_provenance']['source_description_correction']='Selected record-ID set filters original receipt sequence; no literal index sorting.'
 if life == 'codex-luna-webhooks-generic-isolated':
  correction=A/'luna-generic5-test-scope-supplement.json'
  interpretation_files.append(correction)
  facts[5]['verification_and_provenance']['unsupported_claims']=read(correction)['unsupported_claims']
  facts[5]['verification_and_provenance']['test_scope_correction']=read(correction)['correction']
 if life == 'codex-terra-webhooks-occasions-isolated':
  correction=A/'terra-occasions5-test-scope-supplement.json'
  interpretation_files.append(correction)
  facts[5]['verification_and_provenance']['tests']=read(correction)['correction']
 for correction in sorted(A.glob('*-control-diagnostic-supplement.json')):
  content=read(correction)
  if content['lifecycle']==life:
   facts[6]['control'].update(content['classification'])
   facts[6]['control']['diagnostic_interpretation']=content['interpretation']
   interpretation_files.append(correction)
 artifacts=first['artifact_results']+[{'stage':stage,'passed':d['metadata']['artifact_passed'],'correct':d['metadata']['artifact_correct'],'total':d['metadata']['artifact_total']} for stage,d in audits.items()]
 retrieval={'2':first['retrieval_legs']['2'], **{str(stage):facts[stage]['retrieval'] for stage in [4,5]}}
 fidelity={str(stage):facts[stage]['current_and_historical_faithful'] for stage in [3,5,6]}
 first_altered=first['unsupported_standing_or_historical_mutation']
 supplements=[]
 if life == 'zcode-glm-webhooks-generic-isolated':
  supplement=A/'glm-generic-engineering-convention-supplement.json'
  first_altered=read(supplement)['normalization_override']['unsupported_standing_or_historical_mutation']
  supplements.append({'path':str(supplement.relative_to(R)),'sha256':sha(supplement)})
 altered=first_altered or any(f.get('unsupported_standing_or_historical_mutation') is True for f in facts.values())
 control=facts[6]['control']
 false=[]
 unknown=[]
 if first['initial_capture_faithful'] is False:
  false.append('Initial required agreement was omitted or incomplete at stage1; late capture does not repair this component.')
 if first['initial_capture_faithful'] is None:
  unknown.append('Initial capture adherence provider-censored.')
 for stage,state in fidelity.items():
  if state is False:
   false.append(f'Current/historical required record fidelity fails after stage{stage}.')
  elif state is not True:
   unknown.append(f'Current/historical required record fidelity unverified after stage{stage}.')
 for item in artifacts:
  if not item['passed']:
   false.append(f"Stage{item['stage']} frozen artifact failed ({item['correct']}/{item['total']}).")
 for stage,f in retrieval.items():
  good=f.get('successful_use',f.get('successful_prior_record_use'))
  if good is False:
   false.append(f'Stage{stage} has no evidenced full applicable prior-record use leading to correct work.')
  elif good is not True:
   unknown.append(f'Stage{stage} prior-record use unverified.')
 if altered:
  false.append('Unsupported standing/historical agreement mutation or policy advice occurred; see scoped facts/provenance evidence.')
 if control.get('duplicate_curation') is True:
  false.append('Supplied control caused duplicate curation without evidenced new finding.')
 elif control.get('duplicate_curation') is not False:
  unknown.append('Supplied control duplication outcome unverified.')
 result={
  'schema':'webhooks-manual-complete-lifecycle.v2','classification_supplements':supplements+[{'path':str(p.relative_to(R)),'sha256':sha(p)} for p in interpretation_files],'lifecycle':life,'profile_id':first['profile_id'],'arm':first['arm'],'private_world':first['private_world'],'catalog_mode':first['catalog_mode'],
  'initial_capture_faithful':first['initial_capture_faithful'],'initial_capture_status':first['initial_capture_status'],
  'current_and_historical_faithful':fidelity,'retrieval_legs':retrieval,'all_six_artifacts':all(x['passed'] for x in artifacts),'artifact_results':artifacts,
  'unsupported_standing_or_historical_mutation':altered,'stage6_duplicate_curation':control.get('duplicate_curation'),'stage6_evidenced_new_finding':control.get('evidenced_new_finding'),'stage6_control':control,
  'verification_and_provenance':{'phase1':first['verification_and_provenance_concerns'],**{str(stage):f.get('verification_and_provenance',{}) for stage,f in facts.items()}},
  'older_issue_changes':{str(stage):audits[stage]['older_issue_objects_changed'] for stage in audits},
  'provider_availability':first['phase1_provider_availability']+[{'stage':stage,'errors':d['metadata']['errors'],'frozen_infrastructure_fault':d['metadata']['infrastructure_fault']} for stage,d in audits.items() if not d['metadata']['host_success']],
  'strict_six_stage_intersection':{'status':'false' if false else 'unverified' if unknown else 'true','failed_components':false,'unverified_components':unknown},
  'evidence':{'phase1_normalized':str(initial_file.relative_to(R)),'phase1_normalized_sha256':sha(initial_file),'phase1_details':first['detailed_evidence'],'phase2_details':{str(p.relative_to(R)):sha(p) for p in files}},
  'limits':['Full delivered body must be evaluated for required fact coverage independently.','Pre-edit or pre-validation body plus correct work supports observed use; alternate source availability prevents exclusive causal attribution.','Initial Courier provider contract was already durable in starter docs; missing capture target alone does not prove rule disobedience.','A newly observed incidental execution diagnostic is separate from a new durable project agreement and does not establish an obligation to save.','A strict false can coexist with provider-censored adherence because a separate artifact already failed.'],
 }
 with path.open('x') as out:json.dump(result,out,indent=2,ensure_ascii=False)
 print(life,result['strict_six_stage_intersection']['status'])
