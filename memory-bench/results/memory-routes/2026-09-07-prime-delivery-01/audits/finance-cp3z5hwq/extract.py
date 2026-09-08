"""Append-only read-only stage evidence extraction, no candidate or CLI execution."""
from pathlib import Path
import hashlib,json,sys
A=Path(__file__).resolve().parent
ROOT=A.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def prose(p):
 out=[]
 for n,line in enumerate(p.read_text().splitlines(),1):
  e=json.loads(line);v=[]
  if e.get('type')=='text':v.append(e.get('part',{}).get('text',''))
  if e.get('type')=='result':v.append(e.get('response',''))
  if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message':v.append(e['item'].get('text',''))
  if e.get('type')=='assistant':v += [c.get('text','') for c in e.get('message',{}).get('content',[]) if c.get('type')=='text']
  out += [{'stream_line':n,'text':s} for s in v if isinstance(s,str) and s]
 return out
for d in sorted((ROOT/'cases').glob('*-finance-*/stage-*')):
 if not (d/'result.json').exists():continue
 r=read(d/'result.json');out=A/(r['slot']+'.extraction.json')
 if out.exists():
  x=read(out)
  assert all(sha(Path(p))==h for p,h in x['source_sha256'].items()),f'changed source {r["slot"]}'
  continue
 before=read(d/'memory-before.json');after=read(d/'memory-after.json')
 t=read(d/'tool-calls.json')
 x={k:r.get(k) for k in ('slot','lifecycle','profile_id','family','corpus_family','arm','catalog_mode','stage','artifact_passed','artifact_correct','artifact_total','task_closed','host_success','errors','infrastructure_fault','delivery','administrative_memory_reads')}
 x.update(evidence_directory=str(d),memory_before=before,memory_after=after,created=[k for k in after if k not in before],updated=[k for k in after if k in before and before[k]!=after[k]],removed=[k for k in before if k not in after],calls=t,prose=prose(d/'stream.jsonl'),source_sha256={str(d/f):sha(d/f) for f in ('result.json','memory-before.json','memory-after.json','tool-calls.json','stream.jsonl','launch-prompt.txt','task.json')})
 with out.open('x') as f:json.dump(x,f,indent=2,ensure_ascii=False)
 print(r['slot'],r['artifact_passed'],len(before),len(after),len(t))
