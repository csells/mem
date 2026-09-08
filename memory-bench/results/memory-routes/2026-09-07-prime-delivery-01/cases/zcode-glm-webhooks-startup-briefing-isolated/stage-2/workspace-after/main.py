#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT_PROTOCOL = "1"
SUPPORTED_PROTOCOLS = ("1",)

def parse_occurred_at(text):
    if text[-1] in "Zz":
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)

def protocol_counts(q):
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    if protocol not in SUPPORTED_PROTOCOLS:
        return {"error": "unsupported_protocol"}
    receipts = q.get("receipts", [])
    # Protocol 1: (account_id, delivery_id) identifies a delivery; accept the
    # earliest occurred_at UTC instant, ties broken by smallest record_id.
    accepted = {}
    for r in receipts:
        identity = (r["account_id"], r["delivery_id"])
        rank = (parse_occurred_at(r["occurred_at"]), r["record_id"])
        if identity not in accepted or rank < accepted[identity]:
            accepted[identity] = rank
    return {
        "protocol": protocol,
        "accepted_count": len(accepted),
        "duplicate_count": len(receipts) - len(accepted),
    }

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") in ("count", "summary"):
        return protocol_counts(q)
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
