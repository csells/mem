"""Read-only final lifecycle evidence integrity check; no subprocess/model calls."""
from __future__ import annotations

import collections
import datetime
import hashlib
import json
from pathlib import Path

from membench.runner.memory_lifecycle_gate import _finished

BENCH = Path.cwd().resolve()
REPO = BENCH.parent
OUT = Path(__file__).resolve().parent
RUN = BENCH / 'results/memory-routes/2026-09-06-lifecycle-02'
ANALYSIS = BENCH / 'results/memory-routes/2026-09-06-lifecycle-final-analysis/analysis.json'
BASELINE = Path('/var/folders/6k/xzgngnms6jg4_z2l40y0_9vh0000gn/T/mem-lifecycle-before-ns14bnv9/files.json')
errors = []


def read(path):
    return json.loads(path.read_text())


def sha(path):
    if not path.is_file():
        return None
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        errors.append(message)


def pins(mapping, root):
    rows = []
    for name, expected in mapping.items():
        actual = sha(root / name)
        rows.append({'path':name, 'expected':expected, 'actual':actual, 'matches':actual==expected})
    return rows


manifest = read(RUN / 'manifest.json')
source_rows = pins(manifest['source_sha256'], REPO)
frozen_rows = pins(manifest['source_sha256'], RUN/'source')
binary_rows = pins(manifest['binary_sha256'], Path('/'))
for label, rows in [('current source',source_rows),('frozen source',frozen_rows),('binary',binary_rows)]:
    require(all(row['matches'] for row in rows), f'{label} pin mismatch')
baseline_rows = pins(read(BASELINE), REPO)
baseline_changes = [row for row in baseline_rows if not row['matches']]
allowed_source = 'memory-bench/scripts/memory_routes_experiment.py'
require(all(row['path']==allowed_source for row in baseline_changes), 'Unexpected pre-existing file change')

tasks = {task['id']:task for task in manifest['tasks']}
copied = []
sessions = []
seen = set()
receipt_count = 0
for scheduled in manifest['schedule']:
    case_name = scheduled['task']+'-'+scheduled['policy']
    case = RUN/'cases'/case_name
    task = tasks[scheduled['task']]
    aggregate = read(case/'result.json')
    require(len(aggregate['stages'])==len(task['stages'])==8, f'{case_name}: stage count')
    for index, stage in enumerate(task['stages']):
        directory = case/stage['name']
        result = read(directory/'result.json')
        assessment = read(directory/'assessment.json')
        require(aggregate['stages'][index]==assessment, f'{directory}: aggregate mismatch')
        require(assessment['result']==result, f'{directory}: assessment/result mismatch')
        require(result['leg']==stage['name'] and result['policy']==scheduled['policy'], f'{directory}: identity mismatch')
        require(result['session_id'] not in seen, f'{directory}: duplicate session')
        seen.add(result['session_id'])
        require(result['exit_code']==0 and result['terminal_subtype']=='success'
                and result['is_error'] is False and result['behavioral_limit'] is False,
                f'{directory}: unsuccessful/capped result')
        metric = result['memory_evidence']
        require(metric['status']=='ok' and metric['evidence_unknown'] is False
                and metric['unknown_reasons']==[], f'{directory}: unknown memory receipts')
        stream = [json.loads(line) for line in (directory/'stream.jsonl').read_text().splitlines()]
        terminal = [event for event in stream if event.get('type')=='result']
        require(len(terminal)==1, f'{directory}: missing/duplicate terminal result')
        if len(terminal)==1:
            event=terminal[0]
            require(event.get('subtype')=='success' and event.get('is_error') is False,
                    f'{directory}: actual stream failure/cap')
            require(event.get('session_id')==result['session_id'], f'{directory}: stream session mismatch')
            require(event.get('total_cost_usd')==result['cost_usd'], f'{directory}: cost mismatch')
        receipt_rows = read(directory/'receipts.json')
        try:
            finished = _finished(receipt_rows)
            receipt_count += len(finished)
            require(all(row['session_id']==result['session_id'] for row in finished),
                    f'{directory}: wrong receipt session')
            require(all(row['argv'][0] in manifest['binary_sha256'] for row in finished),
                    f'{directory}: receipt binary unpinned')
        except Exception as exc:
            errors.append(f'{directory}: invalid receipts ({type(exc).__name__})')
        events = []
        if scheduled['policy']=='checked':
            local=Path(result['scratch'])
            for name in ('memory_lifecycle_gate.py','memory_lifecycle_hooks.py','bd_receipts.py','memory_routes_grade.py'):
                pin=manifest['source_sha256']['memory-bench/membench/runner/'+name]
                path=local/'bin/membench/runner'/name
                actual=sha(path)
                copied.append({'session':result['session_id'],'case':case_name,'stage':stage['name'],
                               'path':str(path),'expected':pin,'actual':actual,'matches':pin==actual})
                require(pin==actual, f'{directory}: copied {name} differs')
            require(sha(local/'receipts.jsonl') is not None, f'{directory}: scratch receipts missing')
            require([json.loads(line) for line in (local/'receipts.jsonl').read_text().splitlines()]==receipt_rows,
                    f'{directory}: scratch receipt copy differs')
            require(sha(local/'gate-events.jsonl')==sha(directory/'gate-events.jsonl'),
                    f'{directory}: scratch gate events differ')
            require(sha(local/'bin/gate-policy.json')==sha(directory/'gate-policy.json'),
                    f'{directory}: installed policy differs')
            events=[json.loads(line) for line in (directory/'gate-events.jsonl').read_text().splitlines()]
            require(any(event.get('event')=='stop' and event.get('passed') is True for event in events),
                    f'{directory}: no successful measured Stop')
            require(not any(event.get('infrastructure_error') for event in events),
                    f'{directory}: gate infrastructure error')
        sessions.append({'case':case_name,'stage':stage['name'],'session_id':result['session_id'],
                         'terminal_subtype':result['terminal_subtype'],'evidence_unknown':metric['evidence_unknown'],
                         'cost_usd':result['cost_usd'],'gate_event_count':len(events)})
    print('CHECKED',case_name,flush=True)
halts = [str(path.relative_to(RUN)) for path in (RUN/'cases').rglob('halt.json')]
require(not halts, 'Run contains halt artifacts')
require(len(sessions)==len(seen)==manifest['planned_sessions']==96, 'Session coverage differs from 96')
require(len(copied)==128, 'Expected 32 checked sessions times four copied modules')

analysis=read(ANALYSIS)
analysis_rows=pins(analysis['input_sha256'],RUN)
require(all(row['matches'] for row in analysis_rows), 'Final analysis input changed')
require(analysis['unique_sessions_observed']==96, 'Final analysis lacks 96 sessions')
reporter_current=sha(BENCH/'scripts/memory_lifecycle_report.py')
verified_reporter=read(OUT/'final-external-temp/pytest.json')['source_hashes_after']['scripts/memory_lifecycle_report.py']
reporter_provenance={'declared_at_analysis_generation':analysis['reporter_sha256'],
                     'prior_287_test_gate_snapshot':verified_reporter,'current':reporter_current,
                     'analysis_reporter_matches_tested_snapshot':analysis['reporter_sha256']==verified_reporter,
                     'analysis_reporter_matches_current':analysis['reporter_sha256']==reporter_current,
                     'note':'The parent authorized a subsequent report label-only edit. Historical analysis pins are retained; no model evidence is rewritten.'}
require(reporter_provenance['analysis_reporter_matches_tested_snapshot'], 'Analysis reporter not prior verified version')
old=BENCH/'results/memory-routes/2026-09-06-lifecycle-01'
old_sessions=list((old/'cases').glob('*/*/started.json')) if (old/'cases').exists() else []
require(not old_sessions, 'Plan-only lifecycle-01 has session artifacts')
smoke=read(BENCH/'results/memory-routes/2026-09-06-lifecycle-gate-smoke-01/result.json')
require(smoke['model_calls']==0 and smoke['passed'] is True, 'Mechanical smoke model count/pass differs')

output={'schema':'memory-lifecycle-final-integrity.v1','checked_at_utc':datetime.datetime.now(datetime.UTC).isoformat(),
        'passed':not errors,'errors':errors,'run':str(RUN),'manifest_sha256':sha(RUN/'manifest.json'),
        'current_source_pins':source_rows,'frozen_source_pins':frozen_rows,'binary_pins':binary_rows,
        'baseline':{'path':str(BASELINE),'sha256':sha(BASELINE),'files_checked':len(baseline_rows),
                    'unchanged_count':sum(row['matches'] for row in baseline_rows),'changes':baseline_changes,
                    'allowed_existing_source_change':allowed_source,
                    'scope_note':'Snapshot at checked_at_utc. Parent plans an additive link in an old narrative after this check.'},
        'sessions':sessions,'unique_sessions':len(seen),'policies':dict(collections.Counter(row['case'].rsplit('-',1)[-1] for row in sessions)),
        'validated_finished_cli_receipts':receipt_count,'halt_artifacts':halts,'copied_checked_modules':copied,
        'analysis':{'path':str(ANALYSIS),'sha256':sha(ANALYSIS),'input_pins':analysis_rows,'reporter':reporter_provenance},
        'preserved_controls':{'lifecycle_01_session_artifacts':len(old_sessions),'mechanical_smoke_model_calls':smoke['model_calls']},
        'limitations':'This is a file/receipt integrity audit, not new model observation or a claim that source hashes prove semantic correctness. No tests rerun, model calls, source edits, or data mutations.'}
with (OUT/'final-run-integrity.json').open('x') as stream:
    json.dump(output,stream,indent=2)
    stream.write('\n')
print(json.dumps({'passed':output['passed'],'errors':errors,'sessions':len(sessions),
                  'checked_module_files':len(copied),'baseline_unchanged':output['baseline']['unchanged_count'],
                  'baseline_changed':[row['path'] for row in baseline_changes],
                  'finished_receipts':receipt_count,'analysis_inputs':len(analysis_rows),
                  'reporter_provenance':reporter_provenance},indent=2))
raise SystemExit(bool(errors))
