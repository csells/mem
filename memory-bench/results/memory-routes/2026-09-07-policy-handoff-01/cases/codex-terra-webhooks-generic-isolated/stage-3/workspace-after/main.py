#!/usr/bin/env python3
"""Courier Relay's one-request JSON command-line interface."""

from datetime import datetime, timezone
import json
import sys


CURRENT_PROTOCOL = "2"
SUPPORTED_PROTOCOLS = {"1", "2"}


def utc_instant(timestamp):
    """Return an RFC3339 timestamp as a comparable UTC-aware datetime."""
    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"
    return datetime.fromisoformat(timestamp).astimezone(timezone.utc)


def accepted_receipts(receipts, protocol):
    """Select one receipt per delivery identity, preserving input order."""
    selected = {}

    for index, receipt in enumerate(receipts):
        identity = (
            receipt["delivery_id"]
            if protocol == "1"
            else (receipt["account_id"], receipt["delivery_id"])
        )
        candidate = (utc_instant(receipt["occurred_at"]), receipt["record_id"], index, receipt)
        previous = selected.get(identity)

        if previous is None:
            selected[identity] = candidate
            continue

        candidate_time, candidate_id = candidate[:2]
        previous_time, previous_id = previous[:2]
        if protocol == "1":
            wins = candidate_time < previous_time or (
                candidate_time == previous_time and candidate_id < previous_id
            )
        else:
            wins = candidate_time > previous_time or (
                candidate_time == previous_time and candidate_id < previous_id
            )
        if wins:
            selected[identity] = candidate

    return [candidate[3] for candidate in sorted(selected.values(), key=lambda candidate: candidate[2])]


def receipt_result(receipts, protocol):
    accepted = accepted_receipts(receipts, protocol)
    return {
        "protocol": protocol,
        "accepted_count": len(accepted),
        "duplicate_count": len(receipts) - len(accepted),
    }


def run(query):
    command = query.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command not in {"count", "summary"}:
        return {"error": "unknown_command"}

    protocol = query.get("protocol", CURRENT_PROTOCOL)
    if protocol not in SUPPORTED_PROTOCOLS:
        return {"error": "unsupported_protocol"}
    return receipt_result(query["receipts"], protocol)


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
