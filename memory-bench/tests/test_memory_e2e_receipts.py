"""Receipt execution proof survives ordinary subprocess capture without fake reads."""

import json
import os
import subprocess
import sys

from membench.runner import memory_e2e_receipts as receipts


def test_kernel_metadata_matches_current_parent():
    assert receipts.parent_pid(os.getpid()) == os.getppid()


def test_global_options_do_not_hide_reads_or_allow_store_redirection():
    assert receipts.command_name(["--json", "recall", "key"]) == "recall"
    assert receipts.command_name(["--actor", "memories", "--json", "recall", "key"]) == "recall"
    assert receipts.command_name(["--unknown", "recall", "key"]) is None
    for argv in (
        ["-C/elsewhere", "recall", "key"],
        ["recall", "key", "--db=x"],
        ["--database", "different", "recall", "key"],
        ["--global", "memories"],
    ):
        assert receipts.routing_override(argv)
    assert not receipts.routing_override(["remember", "project fact", "--key", "project.note"])


def test_python_capture_gets_clean_json_and_retains_execution(tmp_path):
    binary = tmp_path / "real-bd"
    binary.write_text('#!/bin/sh\nprintf \'{"answer":"saved agreement"}\\n\'\n')
    binary.chmod(0o700)
    store = tmp_path / "store"
    store.mkdir()
    log, shim = receipts.prepare(
        tmp_path / "bin", store, "direct", "session-a", binary=binary, python=sys.executable
    )
    program = (
        "import subprocess,json,sys; "
        "p=subprocess.run([sys.argv[1],'recall','chosen'],capture_output=True,text=True); "
        "assert json.loads(p.stdout)['answer']=='saved agreement'; "
        "assert p.stderr==''; print('consumed without forwarding')"
    )
    result = subprocess.run(
        [sys.executable, "-c", program, str(shim)], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "consumed without forwarding"
    rows = receipts.read(log)
    score = receipts.assess(
        rows,
        root_pid=os.getpid(),
        leg="direct",
        session="session-a",
        tool_outputs=[result.stdout],
        binary=str(binary),
        store=str(store),
    )
    assert score["agent_reads"] == 1
    assert score["stdout_visible_in_session"] == 0
    assert score["unknown_execution"] == 0
    assert json.loads(rows[-1]["stdout"])["answer"] == "saved agreement"
    forged = receipts.assess(
        rows,
        root_pid=999999999,
        leg="direct",
        session="session-a",
        tool_outputs=[],
        binary=str(binary),
        store=str(store),
    )
    assert forged["agent_reads"] == 0 and forged["unknown_execution"] == 1


def test_failed_command_and_wrong_session_cannot_be_accepted(tmp_path):
    row = {
        "event": "finish",
        "invocation_id": "x",
        "leg": "direct",
        "session": "s",
        "ancestors": [os.getpid()],
        "returncode": 9,
        "operation_argv": ["remember", "x"],
        "stdout": "",
        "binary": "/bd",
        "store": "/store",
    }
    score = receipts.assess(
        [row],
        root_pid=os.getpid(),
        leg="direct",
        session="s",
        tool_outputs=[],
        binary="/bd",
        store="/store",
    )
    assert score["agent_writes"] == 0 and score["unknown_execution"] == 1
