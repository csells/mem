"""Preserve initial user-input evidence from isolated scored sessions only."""
from pathlib import Path
import json,hashlib,sqlite3
A=Path(__file__).resolve().parent;R=A.parents[1]
for d in sorted((R/'cases').glob('*-finance-startup-briefing-*/stage-*')):
 if not (d/'result.json').exists():continue
 r=json.loads((d/'result.json').read_text());p=A/(r['slot']+'.startup-host-user.json')
 if p.exists():continue
 launch=(d/'launch-prompt.txt').read_text();evidence=[];equal=None;sources=[]
 if r['host']=='codex':
  for f in (d/'host-evidence').rglob('*.jsonl'):
   sources.append(f)
   for n,line in enumerate(f.read_text().splitlines(),1):
    z=json.loads(line).get('payload',{})
    if z.get('type')=='message' and z.get('role')=='user':
     ts=[c.get('text','') for c in z.get('content',[])];evidence.append({'source':str(f),'line':n,'exact_launch_match':launch in ts})
  equal=any(e['exact_launch_match'] for e in evidence)
 elif r['host']=='zcode':
  f=d/'stream.jsonl';sources.append(f)
  for n,line in enumerate(f.read_text().splitlines(),1):
   z=json.loads(line)
   if z.get('type')=='turn.started':evidence.append({'source':str(f),'line':n,'exact_launch_match':z['payload'].get('input')==launch})
  equal=any(e['exact_launch_match'] for e in evidence)
 elif r['host']=='opencode':
  state=json.loads((d.parent/'state.json').read_text());db=Path(state['scratch'])/d.name/'config/data/opencode/opencode.db'
  c=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
  rows=[dict(zip(('part_id','message_id','data'),row)) for row in c.execute("SELECT p.id,p.message_id,p.data FROM part p JOIN message m ON p.message_id=m.id WHERE m.session_id=? AND json_extract(m.data,'$.role')='user'",(r['session_id'],))];c.close()
  t='\n'.join(json.loads(row['data']).get('text','') for row in rows);equal=t==launch;evidence=[{'source_database':str(db),'session_id':r['session_id'],'rows':rows,'read_mode':'read-only'}]
 else:evidence=[{'source':str(d/'launch.json'),'limitation':'Claude no-persistence event stream does not echo initial user message; submission recorded, separate host user-message proof unavailable.'}];sources=[d/'launch.json',d/'launch-prompt.txt']
 out={'schema':'memory-prime-user-delivery.v1','slot':r['slot'],'startup_submitted':True,'exact_launch_match':equal,'launch_prompt_sha256':hashlib.sha256(launch.encode()).hexdigest(),'evidence':evidence,'source_sha256':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources}}
 with p.open('x') as f:json.dump(out,f,indent=2)
 print(r['slot'],equal)
