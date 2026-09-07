"""Read-only source checks; exclusive per-phase logs and isolated child caches."""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PYTHON = ROOT / '.venv/bin/python'
phase = sys.argv[1]
target = OUT / phase
target.mkdir()
for name in ('tmp', 'cache', 'config'):
    (target / name).mkdir()
env = {key: value for key, value in os.environ.items()
       if key in {'HOME', 'USER', 'LOGNAME', 'SHELL', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TZ', 'TERM', 'USERPROFILE', 'SYSTEMROOT'}}
env.update(PATH=f'{ROOT}/.venv/bin:/usr/bin:/bin:/usr/sbin:/sbin',
           TMPDIR=str(target/'tmp'), TMP=str(target/'tmp'), TEMP=str(target/'tmp'),
           XDG_CONFIG_HOME=str(target/'config'), XDG_CACHE_HOME=str(target/'cache'),
           GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1',
           RUFF_CACHE_DIR=str(target/'cache/ruff'), MYPY_CACHE_DIR=str(target/'cache/mypy'),
           PYTHONDONTWRITEBYTECODE='1')
active = [str(path.relative_to(ROOT)) for pattern in (
    'membench/runner/memory_lifecycle_*.py', 'membench/runner/memory_routes_*.py',
    'scripts/memory_lifecycle_*.py', 'scripts/memory_routes_experiment.py',
    'tests/test_memory_lifecycle_*.py', 'tests/test_memory_routes_*.py')
    for path in sorted(ROOT.glob(pattern)) if 'report' not in path.name]
scripts = [str(path.relative_to(ROOT)) for pattern in (
    'scripts/memory_lifecycle_*.py', 'scripts/memory_routes_experiment.py')
    for path in sorted(ROOT.glob(pattern)) if phase != 'active' or 'report' not in path.name]
tests = sorted({str(path.relative_to(ROOT)) for pattern in (
    'tests/test_memory_routes_*.py', 'tests/test_memory_lifecycle_*.py',
    'tests/test_bd_receipt_surface.py', 'tests/test_native_memory_hook.py',
    'tests/test_bd_real_metrics.py') for path in ROOT.glob(pattern)
    if phase != 'active' or 'report' not in path.name})
def hashes():
    paths = [path for folder in ('membench', 'scripts', 'tests', 'examples')
             for path in (ROOT/folder).rglob('*.py')] + [ROOT/'pyproject.toml']
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)}
def write(name, data):
    with (target/name).open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')
commands = [
    ('ruff', [str(PYTHON), '-m', 'ruff', 'check', *(active if phase == 'active' else ['.'])]),
    ('black', [str(PYTHON), '-m', 'black', '--check', *(active if phase == 'active' else ['.'])]),
    ('mypy', [str(PYTHON), '-m', 'mypy', '--strict', *([p for p in active if p.startswith('membench/')] if phase == 'active' else [])]),
    ('scripts-mypy', [str(PYTHON), '-m', 'mypy', '--strict', '--explicit-package-bases', *scripts]),
    ('pytest', [str(PYTHON), '-m', 'pytest', '-vv', *tests, '--basetemp', str(target/'pytest-temp'),
                '-o', f'cache_dir={target}/cache/pytest', '--junitxml', str(target/'pytest.xml')]),
]
write('scope.json', {'phase': phase, 'test_files': tests, 'script_files': scripts,
                    'python': str(PYTHON), 'path_policy': env['PATH'],
                    'tracked_head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                    'no_model_calls': True, 'source_mutation': False})
results = []
for index, (name, argv) in enumerate(commands, 1):
    before = hashes()
    start = time.monotonic()
    print(f'[{index}/{len(commands)}] START {phase}/{name}', flush=True)
    with (target/f'{name}.log').open('x') as log:
        process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            log.write(line)
            log.flush()
            print(line, end='', flush=True)
        result = process.wait()
    after = hashes()
    row = {'command': argv, 'returncode': result, 'elapsed_s':time.monotonic()-start,
           'source_hashes_before':before, 'source_hashes_after':after,
           'changed_during_check':sorted(p for p in set(before)|set(after) if before.get(p)!=after.get(p))}
    write(name+'.json', row)
    results.append({'gate':name, 'returncode':result, 'elapsed_s':row['elapsed_s'],
                    'changed_during_check':row['changed_during_check']})
    print(f'[{index}/{len(commands)}] END {phase}/{name}: exit {result}',flush=True)
write('results.json', results)
print(f'COMPLETE {phase}: {sum(row["returncode"]==0 for row in results)}/{len(results)} commands passed',flush=True)
sys.exit(int(any(row['returncode'] != 0 for row in results)))
