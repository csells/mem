"""Summarize explicit eligible-use timing without treating validation as implementation."""
from pathlib import Path
import json,time,hashlib,collections
A=Path(__file__).resolve().parent
P1=A.parent/'finance-phase1-lxa0y1o5/phase1-lifecycles-1788808529862145000.json'
rows=[]
for life in json.loads(P1.read_text())['lifecycles']:
 for stage in (2,4,5):
  slot=life['lifecycle']+'-'+str(stage)
  source=P1 if stage==2 else A/(slot+'.audit.json')
  row={'slot':slot,'stage':stage,'lifecycle':life['lifecycle'],'assessed':source.exists(),'successful_use':None,'timing_category':None}
  if source.exists():
   if stage==2:
    leg=life['retrieval_legs']['2'];correct=leg['artifact_correct'];detail=leg.get('route_detail',{})
    category='pre_product_edit' if leg.get('pre_edit_or_informed_use') is True else None
   else:
    r=json.loads(source.read_text());leg=r['retrieval'];detail=leg
    correct=r['artifact']['correct']==r['artifact']['total']
    t=leg.get('timing_class','')
    category=None
    if t in ('pre_edit','before_product_edit'):category='pre_product_edit'
    elif t in ('no_product_behavior_edit_prior_to_test_edit_and_validation','informed_validation_no_product_edit','no_product_edit_prior_to_validation'):category='before_or_informing_test_or_validation_work'
    elif t=='post_test_source_confirmation_no_product_edit':category='post_test_substantive_source_confirmation'
   success=all(leg.get(k) is True for k in ('applicable_prior_record_at_entry','full_prior_body_read','pre_edit_or_informed_use')) and correct
   if success and category is None:raise ValueError('Unknown successful timing '+slot+': '+str(detail))
   row.update(successful_use=success,timing_category=category if success else None,route=leg.get('route'),timing_evidence=detail,artifact_correct=correct,source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
  rows.append(row)
counts=collections.Counter(r['timing_category'] for r in rows if r['successful_use'])
report={'schema':'finance-eligible-use-timing.v1','planned_eligible_legs':60,'assessed_eligible_legs':sum(r['assessed'] for r in rows),'successful_uses':sum(r['successful_use'] is True for r in rows),'successful_timing_counts':dict(counts),'rows':rows,'limits':['Full applicable record + trace-supported use + correct cumulative artifact required.','Pre-product-edit timing does not establish causal necessity where complete source or original approvals were also available.','Test/validation work and post-test source confirmation are not new feature implementation.','Sonnet occasions5 is post-test confirmation; exact comparison is retained in its dedicated qualification.']}
out=A/f'eligible-use-timing-{time.time_ns()}.json'
with out.open('x') as f:json.dump(report,f,indent=2)
print(out);print(json.dumps({k:v for k,v in report.items() if k not in ('rows','limits')},indent=2))
