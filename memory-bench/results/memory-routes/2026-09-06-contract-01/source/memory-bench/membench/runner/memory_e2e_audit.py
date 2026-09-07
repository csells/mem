"""Posthoc CLI-action audit; never changes frozen assessments or executes tools.

Recognizes a bounded subset of Beads 1.2.1's Cobra/pflag arguments and its actual
response formats. Unsupported options/short-option clusters remain unknown.
Shell quoting is already removed in receipt argv; string-option values and the
``--`` terminator still distinguish literal '--help' from the boolean help flag.
This is execution accounting, not a new artifact, capture, or model-use oracle.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

_BOOL_FLAGS = {
    "--json",
    "--no-color",
    "--readonly",
    "--sandbox",
    "-q",
    "--quiet",
    "-v",
    "--verbose",
    "--help",
    "-h",
}
_VALUE_FLAGS = {"--actor", "--format", "--dolt-auto-commit", "--mem-profile"}
_BOOLEANS = {
    "1": True,
    "t": True,
    "T": True,
    "true": True,
    "TRUE": True,
    "True": True,
    "0": False,
    "f": False,
    "F": False,
    "false": False,
    "FALSE": False,
    "False": False,
}
_INPUTS = (
    "execution.json",
    "raw-receipts.json",
    "memory-before.json",
    "memory-after.json",
    "process.json",
    "launch.json",
)


def _parse(argv: list[str]) -> tuple[str, list[str], dict[str, str], bool] | None:
    command = ""
    positional: list[str] = []
    values: dict[str, str] = {}
    help_requested = False
    index = 0
    while index < len(argv):
        arg = argv[index]
        index += 1
        if arg == "--":
            if not command:
                return None
            positional.extend(argv[index:])
            break
        if not arg.startswith("-") or arg == "-":
            if not command:
                command = arg
            else:
                positional.append(arg)
            continue
        flag, separator, value = arg.partition("=")
        if flag in _BOOL_FLAGS or (
            command == "prime" and flag in {"--no-memories", "--memories-only"}
        ):
            boolean = _BOOLEANS.get(value) if separator else True
            if boolean is None:
                return None
            if flag in {"--help", "-h"}:
                help_requested = boolean
            values[flag] = "true" if boolean else "false"
        elif flag in _VALUE_FLAGS or (flag == "--key" and command == "remember"):
            if not separator:
                if index == len(argv):
                    return None
                value = argv[index]
                index += 1
            values[flag] = value
        else:
            if command and command not in {"remember", "recall", "memories", "forget", "prime"}:
                return command, positional, values, False
            return None
    return (command, positional, values, help_requested) if command else None


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _response(stdout: str) -> dict[str, Any] | None:
    try:
        value = json.loads(stdout, object_pairs_hook=_object)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def classify_operation(
    argv: list[str],
    returncode: int,
    stdout: str,
    stderr: str,
    before: dict[str, str],
    after: dict[str, str],
) -> dict[str, Any]:
    """Classify a validated execution, using no hidden expected agreement."""
    if type(returncode) is not int:
        return {"action": "unknown", "reason": "invalid_returncode"}
    if returncode != 0:
        return {"action": "failed", "reason": "nonzero_returncode"}
    parsed = _parse(argv)
    if parsed is None:
        return {"action": "unknown", "reason": "unsupported_arguments"}
    command, args, options, help_requested = parsed
    unknown = {"action": "unknown", "reason": "unrecognized_response_or_semantics"}
    if help_requested or command == "help":
        if re.search(r"(?m)^Usage:\r?\n[ \t]+bd(?:[ \t\r\n]|$)", stdout):
            return {"action": "help", "reason": "parsed_help_and_cli_usage_response"}
        return unknown
    if command == "prime":
        return {"action": "prime", "reason": "successful_prime"}
    if command not in {"remember", "recall", "memories", "forget"}:
        return {"action": "other", "reason": "nonmemory_command"}
    json_requested = options.get("--json") == "true" or options.get("--format") == "json"
    response = _response(stdout) if json_requested else None
    if (
        response is not None
        and "schema_version" in response
        and (type(response["schema_version"]) is not int or response["schema_version"] != 1)
    ):
        return unknown
    if command == "remember":
        if len(args) != 1:
            return unknown
        content = args[0]
        key = options.get("--key", "")
        if not key and response is not None and response.get("action") == "recalled":
            if (
                response.get("key") == content
                and response.get("found") is True
                and isinstance(response.get("value"), str)
            ):
                return {"action": "recall", "key": content, "reason": "cli_recalled_action"}
            return unknown
        if not key and stderr.startswith(f'(recalled "{content}" -- a bare existing key READS.'):
            if any(
                memory.get(content) is not None and stdout == memory[content] + "\n"
                for memory in (before, after)
            ):
                return {
                    "action": "recall",
                    "key": content,
                    "reason": "cli_bare_key_recall_response",
                }
            return unknown
        if response is not None:
            actual_key = response.get("key")
            accepted = (
                response.get("action") in {"remembered", "updated"}
                and isinstance(actual_key, str)
                and bool(actual_key)
                and (not key or actual_key == key)
                and response.get("value") == content
            )
        else:
            acknowledgment = re.fullmatch(
                r"(?:Remembered|Updated) \[([^\r\n]+)\]: [^\r\n]*\r?\n?", stdout
            )
            actual_key = acknowledgment.group(1) if acknowledgment else None
            # A bare-key recall can return arbitrary note text, including text
            # resembling an acknowledgment. Do not infer a write from that body.
            accepted = acknowledgment is not None and bool(key) and actual_key == key
        if accepted:
            return {
                "action": "write",
                "key": actual_key,
                "reason": "cli_write_acknowledgment",
                "retained_final": after.get(str(actual_key)) == content,
            }
        return unknown
    if command == "recall":
        if len(args) != 1:
            return unknown
        key = args[0]
        if (
            response is not None
            and response.get("key") == key
            and response.get("found") is True
            and isinstance(response.get("value"), str)
        ):
            return {"action": "recall", "key": key, "reason": "cli_recall_schema"}
        if any(
            memory.get(key) is not None and stdout == memory[key] + "\n"
            for memory in (before, after)
        ):
            return {"action": "recall", "key": key, "reason": "full_snapshot_body_returned"}
        return unknown
    if command == "memories":
        if len(args) > 1:
            return unknown
        query = args[0] if args else ""
        if response is not None:
            entries = {k: v for k, v in response.items() if k != "schema_version"}
            if not all(isinstance(v, str) for v in entries.values()):
                return unknown
            keys = sorted(entries)
        else:
            lines = stdout.splitlines()
            first = lines[0] if lines else ""
            quoted = json.dumps(query.lower(), ensure_ascii=False)
            if (query and first == f"No memories matching {quoted}" and len(lines) == 1) or (
                not query
                and stdout.strip()
                == "No memories stored. Use 'bd remember \"insight\"' to add one."
            ):
                keys = []
            elif (query and first == f"Memories matching {quoted}:") or (
                not query and re.fullmatch(r"Memories \(\d+\):", first)
            ):
                keys = [
                    line[2:]
                    for line in lines[1:]
                    if line.startswith("  ") and not line.startswith("   ")
                ]
                if not keys or any(key not in before and key not in after for key in keys):
                    return unknown
                if not query and first != f"Memories ({len(keys)}):":
                    return unknown
            else:
                return unknown
        return {
            "action": "query" if query else "list",
            "query": query,
            "candidate_keys": keys,
            "reason": "cli_memory_listing_response",
        }
    return unknown  # Deletion accounting is deliberately unsupported in this audit.


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def audit_session(directory: Path) -> dict[str, Any]:
    """Audit saved execution evidence; refuse inconsistent scored receipt rows."""
    contents = {name: (directory / name).read_bytes() for name in _INPUTS}
    hashes = {name: _sha(content) for name, content in contents.items()}
    values = {
        name: json.loads(content, object_pairs_hook=_object) for name, content in contents.items()
    }
    execution = values["execution.json"]
    original = execution["memory_operations"]
    before, after = values["memory-before.json"], values["memory-after.json"]
    if any(
        not isinstance(memory, dict)
        or not all(isinstance(k, str) and isinstance(v, str) for k, v in memory.items())
        for memory in (before, after)
    ):
        raise ValueError("Memory snapshots must map string keys to bodies")
    raw = values["raw-receipts.json"]
    by_id: dict[str, list[dict[str, Any]]] = {}
    for row in raw:
        if isinstance(row.get("invocation_id"), str):
            by_id.setdefault(row["invocation_id"], []).append(row)
    operations = []
    seen: set[str] = set()
    for row in original["executions"]:
        invocation = row["invocation_id"]
        paired = by_id.get(invocation, [])
        if invocation in seen or len(paired) != 2:
            raise ValueError("Duplicate or incomplete scored invocation")
        seen.add(invocation)
        start, finish = paired
        actual = {
            k: v
            for k, v in row.items()
            if k not in {"command", "stdout_visible_somewhere_in_session"}
        }
        identity = (
            "schema",
            "invocation_id",
            "leg",
            "session",
            "binary",
            "store",
            "operation_argv",
            "ancestors",
        )
        if (
            start.get("event") != "start"
            or finish.get("event") != "finish"
            or actual != finish
            or any(start.get(k) != finish.get(k) for k in identity)
            or finish.get("schema") != "memory-e2e-execution.v1"
            or finish.get("leg") != execution["leg"]
            or finish.get("session") != values["launch.json"]["harness_session"]
            or values["process.json"]["pid"] not in finish.get("ancestors", [])
            or type(finish.get("returncode")) is not int
            or type(start.get("wall_ns")) is not int
            or type(finish.get("wall_ns")) is not int
            or start["wall_ns"] > finish["wall_ns"]
        ):
            raise ValueError("Execution identity or raw payload mismatch")
        for stream in ("stdout", "stderr"):
            try:
                decoded = base64.b64decode(finish[stream + "_base64"], validate=True).decode(
                    "utf-8", errors="replace"
                )
            except ValueError as exc:
                raise ValueError("Invalid receipt base64") from exc
            if decoded != finish[stream]:
                raise ValueError("Receipt bytes and decoded text disagree")
        argv = finish["operation_argv"]
        if not isinstance(argv, list) or not all(isinstance(arg, str) for arg in argv):
            raise ValueError("Invalid receipt argv")
        classified = classify_operation(
            argv, finish["returncode"], finish["stdout"], finish["stderr"], before, after
        )
        operations.append(
            {
                "invocation_id": invocation,
                "argv": argv,
                "original_command": row["command"],
                "wall_ns": finish["wall_ns"],
                "returncode": finish["returncode"],
                "output_visible_in_session": row["stdout_visible_somewhere_in_session"],
                **classified,
            }
        )
    counts = Counter(row["action"] for row in operations)
    corrected = {
        "reads": counts["query"] + counts["list"] + counts["recall"],
        "writes": counts["write"],
        "queries": counts["query"],
        "lists": counts["list"],
        "recalls": counts["recall"],
        "help": counts["help"],
        "prime": counts["prime"],
        "failed": counts["failed"],
        "unknown_semantics": counts["unknown"],
    }
    corrections = [
        {
            **row,
            "execution_sha256": hashes["execution.json"],
            "raw_receipts_sha256": hashes["raw-receipts.json"],
        }
        for row in operations
        if (
            row["action"] in {"help", "list", "unknown"}
            or (row["original_command"] == "remember" and row["action"] == "recall")
        )
    ]
    return {
        "host": execution["host"],
        "arm": execution["arm"],
        "leg": execution["leg"],
        "host_session_id": execution["session_id"],
        "input_sha256": hashes,
        "original_counters": {k: v for k, v in original.items() if k != "executions"},
        "corrected_counters": corrected,
        "operations": operations,
        "corrections": corrections,
        "counters_complete": (
            counts["unknown"] == 0
            and original.get("unknown_execution") == 0
            and len(raw) == 2 * len(seen)
        ),
        "unscored_raw_invocations": sorted(by_id.keys() - seen),
        "artifact_and_capture_verdicts": "unchanged; not regraded",
    }


def audit_run(directory: Path) -> dict[str, Any]:
    """Inspect available saved executions, not an estimate of planned completion."""
    if not directory.is_dir():
        raise NotADirectoryError(directory)
    sessions = sorted(directory.glob("cases/*/*/execution.json"))
    if (directory / "session/execution.json").is_file():
        sessions.append(directory / "session/execution.json")
    rows = [
        {"path": str(path.parent.relative_to(directory)), **audit_session(path.parent)}
        for path in sessions
    ]
    totals: Counter[str] = Counter()
    original_totals: Counter[str] = Counter()
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        totals.update(row["corrected_counters"])
        numeric_original = {k: v for k, v in row["original_counters"].items() if type(v) is int}
        original_totals.update(numeric_original)
        group = groups.setdefault(
            (row["host"], row["arm"]),
            {
                "host": row["host"],
                "arm": row["arm"],
                "recorded_executions": 0,
                "original_counters": Counter(),
                "corrected_counters": Counter(),
            },
        )
        group["recorded_executions"] += 1
        group["original_counters"].update(numeric_original)
        group["corrected_counters"].update(row["corrected_counters"])
    return {
        "run": str(directory.resolve()),
        "recorded_execution_files": len(rows),
        "original_totals": dict(original_totals),
        "corrected_totals": dict(totals),
        "groups": list(groups.values()),
        "counters_complete": bool(rows) and all(row["counters_complete"] for row in rows),
        "sessions": rows,
    }


def write_audit(runs: list[Path], output: Path) -> dict[str, Any]:
    """Write a new artifact exclusively. This function never changes source inputs."""
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    if len({run.resolve() for run in runs}) != len(runs):
        raise ValueError("Duplicate audit run input")
    result = {
        "schema": "memory-e2e-offline-action-audit.v1",
        "posthoc": True,
        "audit_source_sha256": _sha(Path(__file__).read_bytes()),
        "runs": [audit_run(run) for run in runs],
        "limitations": [
            "Beads 1.2.1 response formats; unsupported arguments/actions remain unknown",
            "corrected counts cover recognized successful actions, not retained-content truth",
            "reads count successful classified operations; failed lookups stay in failed commands",
            "empty query results are successful queries, not successful relevant retrievals",
            "query candidates are not necessarily relevant; list fallback is separate",
            "receipt ancestry and session output visibility do not prove model use",
            "locally editable receipt logs are not a security boundary against deliberate forgery",
            "read bodies changed between both snapshots can remain unclassified",
            "recorded executions are not completed lifecycles or independent trials",
            "artifact and capture verdicts remain in untouched frozen assessments",
        ],
    }
    with output.open("x", encoding="utf-8") as target:
        json.dump(result, target, indent=2, ensure_ascii=False)
        target.write("\n")
    return result
