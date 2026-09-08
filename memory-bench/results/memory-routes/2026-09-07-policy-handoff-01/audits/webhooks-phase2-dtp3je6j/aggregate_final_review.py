"""Aggregate completed manual semantic reviews; no model calls or candidate execution."""
import json
import hashlib
from pathlib import Path

A = Path(__file__).resolve().parent
R = A.parents[1]
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def summarize(rows):
    legs = [(d, stage, leg) for d in rows for stage, leg in d['retrieval_legs'].items()]
    def leg_summary(items):
        return {
            'planned_legs': len(items),
            'applicable_prior_at_entry': sum(x.get('applicable_prior_record_at_entry') is True for x in items),
            'complete_agreement_at_entry': sum(x.get('complete_required_agreement_at_entry', x.get('complete_required_provider_agreement_at_entry')) is True for x in items),
            'full_prior_body_delivered': sum(x.get('full_prior_body_read') is True for x in items),
            'full_applicable_body_delivered': sum(x.get('full_prior_body_read') is True and x.get('applicable_prior_record_at_entry') is True for x in items),
            'pre_edit_or_informed_use': sum(x.get('pre_edit_or_informed_use') is True for x in items),
            'successful_use': sum(x.get('successful_use', x.get('successful_prior_record_use')) is True for x in items),
            'full_body_routes': {route: sum(x.get('full_prior_body_read') is True and x.get('route') == route for x in items) for route in ['direct', 'search', 'none']},
            'successful_use_routes': {route: sum(x.get('successful_use', x.get('successful_prior_record_use')) is True and x.get('route') == route for x in items) for route in ['direct', 'search', 'none']},
        }
    return {
        'lifecycles': len(rows),
        'initial_capture_faithful': sum(d['initial_capture_faithful'] is True for d in rows),
        'current_and_historical_faithful': {stage: sum(d['current_and_historical_faithful'][stage] is True for d in rows) for stage in ['3', '5', '6']},
        'all_six_artifacts': sum(d['all_six_artifacts'] for d in rows),
        'artifact_sessions': sum(x['passed'] for d in rows for x in d['artifact_results']),
        'cases_correct': sum(x['correct'] for d in rows for x in d['artifact_results']),
        'cases_total': sum(x['total'] for d in rows for x in d['artifact_results']),
        'retrieval': leg_summary([x for _, _, x in legs]),
        'retrieval_by_stage': {s: leg_summary([x for _, stage, x in legs if stage == s]) for s in ['2', '4', '5']},
        'unsupported_standing_or_historical_mutation': sum(d['unsupported_standing_or_historical_mutation'] is True for d in rows),
        'stage6_duplicate_curation': sum(d['stage6_duplicate_curation'] is True for d in rows),
        'stage6_evidenced_new_finding': sum(d['stage6_evidenced_new_finding'] is True for d in rows),
        'strict_six_stage_intersection': {s: sum(d['strict_six_stage_intersection']['status'] == s for d in rows) for s in ['true', 'false', 'unverified']},
    }

if __name__ == '__main__':
    paths = sorted((A / 'lifecycles-final-v2').glob('*.json'))
    rows = [read(p) for p in paths]
    details = sorted(A.glob('*-isolated-[3456].json'))
    assert len(rows) == 20 and len(details) == 80, (len(rows), len(details))
    results = [read(p) for p in details]
    disagreements = [d['slot'] for d in results if d['saved_output_oracle_recheck']['classification_disagreements']]
    assert not disagreements, disagreements
    controls = [{
        'slot': d['slot'],
        'attachment_correct': next(x['independently_passed'] for x in d['saved_output_oracle_recheck']['observations'] if x['name'] == 'support_attachment'),
        'whole_artifact_correct': d['metadata']['artifact_passed'],
        'product_code_changed': d['findings'].get('product_code_changed'),
        'control': d['findings']['control'],
    } for d in results if d['metadata']['stage'] == 6]
    output = {
        'method': 'Mechanical counts over manual semantic judgments, with independent saved-output JSON/oracle checks; no candidate reruns.',
        'overall': summarize(rows),
        'by_arm': {arm: summarize([d for d in rows if d['arm'] == arm]) for arm in sorted({d['arm'] for d in rows})},
        'by_profile': {profile: summarize([d for d in rows if d['profile_id'] == profile]) for profile in sorted({d['profile_id'] for d in rows})},
        'by_profile_arm': {d['lifecycle']: summarize([d]) for d in rows},
        'stage6_controls': controls,
        'saved_output_classification_disagreements': disagreements,
        'final_lifecycle_hashes': {str(p.relative_to(R)): sha(p) for p in paths},
        'detail_hashes': {str(p.relative_to(R)): sha(p) for p in details},
        'interpretation_files': {str(p.relative_to(R)): sha(p) for p in [A/'initial-capture-trigger-interpretation.json', A/'glm-generic-engineering-convention-supplement.json', A/'reviewer-authorship-scope-clarification.json']},
        'limits': [
            'Initial provider1 contract was already durable in starter docs; target capture omission alone is not proof of rule disobedience.',
            'Full related-body delivery and applicable complete agreement delivery are separate; an inaccurate conflicting record can be read without being a faithful governing agreement.',
            'Correct artifact plus prior-body timing supports observed use, not exclusive causal attribution; alternate sources and correct inherited code remained available.',
            'Some historical legs validate already implemented behavior after body delivery; these are informed validation, not pre-implementation reads.',
            'Partial readback is not full record verification, even where stored body independently preserves all facts.',
            'Implementation regressions, unsupported provenance/verification claims, and stored-policy mutation are separately described in detailed reviews.',
            'No duplicate capture does not imply no memory-related tool attempts, catalog reads, or optional prior recall.',
            'Reviewers are unblinded agents; Courier reviewer independently cross-reviewed the root-authored current corpus and audited outputs.',
        ],
    }
    with (A/'WEBHOOKS-FINAL-AGGREGATE.json').open('x') as out:
        json.dump(output, out, indent=2, ensure_ascii=False)
    print(json.dumps(output['overall'], indent=2))
