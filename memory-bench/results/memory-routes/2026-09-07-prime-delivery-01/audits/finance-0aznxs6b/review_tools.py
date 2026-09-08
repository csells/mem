"""Append-only offline finance extraction; semantic conclusions supplied by reviewer."""
from pathlib import Path
import argparse, hashlib, importlib.util, json, sys, time

AUDIT = Path(__file__).resolve().parent
ROOT = AUDIT.parents[1]
BENCH = ROOT.parents[2]
sys.path.insert(0, str(BENCH))
CORPUS = ROOT / 'frozen-source/memory-bench/fixtures/memory-policy-fork-corpus'
EXTRACTOR = BENCH / 'results/memory-routes/2026-09-07-policy-handoff-verification-01/phase-audit-preparation-1rnm_oth/extract.py'
ORACLE = BENCH / 'results/memory-routes/2026-09-07-policy-handoff-01/audits/finance-phase2-4vuoff9t/review_tools.py'

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

oracle = load(ORACLE, 'retained_finance_independent_oracle')
extractor = load(EXTRACTOR, 'retained_offline_extractor')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.write('\n')

def expected_for(case, world, stage):
    if 'artifact_json_path' not in case:
        return oracle.oracle(case['stdin'], world, stage)
    task = json.loads((CORPUS/world/'tasks.json').read_text())['tasks'][5]['prompt']
    request, _ = json.JSONDecoder().raw_decode(task.split('REQUEST: ',1)[1])
    return {'request':request, 'response':oracle.oracle(request, world, stage)}

def artifact_check(folder, result):
    frozen = CORPUS/result['corpus_family']/'graders'/f"stage-{result['stage']}.json"
    cases = json.loads(frozen.read_text())
    gradefile = folder/'artifact-grade.json'
    grade = json.loads(gradefile.read_text())
    observed = {c['name']:c for c in grade['cases']}
    assert len(observed)==len(cases)
    checked=[]
    for case in cases:
        expected = expected_for(case, result['corpus_family'], result['stage'])
        got = observed[case['name']]
        try:
            parsed = json.loads(got.get('stdout',''), object_pairs_hook=oracle.no_duplicates, parse_constant=oracle.bad_constant)
            correct = got.get('exit')==0 and oracle.strict_equal(parsed, expected)
        except ValueError:
            correct=False
        checked.append({'name':case['name'], 'independent_expected_matches_frozen':oracle.strict_equal(expected,case['expected']), 'correct_saved_output':correct, 'agrees_with_frozen_verdict':correct==got['passed']})
    return {'method':'Previously independently authored closed-form prefix-entitlement oracle, reviewed against unchanged current tasks; saved stdout/artifact only, no candidate execution.', 'oracle_source':str(ORACLE),'oracle_sha256':sha(ORACLE), 'inputs':{str(p.relative_to(ROOT)):sha(p) for p in (frozen,gradefile)}, 'correct':sum(c['correct_saved_output'] for c in checked), 'total':len(checked),'all_expected_agree':all(c['independent_expected_matches_frozen'] for c in checked),'all_verdicts_agree':all(c['agrees_with_frozen_verdict'] for c in checked),'cases':checked}

def inventory():
    return [r for r in json.loads((ROOT/'manifest.json').read_text())['slots'] if r['family']=='finance']

def folder(row):
    return ROOT/'cases'/row['lifecycle']/f"stage-{row['stage']}"

def collect():
    new=[]
    for row in inventory():
        source=folder(row); destination=AUDIT/(row['slot']+'.extraction.json')
        if destination.exists() or not (source/'result.json').exists():
            continue
        data=extractor.extract(source)
        result=json.loads((source/'result.json').read_text())
        data['lifecycle']=row['lifecycle']
        data['independent_artifact_check']=artifact_check(source,result)
        data['stream_sha256']=sha(source/'stream.jsonl')
        data['delivery']=json.loads((source/'delivery.json').read_text())
        data['input_sha256'].update({n:sha(source/n) for n in ('delivery.json','task.json','launch-prompt.txt','task-prompt.txt','startup-briefing.txt')})
        write(destination,data)
        new.append(row['slot'])
        print('EXTRACTED',row['slot'],f"artifact={result['artifact_correct']}/{result['artifact_total']}",f"records={len(data['memory_before'])}->{len(data['memory_after'])}",flush=True)
    print(json.dumps({'new':new,'extracted':len(list(AUDIT.glob('*.extraction.json'))),'audited':len(list(AUDIT.glob('*.audit.json'))),'planned':108}),flush=True)

def show(slot):
    row=next(r for r in inventory() if r['slot']==slot); source=folder(row)
    result=json.loads((source/'result.json').read_text())
    print('CASE',slot,'world',row['corpus_family'],'artifact',result['artifact_correct'],result['artifact_total'],'host',result['host_success'],'errors',result['errors'])
    print('BEFORE',(source/'memory-before.json').read_text())
    print('AFTER',(source/'memory-after.json').read_text())
    for index,call in enumerate(json.loads((source/'tool-calls.json').read_text())):
        body=str(call.get('result') or '')
        print('CALL',index,'event',call.get('tool_use_index'),call.get('tool_result_index'),call['name'],json.dumps(call['arguments'],ensure_ascii=False))
        print('OUTPUT',body[:2400] + (f'\n[VIEW TRUNCATED: {len(body)} chars total]' if len(body)>2400 else ''))
    print('FINAL TASK',json.dumps([t for t in json.loads((source/'tasks-after.json').read_text()) if t['id']==result['task_id']],ensure_ascii=False))
    grade=json.loads((source/'artifact-grade.json').read_text())
    print('FAILED CASES',[c['name'] for c in grade['cases'] if not c['passed']])

def record():
    for manual in json.load(sys.stdin):
        slot=manual['slot']; extracted=json.loads((AUDIT/(slot+'.extraction.json')).read_text())
        result={'schema':'prime-finance-stage-audit.v1','reviewer':'prime_runtime_review; independent finance reviewer, unblinded to model/arm','created_ns':time.time_ns(),**{k:extracted[k] for k in ('slot','lifecycle','profile_id','host','family','arm','stage','corpus_family','catalog_mode')},'artifact':extracted['independent_artifact_check'],'artifact_passed':extracted['artifact_passed'],'host_success':extracted['host_success'],'primary_evidence':{'directory':extracted['evidence_directory'],'input_sha256':extracted['input_sha256'],'stream_sha256':extracted['stream_sha256']},**manual}
        write(AUDIT/(slot+'.audit.json'),result)
        print('AUDITED',slot,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--collect',action='store_true');p.add_argument('--show');p.add_argument('--record',action='store_true');a=p.parse_args()
    if a.collect:collect()
    if a.show:show(a.show)
    if a.record:record()
