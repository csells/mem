"""Whole-agent filesystem isolation; all processes are local and provider-free."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from membench.runner.bd_real_runtime import wrap_agent_runner


@pytest.fixture
def runtime(tmp_path):
    root = tmp_path / "pair"
    cwd, config, shim = (root / name for name in ("cwd", "config", "bin"))
    for path in (cwd, config, shim):
        path.mkdir(parents=True)
    return root, cwd, config, shim, tmp_path / "out/runtime.json"


def wrapper(runtime, inner=subprocess.run, **changes):
    root, cwd, config, _, record = runtime
    values = {
        "pair_root": root,
        "cwd": cwd,
        "config_dir": config,
        "agent_python": Path(sys.executable),
        "bd_binary": Path("/usr/bin/true"),
        "record_path": record,
    }
    return wrap_agent_runner(inner, **{**values, **changes})


def kwargs(runtime):
    _, cwd, config, shim, _ = runtime
    return {
        "cwd": str(cwd),
        "env": {"PATH": f"{shim}:/usr/bin:/bin", "CLAUDE_CONFIG_DIR": str(config)},
        "capture_output": True,
        "text": True,
        "timeout": 15,
    }


def test_actual_namespace_masks_host_and_preserves_candidate(runtime, tmp_path):
    root, cwd, _, _, record = runtime
    secret = tmp_path / "withheld-gold.txt"
    secret.write_text("WITHHELD")
    (cwd / "src/codeprobe").mkdir(parents=True)
    (cwd / "src/codeprobe/__init__.py").write_text('SENTINEL = "candidate"\n')
    script = (
        "import os,pathlib,sys,codeprobe; "
        'assert codeprobe.SENTINEL == "candidate"; '
        f"assert not pathlib.Path({str(secret)!r}).exists(); "
        'assert not pathlib.Path("/home/ds/projects/codeprobe/src").exists(); '
        'assert not pathlib.Path("/home/ds/projects/mem/.mem").exists(); '
        'assert not pathlib.Path("/home/ds/projects/mem/memory-bench/data").exists(); '
        'assert len([p for p in pathlib.Path("/proc").iterdir() if p.name.isdigit()]) < 8; '
        'pathlib.Path("written").write_text("ok"); print(codeprobe.__file__)'
    )
    result = wrapper(runtime)([sys.executable, "-c", script], **kwargs(runtime))
    assert result.returncode == 0, result.stderr
    assert str(cwd / "src/codeprobe") in result.stdout
    assert (cwd / "written").read_text() == "ok"
    evidence = json.loads(record.read_text())
    assert evidence["namespace_probe_returncode"] == 0
    assert evidence["argv"][0].endswith("bwrap")
    assert evidence["environment"]["PYTHONPATH"] == str(cwd / "src")
    assert evidence["environment"]["PATH"].split(":")[0] == str(root / "bin")


def test_readonly_platform_and_hidden_hostproc(runtime):
    script = f"""import pathlib
for path in ['/usr/bd-write-probe', '/home/bd-write-probe', '/tmp/bd-write-probe']:
    try:
        pathlib.Path(path).write_text('no')
    except OSError:
        pass
    else:
        raise AssertionError(path)
assert not pathlib.Path('/proc/{os.getpid()}/root').exists()
"""
    result = wrapper(runtime)([sys.executable, "-c", script], **kwargs(runtime))
    assert result.returncode == 0, result.stderr


def test_explicit_lib_layout_imports_candidate_inside_namespace(runtime):
    _, cwd, _, _, record = runtime
    (cwd / "lib/eb_verify").mkdir(parents=True)
    (cwd / "lib/eb_verify/__init__.py").write_text('SOURCE = "candidate"\n')
    result = wrapper(runtime, python_paths=("lib",))(
        [sys.executable, "-c", 'import eb_verify; assert eb_verify.SOURCE == "candidate"'],
        **kwargs(runtime),
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(record.read_text())["environment"]["PYTHONPATH"] == str(cwd / "lib")


@pytest.mark.parametrize("paths", [(), ("/usr",), ("../outside",), ("",), ("lib:/usr",)])
def test_python_import_roots_cannot_escape_candidate(runtime, paths):
    with pytest.raises(ValueError, match="Python import"):
        wrapper(runtime, python_paths=paths)


def test_python_import_root_external_symlink_refused(runtime, tmp_path):
    _, cwd, _, _, _ = runtime
    outside = tmp_path / "outside"
    outside.mkdir()
    (cwd / "lib").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="Python import"):
        wrapper(runtime, python_paths=("lib",))


@pytest.mark.parametrize("key", ["cwd", "config_dir"])
def test_paths_outside_pair_refused(runtime, tmp_path, key):
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError):
        wrapper(runtime, **{key: outside})


def test_bad_interpreter_refused_before_inner(runtime):
    with pytest.raises(ValueError):
        wrapper(runtime, agent_python=Path("/missing/python"))


def test_no_provider_when_namespace_unavailable(runtime, monkeypatch):
    called = []
    run = wrapper(runtime, inner=lambda *a, **k: called.append(True))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1, "", "namespace denied"),
    )
    with pytest.raises(RuntimeError, match="namespace"):
        run([sys.executable, "-c", "pass"], **kwargs(runtime))
    assert not called


def test_no_secret_in_runtime_evidence(runtime):
    options = kwargs(runtime)
    options["env"]["CLAUDE_CODE_OAUTH_TOKEN"] = "do-not-record-this-fixture"
    result = wrapper(runtime)([sys.executable, "-c", "pass"], **options)
    assert result.returncode == 0
    assert "do-not-record-this-fixture" not in runtime[-1].read_text()


def test_real_bd_and_harness_dependencies(runtime):
    bd, dolt = shutil.which("bd"), shutil.which("dolt")
    if not bd or not dolt:
        pytest.skip("local bd/dolt integration dependencies unavailable")
    root, _cwd, _, _, _ = runtime
    store = root / "store"
    store.mkdir()
    script = f"""import subprocess,sys
sys.path.insert(0,{str(Path(__file__).parents[1])!r})
from membench.runner.bd_receipts import wrapper_main
from membench.runner.native_memory_hook import hook_decision
import pytest
bd={bd!r}
subprocess.run(['git','init','--quiet',{str(store)!r}],check=True)
init=subprocess.run([bd,'init','--quiet','--prefix','localtest'],cwd={str(store)!r},capture_output=True,text=True)
assert init.returncode == 0, init.stderr
subprocess.run([bd,'-C',{str(store)!r},'remember',
                'runtime verified fact','--key','runtime-check'],check=True,capture_output=True)
result=subprocess.run([bd,'-C',{str(store)!r},'recall','runtime-check'],check=True,capture_output=True,text=True)
assert 'runtime verified fact' in result.stdout
print('bd-and-hooks-ok')
"""
    result = wrapper(runtime, bd_binary=Path(bd))([sys.executable, "-c", script], **kwargs(runtime))
    assert result.returncode == 0, result.stderr
    assert "bd-and-hooks-ok" in result.stdout


def test_candidate_python_wins_over_ambient_editable_package(runtime):
    python = Path("/home/ds/projects/codeprobe/.venv/bin/python")
    if not python.is_file():
        pytest.skip("CodeProbe dependency venv unavailable")
    _, cwd, _, _, _ = runtime
    (cwd / "src/codeprobe").mkdir(parents=True)
    (cwd / "src/codeprobe/__init__.py").write_text('SENTINEL="candidate"\n')
    script = (
        'python -c \'import codeprobe,pytest; assert codeprobe.SENTINEL=="candidate"; '
        "print(codeprobe.__file__); print(pytest.__file__)'"
    )
    result = wrapper(runtime, agent_python=python)(["/bin/bash", "-c", script], **kwargs(runtime))
    assert result.returncode == 0, result.stderr
    assert str(cwd / "src/codeprobe") in result.stdout
    assert "/codeprobe/.venv/" in result.stdout


@pytest.mark.parametrize("change", [{"env": None}, {"cwd": "/"}, {"env": {"PATH": "/usr/bin"}}])
def test_boundary_arguments_rejected(runtime, change):
    with pytest.raises(ValueError):
        wrapper(runtime)([sys.executable, "-c", "pass"], **{**kwargs(runtime), **change})


def test_missing_bwrap_refused(runtime, monkeypatch):
    original = shutil.which
    monkeypatch.setattr(
        shutil, "which", lambda name, **kw: None if name == "bwrap" else original(name, **kw)
    )
    with pytest.raises(ValueError, match="Bubblewrap"):
        wrapper(runtime)


def test_missing_dolt_refused(runtime, monkeypatch):
    original = shutil.which
    monkeypatch.setattr(
        shutil, "which", lambda name, **kw: None if name == "dolt" else original(name, **kw)
    )
    with pytest.raises(ValueError, match="dolt"):
        wrapper(runtime)([sys.executable, "-c", "pass"], **kwargs(runtime))


def test_shared_tmp_root_cannot_be_mounted(runtime):
    with pytest.raises(ValueError, match="dedicated"):
        wrapper(runtime, pair_root=Path("/tmp"))


def test_temporary_files_stay_inside_pair(runtime):
    script = "import tempfile; f=tempfile.NamedTemporaryFile(); print(f.name)"
    result = wrapper(runtime)([sys.executable, "-c", script], **kwargs(runtime))
    assert result.returncode == 0, result.stderr
    assert str(runtime[0]) in result.stdout


def test_runtime_home_and_temp_are_per_leg_config(runtime):
    result = wrapper(runtime)([sys.executable, "-c", "pass"], **kwargs(runtime))
    assert result.returncode == 0
    env = json.loads(runtime[-1].read_text())["environment"]
    assert Path(env["HOME"]).is_relative_to(runtime[2])
    assert Path(env["TMPDIR"]).is_relative_to(runtime[2])


def test_runtime_record_must_be_external(runtime):
    with pytest.raises(ValueError, match="outside"):
        wrapper(runtime, record_path=runtime[2] / "runtime.json")
    with pytest.raises(ValueError, match="record_path"):
        wrapper(runtime, record_path=None)


def test_resolver_configuration_is_readable_without_host_run_mount(runtime):
    script = (
        "from pathlib import Path; "
        'p=Path("/etc/resolv.conf"); assert p.is_file(); '
        'assert "nameserver" in p.read_text(); '
        'assert not Path("/run/docker.sock").exists(); print(p.resolve())'
    )
    result = wrapper(runtime)([sys.executable, "-c", script], **kwargs(runtime))
    assert result.returncode == 0, result.stderr
    resolved = str(Path("/etc/resolv.conf").resolve())
    evidence = json.loads(runtime[-1].read_text())
    assert any(row["source"] == resolved for row in evidence["readonly_mounts"])
