"""Compact read-only inspection of completed, unaudited continuation evidence."""
from pathlib import Path
import json
import difflib
OUT=Path(__file__).resolve().parent
ROOT=OUT.parent.parent
n=0
for p in sorted((ROOT/'cases').glob('*/stage-*/result.json')):
 r=json.loads(p.read_text())
 if r['host'] not in ['claude','codex'] or r['phase']!='continuation' or (OUT/f"{r['slot']}.audit.json").exists():continue
 n+=1;p=p.parent
 print('SESSION',r['slot'],'ARTIFACT',r['artifact_correct'],r['artifact_total'],'ACTIONS',r['action_counts'])
 print('DELIVERY',{k:r[k] for k in ['host_success','infrastructure_fault','native_skill_calls','skill_file_read_calls','memory_workflow_read_calls']})
 mb=json.loads((p/'memory-before.json').read_text());ma=json.loads((p/'memory-after.json').read_text())
 print('MEMORY_KEYS',list(mb),list(ma),'UNCHANGED',mb==ma)
 for k,v in ma.items():
  if k not in mb or mb[k]!=v:print('CAPTURE',k,v)
 for i,c in enumerate(json.loads((p/'tool-calls.json').read_text())):
  a=json.dumps(c.get('arguments',{}));result=str(c.get('result',''))
  print('CALL',i,c.get('name'),a[:700])
  if any(s in a for s in ['bd memories','bd memory','bd recall','bd remember']):print('RESULT',result[:5000])
  elif 'references/memory.md' in a:print('PROCEDURE_RETURN_LENGTH',len(result),'COMPLETE_END',result[-120:])
  elif any(s in a for s in ['unittest','test_public.py --cases']):print('VALIDATION_RESULT_END',result[-450:])
 for e in map(json.loads,(p/'stream.jsonl').read_text().splitlines()):
  if e.get('type')=='assistant':
   for c in e.get('message',{}).get('content',[]):
    if c.get('type')=='text':print('PROSE',c['text'])
  if e.get('item',{}).get('type')=='agent_message':print('PROSE',e['item']['text'])
 print('CLOSE_REASONS',[(t['id'],t.get('close_reason')) for t in json.loads((p/'tasks-after.json').read_text())])
 f='README.md';b=p/'workspace-before'/f;a=p/'workspace-after'/f
 print('README_DIFF',''.join(difflib.unified_diff(b.read_text().splitlines(True),a.read_text().splitlines(True))))
 grade=json.loads((p/'artifact-grade.json').read_text());print('FAILED_CASES',[c['name'] for c in grade['cases'] if not c['passed']])
print('UNREVIEWED',n)
