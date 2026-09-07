"""Append native snapshot metadata and observed native read calls, never execute candidates."""
import json,hashlib,sys
from pathlib import Path
from datetime import datetime,timezone
O=Path(__file__).resolve().parent;R=O.parents[1]
for slot in sys.argv[1:]:
 lifecycle,n=slot.rsplit('-',1);n=int(n);p=R/'cases'/lifecycle/f'stage-{n}'
 launch=json.loads((p/'launch.json').read_text());calls=json.loads((p/'tool-calls.json').read_text());r=json.loads((p/'result.json').read_text())
 def files(folder):
  return {str(f.relative_to(folder)):{'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in folder.rglob('*') if f.is_file() and not f.is_symlink()}
 before=files(p.parent/f'stage-{n-1}'/'native-after') if n>1 else {};after=files(p/'native-after')
 native_calls=[]
 for i,c in enumerate(calls):
  a=json.dumps(c.get('arguments',{}))
  if any(w in a for w in ['/native/','ZCODE_STORAGE_DIR','model-io-sess_','cli/rollout','memory_search','memory_read']):native_calls.append({'tool_index':i,'name':c['name'],'arguments':c.get('arguments',{}),'result_sha256':hashlib.sha256(str(c.get('result','')).encode()).hexdigest()})
 doc={'schema':'offline-normal-native-observation.v1','created_utc':datetime.now(timezone.utc).isoformat(),'slot':slot,'host':r['host'],'mode':r['mode'],'public_settings':launch['settings'],'previous_snapshot_files':before,'after_snapshot_files':after,'previous_snapshot_is_proxy_for_carried_start_state':True,'changed_native_paths':[s for s in sorted(set(before)|set(after)) if before.get(s)!=after.get(s)],'observed_native_path_or_tool_calls':native_calls,'interpretation':'Metadata inventory only. Rollout logs, shell startup scripts, tool artifacts and marketplace cache files are not classified as extracted memory records. No observed path read is not proof against implicit host context; disclosed profile/extraction limits remain applicable. Beads record captures are audited separately.','host_success':r['host_success'],'host_errors':r['errors'],'infrastructure_fault':r['infrastructure_fault'],'input_sha256':{str(f.relative_to(R)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [p/'result.json',p/'launch.json',p/'tool-calls.json']},'model_calls_by_auditor':0}
 with (O/(slot+'-native.json')).open('x') as f:json.dump(doc,f,indent=2);f.write('\n')
 print('NATIVE '+slot+' '+str(len(after))+' files, '+str(len(native_calls))+' observed path/tool calls')
