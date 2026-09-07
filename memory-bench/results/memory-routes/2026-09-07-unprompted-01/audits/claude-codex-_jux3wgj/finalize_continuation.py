"""Finalize the completed continuation audit offline; exclusive new outputs only."""
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
OUT=Path(__file__).resolve().parent
ROOT=OUT.parent.parent
CORPUS=ROOT/'frozen-source/memory-bench/fixtures/memory-unprompted-corpus'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(name,obj):
    with (OUT/name).open('x') as f:json.dump(obj,f,indent=2);f.write('\n')
def unique(pairs):
    d={}
    for k,v in pairs:
        if k in d:raise ValueError('duplicate key')
        d[k]=v
    return d
def equal(a,b):
    if type(a) is not type(b):return False
    if isinstance(a,dict):return a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
    if isinstance(a,list):return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    return a==b
plan=[x for x in read(OUT/'scope.json')['scheduled_slots'] if x['phase']=='continuation']
assert len(plan)==24
missing=[x['slot'] for x in plan if not (OUT/f"{x['slot']}.audit.json").exists()]
if missing:
    print('Not finalized; missing audits:',missing)
    raise SystemExit(0)
rows=[];integrity=[];hashes={};exceptions=[]
for slot in plan:
    p=ROOT/'cases'/slot['lifecycle']/f"stage-{slot['stage']}"
    r=read(p/'result.json');a=read(OUT/f"{slot['slot']}.audit.json")
    rows.append((r,a))
    specfile=CORPUS/slot['family']/'tasks.json';spec=read(specfile)
    task=next(t for t in spec['tasks'] if t['stage']==slot['stage'])
    delivered=read(p/'task.json')
    b={t['id']:t for t in read(p/'tasks-before.json')};e={t['id']:t for t in read(p/'tasks-after.json')}
    previous=p.parent/f"stage-{slot['stage']-1}"
    continuity=[]
    for f in (previous/'workspace-after').rglob('*'):
        if f.is_file():
            rel=f.relative_to(previous/'workspace-after');dest=p/'workspace-before'/rel
            if not dest.is_file() or sha(f)!=sha(dest):continuity.append(str(rel))
    gradefile=CORPUS/slot['family']/'graders'/f"stage-{slot['stage']}.json"
    expected=read(gradefile);grade=read(p/'artifact-grade.json');disagree=[];correct=0;wrong=[]
    if len(expected)!=len(grade['cases']):disagree.append('case count')
    for got,want in zip(grade['cases'],expected):
        try: passed=got['exit']==0 and equal(json.loads(got['stdout'],object_pairs_hook=unique),want['expected'])
        except (ValueError,TypeError):passed=False
        correct+=passed
        if not passed:wrong.append(want['name'])
        if got['name']!=want['name'] or got['passed']!=passed:disagree.append(want['name'])
    if not (correct==grade['correct']==r['artifact_correct'] and len(expected)==grade['total']==r['artifact_total'] and grade['passed']==r['artifact_passed']==(correct==len(expected))):disagree.append('aggregate')
    publicfile=CORPUS/slot['family']/task['public_tests']
    report={
        'slot':slot['slot'],
        'task_title_exact':delivered['title']==task['title'],
        'task_body_exact':delivered['description']==(spec.get('common_contract','')+'\n\n'+task['prompt']).strip(),
        'current_public_examples_exact':sha(publicfile)==sha(p/'workspace-before'/task['public_tests']),
        'issue_body_title_mutations':[k for k,v in b.items() if k not in e or any(v.get(f)!=e[k].get(f) for f in ['description','title'])],
        'new_agent_issues':list(set(e)-set(b)),
        'comments_after':sum(t.get('comment_count',0) for t in e.values()),
        'prior_workspace_files_changed_before_next_session':continuity,
        'memory_carried_forward_exact':read(previous/'memory-after.json')==read(p/'memory-before.json'),
        'package_changed_paths':r['package_changed_paths'],
        'prior_audit_evidence_hash_changes':[f for f,h in a['source_sha256'].items() if sha(ROOT/f)!=h],
        'infrastructure_fault':r['infrastructure_fault'],
        'independent_grade_correct':correct,'independent_grade_total':len(expected),
        'independent_grade_failed_case_names':wrong,'frozen_grade_disagreements':disagree}
    bad=any(report[k] for k in ['issue_body_title_mutations','new_agent_issues','comments_after','prior_workspace_files_changed_before_next_session','package_changed_paths','prior_audit_evidence_hash_changes','infrastructure_fault','frozen_grade_disagreements']) or not all(report[k] for k in ['task_title_exact','task_body_exact','current_public_examples_exact','memory_carried_forward_exact'])
    if bad:exceptions.append(slot['slot'])
    integrity.append(report)
    for f in [specfile,gradefile,publicfile,OUT/f"{slot['slot']}.audit.json",*[f for f in p.rglob('*') if f.is_file()]]:
        hashes[str(f.relative_to(ROOT))]=sha(f)
assert len({r['session_id'] for r,a in rows})==24
checkpoint_manifest=read(OUT/'checkpoint-audit-manifest.json')
checkpoint_changes=[f for f,h in checkpoint_manifest['sha256'].items() if not (OUT/f).exists() or sha(OUT/f)!=h]
if checkpoint_changes:exceptions.append('checkpoint_audit_changed')
def norm(r,a):
    return a.get('normalized_memory_actions',{'writes':r['action_counts'].get('write',0),'search_queries':r['action_counts'].get('query',0),'list_all':r['action_counts'].get('list',0),'recalls':r['action_counts'].get('recall',0),'help':r['action_counts'].get('help',0)})
def agg(selected):
    rr=[r for r,a in selected];costs=[r['cost_usd'] for r in rr if r['cost_usd'] is not None];usage={}
    for r in rr:
        if r['host']=='claude':
            for model,v in r['usage'].items():
                total=usage.setdefault(model,Counter())
                for k in ['inputTokens','outputTokens','cacheReadInputTokens','cacheCreationInputTokens','thinkingTokens','webSearchRequests','costUSD']:total[k]+=v.get(k,0)
        else:
            total=usage.setdefault(r['model_requested'],Counter())
            for k in ['input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens','reasoning_output_tokens']:total[k]+=r['usage'].get(k,0)
    actions=Counter()
    for r,a in selected:
        for k,v in norm(r,a).items():
            if type(v) is int:actions[k]+=v
    return {'sessions':len(rr),'revision_opportunities':sum(r['stage']==4 for r in rr),
        'revision_capture_sessions':sum(r['stage']==4 and norm(r,a)['writes']>0 for r,a in selected),
        'current_reuse_opportunities':sum(r['stage']==5 for r in rr),
        'current_reuse_sessions_with_full_memory_read':sum(r['stage']==5 and a['retrieval'].get('full_record_inspection',False) for r,a in selected),
        'historical_reuse_opportunities':sum(r['stage']==6 for r in rr),
        'historical_sessions_with_full_memory_read':sum(r['stage']==6 and a['retrieval'].get('full_record_inspection',False) for r,a in selected),
        'direct_known_reference_sessions':sum(a['retrieval'].get('direct_lookup',False) for r,a in selected),
        'normalized_actual_memory_actions':actions,
        'raw_receipt_agent_writes':sum(r['receipt_assessment']['agent_writes'] for r in rr),
        'raw_receipt_agent_reads':sum(r['receipt_assessment']['agent_reads'] for r in rr),
        'failed_memory_command_attempts':sum(r['receipt_assessment']['failed_commands'] for r in rr),
        'procedure_read_sessions':sum(r['memory_workflow_read_calls']>0 for r in rr),
        'native_skill_sessions':sum(r['native_skill_calls']>0 for r in rr),
        'skill_file_read_sessions':sum(r['skill_file_read_calls']>0 for r in rr),
        'administrative_snapshot_reads_excluded':sum(r['administrative_memory_reads'] for r in rr),
        'prime_calls_excluded':sum(r['receipt_assessment']['prime_calls'] for r in rr),
        'passing_artifact_sessions':sum(r['artifact_passed'] for r in rr),
        'correct_frozen_cases':sum(r['artifact_correct'] for r in rr),'total_frozen_cases':sum(r['artifact_total'] for r in rr),
        'host_success_sessions':sum(r['host_success'] for r in rr),
        'authored_memory_lookup_reminders':sum(a['issue_authored_reminders']['present'] for r,a in selected),
        'unsupported_commentary_sessions':[r['slot'] for r,a in selected if a.get('unsupported_commentary',{}).get('observed',False)],
        'unsupported_memory_prose_sessions':[r['slot'] for r,a in selected if a.get('unsupported_memory_prose',{}).get('observed',False)],
        'reported_cost_usd':sum(costs) if costs else None,'sessions_with_reported_cost':len(costs),
        'sum_recorded_session_durations_s':sum(r['duration_s'] for r in rr),'usage_by_reported_model':usage,
        'slots':[r['slot'] for r in rr]}
summary={'schema':'claude-codex-continuation-audit.v1','created_ns':time.time_ns(),'cohort':str(ROOT),'scope':'24 Claude/Codex isolated stages4-6 sessions',
    'verdict':'Continue frozen normal phase; measured failures retained. No task delivery/state/grade validity exceptions found.' if not exceptions else 'Review concrete integrity exceptions before phase verdict.',
    'integrity_exceptions':exceptions,'totals':agg(rows),
    'host_arm':{f'{h}/{arm}':agg([(r,a) for r,a in rows if r['host']==h and r['arm']==arm]) for h in ['claude','codex'] for arm in ['baseline','memory']},
    'host_totals':{h:agg([(r,a) for r,a in rows if r['host']==h]) for h in ['claude','codex']},
    'adjudication_notes':['Normalized writes exclude bd remember --help, counted as a write by raw receipt metadata in Codex reconciliation stage4. Frozen result files remain untouched.',
    'Claude renewal stage6 unknown action is actual bd --help. Failed bd memory search and literal-list query are discovery attempts without useful memory results.',
    'Recalls after newly saved records are verification, not later-task use. Successful later renewal reads follow search; no direct-known-reference retrieval.',
    'Checkpoint supplemental timestamp-order failures are post hoc, OpenCode-only, and separate; all eight Claude/Codex supplemental probes passed.',
    'Two audit-local clarifications correct a helper-name typo and unit-test-count typo without altering original evidence or model claims.',
    'Dollar costs include Claude auxiliary Haiku; missing Codex cost is not zero. Durations summed across parallel sessions are not cohort elapsed time.']}
put('continuation-summary.json',summary)
put('continuation-integrity.json',{'schema':'claude-codex-continuation-integrity.v1','created_ns':time.time_ns(),'selected_sessions':24,'unique_sessions':24,'exceptions':exceptions,'checkpoint_audit_changes':checkpoint_changes,'independently_compared_cases':sum(x['independent_grade_total'] for x in integrity),'rows':integrity,'evidence_sha256':hashes,'method':'Offline strict type/structure re-comparison of recorded stdout, plus source/task/public/package/state/audit hash checks; no inference or CLI/app invocation.'})
print(json.dumps({'totals':{k:v for k,v in summary['totals'].items() if k not in ['slots','usage_by_reported_model']},'host_arm':{k:{f:v for f,v in x.items() if f in ['sessions','revision_capture_sessions','current_reuse_sessions_with_full_memory_read','historical_sessions_with_full_memory_read','normalized_actual_memory_actions','passing_artifact_sessions','correct_frozen_cases','total_frozen_cases','reported_cost_usd','sum_recorded_session_durations_s']} for k,x in summary['host_arm'].items()},'integrity_exceptions':exceptions},indent=2))
