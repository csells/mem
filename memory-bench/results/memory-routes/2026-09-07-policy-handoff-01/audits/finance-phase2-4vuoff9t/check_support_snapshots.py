"""Independently compare saved workspace support JSON with the business oracle."""
from pathlib import Path
import hashlib,json,os,stat,time
from review_tools import A,CORPUS,expected_for,strict_equal,no_duplicates,bad_constant
rows=[]
for source in sorted(A.glob('*.extraction.json')):
 if source.name.endswith('.delivery-extraction.json'):continue
 x=json.loads(source.read_text())
 if x.get('stage')!=6:continue
 d=Path(x['evidence_directory']);root=d/'workspace-after';rel=Path('support/MC-406.json');p=root/rel
 row={'slot':x['slot'],'path':str(p),'oracle_source':'review_tools.expected_for; frozen task request plus closed-form allocation','regular_safe_path':False,'exists':p.exists(),'exact_support_artifact_correct':False}
 try:
  if any(q.is_symlink() for q in [root,root/'support',p]):raise ValueError('snapshot path contains symlink')
  fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
  with os.fdopen(fd,'rb') as f:
   if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):raise ValueError('artifact not regular')
   data=f.read()
  row['regular_safe_path']=True;row['sha256']=hashlib.sha256(data).hexdigest()
  obj=json.loads(data,object_pairs_hook=no_duplicates,parse_constant=bad_constant)
  expected=expected_for({'artifact_json_path':str(rel)},x['corpus_family'],6)
  row['exact_support_artifact_correct']=strict_equal(obj,expected)
 except (OSError,ValueError) as e:row['error']=str(e)
 grade=json.loads((d/'artifact-grade.json').read_text());case=next(c for c in grade['cases'] if c['name']=='support_MC_406') if any(c['name']=='support_MC_406' for c in grade['cases']) else grade['cases'][-1]
 row['frozen_grade_case']=case['name'];row['frozen_grade_passed']=case['passed'];row['grade_agrees']=case['passed']==row['exact_support_artifact_correct']
 rows.append(row)
report={'schema':'finance-saved-support-artifacts.v1','method':'Offline read of saved workspace-after support JSON; no model, candidate process, memory CLI or source mutation. Missing file stays failed.','assessed':len(rows),'planned':20,'all_grade_verdicts_agree':all(r['grade_agrees'] for r in rows),'rows':rows}
p=A/f'support-snapshot-check-{time.time_ns()}.json'
with p.open('x') as f:json.dump(report,f,indent=2)
print(p);print(json.dumps({'assessed':len(rows),'all_grade_verdicts_agree':report['all_grade_verdicts_agree']}))
