"""Receipt-grounded memory use, independent of task answers or semantic judgments.

Receipts are trusted harness artifacts, not cryptographic proof against an agent
editing its instrumentation. Counts establish execution and delivery, not usefulness.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict

from membench.runner.e1_reliability import _finished_receipts, _read_content, _receipt_call
from membench.runner.tool_surface import (
    MemoryInvocation,
    memory_invocations,
    memory_result_is_attributable,
)
from membench.schemas.trace import ToolCall


class RealOperation(BaseModel):
    """One validated completed execution; raw content supports later blinded review."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    invocation_id: str
    tool_use_id: str
    session_id: str
    argv: tuple[str, ...]
    stdout: str
    stderr: str
    returncode: int
    tool_use_index: int | None
    tool_result_index: int | None
    is_read: bool
    is_write: bool
    accepted_write: bool
    output_observed: bool
    content: tuple[str, ...]
    payload_known: bool


class RealLegEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    scoring_version: int = 1
    leg_id: str
    status: str
    syntactic_read_attempts: int
    syntactic_write_attempts: int
    executed_reads: int
    executed_writes: int
    accepted_writes: int
    observed_reads: int
    observed_content_reads: int
    empty_reads: int
    exposure_commands: int
    evidence_unknown: bool
    unknown_reasons: tuple[str, ...]
    operations: tuple[RealOperation, ...]


def _execution_valid(
    row: Mapping[str, Any],
    start: Mapping[str, Any],
    *,
    expected_binary: str | None,
    expected_store: str | None,
    expected_session: str | None,
) -> bool:
    argv = row.get("argv")
    if (
        not isinstance(argv, list)
        or not all(isinstance(value, str) for value in argv)
        or len(argv) < 4
        or argv[1] != "-C"
        or not PurePosixPath(argv[0]).is_absolute()
        or not PurePosixPath(argv[2]).is_absolute()
        or argv[3:] != row["operation_argv"]
        or argv != start.get("argv")
        or (expected_binary is not None and argv[0] != expected_binary)
        or (expected_store is not None and argv[2] != expected_store)
        or (expected_session is not None and row["session_id"] != expected_session)
    ):
        return False
    begin, end = row.get("start_monotonic_ns"), row.get("end_monotonic_ns")
    if (
        type(begin) is not int
        or type(end) is not int
        or end < begin
        or begin != start.get("start_monotonic_ns")
    ):
        return False
    for field in ("stdout", "stderr"):
        encoded = row.get(f"{field}_base64")
        if not isinstance(encoded, str):
            return False
        try:
            decoded = base64.b64decode(encoded, validate=True).decode("utf-8", errors="replace")
        except (ValueError, binascii.Error):
            return False
        if decoded != row[field]:
            return False
    return True


def _payload(
    invocation: MemoryInvocation, direct: ToolCall, argv: Sequence[str]
) -> tuple[tuple[str, ...], bool]:
    if "--json" not in argv:
        return tuple(value for value in _read_content(invocation, direct) if value.strip()), True
    try:
        body = json.loads(direct.result or "")
    except ValueError:
        return (), False
    if not isinstance(body, dict):
        return (), False
    if invocation.verb == "memories":
        if "schema_version" not in body or any(
            not isinstance(value, str) for key, value in body.items() if key != "schema_version"
        ):
            return (), False
        return (
            tuple(
                value for key, value in body.items() if key != "schema_version" and value.strip()
            ),
            True,
        )
    if body.get("found") is False:
        return (), True
    if body.get("found") is True or invocation.is_recall_by_result:
        value = body.get("value")
        if isinstance(value, str):
            return (value,) if value.strip() else (), True
    return (), False


def _operation(row: Mapping[str, Any], call: ToolCall) -> RealOperation:
    direct = _receipt_call(row)
    invocations = memory_invocations([direct])
    invocation = invocations[0] if invocations else None
    read = bool(invocation and (invocation.is_read or invocation.is_recall_by_result))
    write = bool(invocation and invocation.is_write and not invocation.is_recall_by_result)
    accepted = bool(invocation and invocation.is_accepted_write)
    content: tuple[str, ...] = ()
    payload_known = True
    if invocation:
        if read and row["returncode"] == 0:
            content, payload_known = _payload(invocation, direct, row["operation_argv"])
        elif write:
            content = invocation.stored_content
    # Empty stdout cannot demonstrate delivery by a vacuous substring match.
    # CLI tool results trim boundary whitespace; internal payload text stays exact.
    visible_text = row["stdout"].strip()
    observed = bool(visible_text and call.result is not None and visible_text in call.result)
    return RealOperation(
        invocation_id=row["invocation_id"],
        tool_use_id=row["tool_use_id"],
        session_id=row["session_id"],
        argv=tuple(row["operation_argv"]),
        stdout=row["stdout"],
        stderr=row["stderr"],
        returncode=row["returncode"],
        tool_use_index=call.tool_use_index,
        tool_result_index=call.tool_result_index,
        is_read=read,
        is_write=write,
        accepted_write=accepted,
        output_observed=observed,
        content=content,
        payload_known=payload_known,
    )


def _delivery_reasons(operation: RealOperation) -> list[str]:
    reasons = []
    if not operation.payload_known:
        reasons.append("unrecognized_read_payload")
    if operation.is_read and operation.returncode == 0 and operation.content:
        if not operation.output_observed:
            reasons.append("bd_output_not_observed_in_tool_result")
        elif operation.tool_result_index is None:
            reasons.append("missing_result_delivery_order")
    return reasons


def _validated_operations(
    calls: Sequence[ToolCall],
    receipts: Sequence[Mapping[str, Any]],
    finished: Sequence[Mapping[str, Any]],
    *,
    expected_binary: str | None,
    expected_store: str | None,
    expected_session: str | None,
) -> tuple[list[RealOperation], list[str]]:
    reasons: list[str] = []
    operations: list[RealOperation] = []
    for row in finished:
        starts = [
            r
            for r in receipts
            if r.get("invocation_id") == row["invocation_id"] and r.get("event") == "start"
        ]
        matching = [call for call in calls if call.tool_use_id == row["tool_use_id"]]
        if len(matching) != 1 or matching[0].name != "Bash":
            reasons.append("unmatched_receipt")
            continue
        if len(starts) != 1 or not _execution_valid(
            row,
            starts[0],
            expected_binary=expected_binary,
            expected_store=expected_store,
            expected_session=expected_session,
        ):
            reasons.append("invalid_execution_receipt")
            continue
        operation = _operation(row, matching[0])
        operations.append(operation)
        reasons.extend(_delivery_reasons(operation))
    return operations, reasons


def score_real_leg(
    calls: Sequence[ToolCall],
    receipts: Sequence[Mapping[str, Any]],
    *,
    leg_id: str,
    status: str,
    expected_binary: str | None = None,
    expected_store: str | None = None,
    expected_session: str | None = None,
) -> RealLegEvidence:
    """Count actual memory operations; optional pins bind evidence to the run manifest.

    Static shell mentions are attempts only: an untaken branch needs no execution
    receipt. Direct memory calls without receipts remain unknown. Successful reads
    with absent output are executed but not observed. No ordering means unknown
    delivery timing; it does not erase an otherwise observed payload.
    """
    finished, reasons = _finished_receipts(receipts, expected_leg_id=leg_id)
    if not leg_id.strip():
        raise ValueError("leg_id must be nonempty")
    if status in ("timeout", "error"):
        reasons.append("incomplete_leg")
    if status not in ("ok", "timeout", "error"):
        reasons.append("unknown_status")
    if any(row.get("leg_id") != leg_id for row in receipts):
        reasons.append("receipt_leg_mismatch")
    operations, operation_reasons = _validated_operations(
        calls,
        receipts,
        finished,
        expected_binary=expected_binary,
        expected_store=expected_store,
        expected_session=expected_session,
    )
    reasons.extend(operation_reasons)
    matched_ids = {operation.tool_use_id for operation in operations}
    for call in calls:
        if (
            memory_invocations([call])
            # Reuse only the command-shape check, independent of tool outcome.
            and memory_result_is_attributable(
                call.model_copy(update={"is_error": False, "result": ""})
            )
            and call.tool_use_id not in matched_ids
        ):
            reasons.append("missing_direct_execution_receipt")
    return _summarize_leg(calls, operations, reasons, leg_id=leg_id, status=status)


def _summarize_leg(
    calls: Sequence[ToolCall],
    operations: Sequence[RealOperation],
    reasons: Sequence[str],
    *,
    leg_id: str,
    status: str,
) -> RealLegEvidence:
    attempts = memory_invocations(calls)
    reads = [operation for operation in operations if operation.is_read]
    observed = [
        operation for operation in reads if operation.returncode == 0 and operation.output_observed
    ]
    return RealLegEvidence(
        leg_id=leg_id,
        status=status,
        syntactic_read_attempts=sum(inv.is_read or inv.is_recall_by_result for inv in attempts),
        syntactic_write_attempts=sum(inv.is_write for inv in attempts),
        executed_reads=len(reads),
        executed_writes=sum(op.is_write for op in operations),
        accepted_writes=sum(op.accepted_write for op in operations),
        observed_reads=len(observed),
        observed_content_reads=sum(bool(op.content) for op in observed),
        empty_reads=sum(op.returncode == 0 and op.payload_known and not op.content for op in reads),
        exposure_commands=sum(not op.is_read and not op.is_write for op in operations),
        evidence_unknown=bool(reasons),
        unknown_reasons=tuple(sorted(set(reasons))),
        operations=tuple(operations),
    )
