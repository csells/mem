"""Persist explicitly supplied semantic assessment, with primary evidence hashes."""
from pathlib import Path
import json,sys
A=Path(__file__).resolve().parent
for manual in json.load(sys.stdin):
 slot=manual['slot'];x=json.loads((A/(slot+'.extraction.json')).read_text());folder=Path(x['evidence_directory']);calls=json.loads((folder/'tool-calls.json').read_text())
 review={'schema':'finance-phase2-semantic-review.v1','reviewer':'billing_tasks; finance corpus author unblinded; semantic reviewer agent',**{k:x[k] for k in ('slot','profile_id','arm','stage','corpus_family','catalog_mode')},'artifact':x['independent_artifact_check'],'primary_evidence':{'directory':str(folder),'input_sha256':x['input_sha256'],'stream_sha256':x['stream_sha256'],'tool_index':[{'id':c['tool_use_id'],'use':c['tool_use_index'],'result':c['tool_result_index'],'name':c['name'],'arguments':c['arguments']} for c in calls]},**manual}
 with (A/(slot+'.audit.json')).open('x') as f:json.dump(review,f,indent=2,ensure_ascii=False)
 print('AUDITED',slot)
