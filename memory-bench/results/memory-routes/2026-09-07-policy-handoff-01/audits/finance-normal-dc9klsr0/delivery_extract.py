"""Exact body exposure candidates from actual tool outputs, not semantic use scoring."""
from pathlib import Path
import hashlib,json,sys
A=Path(__file__).resolve().parent

def strings(x):
 if isinstance(x,str):
  yield x
  try:y=json.loads(x)
  except ValueError:return
  if not isinstance(y,str):yield from strings(y)
 elif isinstance(x,list):
  for y in x:yield from strings(y)
 elif isinstance(x,dict):
  for y in x.values():yield from strings(y)

def scan(slot):
 x=json.loads((A/(slot+'.extraction.json')).read_text());folder=Path(x['evidence_directory']);dest=A/(slot+'.delivery-extraction.json')
 if dest.exists():return
 bodies={}
 for state in ('before','after'):
  for key,body in x['memory_'+state].items():bodies.setdefault(body,[]).append({'state':state,'key':key})
 evidence=[];matches=[]
 calls=json.loads((folder/'tool-calls.json').read_text())
 for c in calls:
  texts=list(strings(c.get('result')))
  for body,origins in bodies.items():
   if any(body in s for s in texts):matches.append({'source':'tool-calls.json','use':c['tool_use_index'],'result':c['tool_result_index'],'tool_id':c['tool_use_id'],'tool_name':c['name'],'arguments':c['arguments'],'body_origins':origins,'body_sha256':hashlib.sha256(body.encode()).hexdigest()})
 if x['host']=='codex':
  for path in sorted((folder/'host-evidence').rglob('rollout*.jsonl')):
   evidence.append({'path':str(path.relative_to(folder)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()});lastcall=None
   for i,line in enumerate(path.read_text().splitlines(),1):
    event=json.loads(line);payload=event.get('payload',{})
    if payload.get('type') in ('function_call','custom_tool_call'):lastcall={'line':i,'payload':payload}
    if payload.get('type') not in ('function_call_output','custom_tool_call_output'):continue
    texts=list(strings(payload.get('output')))
    for body,origins in bodies.items():
     if any(body in s for s in texts):matches.append({'source':str(path.relative_to(folder)),'line':i,'call_id':payload.get('call_id'),'preceding_call':lastcall,'body_origins':origins,'body_sha256':hashlib.sha256(body.encode()).hexdigest()})
 result={'schema':'finance-exact-body-delivery-candidates.v1','slot':slot,'role':'Evidence extraction only; does not infer relevant-key lookup, full policy fidelity, read use, timing or curation purpose. Same content can occur under multiple keys; inspect actual command.','before_after_keys':{k:list(x['memory_'+k]) for k in ('before','after')},'exact_body_matches':matches,'model_rollout_evidence':evidence,'limits':['Only output event bodies scanned, not input/write arguments or administrative snapshots.','Exact matching may miss transformed presentations; absence is not proof of non-delivery.','Raw receipts alone do not prove model exposure; pipelines can truncate or transform bodies.']}
 with dest.open('x') as f:json.dump(result,f,indent=2,ensure_ascii=False)
 print(slot,len(matches),'body output matches')
if __name__=='__main__':
 for slot in sys.argv[1:]:scan(slot)
