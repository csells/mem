from pathlib import Path
import json,time,hashlib
A=Path(__file__).resolve().parent
def put(slot,extra):
 e=A/(slot+'.extraction.json');x=json.loads(e.read_text());r={k:x[k] for k in ('slot','lifecycle','profile_id','family','corpus_family','arm','catalog_mode','stage','artifact_passed','artifact_correct','artifact_total')}
 r.update(schema='memory-prime-finance-stage-audit.v1',audited_ns=time.time_ns(),extraction_sha256=hashlib.sha256(e.read_bytes()).hexdigest(),censoring=None,saved_claim_findings=[],unsupported_standing_or_history_mutation=False,duplicate_curation=False)
 r.update(extra)
 with (A/(slot+'.audit.json')).open('x') as f:json.dump(r,f,indent=2)
 print('AUDITED',slot)
