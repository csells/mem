#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT_PROTOCOL = "1"
SUPPORTED_PROTOCOLS = {"1"}


def parse_instant(occurred_at):
    return datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))


def count(receipts):
    winners = {}
    for receipt in receipts:
        delivery_id = receipt["delivery_id"]
        key = (parse_instant(receipt["occurred_at"]), receipt["record_id"])
        best = winners.get(delivery_id)
        if best is None or key < best:
            winners[delivery_id] = key
    accepted_count = len(winners)
    return {
        "accepted_count": accepted_count,
        "duplicate_count": len(receipts) - accepted_count,
    }


def run(q):
    command = q.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command == "count":
        protocol = q.get("protocol", CURRENT_PROTOCOL)
        if protocol not in SUPPORTED_PROTOCOLS:
            return {"error": "unsupported_protocol"}
        result = count(q["receipts"])
        return {"protocol": protocol, **result}
    return {"error": "unknown_command"}


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
