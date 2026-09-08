"""Read-only full-reference and exact startup-echo audit; no agent invocation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import audit_workflow as audit


def full_reference(output: Any, expected: str) -> bool:
    for leaf in audit.text_leaves(output):
        if audit.output_match(leaf, expected):
            return True
        # Actual Claude/zcode Read output numbers every line with a tab. Strip
        # only that display prefix; do not reorder lines or collapse whitespace.
        unnumbered = "\n".join(re.sub(r"^\s*\d+\t", "", line) for line in leaf.splitlines())
        if expected.strip() in unnumbered:
            return True
    return False


def exact_codex_echo(payload: dict[str, Any], prompt: str) -> bool:
    return payload.get("role") == "user" and any(
        isinstance(part, dict) and part.get("type") == "input_text" and part.get("text") == prompt
        for part in payload.get("content", [])
    )


def inspect(workflow_path: Path, reference_path: Path) -> dict[str, Any]:
    row = audit.read(workflow_path)
    folder = Path(row["evidence_root"])
    expected = reference_path.read_text()
    prompt_path = folder / "launch-prompt.txt"
    prompt = prompt_path.read_text()
    hashes = {str(p): audit.sha(p) for p in (workflow_path, reference_path, prompt_path)}
    # Verify the existing immutable observer record before using its evidence links.
    for path, expected_hash in row["source_sha256"].items():
        if audit.sha(Path(path)) != expected_hash:
            raise ValueError(f"Previously audited evidence changed: {path}")
    file_links: list[dict[str, Any]] = []
    echo_links: list[dict[str, Any]] = []
    calls_path = folder / "tool-calls.json"
    calls = audit.read(calls_path)
    hashes[str(calls_path)] = audit.sha(calls_path)
    for index, call in enumerate(calls):
        if "references/memory.md" in json.dumps(call.get("arguments")) and full_reference(
            call.get("result"), expected
        ):
            file_links.append({"source": "normalized", "call_index": index})
    if row["host"] == "codex":
        raw_outputs, _, paths = audit.raw_codex_tools(folder)
        for output in raw_outputs:
            if "references/memory.md" in json.dumps(output["call"]) and full_reference(
                output["output"], expected
            ):
                file_links.append({k: output[k] for k in ("path", "line", "call_id")})
        for path in paths:
            hashes[str(path)] = audit.sha(path)
            if row["startup_submitted"]:
                for index, line in enumerate(path.read_text().splitlines(), 1):
                    event = json.loads(line)
                    if event.get("type") == "response_item" and exact_codex_echo(
                        event.get("payload", {}), prompt
                    ):
                        echo_links.append({"path": str(path), "line": index})
    elif row["host"] == "zcode":
        path = folder / "stream.jsonl"
        hashes[str(path)] = audit.sha(path)
        if row["startup_submitted"]:
            for index, line in enumerate(path.read_text().splitlines(), 1):
                event = json.loads(line)
                if (
                    event.get("type") == "turn.started"
                    and event.get("payload", {}).get("input") == prompt
                ):
                    echo_links.append({"path": str(path), "line": index})
    elif row["host"] == "opencode":
        nested = row["nested_host_sessions"]
        if nested and nested.get("status") == "exported":
            path = Path(nested["path"])
            hashes[str(path)] = audit.sha(path)
            tree = audit.read(path)
            parent = tree["parent_session_id"]
            user_ids = {
                message["id"]
                for message in tree["messages"]
                if message["session_id"] == parent and message["data"].get("role") == "user"
            }
            for part in tree["parts"]:
                data = part["data"]
                if (
                    row["startup_submitted"]
                    and part["message_id"] in user_ids
                    and data.get("type") == "text"
                    and data.get("text") == prompt
                ):
                    echo_links.append({"path": str(path), "part_id": part["id"]})
                if data.get("type") == "tool":
                    state = data.get("state", {})
                    if "references/memory.md" in json.dumps(state.get("input")) and full_reference(
                        state.get("output"), expected
                    ):
                        file_links.append(
                            {
                                "path": str(path),
                                "part_id": part["id"],
                                "child": part["session_id"] != parent,
                            }
                        )
    return {
        "slot": row["slot"],
        "profile_id": row["profile_id"],
        "arm": row["arm"],
        "startup_submitted": row["startup_submitted"],
        "startup_exact_host_echo_observed": True if echo_links else None,
        "startup_echo_status": (
            "verified_exact"
            if echo_links
            else (
                "unverified_in_retained_host_records"
                if row["startup_submitted"]
                else "not_applicable"
            )
        ),
        "startup_echo_links": echo_links,
        "memory_reference_full_read_verified": bool(file_links),
        "memory_reference_full_read_links": file_links,
        "actual_prime_full_output_verified": row["actual_prime_output_exposure"],
        "source_sha256": hashes,
        "limits": (
            "Missing matches are unverified, not proof of absent exposure. "
            "Host echo is not understanding or provider generation."
        ),
    }
