import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

root = Path('/Users/csells/Code/Forks/sjarmak/mem')
bench = root / 'memory-bench'
out = Path('/tmp/memory-routes-gates.veUGcH')
name = sys.argv[1]
commands = {
    'ruff': [str(bench / '.venv/bin/ruff'), 'check', '.', '--cache-dir', str(out / 'ruff-cache')],
    'black': [str(bench / '.venv/bin/black'), '--check', '.'],
    'mypy': [str(bench / '.venv/bin/mypy'), '--strict', '--cache-dir', str(out / 'mypy-cache')],
    'collect': [str(bench / '.venv/bin/python'), '-m', 'pytest', '--collect-only', '-q', '-o', 'cache_dir=' + str(out / 'pytest-cache')],
    'pytest': [str(bench / '.venv/bin/python'), '-m', 'pytest', '-vv', '-o', 'cache_dir=' + str(out / 'pytest-cache'), '--basetemp', str(out / 'pytest-tmp'), '--junitxml', str(out / 'pytest.xml')],
}
if name not in commands:
    raise SystemExit('unknown gate')
settings = dict(os.environ)
for key in list(settings):
    if key.startswith(('BEADS_', 'BD_', 'DOLT_')) or key in {'ANTHROPIC_API_KEY', 'CLAUDE_CODE_OAUTH_TOKEN', 'OPENAI_API_KEY', 'MEMBENCH_LOCAL_CONTEXT_TEST', 'MEMBENCH_BD_BINARY', 'PYTEST_ADDOPTS'}:
        settings.pop(key)
settings['PATH'] = str(bench / '.venv/bin') + os.pathsep + settings['PATH']
settings['MYPY_CACHE_DIR'] = str(out / 'mypy-cache')
settings['RUFF_CACHE_DIR'] = str(out / 'ruff-cache')
settings['BLACK_CACHE_DIR'] = str(out / 'black-cache')
settings['TMPDIR'] = str(out / 'tmp')
settings['PYTHONUNBUFFERED'] = '1'
Path(settings['TMPDIR']).mkdir(exist_ok=True)
source_files = list((bench / 'membench/runner').glob('memory_routes_*.py')) + list((bench / 'scripts').glob('memory_routes_*.py'))
def hashes():
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files}
start = time.time()
before = hashes()
with (out / (name + '.log')).open('x') as log:
    process = subprocess.Popen(commands[name], cwd=bench, env=settings, stdout=log, stderr=subprocess.STDOUT)
    print(json.dumps({'gate': name, 'pid': process.pid, 'log': str(out / (name + '.log')), 'started': start}), flush=True)
    exit_code = process.wait()
record = {'gate': name, 'argv': commands[name], 'exit_code': exit_code, 'seconds': round(time.time() - start, 3), 'source_hashes_before': before, 'source_hashes_after': hashes()}
with (out / (name + '.json')).open('x') as stream:
    json.dump(record, stream, indent=2)
print(json.dumps(record), flush=True)
raise SystemExit(exit_code)
