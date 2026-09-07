"""Close-time checks against public policy, actual state and current-session receipts.

No expected answer enters this module. Wrong but internally consistent facts can pass.
Successful CLI readback is not proof of model-observed delivery or semantic use.
The caller supplies only this session's receipt file; these writable scratch records
are not a security boundary. Only the documented remember/recall forms qualify.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from membench.runner.memory_routes_grade import grade_artifact, grade_capture


def _finished(receipts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    identity = ("invocation_id", "tool_use_id", "session_id", "leg_id")
    for row in receipts:
        if any(not isinstance(row.get(k), str) or not row[k].strip() for k in identity):
            raise ValueError("invalid receipt identity")
        grouped.setdefault(row["invocation_id"], []).append(row)
    finished = []
    contexts = set()
    for pair in grouped.values():
        if len(pair) != 2 or [r.get("event") for r in pair] != ["start", "finish"]:
            raise ValueError("unpaired receipt")
        start, end = pair
        fields = (*identity, "argv", "operation_argv", "start_monotonic_ns")
        if any(start.get(k) != end.get(k) for k in fields):
            raise ValueError("receipt identity mismatch")
        argv, operation = end.get("argv"), end.get("operation_argv")
        if (
            not isinstance(argv, list)
            or len(argv) < 4
            or not all(isinstance(a, str) for a in argv)
            or argv[1] != "-C"
            or not Path(argv[0]).is_absolute()
            or not Path(argv[2]).is_absolute()
            or not isinstance(operation, list)
            or argv[3:] != operation
        ):
            raise ValueError("invalid receipt argv")
        begin, stop = end.get("start_monotonic_ns"), end.get("end_monotonic_ns")
        if type(begin) is not int or type(stop) is not int or begin < 0 or stop < begin:
            raise ValueError("invalid receipt timing")
        if type(end.get("returncode")) is not int:
            raise ValueError("invalid return code")
        for field in ("stdout", "stderr"):
            encoded = end.get(field + "_base64")
            if not isinstance(encoded, str) or not isinstance(end.get(field), str):
                raise ValueError("invalid receipt output")
            if base64.b64decode(encoded, validate=True).decode("utf-8") != end[field]:
                raise ValueError("receipt bytes differ")
        contexts.add((end["session_id"], end["leg_id"], argv[0], argv[2]))
        finished.append(end)
    if len(contexts) > 1:
        raise ValueError("mixed receipt contexts")
    return finished


def _operation(row: dict[str, Any]) -> dict[str, Any] | None:
    args = list(row["operation_argv"])
    structured = "--json" in args
    args = [a for a in args if a not in {"--json", "--sandbox"}]
    if not args or args[0] not in {"remember", "recall"} or row["returncode"] != 0:
        return None
    verb = args.pop(0)
    key = None
    if "--key" in args:
        index = args.index("--key")
        if index + 1 >= len(args):
            return None
        key = args[index + 1]
        del args[index : index + 2]
    if len(args) != 1 or (verb == "recall" and key is not None):
        return None
    if verb == "recall":
        key = args[0]
    if not key or key.startswith("-"):
        return None
    output = row["stdout"]
    acknowledged = True
    if structured:
        try:
            data = json.loads(output)
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        if verb == "remember":
            acknowledged = data.get("key") == key and data.get("action") in {
                "remembered",
                "updated",
            }
            body = args[0]
        else:
            if (
                data.get("key") != key
                or data.get("found") is not True
                or not isinstance(data.get("value"), str)
            ):
                return None
            body = data["value"]
    elif verb == "remember":
        acknowledged = bool(
            re.match(r"^(?:Remembered|Updated) \[" + re.escape(key) + r"\]:", output)
        )
        body = args[0]
    else:
        body = output.rstrip("\r\n")
    return {
        "verb": verb,
        "key": key,
        "body": body,
        "acknowledged": acknowledged,
        "start": row["start_monotonic_ns"],
        "end": row["end_monotonic_ns"],
    }


def evaluate_gate(
    artifact: Path,
    memories: dict[str, str],
    receipts: list[dict[str, Any]],
    required_write_keys: list[str],
    require_read: bool,
    read_matches_artifact: bool = True,
) -> dict[str, Any]:
    """Validate actual artifact, required write/readback, and optional prior recall.

    read_matches_artifact=True accepts any surviving key recalled with this artifact's
    complete JSON. False requires a prior recall of each required key before revision;
    the old configuration need not match the revised artifact. Terminal CR/LF from
    plaintext recall is ignored, but internal/body content is not normalized.
    """
    try:
        if artifact.is_symlink():
            raise ValueError("symlink")
        actual = json.loads(artifact.read_text(encoding="utf-8"))
        if not isinstance(actual, dict) or not grade_artifact(artifact, actual)["passed"]:
            raise ValueError("invalid configuration")
    except (OSError, ValueError):
        return {"passed": False, "reasons": ["invalid_artifact"]}
    try:
        operations = [op for row in _finished(receipts) if (op := _operation(row)) is not None]
    except (ValueError, TypeError):
        return {"passed": False, "reasons": ["invalid_receipts"]}
    reasons = []
    reads = [op for op in operations if op["verb"] == "recall"]
    for key in required_write_keys:
        writes = [op for op in operations if op["verb"] == "remember" and op["key"] == key]
        if not writes:
            reasons.append(f"missing_write:{key}")
            continue
        latest = max(writes, key=lambda op: op["end"])
        if not latest["acknowledged"]:
            reasons.append(f"missing_acknowledgment:{key}")
        body = memories.get(key)
        if body != latest["body"] or grade_capture(memories, key, actual)["passed"] is not True:
            reasons.append(f"saved_body_mismatch:{key}")
        if not any(
            op["key"] == key
            and op["start"] > latest["end"]
            and isinstance(body, str)
            and op["body"].rstrip("\r\n") == body.rstrip("\r\n")
            for op in reads
        ):
            reasons.append(f"missing_readback:{key}")
        if (
            require_read
            and not read_matches_artifact
            and not any(
                op["key"] == key and op["end"] < latest["start"] and op["body"].strip()
                for op in reads
            )
        ):
            reasons.append(f"missing_prior_read:{key}")
    if require_read and read_matches_artifact:
        matching = any(
            op["key"] in memories
            and op["body"].rstrip("\r\n") == memories[op["key"]].rstrip("\r\n")
            and grade_capture(memories, op["key"], actual)["passed"] is True
            for op in reads
        )
        if not matching:
            reasons.append("missing_matching_read")
    elif require_read and not required_write_keys and not any(op["body"].strip() for op in reads):
        reasons.append("missing_read")
    return {"passed": not reasons, "reasons": reasons}
