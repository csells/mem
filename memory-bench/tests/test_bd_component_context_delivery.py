"""Opt-in single-session CLI verification against localhost, with dummy credentials."""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from membench.runner import bd_real_pair as pair
from tests.test_bd_real_context_delivery import MODEL, _local_runner, _response

pytestmark = pytest.mark.skipif(
    os.environ.get("MEMBENCH_LOCAL_CONTEXT_TEST") != "1", reason="opt-in installed CLI local stub"
)
PARENT = "5b76bae6700ee3353b134e8ddfcc96d5807bdbe7"
SEED = "LOCAL_COMPONENT_SEED_942671"
WRITTEN = "LOCAL_COMPONENT_AGENT_WRITE_693247"


def _artifact(root: Path, name: str, content: str) -> dict[str, str]:
    (root / name).write_text(content)
    return {"path": name, "sha256": hashlib.sha256(content.encode()).hexdigest()}


def _spec(root: Path, version: str) -> tuple[dict, dict]:
    root.mkdir()
    row = {
        "row_id": "local-seeded-retrieval",
        "component": "retrieval",
        "intervention": "optional",
        "condition": "focused",
        "initial_store": "seeded",
        "prompt": _artifact(root, "prompt.md", "Review the fixture and reply OK.\n"),
        "sources": [],
        "seed": _artifact(root, "seed.txt", SEED),
    }
    configuration = {
        "input_root": str(root),
        "repo_absolute": "/home/ds/projects/EnterpriseBench",
        "base_commit": PARENT,
        "agent_python": sys.executable,
        "python_paths": ["lib"],
        "bd_binary": shutil.which("bd"),
        "model": MODEL,
        "cli_version": version,
        "timeout_s": 45,
        "seed_key": "local-component-seed",
    }
    return row, configuration


def _tool_command() -> str:
    probe = """from pathlib import Path
import eb_verify.task_parser as parser
assert Path(parser.__file__).resolve().is_relative_to(Path.cwd() / 'lib')
hidden = ['/home/ds/projects/EnterpriseBench/lib/eb_verify/task_parser.py',
          '/home/ds/projects/mem/memory-bench/results/bd-source-curation-20260905']
for name in hidden:
    assert not Path(name).exists(), name
    assert not Path('/proc/1/root' + name).exists(), name
try:
    Path('/tmp/component-outside-write').write_text('must be denied')
except OSError:
    pass
else:
    raise AssertionError('outside-root write succeeded')
print('COMPONENT_BOUNDARY_OK')
"""
    return (
        "bd recall local-component-seed && "
        f"bd remember {shlex.quote(WRITTEN)} --key local-component-agent && "
        "bd recall local-component-agent && "
        f"python -c {shlex.quote(probe)}"
    )


def _server(requests: list) -> tuple[http.server.ThreadingHTTPServer, threading.Thread]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            requests.append((self.path, raw))
            calls = sum(path.startswith("/v1/messages") for path, _ in requests)
            data = _response(_tool_command() if calls == 1 else None)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _texts(body: dict) -> list[str]:
    blocks = list(body.get("system", []))
    for message in body.get("messages", []):
        blocks.extend(message.get("content", []))
    return [block.get("text", "") for block in blocks if isinstance(block, dict)]


def _verify(out: Path, record: dict, requests: list) -> None:
    assert record["component"] == "retrieval"
    assert record["status"] == "completed"
    agent = record["agent"]
    assert agent["status"] == "ok" and not agent["integrity_errors"]
    assert agent["memory"]["accepted_writes"] == 1
    assert agent["memory"]["observed_content_reads"] == 2
    assert not agent["memory"]["evidence_unknown"]
    assert len(requests) == 2
    assert all(path.startswith("/v1/messages") for path, _ in requests)
    for index, (_, raw) in enumerate(requests):
        (out / f"local-request-{index}.json").write_bytes(raw)
    expected = (out / "leg-0/instructions.md").read_text()
    assert pair.FOCUSED_PROTOCOL in expected
    texts = _texts(json.loads(requests[0][1]))
    # CLI 2.1.261 removes HTML comments and whitespace immediately following them.
    # Preserve every other byte, including internal and preceding whitespace.
    visible = re.sub(r"<!--[\s\S]*?-->\s*", "", expected)
    assert sum(text.count(visible) for text in texts) == 1
    delivered = requests[1][1].decode()
    assert all(text in delivered for text in (SEED, WRITTEN, "COMPONENT_BOUNDARY_OK"))
    receipts = json.loads((out / "leg-0/receipts.json").read_text())
    finished = [row for row in receipts if row.get("event") == "finish"]
    assert [row["operation_argv"][0] for row in finished] == ["recall", "remember", "recall"]
    assert all(row["returncode"] == 0 for row in finished)
    assert Path(json.loads((out / "leg-0/argv.json").read_text())[0]).name == "bwrap"
    assert (out / "leg-0/runtime.json").is_file()


def test_component_cli_seed_receipts_instructions_and_boundary(tmp_path, monkeypatch):
    from membench.runner.bd_component_session import run_component_session

    cli = shutil.which("claude")
    assert cli
    version = subprocess.check_output([cli, "--version"], text=True).split()[0]
    row, configuration = _spec(tmp_path / "inputs", version)
    requests = []
    server, thread = _server(requests)
    monkeypatch.setattr(
        pair, "AGENT_RUNNER", _local_runner(f"http://127.0.0.1:{server.server_port}")
    )
    out = tmp_path / "run"
    try:
        record = run_component_session(row, configuration, out)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    _verify(out, record, requests)
