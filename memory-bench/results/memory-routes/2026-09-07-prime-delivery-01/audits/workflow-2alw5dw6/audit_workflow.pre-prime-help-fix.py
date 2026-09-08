"""Read-only command/feedback audit. Never invokes agents, bd, or candidate code.

Per-session records are exclusive and reused only after their source hashes match.
Snapshots are append-only. Execution is established by ancestry-checked receipts;
output exposure is a separate trace link, never a claim of understanding or use.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import time
from collections import Counter
from pathlib import Path

AUDIT = Path(__file__).resolve().parent
COHORT = AUDIT.parents[1]
REPO = COHORT.parents[3]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def text_leaves(value, depth=0):
    """Decode only real JSON envelopes; never interpret shell code or escapes."""
    if depth > 8:
        return []
    if isinstance(value, str):
        leaves = [value]
        try:
            nested = json.loads(value)
        except ValueError:
            return leaves
        if nested != value:
            leaves += text_leaves(nested, depth + 1)
        return leaves
    if isinstance(value, list):
        return [leaf for child in value for leaf in text_leaves(child, depth + 1)]
    if isinstance(value, dict):
        return [
            leaf
            for key in ("output", "text", "content", "value", "result", "results")
            if key in value
            for leaf in text_leaves(value[key], depth + 1)
        ]
    return []


def output_match(output, expected):
    if not expected.strip():
        return None
    for leaf in text_leaves(output):
        candidate = expected.strip()
        for form in ("literal", "json_escaped_once", "json_escaped_twice"):
            if candidate in leaf:
                return form
            candidate = json.dumps(candidate, ensure_ascii=False)[1:-1]
    return None


def operation(argv, fallback):
    if "--help" in argv or "-h" in argv or (argv and argv[0] == "help"):
        return "help"
    return {
        "memories": "search_or_list",
        "remember": "save",
    }.get(fallback, fallback or "unknown")


def stream_prose(events):
    found = []
    for line, event in events:
        parts = []
        if event.get("type") == "text":
            parts.append(event.get("part", {}).get("text", ""))
        if (
            event.get("type") == "item.completed"
            and event.get("item", {}).get("type") == "agent_message"
        ):
            parts.append(event["item"].get("text", ""))
        if event.get("type") == "assistant":
            parts += [
                c.get("text", "")
                for c in event.get("message", {}).get("content", [])
                if c.get("type") == "text"
            ]
        if event.get("type") == "result" and isinstance(event.get("response"), str):
            parts.append(event["response"])
        found += [{"stream_line": line, "text": p} for p in parts if p]
    return found


def raw_codex_tools(folder):
    outputs, inputs, paths = [], {}, []
    for path in sorted((folder / "host-evidence").rglob("rollout*.jsonl")):
        paths.append(path)
        calls = {}
        for line, text in enumerate(path.read_text().splitlines(), 1):
            event = json.loads(text)
            if event.get("type") != "response_item":
                continue
            payload = event.get("payload", {})
            kind = payload.get("type")
            ref = {"path": str(path), "line": line, "call_id": payload.get("call_id")}
            if kind in ("function_call", "custom_tool_call"):
                calls[payload.get("call_id")] = payload
                inputs[(str(path), payload.get("call_id"))] = {**ref, "payload": payload}
            if kind in ("function_call_output", "custom_tool_call_output"):
                call = calls.get(payload.get("call_id"), {})
                outputs.append({**ref, "output": payload.get("output"), "call": call})
    return outputs, list(inputs.values()), paths


def brief_argv(argv):
    return [
        (
            value
            if len(value) <= 600
            else {
                "preview": value[:300],
                "characters": len(value),
                "sha256": hashlib.sha256(value.encode()).hexdigest(),
                "full_value": "original raw-receipts.json operation_argv",
            }
        )
        for value in argv
    ]


def opencode_sessions(folder, result):
    """Retain exact parent/descendant messages from this stage's isolated DB."""
    if result["host"] != "opencode":
        return None, [], [], []
    destination = AUDIT / f"{result['slot']}.opencode-sessions.json"
    if destination.exists():
        saved = read(destination)
    else:
        state = read(folder.parent / "state.json")
        db = Path(state["scratch"]) / f"stage-{result['stage']}/config/data/opencode/opencode.db"
        if not db.is_file():
            return {"status": "isolated database unavailable", "path": str(db)}, [], [], []
        connection = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            sessions = [
                dict(r)
                for r in connection.execute(
                    "WITH RECURSIVE tree(id) AS (SELECT id FROM session WHERE id=? "
                    "UNION SELECT session.id FROM session JOIN tree ON session.parent_id=tree.id) "
                    "SELECT session.* FROM session JOIN tree ON session.id=tree.id "
                    "ORDER BY time_created",
                    (result["session_id"],),
                )
            ]
            messages, parts = [], []
            for session in sessions:
                messages += [
                    {"id": r["id"], "session_id": r["session_id"], "data": json.loads(r["data"])}
                    for r in connection.execute(
                        "SELECT * FROM message WHERE session_id=? ORDER BY time_created",
                        (session["id"],),
                    )
                ]
                parts += [
                    {
                        "id": r["id"],
                        "message_id": r["message_id"],
                        "session_id": r["session_id"],
                        "data": json.loads(r["data"]),
                    }
                    for r in connection.execute(
                        "SELECT * FROM part WHERE session_id=? ORDER BY time_created",
                        (session["id"],),
                    )
                ]
        finally:
            connection.close()
        saved = {
            "schema": "isolated-opencode-tree-readonly-export.v1",
            "created_ns": time.time_ns(),
            "db_path": str(db),
            "scope": "exact scored parent and recursive descendants; mode=ro",
            "parent_session_id": result["session_id"],
            "sessions": sessions,
            "messages": messages,
            "parts": parts,
        }
        write(destination, saved)
    tools = []
    for part in saved["parts"]:
        data = part["data"]
        if data.get("type") != "tool":
            continue
        tools.append(
            {
                "source": "isolated_opencode_db",
                "path": str(destination),
                "part_id": part["id"],
                "message_id": part["message_id"],
                "session_id": part["session_id"],
                "child_session": part["session_id"] != result["session_id"],
                "tool": data.get("tool"),
                "state": data.get("state", {}),
            }
        )
    summary = []
    for session in saved["sessions"]:
        messages = [
            m
            for m in saved["messages"]
            if m["session_id"] == session["id"] and m["data"].get("role") == "assistant"
        ]
        summary.append(
            {
                "session_id": session["id"],
                "parent_id": session["parent_id"],
                "child_session": session["id"] != result["session_id"],
                "agent": session.get("agent"),
                "actual_assistant_models": sorted(
                    {
                        m["data"].get("providerID", "?") + "/" + m["data"].get("modelID", "?")
                        for m in messages
                    }
                ),
                "session_usage": {
                    k: v for k, v in session.items() if k.startswith("tokens_") or k == "cost"
                },
                "unique_assistant_messages": len(messages),
            }
        )
    return (
        {"status": "exported", "path": str(destination), "sessions": summary},
        tools,
        [destination],
        saved["messages"],
    )


def inspect_session(folder):
    result = read(folder / "result.json")
    calls = read(folder / "tool-calls.json")
    launch = read(folder / "launch.json")
    raw_outputs, raw_calls, raw_paths = raw_codex_tools(folder)
    nested, db_tools, db_paths, _db_messages = opencode_sessions(folder, result)
    paths = (
        [
            folder / name
            for name in (
                "result.json",
                "tool-calls.json",
                "raw-receipts.json",
                "launch.json",
                "stream.jsonl",
                "delivery.json",
                "launch-prompt.txt",
            )
        ]
        + raw_paths
        + db_paths
    )
    executions = []
    for index, entry in enumerate(result["receipt_assessment"]["executions"]):
        stdout = entry.get("stdout", "")
        links = []
        for call_index, call in enumerate(calls):
            match = output_match(call.get("result"), stdout)
            if match:
                links.append(
                    {
                        "source": "normalized",
                        "call_index": call_index,
                        "tool_use_id": call.get("tool_use_id"),
                        "form": match,
                        "arguments": call.get("arguments"),
                    }
                )
        for output in raw_outputs:
            match = output_match(output["output"], stdout)
            if match:
                links.append(
                    {
                        "source": "raw_codex",
                        "path": output["path"],
                        "line": output["line"],
                        "call_id": output["call_id"],
                        "form": match,
                        "arguments": output["call"].get("input", output["call"].get("arguments")),
                    }
                )
        for tool in db_tools:
            match = output_match(tool["state"].get("output"), stdout)
            if match:
                links.append(
                    {
                        **{k: v for k, v in tool.items() if k not in ("tool", "state")},
                        "form": match,
                        "arguments": tool["state"].get("input"),
                    }
                )
        is_prime = entry.get("command") == "prime"
        prime_links = [
            {k: v for k, v in link.items() if k != "arguments"}
            for link in links
            if is_prime and re.search(r"\bbd\s+prime\b", str(link["arguments"]))
        ]
        executions.append(
            {
                "receipt_index": index,
                "invocation_id": entry["invocation_id"],
                "wall_ns": entry["wall_ns"],
                "operation": operation(entry["operation_argv"], entry.get("command")),
                "command": entry.get("command"),
                "argv": brief_argv(entry["operation_argv"]),
                "returncode": entry["returncode"],
                "success": entry["returncode"] == 0,
                "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
                "stdout_characters": len(stdout),
                "feedback_stdout": stdout[:2500] if entry["returncode"] else None,
                "feedback_stderr": entry.get("stderr", "")[:2500],
                "output_links": [
                    {k: v for k, v in link.items() if k != "arguments"} for link in links
                ],
                "prime_output_command_links": prime_links,
                "normalized_gap_recovered": bool(links)
                and not any(link["source"] == "normalized" for link in links),
                "empty_search": entry.get("command") == "memories"
                and (stdout.startswith("No memories") or stdout.strip() in ("[]", "{}")),
            }
        )
    native_skills = [
        {
            "call_index": i,
            "tool_use_id": c.get("tool_use_id"),
            "arguments": c.get("arguments"),
            "is_error": c.get("is_error"),
            "result": str(c.get("result", ""))[:1600],
        }
        for i, c in enumerate(calls)
        if c.get("name", "").lower() == "skill"
    ]
    events = [
        (n, json.loads(t))
        for n, t in enumerate((folder / "stream.jsonl").read_text().splitlines(), 1)
    ]
    pseudo = [
        p
        for p in stream_prose(events)
        if re.search(r"<function=|<tool_call>|</tool_call>", p["text"])
    ]
    raw_tool_events = [
        line
        for line, event in events
        if event.get("type") in ("tool_use", "tool_result", "tool.updated")
        or (
            event.get("type") == "assistant"
            and any(
                c.get("type") == "tool_use" for c in event.get("message", {}).get("content", [])
            )
        )
        or (
            event.get("type") in ("item.started", "item.completed")
            and event.get("item", {}).get("type")
            in ("command_execution", "mcp_tool_call", "file_change")
        )
    ]
    no_calls = (
        not calls and not raw_calls and not raw_tool_events and not executions and not db_tools
    )
    native_files = {
        str(p.relative_to(folder / "native-after")): sha(p)
        for p in (folder / "native-after").rglob("*")
        if p.is_file()
    }
    tool_errors = [
        {
            "call_index": i,
            "name": c.get("name"),
            "arguments": c.get("arguments"),
            "result": str(c.get("result", ""))[:2500],
        }
        for i, c in enumerate(calls)
        if c.get("is_error")
    ]
    return {
        "schema": "prime-workflow-session.v1",
        "created_ns": time.time_ns(),
        **{
            k: result[k]
            for k in (
                "slot",
                "lifecycle",
                "profile_id",
                "host",
                "family",
                "arm",
                "catalog_mode",
                "stage",
                "phase",
            )
        },
        "evidence_root": str(folder),
        "source_sha256": {str(p): sha(p) for p in paths},
        "helper_sha256": sha(Path(__file__)),
        "executions": executions,
        "unknown_receipt_executions": result["receipt_assessment"]["unknown_execution"],
        "operation_counts": dict(Counter(e["operation"] for e in executions)),
        "success_counts": dict(Counter(e["operation"] for e in executions if e["success"])),
        "failed_counts": dict(Counter(e["operation"] for e in executions if not e["success"])),
        "native_skill_calls": native_skills,
        "native_skill_prime_arguments": sum(
            "prime" in str(c["arguments"].get("args", "")).split() for c in native_skills
        ),
        "actual_prime_output_exposure": any(
            e["success"] and e["prime_output_command_links"] for e in executions
        ),
        "startup_submitted": result["delivery"]["startup_briefing_injected"],
        "startup_understanding": "not inferred",
        "tool_error_feedback": tool_errors,
        "pseudo_tool_text": pseudo,
        "pseudo_tool_only_session": bool(pseudo) and no_calls,
        "no_actual_tools_in_preserved_trace": no_calls,
        "normalized_call_count": len(calls),
        "raw_codex_call_count": len(raw_calls),
        "raw_tool_event_lines": raw_tool_events,
        "nested_host_sessions": nested,
        "child_tool_count": sum(t["child_session"] for t in db_tools),
        "child_tool_feedback": [
            {k: v for k, v in t.items() if k != "state"} | {"state": t["state"]}
            for t in db_tools
            if t["child_session"] and t["state"].get("status") == "error"
        ],
        "zcode_model_ref_receipts": [
            {
                "stream_line": line,
                "event_type": event.get("type"),
                "modelRef": event["payload"]["modelRef"],
            }
            for line, event in events
            if isinstance(event.get("payload"), dict) and "modelRef" in event["payload"]
        ],
        "actual_models": result["models_observed"],
        "requested_model": result["model_requested"],
        "cost_usd": result["cost_usd"],
        "usage_receipt": result["usage"],
        "cost_scope": (
            "Host reported cost only; null is unknown, local zero excludes hardware/energy"
        ),
        "usage_scope": (
            "Original host observation may omit child usage; OpenCode parent and child "
            "session usage are retained separately and must not be added twice to parent totals."
        ),
        "native_settings": launch["settings"],
        "native_file_sha256": native_files,
        "recovered_assessment": result.get("recovered_assessment"),
        "process_exit_observed": result.get(
            "process_exit_observed", result["exit_code"] is not None
        ),
        "exit_code": result["exit_code"],
        "infrastructure_fault": result["infrastructure_fault"],
        "administrative_memory_reads": result["administrative_memory_reads"],
        "artifact_passed": result["artifact_passed"],
        "semantic_memory_fidelity_or_use": "not assessed by workflow audit",
    }


def capture():
    manifest = read(COHORT / "manifest.json")
    rows = []
    for slot in manifest["slots"]:
        folder = COHORT / "cases" / slot["lifecycle"] / f"stage-{slot['stage']}"
        if not (folder / "result.json").is_file():
            continue
        destination = AUDIT / f"{slot['slot']}.workflow.json"
        if destination.exists():
            row = read(destination)
            if any(sha(Path(p)) != h for p, h in row["source_sha256"].items()):
                raise ValueError(f"Previously audited source changed: {slot['slot']}")
        else:
            row = inspect_session(folder)
            write(destination, row)
            print("AUDITED", slot["slot"], flush=True)
        rows.append(row)
    return manifest, rows


def snapshot(label, expected):
    manifest, rows = capture()
    if expected is not None and len(rows) != expected:
        raise ValueError(f"Snapshot requires {expected} assessed sessions; found {len(rows)}")
    recovery = read(COHORT / "recovery-01/operational-plan.json")
    statuses = []
    observed = {r["slot"]: r for r in rows}
    for slot in manifest["slots"]:
        row = observed.get(slot["slot"])
        folder = COHORT / "cases" / slot["lifecycle"] / f"stage-{slot['stage']}"
        status = (
            "assessed_posthoc"
            if row and row["recovered_assessment"]
            else (
                "assessed"
                if row
                else (
                    "censored_prelaunch_claim"
                    if slot["slot"] in recovery["preexisting_claims_without_result"]
                    else (
                        "censored_missing_predecessor"
                        if slot["lifecycle"] in recovery["censored_lifecycles"]
                        else "claimed_unassessed" if folder.exists() else "not_started"
                    )
                )
            )
        )
        statuses.append({**slot, "status": status})
    configs = []
    for name, expected_hash in manifest["profile_sha256"].items():
        path = Path(name) if Path(name).is_absolute() else REPO / name
        actual = sha(path) if path.is_file() else None
        configs.append(
            {
                "path": name,
                "expected_sha256": expected_hash,
                "actual_sha256": actual,
                "unchanged": actual == expected_hash,
            }
        )
    groups = []
    for profile in manifest["admitted_profile_ids"]:
        for arm in ("thin-prime", "rich-prime", "startup-briefing"):
            selected = [r for r in rows if r["profile_id"] == profile and r["arm"] == arm]
            commands = [e for r in selected for e in r["executions"]]
            groups.append(
                {
                    "profile_id": profile,
                    "arm": arm,
                    "assessed": len(selected),
                    "planned": sum(
                        s["profile_id"] == profile and s["arm"] == arm for s in manifest["slots"]
                    ),
                    "success_counts": dict(
                        Counter(e["operation"] for e in commands if e["success"])
                    ),
                    "failure_counts": dict(
                        Counter(e["operation"] for e in commands if not e["success"])
                    ),
                    "prime_exposed_sessions": sum(
                        r["actual_prime_output_exposure"] for r in selected
                    ),
                    "native_skill_prime_sessions": sum(
                        bool(r["native_skill_prime_arguments"]) for r in selected
                    ),
                    "pseudo_tool_only_sessions": sum(
                        r["pseudo_tool_only_session"] for r in selected
                    ),
                    "known_cost_usd": sum(
                        r["cost_usd"] for r in selected if r["cost_usd"] is not None
                    ),
                    "unknown_cost_sessions": sum(r["cost_usd"] is None for r in selected),
                    "native_nonempty_sessions": sum(
                        bool(r["native_file_sha256"]) for r in selected
                    ),
                    "actual_models": sorted({m for r in selected for m in r["actual_models"]}),
                }
            )
    value = {
        "schema": "prime-workflow-snapshot.v1",
        "label": label,
        "created_ns": time.time_ns(),
        "manifest_sha256": sha(COHORT / "manifest.json"),
        "helper_sha256": sha(Path(__file__)),
        "planned": len(manifest["slots"]),
        "assessed": len(rows),
        "status_counts": dict(Counter(s["status"] for s in statuses)),
        "slots": statuses,
        "groups": groups,
        "profile_config_checks": configs,
        "known_cost_usd": sum(r["cost_usd"] for r in rows if r["cost_usd"] is not None),
        "unknown_cost_sessions": sum(r["cost_usd"] is None for r in rows),
        "normalization_gaps_recovered": [
            {"slot": r["slot"], "receipt_index": e["receipt_index"], "operation": e["operation"]}
            for r in rows
            for e in r["executions"]
            if e["normalized_gap_recovered"]
        ],
        "failed_commands": [
            {"slot": r["slot"], **e} for r in rows for e in r["executions"] if not e["success"]
        ],
        "pseudo_tool_only_slots": [r["slot"] for r in rows if r["pseudo_tool_only_session"]],
        "sessions": [
            {
                "slot": r["slot"],
                "audit_path": str(AUDIT / f"{r['slot']}.workflow.json"),
                "audit_sha256": sha(AUDIT / f"{r['slot']}.workflow.json"),
            }
            for r in rows
        ],
        "limits": [
            "No automatic semantic fidelity, retrieval-route, or memory-use verdicts.",
            "Successful help is help, never capture, recall, closure, or prime execution.",
            "Output links establish retained stdout in a tool response; exact one-to-one "
            "attribution is not guaranteed for duplicate output.",
            "A missing normalized or raw match is unverified exposure, not proof of no exposure.",
            "Startup submission and native Skill calls do not certify actual bd prime "
            "execution or understanding.",
            "Native file presence does not establish automatic memory extraction or use.",
            "Counts do not certify artifact correctness or faithful retained information.",
        ],
    }
    path = AUDIT / f"{label}-{time.time_ns()}.json"
    write(path, value)
    print(
        json.dumps(
            {
                "snapshot": str(path),
                "assessed": len(rows),
                "known_cost_usd": value["known_cost_usd"],
                "unknown_cost_sessions": value["unknown_cost_sessions"],
            }
        ),
        flush=True,
    )
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-only", action="store_true")
    parser.add_argument("--snapshot", choices=("phase1", "final"))
    parser.add_argument("--expect-assessed", type=int)
    arguments = parser.parse_args()
    if arguments.capture_only:
        capture()
    elif arguments.snapshot:
        snapshot(arguments.snapshot, arguments.expect_assessed)
    else:
        parser.error("Choose --capture-only or --snapshot")
