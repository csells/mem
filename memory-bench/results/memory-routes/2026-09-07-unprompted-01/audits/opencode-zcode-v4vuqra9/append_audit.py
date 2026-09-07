"""Append manually assessed sessions; read evidence only, never execute a candidate."""
import hashlib,json,sys
from pathlib import Path
from datetime import datetime,timezone
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
for item in json.load(sys.stdin):
    slot=item['slot']
    lifecycle,stage=slot.rsplit('-',1)
    folder=ROOT/'cases'/lifecycle/f'stage-{stage}'
    r=json.loads((folder/'result.json').read_text())
    before=json.loads((folder/'memory-before.json').read_text());after=json.loads((folder/'memory-after.json').read_text())
    receipts=json.loads((folder/'raw-receipts.json').read_text())
    calls=json.loads((folder/'tool-calls.json').read_text())
    tasks_before=json.loads((folder/'tasks-before.json').read_text());tasks_after=json.loads((folder/'tasks-after.json').read_text())
    def tree(label):
        return {str(p.relative_to(folder/label)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (folder/label).rglob('*') if p.is_file() and not p.is_symlink()}
    old,new=tree('workspace-before'),tree('workspace-after')
    changed=[path for path in sorted(set(old)|set(new)) if old.get(path)!=new.get(path)]
    evidence=[p for p in folder.iterdir() if p.is_file()]
    evidence += [p for label in ['workspace-before','workspace-after'] for p in (folder/label).rglob('*') if p.is_file() and not p.is_symlink()]
    doc={'schema':'independent-ordinary-session-audit.v1','created_utc':datetime.now(timezone.utc).isoformat(),'slot':slot,'host':r['host'],'arm':r['arm'],'family':r['family'],'stage':r['stage'],'session_id':r['session_id'],'model':r['models_observed'],'artifact':{'passed':r['artifact_passed'],'correct':r['artifact_correct'],'total':r['artifact_total']},'instruction_observation':{k:r.get(k) for k in ['native_skill_calls','skill_file_read_calls','memory_workflow_read_calls','skill_read_attempts','task_closed','infrastructure_fault']},'memory_before':before,'memory_after':after,'receipt_operations':[{'argv':x['operation_argv'],'returncode':x['returncode'],'invocation_id':x['invocation_id']} for x in receipts if x['event']=='finish'],'tool_names':[x['name'] for x in calls],'workspace_changed_paths':changed,'task_status_before':[{k:x.get(k) for k in ['id','title','status','comment_count']} for x in tasks_before],'task_status_after':[{k:x.get(k) for k in ['id','title','status','comment_count']} for x in tasks_after],'manual_assessment':item,'input_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence},'model_calls_by_auditor':0}
    with (OUT/(slot+'.json')).open('x') as f:json.dump(doc,f,indent=2);f.write('\n')
    print('AUDITED '+slot,flush=True)
