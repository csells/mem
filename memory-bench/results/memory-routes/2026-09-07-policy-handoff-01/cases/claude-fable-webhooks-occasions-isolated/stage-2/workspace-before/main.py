#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT_PROTOCOL = "1"
SUPPORTED_PROTOCOLS = {"1"}


def parse_instant(text):
    """Parse an RFC3339 timestamp (Z or explicit numeric offset) to a UTC instant."""
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def select_protocol(q):
    protocol = q.get("protocol")
    if protocol is None:
        return CURRENT_PROTOCOL
    return protocol if protocol in SUPPORTED_PROTOCOLS else None


def accepted_receipts_v1(receipts):
    """Protocol 1: one accepted receipt per (account_id, delivery_id).

    Earliest occurred_at UTC instant wins; ties use the smallest record_id
    (Unicode code-point order). Accepted receipts keep original input order.
    """
    winners = {}
    for index, receipt in enumerate(receipts):
        identity = (receipt["account_id"], receipt["delivery_id"])
        key = (parse_instant(receipt["occurred_at"]), receipt["record_id"])
        current = winners.get(identity)
        if current is None or key < current[0]:
            winners[identity] = (key, index)
    accepted_indexes = sorted(index for _, index in winners.values())
    return [receipts[i] for i in accepted_indexes]


def count(q):
    protocol = select_protocol(q)
    if protocol is None:
        return {"error": "unsupported_protocol"}
    receipts = q.get("receipts", [])
    accepted = accepted_receipts_v1(receipts)
    return {
        "protocol": protocol,
        "accepted_count": len(accepted),
        "duplicate_count": len(receipts) - len(accepted),
    }


def run(q):
    command = q.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command == "count":
        return count(q)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
