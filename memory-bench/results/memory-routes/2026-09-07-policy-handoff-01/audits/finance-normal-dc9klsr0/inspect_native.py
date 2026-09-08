"""Read actual native snapshot files only; no model, CLI or mutable SQLite access."""
from pathlib import Path
import json,sqlite3,hashlib
A=Path(__file__).resolve().parent
for p in sorted(A.glob('*.extraction.json')):
 x=json.loads(p.read_text());dest=A/(x['slot']+'.native-inspection.json')
 if dest.exists():continue
 d=Path(x['evidence_directory']);files=[]
 for f in sorted((d/'native-after').rglob('*')):
  if f.is_symlink():files.append({'path':str(f.relative_to(d)),'symlink':True,'contents_not_followed':True});continue
  if not f.is_file():continue
  v={'path':str(f.relative_to(d)),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'size':f.stat().st_size}
  if f.suffix=='.sqlite':
   db=sqlite3.connect(f.as_uri()+'?mode=ro&immutable=1',uri=True);v['sqlite_tables']={}
   for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
    table='"'+name.replace('"','""')+'"';count=db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0];entry={'row_count':count}
    if name in ('stage1_outputs','jobs') and count:
     db.row_factory=sqlite3.Row;entry['rows']=[{k:(value.hex() if isinstance(value,bytes) else value) for k,value in dict(row).items()} for row in db.execute('SELECT * FROM '+table).fetchall()]
    v['sqlite_tables'][name]=entry
   db.close()
  else:
   try:v['text']=f.read_text()
   except UnicodeDecodeError:v['binary_uninterpreted']=True
  files.append(v)
 o={'schema':'finance-normal-native-snapshot.v1','slot':x['slot'],'files':files,'settings':x['settings'],'limit':'Actual copied native-after files inspected; settings or file presence alone do not establish model-visible use. Explicit reads/writes and any automatic generation require trace adjudication. SQLite opened immutable read-only.'}
 with dest.open('x') as out:json.dump(o,out,indent=2)
 print(x['slot'],len(files),'native files')
