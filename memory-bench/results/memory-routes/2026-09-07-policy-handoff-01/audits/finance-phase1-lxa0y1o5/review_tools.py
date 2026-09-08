"""Read-only completed-session collection; no candidate processes or semantic scoring."""
from pathlib import Path
import argparse, hashlib, importlib.util, json

ROOT = Path(__file__).resolve().parents[2]
AUDIT = Path(__file__).resolve().parent
BENCH = ROOT.parents[2]
HELPER = BENCH / 'results/memory-routes/2026-09-07-policy-handoff-verification-01/phase-audit-preparation-1rnm_oth/extract.py'


def oracle(request, world):
    command = request.get('command')
    if command == 'ping':
        return {'status': 'ok', 'product': 'Meridian Credits'}
    if command not in ('quote', 'total'):
        return {'error': 'unknown_command'}
    lines = [request['line']] if command == 'quote' else request['lines']
    groups = {}
    for line in lines:
        group = line['account_id'] if world == 'finance/account-first' else (line['account_id'], line['subscription_id'])
        groups[group] = groups.get(group, 0) + line['charge_cents'] // 10
    credit = sum(min(2400, value) for value in groups.values())
    result = {'release': '1.0', 'credit_cents': credit, 'amount_due_cents': sum(x['charge_cents'] for x in lines) - credit}
    if command == 'quote':
        result['line_id'] = lines[0]['line_id']
    return result


def no_duplicates(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate key')
        obj[key] = value
    return obj


def strict_equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(strict_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(strict_equal(a,b) for a,b in zip(left,right))
    return left == right


def saved_output_check(directory, result):
    path = ROOT / 'frozen-source/memory-bench/fixtures/memory-policy-fork-corpus' / result['corpus_family'] / 'graders' / f"stage-{result['stage']}.json"
    cases = json.loads(path.read_text())
    grade_path = directory / 'artifact-grade.json'
    saved = json.loads(grade_path.read_text())
    observed = {c['name']: c for c in saved['cases']}
    checks = []
    for case in cases:
        expected = oracle(case['stdin'], result['corpus_family'])
        actual = observed[case['name']]
        try:
            parsed = json.loads(actual.get('stdout', ''), object_pairs_hook=no_duplicates)
            correct = actual.get('exit') == 0 and strict_equal(parsed, expected)
        except ValueError:
            correct = False
        checks.append({'name': case['name'], 'independent_expected_matches_frozen': strict_equal(expected,case['expected']), 'correct_saved_stdout': correct, 'agrees_with_frozen_verdict': correct == actual['passed']})
    return {'method': 'Independent phase1 formula recomputed against saved stdout; candidate not rerun.', 'inputs': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (path,grade_path)}, 'cases': checks, 'correct': sum(c['correct_saved_stdout'] for c in checks), 'total': len(checks), 'all_expected_agree': all(c['independent_expected_matches_frozen'] for c in checks), 'all_verdicts_agree': all(c['agrees_with_frozen_verdict'] for c in checks)}


def inventory():
    manifest=json.loads((ROOT/'manifest.json').read_text())
    return [r for r in manifest['slots'] if r['phase']=='phase1' and r['family']=='finance']


def directory(row):
    return ROOT/'cases'/row['lifecycle']/f"stage-{row['stage']}"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect', action='store_true')
    parser.add_argument('--show')
    args=parser.parse_args()
    for row in inventory():
        folder=directory(row)
        if not (folder/'result.json').is_file():
            continue
        result=json.loads((folder/'result.json').read_text())
        if args.show and args.show != row['slot']:
            continue
        print(row['slot'],result['artifact_correct'],result['artifact_total'],result['memory_after_count'],result['action_counts'])
        if args.collect:
            output=AUDIT/(row['slot']+'.extraction.json')
            if not output.exists():
                spec=importlib.util.spec_from_file_location('prepared_audit_extract',HELPER)
                module=importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                extracted=module.extract(folder)
                extracted['independent_artifact_check']=saved_output_check(folder,result)
                with output.open('x') as target:json.dump(extracted,target,indent=2,ensure_ascii=False)
        if args.show:
            print('BEFORE', (folder/'memory-before.json').read_text())
            print('AFTER', (folder/'memory-after.json').read_text())
            for call in json.loads((folder/'tool-calls.json').read_text()):
                print('CALL',call.get('tool_call_index'),call.get('name'),json.dumps(call.get('arguments'),ensure_ascii=False))
                out=call.get('result')
                if out:
                    print('OUTPUT', str(out)[:2500])
            print('ISSUE',json.dumps([t for t in json.loads((folder/'tasks-after.json').read_text()) if t.get('id')==result['task_id']],ensure_ascii=False))


if __name__=='__main__':main()
