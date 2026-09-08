#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT_PROTOCOL = "1"

def tally(receipts):
    best = {}
    for r in receipts:
        key = (datetime.fromisoformat(r["occurred_at"]), r["record_id"])
        delivery_id = r["delivery_id"]
        if delivery_id not in best or key < best[delivery_id]:
            best[delivery_id] = key
    accepted_count = len(best)
    return accepted_count, len(receipts) - accepted_count

def counts(q):
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    accepted_count, duplicate_count = tally(q.get("receipts", []))
    return {
        "protocol": protocol,
        "accepted_count": accepted_count,
        "duplicate_count": duplicate_count,
    }

def run(q):
    command = q.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command in ("count", "summary"):
        return counts(q)
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
