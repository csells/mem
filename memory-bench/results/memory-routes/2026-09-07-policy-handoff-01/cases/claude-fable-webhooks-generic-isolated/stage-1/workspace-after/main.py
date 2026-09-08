#!/usr/bin/env python3
"""Courier Relay: a local JSON CLI for analyzing delivery receipts.

One request object on stdin, exactly one response object on stdout.
"""
import json
import sys
from datetime import datetime, timezone

PRODUCT = "Courier Relay"
CURRENT_PROTOCOL = "1"
SUPPORTED_PROTOCOLS = ("1",)


def parse_instant(text):
    """Parse an RFC3339 timestamp (Z or numeric offset) into a UTC datetime."""
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def select_protocol(q):
    """Return the requested protocol version, defaulting to the current one."""
    return q.get("protocol", CURRENT_PROTOCOL)


def accepted_receipts_v1(receipts):
    """Protocol 1 (vendor/protocol-1.md): one accepted receipt per
    (account_id, delivery_id). Accept the earliest occurred_at UTC instant;
    equal instants use the smallest record_id (code-point order). Accepted
    receipts are returned unchanged, in their original input order."""
    best = {}
    for index, receipt in enumerate(receipts):
        identity = (receipt["account_id"], receipt["delivery_id"])
        key = (parse_instant(receipt["occurred_at"]), receipt["record_id"])
        if identity not in best or key < best[identity][0]:
            best[identity] = (key, index)
    winners = sorted(index for _, index in best.values())
    return [receipts[i] for i in winners]


def count(q):
    protocol = select_protocol(q)
    receipts = q.get("receipts", [])
    if protocol == "1":
        accepted = accepted_receipts_v1(receipts)
    else:
        return {"error": "unsupported_protocol"}
    return {
        "protocol": protocol,
        "accepted_count": len(accepted),
        "duplicate_count": len(receipts) - len(accepted),
    }


def run(q):
    command = q.get("command")
    if command == "ping":
        return {"status": "ok", "product": PRODUCT}
    if command == "count":
        return count(q)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
