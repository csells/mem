"""Post-session graders execute candidate code inside an offline namespace."""

from __future__ import annotations

import io
import json
import os
import shutil
import socket
import sys
import tarfile
from pathlib import Path

import pytest

from membench.runner.bd_component_grade import grade_snapshot


@pytest.fixture
def setup(tmp_path):
    assert shutil.which("bwrap") and shutil.which("bd")
    snapshot = tmp_path / "candidate.tar"
    with tarfile.open(snapshot, "w") as archive:
        raw = b"candidate payload"
        info = tarfile.TarInfo("source.txt")
        info.size = len(raw)
        archive.addfile(info, io.BytesIO(raw))
    grader = tmp_path / "grader"
    grader.mkdir()
    return snapshot, grader, Path(sys.executable), Path(shutil.which("bd"))


def test_real_namespace_denies_host_writes_process_and_network(tmp_path, setup, monkeypatch):
    snapshot, grader, python, bd = setup
    secret = tmp_path / "host-secret"
    secret.write_text("hidden gold")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "local-canary-must-not-leak")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    code = f"""import json,os,socket,sys
from pathlib import Path
assert Path(sys.argv[1],'source.txt').read_text()=='candidate payload'
assert not Path({str(secret)!r}).exists()
assert not Path('/proc/{os.getpid()}/root').exists()
assert not any('KEY' in k or 'TOKEN' in k for k in os.environ)
try:
 Path('/tmp/forbidden-host-write').write_text('no')
except OSError: pass
else: raise AssertionError('outside root writable')
try:
 Path(__file__).write_text('no')
except OSError: pass
else: raise AssertionError('grader writable')
s=socket.socket();s.settimeout(.2)
assert s.connect_ex(('127.0.0.1',{port})) != 0
assert len(list(Path('/proc').glob('[0-9]*'))) < 10
print(json.dumps({{'status':'pass','boundary':'checked'}}))
"""
    (grader / "grade.py").write_text(code)
    try:
        result = grade_snapshot(snapshot, grader, python, bd, tmp_path / "out")
    finally:
        listener.close()
    assert result["status"] == "pass" and result["grader"]["boundary"] == "checked"
    evidence = json.loads((tmp_path / "out/runtime.json").read_text())
    assert evidence["network"] == "isolated" and "--share-net" not in evidence["argv"]
    assert "local-canary" not in json.dumps(evidence)


@pytest.mark.parametrize(
    "status,exit_code,expected",
    [
        ("pass", 0, "pass"),
        ("fail", 1, "fail"),
        ("error", 1, "error"),
        ("pass", 1, "error"),
        ("fail", 0, "error"),
        ("other", 0, "error"),
    ],
)
def test_result_exit_contract(tmp_path, setup, status, exit_code, expected):
    snapshot, grader, python, bd = setup
    (grader / "grade.py").write_text(
        f'import json,sys; print(json.dumps({{"status":{status!r}}}));sys.exit({exit_code})'
    )
    assert grade_snapshot(snapshot, grader, python, bd, tmp_path / "out")["status"] == expected


def test_timeout_preserves_partial_output(tmp_path, setup):
    snapshot, grader, python, bd = setup
    (grader / "grade.py").write_text("import time;print('partial',flush=True);time.sleep(30)")
    result = grade_snapshot(snapshot, grader, python, bd, tmp_path / "out", timeout_s=0.2)
    assert result["status"] == "error" and result["error_type"] == "TimeoutExpired"
    assert "partial" in (tmp_path / "out/stdout.txt").read_text()


def test_archive_escape_refused_before_grader(tmp_path, setup):
    snapshot, grader, python, bd = setup
    with tarfile.open(snapshot, "w") as archive:
        info = tarfile.TarInfo("escape")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        archive.addfile(info)
    (grader / "grade.py").write_text("raise AssertionError('must not execute')")
    result = grade_snapshot(snapshot, grader, python, bd, tmp_path / "out")
    assert result["status"] == "error"
    assert not (tmp_path / "out/process.json").exists()


def test_malformed_json_is_infrastructure_error(tmp_path, setup):
    snapshot, grader, python, bd = setup
    (grader / "grade.py").write_text("print('not json')")
    assert grade_snapshot(snapshot, grader, python, bd, tmp_path / "out")["status"] == "error"


def test_output_inside_grader_refused_without_mutation(tmp_path, setup):
    snapshot, grader, python, bd = setup
    (grader / "grade.py").write_text('print(\'{"status":"pass"}\')')
    with pytest.raises(ValueError):
        grade_snapshot(snapshot, grader, python, bd, grader / "unsafe-output")
    assert not (grader / "unsafe-output").exists()


def test_namespace_probe_failure_never_runs_grader(tmp_path, setup, monkeypatch):
    import subprocess

    from membench.runner import bd_component_grade as module

    snapshot, grader, python, bd = setup
    (grader / "grade.py").write_text("raise AssertionError('must not execute')")
    calls = []

    def failure(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1, "", "namespace denied")

    monkeypatch.setattr(module.subprocess, "run", failure)
    result = grade_snapshot(snapshot, grader, python, bd, tmp_path / "out")
    assert result["status"] == "error" and len(calls) == 1
    assert not (tmp_path / "out/process.json").exists()
