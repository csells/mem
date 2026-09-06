"""Opt-in installed CLI request capture: local stub only, never a provider call.

Run MEMBENCH_LOCAL_CONTEXT_TEST=1 pytest -q tests/test_bd_real_context_delivery.py.
The child environment is replaced, credentials are dummy, and proxies trap external
HTTP(S). Request bodies contain only temporary fixture data and may be archived.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from membench.runner import bd_real_pair as pair
from membench.runner.tool_surface import MemoryToolSurface, provision_memory_tool

pytestmark = pytest.mark.skipif(
    os.environ.get("MEMBENCH_LOCAL_CONTEXT_TEST") != "1", reason="opt-in installed CLI local stub"
)
MODEL = "claude-sonnet-4-6"


def _response(tool_command=None):
    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_local",
                    "type": "message",
                    "role": "assistant",
                    "content": [],
                    "model": MODEL,
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 1, "output_tokens": 0},
                },
            },
        ),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "LOCAL_STUB_OK"},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 1},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    if tool_command is not None:
        events[1] = (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "tool_use",
                    "id": "tool_local_bd",
                    "name": "Bash",
                    "input": {},
                },
            },
        )
        events[2] = (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": json.dumps({"command": tool_command}),
                },
            },
        )
        events[4][1]["delta"]["stop_reason"] = "tool_use"
    return "".join(
        f"event: {name}\ndata: {json.dumps(value)}\n\n" for name, value in events
    ).encode()


def _local_runner(base_url):
    def local_runner(argv, **kwargs):
        assert argv[argv.index("--setting-sources") + 1] == "user"
        assert Path(argv[0]).name == "bwrap"
        env = {
            **{
                key: value
                for key, value in kwargs["env"].items()
                if key
                in (
                    "PATH",
                    "HOME",
                    "PWD",
                    "CLAUDE_CONFIG_DIR",
                    "TMPDIR",
                    "PYTHONPATH",
                    "VIRTUAL_ENV",
                    "PYTHONNOUSERSITE",
                    "PYTHONDONTWRITEBYTECODE",
                )
            },
            "ANTHROPIC_BASE_URL": base_url,
            "ANTHROPIC_API_KEY": "local-stub-dummy-not-a-secret",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "DISABLE_TELEMETRY": "1",
            "DISABLE_ERROR_REPORTING": "1",
            "DISABLE_AUTOUPDATER": "1",
            "HTTP_PROXY": base_url,
            "HTTPS_PROXY": base_url,
            "NO_PROXY": "127.0.0.1,localhost",
        }
        return pair.run_in_session(argv, **{**kwargs, "env": env})

    return local_runner


@pytest.mark.parametrize("condition", ["current", "focused"])
def test_real_leg_delivers_full_assembled_instructions(tmp_path, monkeypatch, condition):
    cli = shutil.which("claude")
    assert cli, "Installed CLI required for opted-in test"
    version = subprocess.check_output([cli, "--version"], text=True).split()[0]
    requests = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            requests.append((self.path, raw))
            data = _response() if self.path.startswith("/v1/messages") else b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    pair_root = tmp_path / "pair-runtime"
    pair_root.mkdir()
    cwd, config, store, bin_dir, home = (
        pair_root / name for name in ("cwd", "config", "store", "bin", "home")
    )
    for path in (cwd, store, bin_dir, home):
        path.mkdir()
    (cwd / "CLAUDE.md").write_text(
        "REPOSITORY_CONTEXT_CANARY_274963: preserve existing contracts.\n"
    )
    surface = MemoryToolSurface(
        store_dir=store,
        bin_dir=bin_dir,
        bd_binary="/usr/bin/true",
        config_dir=config,
        bd_context={"CLAUDE.md": "BD_CONTEXT_CANARY_418592"},
    )
    pair._plant_context(cwd, surface, condition)
    expected = (cwd / "CLAUDE.md").read_text()
    base_url = f"http://127.0.0.1:{server.server_port}"

    local_runner = _local_runner(base_url)

    monkeypatch.setattr(pair, "AGENT_RUNNER", local_runner)
    try:
        record = pair._leg(
            cwd=cwd,
            surface=surface,
            prompt="Reply OK.",
            leg=0,
            out=tmp_path / "leg",
            model=MODEL,
            cli_version=version,
            timeout_s=30,
            pair_root=pair_root,
            agent_python=Path(sys.executable),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    model_requests = [(path, raw) for path, raw in requests if path.startswith("/v1/messages")]
    assert len(requests) == len(model_requests) == 1
    raw = model_requests[0][1]
    (tmp_path / "request.json").write_bytes(raw)
    body = json.loads(raw)
    supplied = json.dumps(
        {"system": body.get("system"), "messages": body.get("messages")}, ensure_ascii=False
    )
    # Compare decoded block text, so JSON serialization escaping cannot hide a missing byte.
    texts = [block.get("text", "") for block in body.get("system", []) if isinstance(block, dict)]
    for message in body.get("messages", []):
        texts.extend(
            block.get("text", "") for block in message.get("content", []) if isinstance(block, dict)
        )
    observed = any(expected in text for text in texts)
    (tmp_path / "request-summary.json").write_text(
        json.dumps(
            {
                "cli_version": version,
                "condition": condition,
                "setting_sources": "user",
                "request_sha256": hashlib.sha256(raw).hexdigest(),
                "system_messages_sha256": hashlib.sha256(supplied.encode()).hexdigest(),
                "instructions_sha256": hashlib.sha256(expected.encode()).hexdigest(),
                "full_instructions_delivered": observed,
                "status": record["status"],
            },
            indent=2,
        )
        + "\n"
    )
    assert (
        observed
    ), "Full assembled condition and repository instructions absent from actual request"
    assert sum(text.count(expected) for text in texts) == 1, "Instructions delivered more than once"
    assert record["status"] == "ok" and not record["integrity_errors"]
    assert (tmp_path / "leg/runtime.json").is_file()
    assert Path(json.loads((tmp_path / "leg/argv.json").read_text())[0]).name == "bwrap"
    assert not (tmp_path / "leg").is_relative_to(pair_root)


def test_real_cli_bd_receipts_inside_runtime(tmp_path, monkeypatch):
    cli = shutil.which("claude")
    assert cli
    version = subprocess.check_output([cli, "--version"], text=True).split()[0]
    requests = []
    command = (
        'bd remember "LOCAL_BD_RUNTIME_FACT_591842" --key local-runtime-proof '
        "&& bd recall local-runtime-proof"
    )

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            requests.append((self.path, raw))
            model_calls = sum(path.startswith("/v1/messages") for path, _ in requests)
            data = _response(command if model_calls == 1 else None)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    pair_root = tmp_path / "pair-runtime"
    cwd = pair_root / "workspace"
    cwd.mkdir(parents=True)
    surface = provision_memory_tool(pair_root / "memory", sandbox=cwd)
    from dataclasses import replace

    surface = replace(surface, config_dir=pair_root / "memory/config")
    pair._plant_context(cwd, surface, "current")
    monkeypatch.setattr(
        pair, "AGENT_RUNNER", _local_runner(f"http://127.0.0.1:{server.server_port}")
    )
    try:
        record = pair._leg(
            cwd=cwd,
            pair_root=pair_root,
            agent_python=Path(sys.executable),
            surface=surface,
            prompt="Save and recall the fixture fact.",
            leg=0,
            out=tmp_path / "leg",
            model=MODEL,
            cli_version=version,
            timeout_s=45,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert len(requests) == 2
    assert all(path.startswith("/v1/messages") for path, _ in requests)
    assert record["memory"]["accepted_writes"] == 1
    assert record["memory"]["observed_content_reads"] == 1
    receipts = json.loads((tmp_path / "leg/receipts.json").read_text())
    finished = [row for row in receipts if row.get("event") == "finish"]
    assert len(finished) == 2 and all(row["returncode"] == 0 for row in finished)
    assert "LOCAL_BD_RUNTIME_FACT_591842" in requests[1][1].decode()
    assert Path(json.loads((tmp_path / "leg/argv.json").read_text())[0]).name == "bwrap"
