"""Public-input completion checks for the isolated lifecycle experiment.

These checks wrap task closure and the host's Stop event. They do not gate every
side effect, classify durable knowledge autonomously, or defend against an agent
editing its instrumentation. Administrative reads are logged separately from
agent-executed memory operations. No hidden oracle is accepted by this module.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from membench.runner.bd_receipts import append_record, wrapper_main
from membench.runner.memory_lifecycle_gate import evaluate_gate

SPEC_KEYS = frozenset(
    {
        "binary",
        "store",
        "artifact",
        "receipts",
        "events",
        "task_id",
        "required_write_keys",
        "require_read",
        "read_matches_artifact",
    }
)


def load_spec(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.keys() != SPEC_KEYS:
        raise ValueError("Completion check accepts only its public policy and runtime paths")
    if not all(
        isinstance(value[key], str) and value[key]
        for key in SPEC_KEYS - {"required_write_keys", "require_read", "read_matches_artifact"}
    ):
        raise ValueError("Invalid completion-check runtime identity")
    if any(type(value[key]) is not bool for key in ("require_read", "read_matches_artifact")):
        raise ValueError("Invalid completion-check read policy")
    keys = value["required_write_keys"]
    if not isinstance(keys, list) or any(not isinstance(key, str) or not key for key in keys):
        raise ValueError("Invalid required memory references")
    return value


def _query(spec: dict[str, Any], args: list[str]) -> Any:
    result = subprocess.run(
        [spec["binary"], "-C", spec["store"], *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Completion check could not inspect bd: {result.stderr[-1000:]}")
    return json.loads(result.stdout)


def check(spec: dict[str, Any], *, event: str, require_closed: bool) -> dict[str, Any]:
    start = time.monotonic()
    state = _query(spec, ["memories", "--json"])
    if not isinstance(state, dict) or state.pop("schema_version", None) != 1:
        raise ValueError("Unexpected memory snapshot schema")
    if any(not isinstance(value, str) for value in state.values()):
        raise ValueError("Unexpected memory snapshot body")
    receipt_path = Path(spec["receipts"])
    receipts = (
        [json.loads(line) for line in receipt_path.read_text().splitlines()]
        if (receipt_path.exists())
        else []
    )
    verdict = evaluate_gate(
        Path(spec["artifact"]),
        state,
        receipts,
        spec["required_write_keys"],
        spec["require_read"],
        spec["read_matches_artifact"],
    )
    query_count = 1
    if require_closed:
        task = _query(spec, ["show", spec["task_id"], "--json"])
        query_count += 1
        if not isinstance(task, list) or len(task) != 1 or task[0].get("status") != "closed":
            verdict["reasons"].append("assigned_task_not_closed")
            verdict["passed"] = False
    append_record(
        Path(spec["events"]),
        {
            "event": event,
            **verdict,
            "duration_s": time.monotonic() - start,
            "administrative_bd_queries": query_count,
            "tool_use_id": os.environ.get("MEMBENCH_BD_TOOL_USE_ID"),
            "session_id": os.environ.get("MEMBENCH_BD_SESSION_ID"),
            "leg_id": os.environ.get("MEMBENCH_BD_LEG_ID"),
        },
    )
    return verdict


def closing(argv: list[str]) -> bool:
    if "--help" in argv or "-h" in argv:
        return False
    if "close" in argv:
        return True
    return "update" in argv and (
        "--status=closed" in argv
        or any(argv[i : i + 2] == ["--status", "closed"] for i in range(len(argv) - 1))
    )


def cli_main(spec_path: str) -> int:
    spec = load_spec(Path(spec_path))
    if closing(sys.argv[1:]):
        verdict = check(spec, event="close", require_closed=False)
        if not verdict["passed"]:
            print(
                "Task completion needs attention: " + "; ".join(verdict["reasons"]), file=sys.stderr
            )
            return 2
    return wrapper_main(binary=spec["binary"], store=spec["store"], receipt_path=spec["receipts"])


def stop_main(spec_path: str) -> None:
    event = json.load(sys.stdin)
    if event.get("hook_event_name") != "Stop":
        raise ValueError("Expected Stop event")
    spec = load_spec(Path(spec_path))
    try:
        verdict = check(spec, event="stop", require_closed=True)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        append_record(
            Path(spec["events"]),
            {
                "event": "stop",
                "passed": False,
                "infrastructure_error": type(exc).__name__,
                "reasons": [str(exc)],
            },
        )
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": "The completion check could not " "inspect this task: " + str(exc),
                }
            )
        )
        return
    if verdict["passed"]:
        print("{}")
    else:
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": "Complete the assigned task's public handoff requirements: "
                    + "; ".join(verdict["reasons"]),
                }
            )
        )
