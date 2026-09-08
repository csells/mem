"""Read-only evidence viewer; no candidate execution and no semantic inference."""
from pathlib import Path
import json,sys,argparse,difflib
A=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('slot');p.add_argument('--calls',action='store_true');p.add_argument('--results',nargs='*',type=int);p.add_argument('--memory',action='store_true');p.add_argument('--prose',action='store_true');p.add_argument('--diff',action='store_true');a=p.parse_args()
x=json.loads((A/(a.slot+'.extraction.json')).read_text());d=Path(x['evidence_directory'])
print('SLOT',a.slot,'DIR',d)
print('META',json.dumps({k:x[k] for k in ('corpus_family','catalog_mode','host_success','duration_s','task_closed','infrastructure_fault','created','updated','missing_after','artifact_correct','artifact_total')},ensure_ascii=False))
if a.memory:print('BEFORE',json.dumps(x['memory_before'],indent=2,ensure_ascii=False));print('AFTER',json.dumps(x['memory_after'],indent=2,ensure_ascii=False))
for c in json.loads((d/'tool-calls.json').read_text()):
 if a.calls or (a.results is not None and c['tool_use_index'] in a.results):
  print('CALL',c['tool_use_index'],c['tool_result_index'],c['tool_use_id'],c['name'],json.dumps(c['arguments'],ensure_ascii=False))
  if a.results is not None and (not a.results or c['tool_use_index'] in a.results):print('RESULT',c['result'])
if a.prose:
 for i,l in enumerate((d/'stream.jsonl').read_text().splitlines(),1):
  o=json.loads(l);t=o.get('type');values=[]
  if t=='result' and isinstance(o.get('response'),str):values.append(o['response'])
  if t=='text' and isinstance(o.get('part',{}).get('text'),str):values.append(o['part']['text'])
  if t=='item.completed' and o.get('item',{}).get('type')=='agent_message':values.append(o['item']['text'])
  if t=='assistant':
   msg=o.get('message',{});contents=msg.get('content',[]) if isinstance(msg,dict) else []
   values.extend(c['text'] for c in contents if c.get('type')=='text' and isinstance(c.get('text'),str))
  for value in values:print('PROSELINE',i,value)
if a.diff:
 before=d/'workspace-before';after=d/'workspace-after'
 files=sorted(set(f.relative_to(z) for z in (before,after) for f in z.rglob('*') if f.is_file() and f.suffix in ('.py','.json','.md') and not any(part.startswith('.') for part in f.relative_to(z).parts)))
 for name in files:
  l=(before/name).read_text().splitlines() if (before/name).exists() else [];r=(after/name).read_text().splitlines() if (after/name).exists() else []
  if l!=r:print('DIFF',name,'\n'+'\n'.join(difflib.unified_diff(l,r,fromfile='before/'+str(name),tofile='after/'+str(name),lineterm='')))
