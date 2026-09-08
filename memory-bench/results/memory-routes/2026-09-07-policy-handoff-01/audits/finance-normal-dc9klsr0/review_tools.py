"""Offline business oracle and evidence collector. Never executes candidate code."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,time
A=Path(__file__).resolve().parent
ROOT=A.parents[1]
BENCH=ROOT.parents[2]
CORPUS=ROOT/'frozen-source/memory-bench/fixtures/memory-policy-fork-corpus'
HELPER=BENCH/'results/memory-routes/2026-09-07-policy-handoff-verification-01/phase-audit-preparation-1rnm_oth/extract.py'

def strict_equal(a,b):
 if type(a) is not type(b):return False
 if isinstance(a,dict):return a.keys()==b.keys() and all(strict_equal(a[k],b[k]) for k in a)
 if isinstance(a,list):return len(a)==len(b) and all(strict_equal(x,y) for x,y in zip(a,b))
 return a==b

def no_duplicates(pairs):
 result={}
 for k,v in pairs:
  if k in result:raise ValueError('duplicate key')
  result[k]=v
 return result

def bad_constant(s):raise ValueError('nonfinite JSON constant: '+s)

def oracle(request,world,stage):
 command=request.get('command')
 if command=='ping':return {'status':'ok','product':'Meridian Credits'}
 if command not in ('quote','total','statement'):return {'error':'unknown_command'}
 release=request.get('release','1.0' if stage<3 else '2.0')
 assert release in ('1.0','2.0')
 rate,cap=(10,2400) if release=='1.0' else (15,3000)
 account_scope=(world=='finance/account-first') == (release=='1.0')
 lines=[request['line']] if command=='quote' else request['lines']
 def group(line):return line['account_id'] if account_scope else (line['account_id'],line['subscription_id'])
 def priority(line):return (line['service_on'],line['line_id']) if release=='1.0' else (-line['charge_cents'],line['line_id'])
 def uncapped(line):return line['charge_cents']*rate//100
 # Closed-form prefix entitlement: no mutable cap allocator or candidate imports.
 assigned=[min(uncapped(line),max(0,cap-sum(uncapped(prior) for prior in lines if group(prior)==group(line) and priority(prior)<priority(line)))) for line in lines]
 total=sum(assigned)
 response={'release':release,'credit_cents':total,'amount_due_cents':sum(l['charge_cents'] for l in lines)-total}
 if command=='quote':response['line_id']=lines[0]['line_id']
 if command=='statement':response['lines']=[{'line_id':l['line_id'],'credit_cents':c,'amount_due_cents':l['charge_cents']-c} for l,c in zip(lines,assigned)]
 return response

def expected_for(case,world,stage):
 if 'artifact_json_path' not in case:return oracle(case['stdin'],world,stage)
 tasks=json.loads((CORPUS/world/'tasks.json').read_text())
 supplied=next(t['prompt'] for t in tasks['tasks'] if t['stage']==6)
 request,_=json.JSONDecoder().raw_decode(supplied.split('REQUEST: ',1)[1])
 return {'request':request,'response':oracle(request,world,stage)}

def check_saved(folder,result):
 path=CORPUS/result['corpus_family']/'graders'/f"stage-{result['stage']}.json"
 cases=json.loads(path.read_text()); gradepath=folder/'artifact-grade.json'; grade=json.loads(gradepath.read_text())
 actual={c['name']:c for c in grade['cases']};assert len(actual)==len(cases)
 checks=[]
 for case in cases:
  expected=expected_for(case,result['corpus_family'],result['stage']);got=actual[case['name']]
  try:
   parsed=json.loads(got.get('stdout',''),object_pairs_hook=no_duplicates,parse_constant=bad_constant)
   correct=got.get('exit')==0 and strict_equal(parsed,expected)
  except ValueError:correct=False
  checks.append({'name':case['name'],'independent_expected_matches_frozen':strict_equal(expected,case['expected']),'correct_saved_output':correct,'agrees_with_frozen_verdict':correct==got['passed'],'case_kind':'artifact_json_path' if 'artifact_json_path' in case else 'stdin_stdout'})
 return {'method':'Independent closed-form business oracle vs saved output; support request parsed from actual frozen task6. No candidate code execution.','inputs':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (path,gradepath)},'cases':checks,'correct':sum(c['correct_saved_output'] for c in checks),'total':len(checks),'all_expected_agree':all(c['independent_expected_matches_frozen'] for c in checks),'all_verdicts_agree':all(c['agrees_with_frozen_verdict'] for c in checks)}

def collect():
 manifest=json.loads((ROOT/'manifest.json').read_text()); rows=[r for r in manifest['slots'] if r['phase']=='normal' and r['family']=='finance'];assert len(rows)==24
 new=[];published=0
 for row in rows:
  folder=ROOT/'cases'/row['lifecycle']/f"stage-{row['stage']}"
  if not (folder/'result.json').is_file():continue
  published+=1;dest=A/(row['slot']+'.extraction.json')
  if dest.exists():continue
  spec=importlib.util.spec_from_file_location('offline_extract',HELPER); module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  extracted=module.extract(folder);result=json.loads((folder/'result.json').read_text());extracted['independent_artifact_check']=check_saved(folder,result)
  extracted['stream_sha256']=hashlib.sha256((folder/'stream.jsonl').read_bytes()).hexdigest()
  with dest.open('x') as f:json.dump(extracted,f,indent=2,ensure_ascii=False)
  new.append({'slot':row['slot'],'artifact':f"{result['artifact_correct']}/{result['artifact_total']}",'keys_before':len(extracted['memory_before']),'keys_after':len(extracted['memory_after']),'oracle_agrees':extracted['independent_artifact_check']['all_expected_agree'] and extracted['independent_artifact_check']['all_verdicts_agree']})
 print(json.dumps({'published':published,'planned':24,'new':new},indent=2))

def self_check():
 checks=[]
 for world in ('finance/account-first','finance/subscription-first'):
  for stage in range(1,7):
   cases=json.loads((CORPUS/world/'graders'/f'stage-{stage}.json').read_text())
   failures=[c['name'] for c in cases if not strict_equal(expected_for(c,world,stage),c['expected'])]
   checks.append({'world':world,'stage':stage,'cases':len(cases),'failures':failures})
 assert not any(c['failures'] for c in checks),checks
 report={'method':'Independent closed-form oracle vs every frozen expected case; no candidates or models.','total_cases':sum(c['cases'] for c in checks),'checks':checks,'oracle_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
 dest=A/f'oracle-self-check-{time.time_ns()}.json'
 with dest.open('x') as f:json.dump(report,f,indent=2)
 print(dest,report['total_cases'],'expected cases agree')

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--collect',action='store_true');parser.add_argument('--self-check',action='store_true');args=parser.parse_args()
 if args.self_check:self_check()
 if args.collect:collect()
