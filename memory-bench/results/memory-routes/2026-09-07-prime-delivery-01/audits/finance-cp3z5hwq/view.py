from pathlib import Path
import json,argparse
A=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('slot');p.add_argument('--call',type=int);p.add_argument('--memory',action='store_true');p.add_argument('--prose',action='store_true');p.add_argument('--raw',action='store_true');a=p.parse_args();x=json.loads((A/(a.slot+'.extraction.json')).read_text());d=Path(x['evidence_directory'])
print({k:x[k] for k in ('slot','corpus_family','catalog_mode','artifact_passed','created','updated','removed')})
if a.memory:print('BEFORE',json.dumps(x['memory_before'],ensure_ascii=False,indent=2));print('AFTER',json.dumps(x['memory_after'],ensure_ascii=False,indent=2))
if a.prose:print(json.dumps(x['prose'],ensure_ascii=False,indent=2))
for i,c in enumerate(x['calls']):
 if a.call is not None and i!=a.call:continue
 print(i,c['tool_use_id'],c['tool_use_index'],c['tool_result_index'],c['name'],json.dumps(c['arguments'],ensure_ascii=False)[:2000 if a.call is None else 999999]);print('OUT:',c['result'][:300 if a.call is None else 999999])
def strings(z):
 if isinstance(z,dict):
  for v in z.values():yield from strings(v)
 elif isinstance(z,list):
  for v in z:yield from strings(v)
 elif isinstance(z,str):
  yield z
  try:a=json.loads(z)
  except (ValueError,TypeError):return
  if a!=z:yield from strings(a)
if a.raw:
 for f in (d/'host-evidence').rglob('*.jsonl'):
  for n,line in enumerate(f.read_text().splitlines(),1):
   z=json.loads(line).get('payload',{})
   if z.get('type') in ('custom_tool_call_output','function_call_output'):
    ss=list(strings(z.get('output')))
    print('RAW',f.name,n,'complete_before_keys',[k for k,v in x['memory_before'].items() if any(v in s for s in ss)],'contains_mem_ref',any('# Project memory' in s for s in ss),'truncated',any('tokens truncated' in s for s in ss))
