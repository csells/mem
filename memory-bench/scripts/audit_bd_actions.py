#!/usr/bin/env python3
"""Post hoc mechanical audit of acknowledged config.json Write events; no agent calls.

This supplements frozen scores. It does not replay later filesystem mutations or
judge whether all requested fields retain their meaning. Paths are lexical, not resolved
through the vanished sandbox's symlinks. Run with EXPERIMENT --out AUDIT_DIRECTORY.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from membench.runner.bd_actions import valid_write as valid_write
from membench.runner.bd_actions import write_reason
from membench.runner.bd_experiment import _pair_dir, source_fingerprint
from membench.runner.e1_grid import corpus_fingerprint
from membench.runner.e1_reliability import score_bd_leg
from membench.runner.headless_agent import tool_calls_from_stream
from membench.runner.resume_cache import digest
from membench.runner.toolreq_corpus import load_twin_corpus
from membench.runner.toolreq_realagent import DEFAULT_CORPUS, ToolReqRealAgentTask


def stream_cwd(stream: str) -> str | None:
    values = set()
    for line in stream.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(event, dict)
            and event.get("type") == "system"
            and event.get("subtype") == "init"
        ):
            cwd = event.get("cwd")
            if isinstance(cwd, str) and cwd.startswith("/") and "\x00" not in cwd:
                values.add(posixpath.normpath(cwd))
    return next(iter(values)) if len(values) == 1 else None


def evidence_value(leg: Mapping[str, Any] | None, key: str) -> bool | None:
    if leg is None or leg.get("status") != "ok":
        return None
    evidence = leg.get("bd_evidence") or {}
    value = evidence.get(key)
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"Nonboolean evidence {key}")
    return (
        None
        if value is False and key != "goal_action_success" and evidence.get("bd_evidence_unknown")
        else value
    )


def goal_audit(task: ToolReqRealAgentTask, goal: Mapping[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "strict_artifact_success": None,
        "strict_observed_recall": None,
        "strict_recall_before_action": None,
        "qualifying_write_ids": [],
        "write_checks": [],
        "audit_unknown_reasons": [],
        "cwd": None,
    }
    if goal is None or goal.get("status") != "ok":
        return {**result, "audit_unknown_reasons": ["missing_or_unmeasured_goal"]}
    stream = str(goal.get("stream", ""))
    cwd = stream_cwd(stream)
    if cwd is None:
        return {**result, "audit_unknown_reasons": ["missing_or_ambiguous_init_cwd"]}
    calls = tool_calls_from_stream(stream)
    forbidden = tuple(
        value
        for check in task.goal_step.outcome_checks
        for action in check.requires_action
        for value in action.forbidden_values
    )
    reasons = {
        index: write_reason(call, cwd=cwd, required=task.current_opaque_values, forbidden=forbidden)
        for index, call in enumerate(calls)
        if call.name == "Write"
    }
    qualifying = [call for index, call in enumerate(calls) if reasons.get(index) == "qualifies"]
    result = {
        **result,
        "cwd": cwd,
        "strict_artifact_success": bool(qualifying),
        "strict_recall_before_action": None if qualifying else False,
        "qualifying_write_ids": [call.tool_use_id for call in qualifying],
        "write_checks": [
            {
                "tool_use_id": calls[index].tool_use_id,
                "tool_use_index": calls[index].tool_use_index,
                "reason": reason,
            }
            for index, reason in reasons.items()
        ],
    }
    receipts, leg_id = goal.get("bd_receipts"), goal.get("bd_receipt_leg_id")
    if not isinstance(receipts, list) or not isinstance(leg_id, str) or not leg_id:
        return {**result, "audit_unknown_reasons": ["missing_receipt_observation_identity"]}
    rescored = score_bd_leg(
        task,
        calls,
        leg=1,
        role="goal",
        status="ok",
        config_dir=None,
        cwd=cwd,
        receipts=receipts,
        expected_leg_id=leg_id,
    )
    observed = rescored.model_dump()
    observed_leg = {"status": "ok", "bd_evidence": observed}
    return {
        **result,
        "strict_observed_recall": evidence_value(observed_leg, "bd_recall_complete"),
        "strict_recall_before_action": (
            evidence_value(observed_leg, "bd_recall_before_action") if qualifying else False
        ),
        "audit_unknown_reasons": list(rescored.bd_evidence_unknown_reasons),
    }


def read_object(path: Path, hashes: dict[str, str], root: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    hashes[str(path.relative_to(root))] = hashlib.sha256(raw).hexdigest()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def load_pair(
    root: Path, pair: Mapping[str, Any], manifest: Mapping[str, Any], hashes: dict[str, str]
) -> dict[str, dict[str, Any]]:
    directory = _pair_dir(root, pair)
    for name in ("started.json", "cell.json"):
        path = directory / name
        if path.exists():
            saved = read_object(path, hashes, root)
            if saved.get("pair") != pair or saved.get("manifest_digest") != digest(manifest):
                raise ValueError(f"Pair identity mismatch: {path}")
    legs: dict[str, dict[str, Any]] = {}
    for path in sorted((directory / "legs").glob("*.json")):
        leg = read_object(path, hashes, root)
        role = leg.get("role")
        if role not in ("establish", "goal") or role in legs:
            raise ValueError(f"Unexpected or duplicate leg: {path}")
        if leg.get("leg") != (0 if role == "establish" else 1) or any(
            leg.get(key) != pair[key] for key in ("work_id", "variant")
        ):
            raise ValueError(f"Leg identity mismatch: {path}")
        legs[role] = leg
    return legs


def summarize(values: Sequence[bool | None]) -> dict[str, Any]:
    success, failure = sum(v is True for v in values), sum(v is False for v in values)
    unknown = len(values) - success - failure
    return {
        "success": success,
        "failure": failure,
        "unknown": unknown,
        "scheduled": len(values),
        "scheduled_rate_bounds": (
            [success / len(values), (success + unknown) / len(values)] if values else [None, None]
        ),
    }


def disagreements(rows: Sequence[dict[str, Any]], saved: str, strict: str) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row[saved] is not None and row[strict] is not None and row[saved] != row[strict]
    ]


def audit(root: Path, *, corpus_dir: Path = DEFAULT_CORPUS) -> dict[str, Any]:
    hashes: dict[str, str] = {}
    manifest = read_object(root / "manifest.json", hashes, root)
    schedule = manifest["schedule"]
    if len({digest(pair) for pair in schedule}) != len(schedule):
        raise ValueError("Duplicate scheduled pair")
    _, corpus = load_twin_corpus(corpus_dir)
    identities = {(p["work_id"], p["variant"]) for p in schedule}
    tasks = [task for task in corpus if (task.work_id, task.variant) in identities]
    if len(tasks) != len(identities) or corpus_fingerprint(tasks) != manifest["corpus_fingerprint"]:
        raise ValueError("Frozen task corpus identity differs from audit corpus")
    indexed = {(task.work_id, task.variant): task for task in tasks}
    rows = []
    for pair in schedule:
        legs = load_pair(root, pair, manifest, hashes)
        goal = legs.get("goal")
        observed = goal_audit(indexed[(pair["work_id"], pair["variant"])], goal)
        capture = evidence_value(legs.get("establish"), "bd_capture_complete")
        parts = [
            capture,
            observed["strict_artifact_success"],
            observed["strict_observed_recall"],
            observed["strict_recall_before_action"],
        ]
        saved = (goal or {}).get("bd_evidence") or {}
        saved_parts = [
            capture,
            evidence_value(goal, "goal_action_success"),
            evidence_value(goal, "bd_recall_complete"),
            evidence_value(goal, "bd_recall_before_action"),
        ]
        rows.append(
            {
                **pair,
                **observed,
                "saved_goal_action_success": saved.get("goal_action_success"),
                "saved_recall_before_action": evidence_value(goal, "bd_recall_before_action"),
                "saved_handoff": (
                    False if False in saved_parts else (True if all(saved_parts) else None)
                ),
                "establish_capture": capture,
                "strict_handoff": False if False in parts else (True if all(parts) else None),
            }
        )
    groups = [
        {
            "condition": condition,
            "variant": variant,
            **{
                key: summarize(
                    [
                        row[key]
                        for row in rows
                        if row["condition"] == condition and row["variant"] == variant
                    ]
                )
                for key in ("strict_artifact_success", "strict_handoff")
            },
        }
        for condition, variant in sorted({(row["condition"], row["variant"]) for row in rows})
    ]
    return {
        "audit_version": 2,
        "audit_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scoring_source_fingerprint": source_fingerprint(),
        "manifest_digest": digest(manifest),
        "manifest": manifest,
        "artifact_sha256": hashes,
        "scheduled_pairs": len(rows),
        "groups": groups,
        "pairs": rows,
        "discrepancies": disagreements(
            rows, "saved_goal_action_success", "strict_artifact_success"
        ),
        "recall_before_action_discrepancies": disagreements(
            rows, "saved_recall_before_action", "strict_recall_before_action"
        ),
        "handoff_discrepancies": disagreements(rows, "saved_handoff", "strict_handoff"),
        "limitations": [
            "Post hoc mechanical audit, not the frozen primary endpoint.",
            "Success witnesses a qualifying acknowledged Write, "
            "not final on-disk state after later mutations.",
            "JSON string values must contain required tokens; keys/filenames do not qualify.",
            "No semantic all-fields judge; lexical paths do not resolve sandbox symlinks.",
            "Unknown/missing goals remain in full-schedule bounds; original evidence is unchanged.",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS)
    args = parser.parse_args(argv)
    report = audit(args.experiment, corpus_dir=args.corpus_dir)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "audit.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    lines = [
        "# Mechanical action audit",
        "",
        f"Scheduled pairs: {report['scheduled_pairs']}.",
        "",
        "| Condition | Variant | Qualifying Write yes / no / unknown "
        "| Strict handoff yes / no / unknown |",
        "|---|---|---:|---:|",
    ]
    for group in report["groups"]:
        values = [
            " / ".join(str(group[key][name]) for name in ("success", "failure", "unknown"))
            for key in ("strict_artifact_success", "strict_handoff")
        ]
        lines.append(f"| {group['condition']} | {group['variant']} | {values[0]} | {values[1]} |")
    (args.out / "report.md").write_text("\n".join([*lines, "", *report["limitations"], ""]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
