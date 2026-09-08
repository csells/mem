"""Read frozen slots and published receipts; semantic outcomes require separate audit."""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
from pathlib import Path
import time


def read(path):
    return json.loads(path.read_text())


def summarize(root):
    manifest = read(root / 'manifest.json')
    rows = []
    for slot in manifest['slots']:
        path = root / 'cases' / slot['lifecycle'] / f"stage-{slot['stage']}"
        result = read(path / 'result.json') if (path / 'result.json').is_file() else None
        if result is not None and result['slot'] != slot['slot']:
            raise ValueError('Result does not match frozen slot')
        grader = root / 'frozen-source/memory-bench/fixtures/memory-policy-fork-corpus' / slot['corpus_family'] / f"graders/stage-{slot['stage']}.json"
        row = {**slot, 'started': (path / 'process.json').is_file(),
               'assessed': result is not None, 'planned_cases': len(read(grader))}
        if row['started']:
            row['started_ns'] = read(path / 'process.json')['started_ns']
        if result:
            row.update({key: result[key] for key in (
                'artifact_passed', 'artifact_correct', 'artifact_total', 'host_success',
                'timed_out', 'cost_usd', 'duration_s', 'action_counts', 'task_closed',
                'infrastructure_fault', 'model_requested', 'models_observed', 'session_id',
                'administrative_memory_reads', 'package_changed_paths')})
            row['errors'] = result.get('errors', [])
            row['provider_quota_reported'] = any("You've hit your usage limit" in error
                                                 for error in row['errors'])
            row['turn_limit_reported'] = 'error_max_turns' in row['errors']
            row['authentication_rejection_reported'] = any('refresh token was revoked' in str(error) or 'could not be refreshed' in str(error) for error in row['errors'])
            before, after = read(path / 'memory-before.json'), read(path / 'memory-after.json')
            row['entry_keys'] = sorted(before)
            row['exit_keys'] = sorted(after)
            row['new_keys'] = sorted(set(after) - set(before))
            row['changed_keys'] = sorted(key for key in before if key in after and before[key] != after[key])
            row['removed_keys'] = sorted(set(before) - set(after))
            row['memory_unchanged'] = before == after
            attachment_cases = [case for case in read(path / 'artifact-grade.json')['cases']
                                if 'artifact_json_path' in case]
            if bool(attachment_cases) != (slot['stage'] == 6):
                raise ValueError('Supplied attachment grading must occur only at stage 6')
            row['support_artifact_passed'] = (all(case['passed'] for case in attachment_cases)
                                               if attachment_cases else None)
        rows.append(row)
    expected_paths = {root / 'cases' / row['lifecycle'] / f"stage-{row['stage']}" / 'result.json' for row in rows}
    unexpected = set((root / 'cases').glob('*/stage-*/result.json')) - expected_paths
    if unexpected:
        raise ValueError('Unexpected result paths outside frozen schedule')
    def metrics(selected):
        done = [row for row in selected if row['assessed']]
        return {
            'planned': len(selected), 'started': sum(row['started'] for row in selected),
            'assessed': len(done), 'correct_artifacts': sum(row['artifact_passed'] for row in done),
            'planned_cases': sum(row['planned_cases'] for row in selected),
            'assessed_cases': sum(row['artifact_total'] for row in done),
            'correct_cases': sum(row['artifact_correct'] for row in done),
            'host_success': sum(row['host_success'] for row in done),
            'timeouts': sum(row['timed_out'] for row in done),
            'infrastructure_faults': sum(row['infrastructure_fault'] for row in done),
            'provider_quota_reported': sum(row['provider_quota_reported'] for row in done),
            'turn_limit_reported': sum(row['turn_limit_reported'] for row in done),
            'authentication_rejection_reported': sum(row['authentication_rejection_reported'] for row in done),
            'reported_usd': sum(row['cost_usd'] for row in done if row['cost_usd'] is not None),
            'cost_unreported': sum(row['cost_usd'] is None for row in done),
            'administrative_memory_reads': sum(row['administrative_memory_reads'] for row in done),
            'stage1_any_retained': sum(row['stage'] == 1 and bool(row['exit_keys']) for row in done),
            'stage1_assessed': sum(row['stage'] == 1 for row in done),
            'stage6_changed_store': sum(row['stage'] == 6 and not row['memory_unchanged'] for row in done),
            'stage6_assessed': sum(row['stage'] == 6 for row in done),
            'support_planned': sum(row['stage'] == 6 for row in selected),
            'support_assessed': sum(row['support_artifact_passed'] is not None for row in done),
            'support_correct': sum(row['support_artifact_passed'] is True for row in done),
            'session_duration_sum_s': sum(row['duration_s'] for row in done),
            'approximate_cli_span_s': ((max(row['started_ns'] / 1e9 + row['duration_s'] for row in done)
                                         - min(row['started_ns'] / 1e9 for row in done)) if done else None),
        }
    result = {'schema': 'prime-delivery-mechanical-summary.v1', 'created_ns': time.time_ns(),
              'manifest_sha256': hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest(),
              'scope': 'Mechanical counts only; no semantic fidelity, relevance, duplication, or use inferred',
              'overall': metrics(rows), 'rows': rows}
    for field in ('phase', 'profile_id', 'arm', 'family', 'mode', 'catalog_mode', 'stage'):
        result[field] = {str(value): metrics([row for row in rows if row[field] == value])
                         for value in dict.fromkeys(row[field] for row in rows)}
    result['main_arm'] = {arm: metrics([row for row in rows if row['mode'] == 'isolated' and row['arm'] == arm])
                          for arm in ('thin-prime', 'rich-prime', 'startup-briefing')}
    result['main_profile_arm'] = {f'{profile}/{arm}': metrics([row for row in rows if row['mode'] == 'isolated' and row['profile_id'] == profile and row['arm'] == arm])
                                 for profile in manifest['admitted_profile_ids'] for arm in ('thin-prime', 'rich-prime', 'startup-briefing')}
    sessions = [row['session_id'] for row in rows if row['assessed']]
    result['duplicate_host_session_ids'] = {key: count for key, count in collections.Counter(sessions).items() if count > 1}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    summary = summarize(args.root)
    with args.out.open('x') as handle:
        json.dump(summary, handle, indent=2)
        handle.write('\n')
    print(json.dumps(summary['overall'], indent=2))
