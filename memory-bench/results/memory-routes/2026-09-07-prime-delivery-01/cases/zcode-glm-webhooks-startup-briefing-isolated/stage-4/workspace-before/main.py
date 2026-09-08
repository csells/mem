#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT_PROTOCOL = "2"
SUPPORTED_PROTOCOLS = ("1", "2")

def parse_occurred_at(text):
    if text[-1] in "Zz":
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)

def protocol_counts(q):
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    if protocol not in SUPPORTED_PROTOCOLS:
        return {"error": "unsupported_protocol"}
    receipts = q.get("receipts", [])
    accepted = {}
    for r in receipts:
        if protocol == "1":
            # Protocol 1: (account_id, delivery_id) identifies a delivery; the
            # earliest occurred_at UTC instant wins, ties by smallest record_id.
            identity = (r["account_id"], r["delivery_id"])
            rank = (parse_occurred_at(r["occurred_at"]), r["record_id"])
        else:
            # Protocol 2: delivery_id alone identifies a delivery across all
            # accounts; the latest UTC instant wins, ties by smallest record_id.
            # The instant is negated so the smallest rank still wins; epoch
            # seconds at second precision are exact as floats.
            identity = r["delivery_id"]
            rank = (-parse_occurred_at(r["occurred_at"]).timestamp(), r["record_id"])
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
