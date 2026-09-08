"""Offline extraction only; never awards fidelity, relevance, or implementation use."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from membench.runner.memory_e2e_audit import classify_operation


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract(directory: Path) -> dict:
    hashes = {}

    def read(name: str):
        path = directory / name
        data = path.read_bytes()
        hashes[name] = digest(data)
        return json.loads(data)

    result = read('result.json')
    before, after = read('memory-before.json'), read('memory-after.json')
    launch = read('launch.json')
    calls = read('tool-calls.json')
    read('raw-receipts.json')
    tasks = read('tasks-after.json')
    entry_catalog = None
    if (directory / 'memory-catalog-before.json').is_file():
        entry_catalog = read('memory-catalog-before.json')
    operations = []
    for operation in result['receipt_assessment']['executions']:
        classified = classify_operation(operation['operation_argv'], operation['returncode'],
                                        operation['stdout'], operation['stderr'], before, after)
        key = classified.get('key')
        entry_body = before.get(key)
        returned_entry_body = entry_body is not None and operation['stdout'] == entry_body + '\n'
        if not returned_entry_body:
            try:
                response = json.loads(operation['stdout'])
                returned_entry_body = (entry_body is not None and isinstance(response, dict)
                                       and response.get('value') == entry_body
                                       and response.get('key') == key)
            except ValueError:
                pass
        operations.append({**classified,
                           'argv': operation['operation_argv'],
                           'wall_ns': operation['wall_ns'],
                           'returncode': operation['returncode'],
                           'stdout_visible_somewhere_in_session': operation.get('stdout_visible_somewhere_in_session'),
                           'key_existed_at_entry': key in before,
                           'entry_body_returned': returned_entry_body,
                           'key_was_in_delivered_catalog': bool(entry_catalog and key in entry_catalog['keys'])})
    metadata = {k: result.get(k) for k in (
        'slot', 'profile_id', 'host', 'family', 'corpus_family', 'arm', 'mode', 'stage', 'phase',
        'catalog_mode', 'task_id', 'model_requested', 'models_observed', 'session_id',
        'artifact_passed', 'artifact_correct', 'artifact_total', 'infrastructure_fault',
        'cost_usd', 'usage', 'duration_s', 'host_success', 'exit_code', 'timed_out',
        'task_closed', 'package_changed_paths')}
    return {**metadata,
            'evidence_directory': str(directory.resolve()),
            'input_sha256': hashes,
            'memory_before': before, 'memory_after': after,
            'created': {k: v for k, v in after.items() if k not in before},
            'updated': {k: {'before': before[k], 'after': v} for k, v in after.items() if k in before and before[k] != v},
            'missing_after': {k: v for k, v in before.items() if k not in after},
            'snapshot_counts_match_result': (len(before) == result['memory_before_count'] and len(after) == result['memory_after_count']),
            'catalog_matches_actual_entry_keys': (entry_catalog == {'keys': sorted(before)} if result.get('catalog_mode') == 'indexed' else entry_catalog is None),
            'settings': launch['settings'], 'operations': operations,
            'catalog_related_tool_candidates': [c for c in calls if 'BEADS_MEMORY_INDEX' in json.dumps(c.get('arguments')) or 'memory-catalog.json' in json.dumps(c.get('arguments'))],
            'issue_completion': [t for t in tasks if t.get('id') == result['task_id']],
            'native_files': [str(p.relative_to(directory / 'native-after')) for p in sorted((directory / 'native-after').rglob('*')) if p.is_file() and not p.is_symlink()],
            'manual_review_required': ['agreement fidelity and approval provenance', 'retained-record relevance', 'actual catalog read and reference origin', 'read timing relative to first implementation edit', 'alternative-source retention/use', 'unsupported claims', 'native-memory content and reads', 'duplicate versus genuinely new finding']}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cohort', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--phase', choices=['phase1', 'phase2', 'normal'])
    parser.add_argument('--profile', action='append')
    args = parser.parse_args()
    manifest_bytes = (args.cohort / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    planned = [r for r in manifest['slots'] if (not args.phase or r['phase'] == args.phase) and (not args.profile or r['profile_id'] in args.profile)]
    sessions, pending = [], []
    for row in planned:
        directory = args.cohort / 'cases' / row['lifecycle'] / f"stage-{row['stage']}"
        if (directory / 'result.json').is_file():
            sessions.append(extract(directory))
        else:
            pending.append({'slot': row['slot'], 'claimed': directory.exists()})
    document = {'schema': 'policy-handoff-offline-extraction.v1',
                'manifest_sha256': digest(manifest_bytes), 'extractor_sha256': digest(Path(__file__).read_bytes()),
                'planned': len(planned), 'published': len(sessions), 'pending': pending,
                'limitations': ['Extraction is not semantic grading or proof of model use.',
                                'Catalog exposure differs from catalog reading and full retrieval.',
                                'Successful listing/search is not full record use.',
                                'Entry-body matching excludes readback of a newly created record.',
                                'Native file presence does not demonstrate capture or retrieval.'],
                'sessions': sessions}
    with args.output.open('x') as target:
        json.dump(document, target, indent=2, ensure_ascii=False)
        target.write('\n')
    print(json.dumps({'planned': len(planned), 'published': len(sessions), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
