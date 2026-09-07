"""Exclusive normal-session audit publication with native evidence hashes."""
from pathlib import Path
import hashlib
import json
import runpy
import sqlite3
OUT=Path(__file__).resolve().parent
ROOT=OUT.parent.parent
BASE=runpy.run_path(str(OUT/'audit_io.py'))['save']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(review):
    assert review['lifecycle'].endswith('-normal')
    p=ROOT/'cases'/review['lifecycle']/f"stage-{review['stage']}"
    native=p/'native-after';previous=p.parent/f"stage-{review['stage']-1}"/'native-after'
    current={str(f.relative_to(native)):f for f in native.rglob('*') if f.is_file()}
    before={str(f.relative_to(previous)):f for f in previous.rglob('*') if f.is_file()} if previous.exists() else {}
    dbs=[]
    for name,f in current.items():
        if f.suffix!='.sqlite':continue
        h=sha(f);item={'path':name,'sha256':h,'wal_present':Path(str(f)+'-wal').exists()}
        if not item['wal_present']:
            con=sqlite3.connect(f.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
            names=[x[0] for x in con.execute("SELECT name FROM sqlite_schema WHERE type='table'")]
            item['table_counts']={n:con.execute('SELECT count(*) FROM "'+n.replace('"','""')+'"').fetchone()[0] for n in names}
            con.close()
            assert sha(f)==h
        else:item['content_assessment']='WAL present; not read with immutable SQLite mode.'
        dbs.append(item)
    review['native_snapshot_evidence']={
        'launch_settings':json.loads((p/'launch.json').read_text())['settings'],
        'files':list(current),'new_files':sorted(set(current)-set(before)),
        'changed_files':sorted(n for n in set(current)&set(before) if sha(current[n])!=sha(before[n])),
        'missing_previous_files':sorted(set(before)-set(current)),
        'runtime_databases':dbs,
        'method':'Current archived snapshot compared to predecessor snapshot; no native-before archive exists. Frozen runner copies predecessor native directory before launch. Database inspection mode=ro&immutable=1 only when no WAL exists.',
        'source_sha256':{str(f.relative_to(ROOT)):sha(f) for f in [p/'launch.json',*current.values(),*before.values()]}}
    return BASE(review)
