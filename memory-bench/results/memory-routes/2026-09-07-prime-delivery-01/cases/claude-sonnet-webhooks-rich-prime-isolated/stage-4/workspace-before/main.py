#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT_PROTOCOL = "2"
SUPPORTED_PROTOCOLS = {"1", "2"}


def parse_instant(occurred_at):
    return datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))


def identity(receipt, protocol):
    if protocol == "2":
        return (receipt["account_id"], receipt["delivery_id"])
    return receipt["delivery_id"]


def count(receipts, protocol):
    winners = {}
    for receipt in receipts:
        key_id = identity(receipt, protocol)
        key = (parse_instant(receipt["occurred_at"]), receipt["record_id"])
        best = winners.get(key_id)
        if best is None or key < best:
            winners[key_id] = key
    accepted_count = len(winners)
    return {
        "accepted_count": accepted_count,
        "duplicate_count": len(receipts) - accepted_count,
    }


def run(q):
    command = q.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command in ("count", "summary"):
        protocol = q.get("protocol", CURRENT_PROTOCOL)
        if protocol not in SUPPORTED_PROTOCOLS:
            return {"error": "unsupported_protocol"}
        result = count(q["receipts"], protocol)
        return {"protocol": protocol, **result}
    return {"error": "unknown_command"}


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
