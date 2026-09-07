"""Bd-specific evidence for E1's establish → fresh-session goal pairs.

Required values are authored opaque tokens, matched mechanically. A completed handoff is
an observed conjunction, not a claim that bd causally supplied the goal action. Compound
shell results cannot establish which command returned a value and are left unattributed.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from membench.metrics.scorers import states_value
from membench.runner.bd_actions import UNKNOWN_DESTINATION, write_reason
from membench.runner.realagent_probe import REAL_TOOL
from membench.runner.tool_surface import (
    MemoryInvocation,
    command_segments,
    memory_invocations,
    memory_result_is_attributable,
    native_memory_accesses,
)
from membench.runner.toolreq_realagent import ToolReqRealAgentTask
from membench.schemas.trace import ToolCall

RELIABILITY_VERSION = 3
ROLES = ("establish", "goal")


class BdLegEvidence(BaseModel):
    """Compact evidence persisted beside the stream and in the resumable cell."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Zero identifies historical artifacts that did not persist their scorer version.
    scoring_version: int = Field(default=0, ge=0)
    leg: int = Field(ge=0)
    role: Literal["establish", "goal"]
    status: Literal["ok", "timeout", "error"]
    bd_read_attempts: int = Field(default=0, ge=0)
    bd_write_attempts: int = Field(default=0, ge=0)
    bd_accepted_writes: int = Field(default=0, ge=0)
    bd_unattributed_read_blocks: int = Field(default=0, ge=0)
    bd_unattributed_write_blocks: int = Field(default=0, ge=0)
    bd_capture_complete: bool = False
    bd_recall_complete: bool = False
    bd_recall_before_action: bool | None = False
    native_read_attempts: int = Field(default=0, ge=0)
    native_write_attempts: int = Field(default=0, ge=0)
    native_answered_reads: int = Field(default=0, ge=0)
    goal_action_success: bool | None = None
    bd_evidence_unknown: bool = False
    bd_evidence_unknown_reasons: tuple[str, ...] = ()


def _read_content(invocation: MemoryInvocation, call: ToolCall) -> list[str]:
    """Extract payload fields from the shipped bd formats, excluding query/key metadata."""
    result = call.result or ""
    segments = command_segments(str(call.arguments.get("command", "")))
    if "--json" in segments[0]:
        try:
            body = json.loads(result)
        except json.JSONDecodeError:
            return []
        if not isinstance(body, dict):
            return []
        if invocation.verb == "memories":
            return (
                [
                    value
                    for key, value in body.items()
                    if key != "schema_version" and isinstance(value, str)
                ]
                if "schema_version" in body
                else []
            )
        value = body.get("value")
        return [value] if body.get("found") is True and isinstance(value, str) else []
    if invocation.verb == "memories":
        # Text search prints a heading (which repeats the query), two-space keys,
        # and four-space content. A miss has no content rows, even though it echoes the query.
        return [line[4:] for line in result.splitlines() if line.startswith("    ")]
    if invocation.is_recall_by_result:
        return ["\n".join(result.splitlines()[1:])]
    return [result]


def _read_payloads(calls: Sequence[ToolCall]) -> tuple[list[str], int]:
    payloads: list[str] = []
    unattributed = 0
    for call in calls:
        invocations = memory_invocations([call])
        reads = [inv for inv in invocations if inv.is_read or inv.is_recall_by_result]
        if not reads or call.result is None or call.is_error:
            continue
        # Only a direct, single bd command owns the whole tool_result. In particular,
        # `bd recall missing; cat MEMORY.md` must not credit the native payload to bd.
        if memory_result_is_attributable(call):
            payloads.extend(_read_content(invocations[0], call))
        else:
            unattributed += 1
    return payloads, unattributed


def _contains_all(payloads: Sequence[str], values: Sequence[str]) -> bool:
    return bool(values) and all(
        any(states_value(payload, value) for payload in payloads) for value in values
    )


def _goal_writes(
    task: ToolReqRealAgentTask, calls: Sequence[ToolCall], *, cwd: Path | str | None
) -> tuple[tuple[ToolCall, ...], bool]:
    checks = task.goal_step.outcome_checks
    actions = [action for check in checks for action in check.requires_action]
    if (
        not checks
        or any(not check.requires_action for check in checks)
        or any(action.tool != REAL_TOOL or not action.arg_values for action in actions)
    ):
        raise ValueError("bd reliability requires an explicit config.json Write contract")
    required = tuple(value for action in actions for value in action.arg_values)
    forbidden = tuple(value for action in actions for value in action.forbidden_values)
    reasons = [
        (call, write_reason(call, cwd=cwd, required=required, forbidden=forbidden))
        for call in calls
    ]
    return (
        tuple(call for call, reason in reasons if reason == "qualifies"),
        any(reason == UNKNOWN_DESTINATION for _, reason in reasons),
    )


def _recall_before_action(
    task: ToolReqRealAgentTask,
    calls: Sequence[ToolCall],
    *,
    goal_writes: Sequence[ToolCall],
    ambiguous_goal: bool,
) -> bool | None:
    delivered = [(call, _read_payloads([call])[0]) for call in calls]
    before, _ = _receipt_before_action(
        task,
        [(call, payloads) for call, payloads in delivered if payloads],
        goal_writes=goal_writes,
        ambiguous_goal=ambiguous_goal,
    )
    return before


class _ReceiptIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)

    invocation_id: str = Field(min_length=1)
    tool_use_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    leg_id: str = Field(min_length=1)
    operation_argv: list[str] = Field(min_length=1)
    event: Literal["start", "finish"]


def _finished_receipts(
    receipts: Sequence[Mapping[str, Any]], *, expected_leg_id: str
) -> tuple[list[Mapping[str, Any]], list[str]]:
    indexed: dict[str, list[tuple[_ReceiptIdentity, Mapping[str, Any]]]] = {}
    reasons: list[str] = []
    for row in receipts:
        if row.get("leg_id") not in (None, "", expected_leg_id):
            continue
        try:
            identity = _ReceiptIdentity.model_validate(row)
        except ValueError:
            reasons.append("malformed_receipt")
            continue
        indexed.setdefault(identity.invocation_id, []).append((identity, row))
    finished = []
    for rows in indexed.values():
        if len(rows) != 2 or [identity.event for identity, _ in rows] != ["start", "finish"]:
            reasons.append("incomplete_or_duplicate_receipt")
            continue
        (start, _), (finish, body) = rows
        if start.model_dump(exclude={"event"}) != finish.model_dump(exclude={"event"}):
            reasons.append("receipt_identity_mismatch")
            continue
        if (
            type(body.get("returncode")) is not int
            or not isinstance(body.get("stdout"), str)
            or not isinstance(body.get("stderr"), str)
        ):
            reasons.append("malformed_receipt_outcome")
            continue
        finished.append(body)
    return finished, reasons


def _receipt_call(receipt: Mapping[str, Any]) -> ToolCall:
    return ToolCall(
        name="Bash",
        arguments={"command": shlex.join(["bd", *receipt["operation_argv"]])},
        result=receipt["stdout"],
        is_error=receipt["returncode"] != 0,
    )


def _receipt_before_action(
    task: ToolReqRealAgentTask,
    delivered: Sequence[tuple[ToolCall, Sequence[str]]],
    *,
    goal_writes: Sequence[ToolCall],
    ambiguous_goal: bool,
) -> tuple[bool | None, bool]:
    unknown_order = False
    for call in goal_writes:
        if call.tool_use_index is None:
            unknown_order = True
            continue
        before = [
            payload
            for read, payloads in delivered
            if read.tool_result_index is not None and read.tool_result_index < call.tool_use_index
            for payload in payloads
        ]
        if _contains_all(before, task.current_opaque_values):
            return True, unknown_order
        if any(read.tool_result_index is None for read, _ in delivered):
            unknown_order = True
    return (None if ambiguous_goal or unknown_order else False), unknown_order


def _observe_receipts(
    calls: Sequence[ToolCall], finished: Sequence[Mapping[str, Any]]
) -> tuple[list[MemoryInvocation], list[tuple[ToolCall, Sequence[str]]], list[str]]:
    reasons: list[str] = []
    calls_by_id: dict[str, list[ToolCall]] = {}
    for call in calls:
        if call.tool_use_id:
            calls_by_id.setdefault(call.tool_use_id, []).append(call)
    observed: list[MemoryInvocation] = []
    delivered: list[tuple[ToolCall, Sequence[str]]] = []
    matched_counts: dict[str, int] = {}
    for receipt in finished:
        matching = calls_by_id.get(receipt["tool_use_id"], [])
        if len(matching) != 1 or matching[0].name != "Bash":
            reasons.append("unmatched_receipt")
            continue
        call = matching[0]
        direct = _receipt_call(receipt)
        invocations = memory_invocations([direct])
        matched_counts[receipt["tool_use_id"]] = matched_counts.get(
            receipt["tool_use_id"], 0
        ) + len(invocations)
        observed.extend(invocations)
        reads = [inv for inv in invocations if inv.is_read or inv.is_recall_by_result]
        if not reads or direct.is_error:
            continue
        payloads = _read_content(reads[0], direct)
        if not payloads:
            continue
        if call.result is None or receipt["stdout"].strip() not in call.result:
            reasons.append("bd_output_not_observed_in_tool_result")
            continue
        delivered.append((call, payloads))
        if call.tool_result_index is None:
            reasons.append("missing_result_delivery_order")
    for call in calls:
        expected = len(memory_invocations([call]))
        if expected > matched_counts.get(call.tool_use_id or "", 0):
            reasons.append("missing_execution_receipt")
    return observed, delivered, reasons


def _score_receipts(
    task: ToolReqRealAgentTask,
    calls: Sequence[ToolCall],
    receipts: Sequence[Mapping[str, Any]],
    *,
    expected_leg_id: str,
    score_action: bool,
    goal_writes: Sequence[ToolCall],
    ambiguous_goal: bool,
) -> dict[str, Any]:
    finished, reasons = _finished_receipts(receipts, expected_leg_id=expected_leg_id)
    observed, delivered, observation_reasons = _observe_receipts(calls, finished)
    reasons.extend(observation_reasons)
    accepted = [inv for inv in observed if inv.is_accepted_write]
    before, ordering_unknown = (
        _receipt_before_action(
            task, delivered, goal_writes=goal_writes, ambiguous_goal=ambiguous_goal
        )
        if score_action
        else (False, False)
    )
    if ordering_unknown:
        reasons.append("missing_action_use_order")
    attempts = memory_invocations(calls)
    return {
        "bd_read_attempts": max(
            sum(inv.is_read or inv.is_recall_by_result for inv in attempts),
            sum(inv.is_read or inv.is_recall_by_result for inv in observed),
        ),
        "bd_write_attempts": max(
            sum(inv.is_write for inv in attempts), sum(inv.is_write for inv in observed)
        ),
        "bd_accepted_writes": len(accepted),
        "bd_capture_complete": _contains_all(
            [text for inv in accepted for text in inv.stored_content], task.current_opaque_values
        ),
        "bd_recall_complete": _contains_all(
            [text for _, payloads in delivered for text in payloads], task.current_opaque_values
        ),
        "bd_recall_before_action": before,
        "bd_unattributed_read_blocks": 0,
        "bd_unattributed_write_blocks": 0,
        "bd_evidence_unknown": bool(reasons),
        "bd_evidence_unknown_reasons": tuple(sorted(set(reasons))),
    }


def score_bd_leg(
    task: ToolReqRealAgentTask,
    calls: Sequence[ToolCall],
    *,
    leg: int,
    role: str,
    status: str,
    config_dir: Path | None,
    receipts: Sequence[Mapping[str, Any]] | None = None,
    expected_leg_id: str | None = None,
    cwd: Path | str | None = None,
) -> BdLegEvidence:
    """Separate attempts, acknowledged content, returned values and completed actions."""
    if receipts is not None and not expected_leg_id:
        raise ValueError("Receipt scoring requires an expected leg identity")
    goal_writes, ambiguous_goal = (
        _goal_writes(task, calls, cwd=cwd) if role == "goal" and status == "ok" else ((), False)
    )
    invocations = memory_invocations(calls)
    accepted = [
        inv
        for call in calls
        if memory_result_is_attributable(call)
        for inv in memory_invocations([call])
        if inv.is_accepted_write
    ]
    payloads, unattributed = _read_payloads(calls)
    native = native_memory_accesses(calls, config_dir=config_dir)
    return BdLegEvidence.model_validate(
        {
            "scoring_version": RELIABILITY_VERSION,
            "leg": leg,
            "role": role,
            "status": status,
            "bd_read_attempts": sum(inv.is_read or inv.is_recall_by_result for inv in invocations),
            "bd_write_attempts": sum(inv.is_write for inv in invocations),
            "bd_accepted_writes": len(accepted),
            "bd_unattributed_read_blocks": unattributed,
            "bd_unattributed_write_blocks": sum(
                any(inv.is_write for inv in memory_invocations([call]))
                for call in calls
                if not memory_result_is_attributable(call)
                and call.result is not None
                and not call.is_error
            ),
            "bd_capture_complete": _contains_all(
                [text for inv in accepted for text in inv.stored_content],
                task.current_opaque_values,
            ),
            "bd_recall_complete": _contains_all(payloads, task.current_opaque_values),
            "bd_recall_before_action": (
                _recall_before_action(
                    task, calls, goal_writes=goal_writes, ambiguous_goal=ambiguous_goal
                )
                if role == "goal" and status == "ok"
                else False
            ),
            "native_read_attempts": sum(access.is_read for access in native),
            "native_write_attempts": sum(access.is_write for access in native),
            "native_answered_reads": sum(
                access.is_read and access.satisfied is True for access in native
            ),
            "goal_action_success": (
                (True if goal_writes else None if ambiguous_goal else False)
                if role == "goal" and status == "ok"
                else None
            ),
            **(
                _score_receipts(
                    task,
                    calls,
                    receipts,
                    expected_leg_id=expected_leg_id or "",
                    score_action=role == "goal" and status == "ok",
                    goal_writes=goal_writes,
                    ambiguous_goal=ambiguous_goal,
                )
                if receipts is not None
                else {}
            ),
        }
    )


def _role_report(evidence: Sequence[BdLegEvidence], *, scheduled: int) -> dict[str, Any]:
    measured = [leg for leg in evidence if leg.status == "ok"]
    return {
        "scheduled": scheduled,
        "measured": len(measured),
        "bd_evidence_unknown_legs": sum(leg.bd_evidence_unknown for leg in evidence),
        "missing": scheduled - len(evidence),
        "timeout": sum(leg.status == "timeout" for leg in evidence),
        "error": sum(leg.status == "error" for leg in evidence),
        "bd_read_attempt_legs": sum(leg.bd_read_attempts > 0 for leg in measured),
        "bd_write_attempt_legs": sum(leg.bd_write_attempts > 0 for leg in measured),
        "bd_accepted_write_legs": sum(leg.bd_accepted_writes > 0 for leg in measured),
        "bd_capture_complete_legs": sum(leg.bd_capture_complete for leg in measured),
        "bd_recall_complete_legs": sum(leg.bd_recall_complete for leg in measured),
        "bd_unattributed_read_blocks": sum(leg.bd_unattributed_read_blocks for leg in measured),
        "bd_unattributed_write_blocks": sum(leg.bd_unattributed_write_blocks for leg in measured),
        "native_read_attempt_legs": sum(leg.native_read_attempts > 0 for leg in measured),
        "native_write_attempt_legs": sum(leg.native_write_attempts > 0 for leg in measured),
        "native_answered_read_legs": sum(leg.native_answered_reads > 0 for leg in measured),
        "goal_action_success_legs": sum(
            leg.goal_action_success is True and leg.scoring_version == RELIABILITY_VERSION
            for leg in measured
        ),
        "legacy_goal_action_success_legs": sum(
            leg.goal_action_success is True and leg.scoring_version != RELIABILITY_VERSION
            for leg in measured
        ),
        "legacy_evidence_legs": sum(leg.scoring_version != RELIABILITY_VERSION for leg in evidence),
    }


def _index_legs(raw: Sequence[Any], *, runs: int) -> dict[int, BdLegEvidence]:
    indexed: dict[int, BdLegEvidence] = {}
    if runs <= 0 or runs % len(ROLES):
        raise ValueError("bd reliability requires a positive number of two-leg pairs")
    for row in raw:
        leg = BdLegEvidence.model_validate(row)
        if leg.leg in indexed:
            raise ValueError(f"duplicate bd evidence for leg {leg.leg}")
        if leg.leg >= runs or leg.role != ROLES[leg.leg % len(ROLES)]:
            raise ValueError(f"leg {leg.leg}: invalid role or position in two-leg pair")
        indexed[leg.leg] = leg
    return indexed


def _bd_component(
    leg: BdLegEvidence | None,
    field: Literal["bd_capture_complete", "bd_recall_complete", "bd_recall_before_action"],
) -> bool | None:
    if leg is None or leg.status != "ok":
        return None
    if field == "bd_recall_before_action" and leg.scoring_version != RELIABILITY_VERSION:
        return None
    if getattr(leg, field) is None:
        return None
    if getattr(leg, field):
        return True
    return None if leg.bd_evidence_unknown else False


def _pair_report(indexed: Mapping[int, BdLegEvidence], *, runs: int) -> dict[str, Any]:
    pairs = [(indexed.get(i), indexed.get(i + 1)) for i in range(0, runs, len(ROLES))]
    components = [
        (
            _bd_component(first, "bd_capture_complete"),
            _bd_component(goal, "bd_recall_complete"),
            (
                goal.goal_action_success
                if goal is not None
                and goal.status == "ok"
                and goal.scoring_version == RELIABILITY_VERSION
                else None
            ),
            _bd_component(goal, "bd_recall_before_action"),
        )
        for first, goal in pairs
    ]
    handoffs = [
        False if False in values else True if all(value is True for value in values) else None
        for values in components
    ]
    measured_complete = sum(
        first is not None
        and goal is not None
        and first.status == goal.status == "ok"
        and goal.goal_action_success is not None
        and goal.bd_recall_before_action is not None
        and first.scoring_version == goal.scoring_version == RELIABILITY_VERSION
        and not first.bd_evidence_unknown
        and not goal.bd_evidence_unknown
        for first, goal in pairs
    )
    unknown = sum(outcome is None for outcome in handoffs)
    return {
        "scheduled": len(pairs),
        "complete": len(pairs) - unknown,
        "unknown": unknown,
        "measurement_incomplete": len(pairs) - measured_complete,
        "bd_capture_complete": sum(values[0] is True for values in components),
        "bd_recall_complete": sum(values[1] is True for values in components),
        "goal_action_success": sum(values[2] is True for values in components),
        "bd_handoff_observed": sum(outcome is True for outcome in handoffs),
    }


def _bounds(pairs: Mapping[str, Any]) -> list[float]:
    return [
        pairs["bd_handoff_observed"] / pairs["scheduled"],
        (pairs["bd_handoff_observed"] + pairs["unknown"]) / pairs["scheduled"],
    ]


def _task_report(row: Mapping[str, Any]) -> dict[str, Any]:
    runs = int(row["metrics"]["runs"])
    indexed = _index_legs(row.get("bd_evidence", ()), runs=runs)
    return {
        "rung": row["rung"],
        "variant": row["variant"],
        "work_id": row["work_id"],
        "native_memory_pinned_off": row["native_memory_pinned_off"],
        "evidence_versions": sorted({leg.scoring_version for leg in indexed.values()}),
        "roles": {
            role: _role_report(
                [leg for leg in indexed.values() if leg.role == role], scheduled=runs // len(ROLES)
            )
            for role in ROLES
        },
        "pairs": _pair_report(indexed, runs=runs),
    }


def _group_reports(tasks: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = sorted({(task["rung"], task["variant"]) for task in tasks})
    groups: list[dict[str, Any]] = []
    for rung, variant in keys:
        selected = [task for task in tasks if (task["rung"], task["variant"]) == (rung, variant)]
        pins = {task["native_memory_pinned_off"] for task in selected}
        if len(pins) != 1:
            raise ValueError(f"{rung}/{variant}: mixed native memory settings")
        pairs = {key: sum(task["pairs"][key] for task in selected) for key in selected[0]["pairs"]}
        groups.append(
            {
                "rung": rung,
                "variant": variant,
                "tasks": len(selected),
                "native_memory_pinned_off": selected[0]["native_memory_pinned_off"],
                "roles": {
                    role: {
                        key: sum(task["roles"][role][key] for task in selected)
                        for key in selected[0]["roles"][role]
                    }
                    for role in ROLES
                },
                "pairs": {**pairs, "rate_bounds": _bounds(pairs)},
            }
        )
    return groups


def reliability_report(cells: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate within task/repeat first; legacy cells never acquire invented outcomes."""
    keys = [(row["rung"], row["variant"], row["work_id"]) for row in cells]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate cell in bd reliability evidence")
    evidenced = sum(bool(row.get("bd_evidence")) for row in cells)
    tasks = [_task_report(row) for row in cells] if evidenced else []
    groups = _group_reports(tasks)
    return {
        "version": RELIABILITY_VERSION,
        "evidence_versions": sorted(
            {version for task in tasks for version in task["evidence_versions"]}
        ),
        "endpoint": "bd_handoff_observed",
        "primary_variant": "necessary",
        "status": (
            "measured"
            if tasks and all(task["pairs"]["measurement_incomplete"] == 0 for task in tasks)
            else "partial" if tasks else "unmeasured"
        ),
        "cells_without_evidence": len(cells) - evidenced,
        "same_native_settings_across_rungs": (
            len({group["native_memory_pinned_off"] for group in groups}) <= 1 if groups else None
        ),
        "groups": groups,
        "per_task": [
            {**task, "pairs": {**task["pairs"], "rate_bounds": _bounds(task["pairs"])}}
            for task in tasks
        ],
        "interpretation": (
            "Capture all required values in acknowledged bd writes during establish, receive all "
            "values in authenticated bd output delivered in tool results before completing a goal "
            "config.json Write whose decoded JSON string values carry the required tokens. "
            "This is an observed conjunction, not causal attribution. Bounds assign unknown pairs "
            "failure/success; they are not confidence intervals. Legacy compound shell reads "
            "remain unattributed. Complete counts decidable handoff outcomes; "
            "Unversioned cached action/order scores remain unknown until rescored; "
            "measurement_incomplete "
            "retains receipt/leg gaps even when an outcome is already known. Task rows "
            "support paired, task-clustered analysis; repeat legs are not "
            "independent tasks. Native answered reads only mean the tool returned without an error."
        ),
    }
