"""Two authorized neutral Codex smokes; never copies credentials into evidence."""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import tempfile
import time
import tomllib
from pathlib import Path

from membench.runner.memory_routes_runtime import make_profile

OUT=Path(__file__).resolve().parent
ROOT=Path(tempfile.mkdtemp(prefix='memory-host-codex-',dir='/private/tmp')).resolve()
SOURCE_HOME=Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))
CONFIG=tomllib.loads((SOURCE_HOME/'config.toml').read_text())
MODEL=CONFIG['model']
EFFORT=CONFIG['model_reasoning_effort']
TIER=CONFIG.get('service_tier')
BINARY=Path('/opt/homebrew/lib/node_modules/@openai/codex/node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex').resolve()
LAUNCHER=Path('/opt/homebrew/bin/codex').resolve()
PROMPT='In the current directory, use a shell tool to execute /bin/echo CODEX_SMOKE_OK. Create smoke.txt whose exact bytes are codex-smoke-ok followed by one LF newline. Verify the file with a shell command, then reply DONE. Do not inspect files outside this directory.'
AUTH_BYTES=(SOURCE_HOME/'auth.json').read_bytes()
AUTH=json.loads(AUTH_BYTES)
assert AUTH.get('auth_mode')=='chatgpt'
SECRETS=[value for value in AUTH.get('tokens',{}).values() if isinstance(value,str) and len(value)>16]
if AUTH.get('OPENAI_API_KEY'):
    raise RuntimeError('Existing auth includes an API key; refuse ambiguous billing route')


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def clean(text):
    if any(secret in text for secret in SECRETS):
        raise RuntimeError('Credential material found in captured output; evidence copy refused')
    return text


def save(path,value):
    encoded=json.dumps(value,indent=2)+'\n'
    with path.open('x') as stream:stream.write(clean(encoded))


def inventory(path):
    return sorted(str(p.relative_to(path)) for p in path.rglob('*') if p.is_file() and p.name!='auth.json')


def run():
    save(OUT/'manifest.json',{'schema':'memory-host-codex-smoke.v1','scratch':str(ROOT),
         'model':MODEL,'reasoning_effort':EFFORT,'service_tier':TIER,'prompt':PROMPT,
         'planned_model_sessions':2,'native_default':'memories feature off by default; preserve that state',
         'auth':'Existing file-backed ChatGPT auth copied only to private scratch mode0600; no new login or key',
         'binaries':{str(p):digest(p) for p in (BINARY,LAUNCHER)},
         'source_sha256':digest(Path(__file__)),'user_config_sha256':digest(SOURCE_HOME/'config.toml')})
    completed=[]
    for mode in ('isolated','default'):
        evidence=OUT/mode;evidence.mkdir()
        local=ROOT/mode;local.mkdir(mode=0o700)
        for name in ('work','config','tmp','xdg','bin'):(local/name).mkdir(mode=0o700)
        auth=local/'config/auth.json'
        fd=os.open(auth,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(AUTH_BYTES)
        env={k:v for k,v in os.environ.items() if k in ('HOME','USER','LOGNAME','LANG','LC_ALL','LC_CTYPE','TZ','TERM')}
        env.update(CODEX_HOME=str(local/'config'),TMPDIR=str(local/'tmp'),TMP=str(local/'tmp'),TEMP=str(local/'tmp'),
                   XDG_CONFIG_HOME=str(local/'xdg'),XDG_CACHE_HOME=str(local/'xdg/cache'),
                   PATH=str(local/'bin')+':/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',SHELL='/bin/bash',
                   GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_NOSYSTEM='1')
        profile=make_profile(local/'sandbox.sb',[local],[local])
        prefix=['/usr/bin/sandbox-exec','-f',str(profile),str(BINARY)]
        common=['-c','cli_auth_credentials_store="file"','-c','check_for_update_on_startup=false']
        for label,args in (
            ('version',['--version']),
            ('auth',common+['login','status']),
            ('features',common+['features','list']),
        ):
            result=subprocess.run(prefix+args,cwd=local/'work',env=env,capture_output=True,text=True,timeout=30)
            save(evidence/(label+'.json'),{'argv':prefix+args,'returncode':result.returncode,'stdout':clean(result.stdout),'stderr':clean(result.stderr)})
            if result.returncode:raise RuntimeError(f'{mode} {label} preflight failed')
        feature_line=next(line for line in result.stdout.splitlines() if line.split()[0]=='memories')
        assert feature_line.split()[-1]=='false'
        argv=prefix+['-a','never',*common,'exec','--ignore-user-config','--ignore-rules','--skip-git-repo-check',
                     '--sandbox','danger-full-access','--json','--color','never','--model',MODEL,
                     '-c',f'model_reasoning_effort="{EFFORT}"','-c','project_doc_max_bytes=0',
                     '-c','features.skip_host_skill_discovery=true','-c','shell_environment_policy.inherit="all"',
                     '--disable','apps','--disable','plugins','--disable','browser_use','--disable','computer_use',
                     '--disable','multi_agent','--disable','goals','--disable','shell_snapshot']
        if TIER:argv+=['-c',f'service_tier="{TIER}"']
        if mode=='isolated':
            argv+=['--ephemeral','--disable','memories','-c','memories.generate_memories=false','-c','memories.use_memories=false']
        argv+=[PROMPT]
        before=inventory(local/'config')
        save(evidence/'started.json',{'mode':mode,'argv':argv,'scratch':str(local),'config_files_before':before,
                                     'native_feature_before':feature_line,'timeout_s':180})
        start=time.monotonic()
        print('START',mode,MODEL,EFFORT,flush=True)
        with (local/'stream.jsonl').open('x') as stdout,(local/'stderr.txt').open('x') as stderr:
            process=subprocess.Popen(argv,cwd=local/'work',env=env,stdout=stdout,stderr=stderr,text=True,start_new_session=True)
            try:code=process.wait(timeout=180)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
                save(evidence/'halt.json',{'reason':'model_timeout','elapsed_s':time.monotonic()-start})
                raise RuntimeError('Paid smoke interrupted; no retry') from None
        output=clean((local/'stream.jsonl').read_text());stderr_text=clean((local/'stderr.txt').read_text())
        with (evidence/'stream.jsonl').open('x') as stream:stream.write(output)
        with (evidence/'stderr.txt').open('x') as stream:stream.write(stderr_text)
        events=[json.loads(line) for line in output.splitlines() if line.strip()]
        terminal=[event for event in events if event.get('type') in ('turn.completed','turn.failed')]
        artifact=local/'work/smoke.txt'
        valid=artifact.is_file() and artifact.read_bytes()==b'codex-smoke-ok\n'
        summary={'mode':mode,'returncode':code,'duration_s':time.monotonic()-start,'artifact_exact':valid,
                 'event_types':sorted({event.get('type') for event in events}), 'terminal':terminal,
                 'native_files':[p for p in inventory(local/'config') if 'memor' in p],
                 'config_files_after':inventory(local/'config'),'rollout_models':[]}
        for rollout in (local/'config/sessions').rglob('*.jsonl'):
            for line in rollout.read_text().splitlines():
                event=json.loads(line)
                if event.get('type')=='turn_context':
                    p=event['payload'];summary['rollout_models'].append({k:p.get(k) for k in ('model','effort','service_tier')})
        save(evidence/'result.json',summary)
        print('END',mode,'exit',code,'artifact',valid,'events',len(events),flush=True)
        completed.append(summary)
        if code or not valid or len(terminal)!=1 or terminal[0]['type']!='turn.completed':
            raise RuntimeError('Smoke failed; no model fallback or retry')
    unchanged=(SOURCE_HOME/'auth.json').read_bytes()==AUTH_BYTES
    save(OUT/'result.json',{'passed':True,'completed_model_sessions':len(completed),'sessions':completed,'original_auth_bytes_unchanged':unchanged})
    assert unchanged,'Original auth changed concurrently; report rather than restore'


try:run()
except Exception as exc:
    save(OUT/'halt.json',{'type':type(exc).__name__,'message':str(exc),'scratch':str(ROOT)})
    raise
