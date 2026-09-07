import hashlib,json,os,subprocess,sys,time
from pathlib import Path
root=Path(__file__).resolve().parent
repo=Path('/Users/csells/Code/Forks/sjarmak/mem')
cwd=repo/'memory-bench'
venv=cwd/'.venv/bin'
name=sys.argv[1]
scripts=sorted(str(p.relative_to(cwd)) for p in (cwd/'scripts').glob('memory_routes_*.py'))
tests=sorted(str(p.relative_to(cwd)) for p in (cwd/'tests').glob('test_memory_routes_*.py'))
upstream=['tests/test_audit_bd_actions.py','tests/test_bd_experiment.py','tests/test_bd_receipt_surface.py','tests/test_native_memory_hook.py']
commands={
 'ruff':[str(venv/'ruff'),'check','.', '--cache-dir',str(root/'ruff-cache')],
 'black':[str(venv/'black'),'--check','.'],
 'mypy':[str(venv/'mypy'),'--strict','--cache-dir',str(root/'mypy-cache')],
 'scripts-mypy':[str(venv/'mypy'),'--strict','--explicit-package-bases','--cache-dir',str(root/'scripts-mypy-cache'),*scripts],
 'pytest':[str(venv/'python'),'-m','pytest','-vv','-o','cache_dir='+str(root/'pytest-cache'),'--basetemp',str(root/'pytest-tmp'),'--junitxml',str(root/'pytest.xml'),*tests,*upstream],
}
argv=commands[name]
env={k:v for k,v in os.environ.items() if not k.startswith(('BEADS_','BD_','DOLT_')) and k not in {'ANTHROPIC_API_KEY','CLAUDE_CODE_OAUTH_TOKEN','OPENAI_API_KEY','MEMBENCH_LOCAL_CONTEXT_TEST','MEMBENCH_BD_BINARY','PYTEST_ADDOPTS','PYTHONPATH'}}
env['PATH']=str(venv)+':/usr/bin:/bin:/usr/sbin:/sbin'
env['TMPDIR']=str(root/'scratch')
env['PYTHONUNBUFFERED']='1'
def hashes():
 paths=sorted([*(cwd/'membench/runner').glob('memory_routes_*.py'),*(cwd/'scripts').glob('memory_routes_*.py'),*(cwd/'tests').glob('test_memory_routes_*.py'),*(cwd/p for p in upstream),cwd/'membench/runner/bd_receipt_surface.py',cwd/'membench/runner/native_memory_hook.py'])
 return {str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
metadata={'gate':name,'argv':argv,'cwd':str(cwd),'source_hashes_before':hashes()}
start=time.monotonic()
print(json.dumps({'gate':name,'status':'started','log':str(root/(name+'.log'))}),flush=True)
with (root/(name+'.log')).open('x') as output:
 result=subprocess.run(argv,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT)
metadata.update(exit_code=result.returncode,seconds=round(time.monotonic()-start,3),source_hashes_after=hashes())
with (root/(name+'.json')).open('x') as output: json.dump(metadata,output,indent=2)
print(json.dumps({'gate':name,'exit_code':result.returncode,'seconds':metadata['seconds']}),flush=True)
print('\n'.join((root/(name+'.log')).read_text().splitlines()[-12:]),flush=True)
sys.exit(result.returncode)
