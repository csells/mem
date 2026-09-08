"""Persist manually supplied assessment; no semantic inference."""
from pathlib import Path
import hashlib,json,sys
AUDIT=Path(__file__).resolve().parent
ROOT=AUDIT.parents[1]
for manual in json.load(sys.stdin):
 slot=manual['slot']
 extracted=json.loads((AUDIT/(slot+'.extraction.json')).read_text())
 folder=Path(extracted['evidence_directory'])
 calls=json.loads((folder/'tool-calls.json').read_text())
 result={
  'schema':'finance-phase1-semantic-review.v1',
  'reviewer':'billing_tasks; finance corpus author unblinded',
  'assessment':'Semantic audit by the reviewer agent; not a human annotator or automatic command-count verdict.',
  **{k:extracted[k] for k in ('slot','profile_id','arm','stage','corpus_family','catalog_mode')},
  'artifact':extracted['independent_artifact_check'],
  'primary_evidence':{'directory':str(folder),'input_sha256':extracted['input_sha256'],
    'stream_sha256':hashlib.sha256((folder/'stream.jsonl').read_bytes()).hexdigest(),
    'tool_index':[{'tool_use_id':c['tool_use_id'],'tool_use_index':c['tool_use_index'],'tool_result_index':c['tool_result_index'],'name':c['name'],'arguments':c['arguments']} for c in calls]},
  **manual,
 }
 with (AUDIT/(slot+'.audit.json')).open('x') as output:json.dump(result,output,indent=2,ensure_ascii=False)
 print('AUDITED',slot)
