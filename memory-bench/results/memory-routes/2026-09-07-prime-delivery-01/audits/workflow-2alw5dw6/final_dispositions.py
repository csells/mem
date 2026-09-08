"""Read-only terminal slot audit; no inference, execution, repair, or retries."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

AUTH_FAILURE = "File-backed Codex ChatGPT authentication unavailable"
QUOTA_PREFIX = "You've hit your usage limit."
AUTH_REJECTED = (
    "Your access token could not be refreshed because your refresh token was revoked. "
    "Please log out and sign in again."
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> Any:
    return json.loads(path.read_text())


def stream_evidence(path: Path, host: str) -> dict[str, Any]:
    """Recognize actual output/tool events, never model configuration or token counts.

    Denial recognition is narrow: observed Codex quota/auth top-level error
    contracts. Unknown errors remain unknown, rather than being guessed from words
    embedded in a user prompt, a tool result, or ordinary assistant prose.
    """
    generation: list[dict[str, Any]] = []
    denials: list[dict[str, Any]] = []
    malformed: list[int] = []
    if not path.is_file():
        return {"generation": generation, "provider_denials": denials, "malformed_lines": []}
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            malformed.append(line_number)
            continue
        if not isinstance(event, dict):
            malformed.append(line_number)
            continue
        kind = event.get("type")
        generated = False
        if host == "codex":
            item = event.get("item", {})
            if kind in {"item.started", "item.completed"} and isinstance(item, dict):
                generated = (
                    (item.get("type") == "agent_message" and bool(item.get("text")))
                    or (item.get("type") == "command_execution" and bool(item.get("command")))
                    or item.get("type") in {"file_change", "mcp_tool_call", "web_search"}
                )
            message = (
                event.get("message")
                if kind == "error"
                else (
                    event.get("error", {}).get("message")
                    if kind == "turn.failed" and isinstance(event.get("error"), dict)
                    else None
                )
            )
            denial_kind = (
                "quota"
                if isinstance(message, str) and message.startswith(QUOTA_PREFIX)
                else "authentication_rejected" if message == AUTH_REJECTED else None
            )
            if denial_kind:
                denials.append(
                    {"line": line_number, "type": kind, "kind": denial_kind, "message": message}
                )
        elif host == "claude":
            message = event.get("message", {})
            if kind == "assistant" and isinstance(message, dict):
                generated = any(
                    isinstance(block, dict)
                    and (
                        block.get("type") == "tool_use"
                        or (block.get("type") == "text" and bool(block.get("text")))
                        or (block.get("type") == "thinking" and bool(block.get("thinking")))
                    )
                    for block in message.get("content", [])
                ) and not event.get("isApiErrorMessage", False)
        elif host == "opencode":
            part = event.get("part", {})
            if isinstance(part, dict):
                generated = (kind in {"text", "reasoning"} and bool(part.get("text"))) or (
                    kind == "tool_use" and part.get("type") == "tool"
                )
        elif host == "zcode":
            payload = event.get("payload", {})
            if isinstance(payload, dict):
                generated = kind == "model.streaming" and bool(payload.get("delta"))
        else:
            raise ValueError(f"Unsupported host: {host}")
        # One concrete output event is sufficient; no reasoning/body content is exported.
        if generated and not generation:
            generation.append({"line": line_number, "type": kind})
    return {"generation": generation, "provider_denials": denials, "malformed_lines": malformed}


def disposition(
    *,
    assessed: bool,
    generated: bool,
    denied: bool,
    original_claim: bool,
    original_lifecycle: bool,
    directory_exists: bool,
    process_exists: bool,
    auth_failure: bool,
    profile_blocked: bool,
    predecessor_missing: bool,
) -> str:
    if assessed:
        if generated and denied:
            return "assessed_generation_with_provider_denial"
        if denied:
            return "assessed_provider_denial_without_observed_generation"
        return "assessed_generation" if generated else "assessed_generation_unverified"
    if original_claim:
        return "original_prelaunch_censor"
    if original_lifecycle:
        return "original_downstream_missing_predecessor"
    if directory_exists:
        if process_exists:
            return "started_unassessed"
        return "new_auth_setup_claim" if auth_failure else "claimed_unassessed"
    if predecessor_missing:
        return "downstream_missing_predecessor"
    if profile_blocked:
        return "later_profile_blocked_untouched"
    return "untouched_no_recorded_blocker"


def export(cohort: Path, summary_path: Path) -> dict[str, Any]:
    """Build an immutable terminal report only after the actual phase-two summary."""
    manifest_path = cohort / "manifest.json"
    original_path = cohort / "recovery-01/operational-plan.json"
    manifest, original, summary = read(manifest_path), read(original_path), read(summary_path)
    slots = manifest["slots"]
    if len(slots) != 216 or len({row["slot"] for row in slots}) != 216:
        raise ValueError("Expected all 216 unique frozen manifest slots")
    if summary.get("phase") != "phase2" or summary.get("manifest_sha256") != sha(manifest_path):
        raise ValueError("Terminal summary does not match phase two and the actual manifest")
    if original.get("manifest_sha256") != sha(manifest_path):
        raise ValueError("Original operational plan does not match the actual manifest")
    hashes = {str(p): sha(p) for p in [manifest_path, original_path, summary_path]}
    failures: dict[str, dict[str, Any]] = {}
    for path in sorted(summary_path.parent.glob("*-failure.json")):
        failure = read(path)
        failures[failure["profile"]] = failure
        hashes[str(path)] = sha(path)
    original_claims = set(original["preexisting_claims_without_result"])
    original_lifecycles = set(original["censored_lifecycles"])
    blocked = set(summary["blocked_profiles"])
    assessed_results: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for slot in slots:
        folder = cohort / "cases" / slot["lifecycle"] / f"stage-{slot['stage']}"
        result_path, process_path = folder / "result.json", folder / "process.json"
        result = read(result_path) if result_path.is_file() else None
        if result is not None:
            if any(result.get(k) != slot[k] for k in ("slot", "lifecycle", "profile_id", "stage")):
                raise ValueError(f"Result identity mismatch: {slot['slot']}")
            assessed_results[slot["slot"]] = result
        paths = [folder / n for n in ("result.json", "process.json", "stream.jsonl", "launch.json")]
        # Preserve prelaunch evidence as hashes; do not export prompts or credentials.
        if result is None and folder.exists():
            paths.extend(p for p in folder.iterdir() if p.is_file())
        source_hashes = {str(p): sha(p) for p in paths if p.is_file()}
        hashes.update(source_hashes)
        evidence = stream_evidence(folder / "stream.jsonl", slot["host"])
        failure = failures.get(slot["profile_id"])
        previous = folder.parent / f"stage-{slot['stage'] - 1}" / "result.json"
        predecessor_missing = slot["stage"] > 1 and not previous.is_file()
        status = disposition(
            assessed=result is not None,
            generated=bool(evidence["generation"]),
            denied=bool(evidence["provider_denials"]),
            original_claim=slot["slot"] in original_claims,
            original_lifecycle=slot["lifecycle"] in original_lifecycles,
            directory_exists=folder.exists(),
            process_exists=process_path.is_file(),
            auth_failure=bool(failure and failure.get("message") == AUTH_FAILURE),
            profile_blocked=slot["profile_id"] in blocked,
            predecessor_missing=predecessor_missing,
        )
        rows.append(
            {
                **slot,
                "status": status,
                "assessed": result is not None,
                "generation_observed": bool(evidence["generation"]),
                "provider_denial_observed": bool(evidence["provider_denials"]),
                "provider_denial_kinds": sorted({d["kind"] for d in evidence["provider_denials"]}),
                "raw_stream_evidence": evidence,
                "session_directory_exists": folder.exists(),
                "process_start_record": read(process_path) if process_path.is_file() else None,
                "process_exit_observed": (
                    result.get("process_exit_observed", result.get("exit_code") is not None)
                    if result
                    else None
                ),
                "exit_code": result.get("exit_code") if result else None,
                "posthoc_assessment": bool(result and result.get("recovered_assessment")),
                "artifact_passed": result.get("artifact_passed") if result else None,
                "profile_failure": failure,
                "predecessor_missing": predecessor_missing,
                "source_sha256": source_hashes,
            }
        )
    phase_assessed = sum(row["assessed"] for row in rows if row["phase"] == "phase2")
    if phase_assessed != summary["phase_assessed"]:
        raise ValueError("Actual phase-two results do not match its terminal summary")
    all_results = list((cohort / "cases").glob("*/stage-*/result.json"))
    if len(all_results) != len(assessed_results):
        raise ValueError("Result outside manifest or duplicate slot evidence")
    return {
        "schema": "prime-terminal-operational-dispositions.v1",
        "created_ns": time.time_ns(),
        "planned": 216,
        "assessed": len(assessed_results),
        "unassessed": 216 - len(assessed_results),
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "provider_denial_session_counts": dict(
            Counter(kind for row in rows for kind in row["provider_denial_kinds"])
        ),
        "profiles": {
            identity: dict(Counter(row["status"] for row in rows if row["profile_id"] == identity))
            for identity in manifest["admitted_profile_ids"]
        },
        "rows": rows,
        "source_sha256": hashes,
        "helper_sha256": sha(Path(__file__)),
        "model_calls": 0,
        "limits": [
            "Observed generation is an output/tool event, not requested model metadata.",
            "Denial recognition covers observed Codex usage-limit and revoked-token errors only.",
            "Unrecognized or malformed events are retained as unverified, not invented behavior.",
            "A process-start record proves a recorded launch, not a currently live process.",
            "Quota-denied artifacts retain their independent assessment; no adoption credit.",
            "Posthoc assessment and unknown OS exit remain explicit; no trial is restarted.",
            "No classification establishes faithful capture, policy applicability or memory use.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    value = export(args.cohort.resolve(), args.summary.resolve())
    with args.out.open("x") as output:
        json.dump(value, output, indent=2)
        output.write("\n")
    print(
        json.dumps(
            {
                "output": str(args.out),
                "assessed": value["assessed"],
                "statuses": value["status_counts"],
            }
        )
    )


if __name__ == "__main__":
    main()
