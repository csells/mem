#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT_PROTOCOL = "1"

def count(q):
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    best = {}
    for r in q.get("receipts", []):
        key = (datetime.fromisoformat(r["occurred_at"]), r["record_id"])
        delivery_id = r["delivery_id"]
        if delivery_id not in best or key < best[delivery_id]:
            best[delivery_id] = key
    accepted_count = len(best)
    total = len(q.get("receipts", []))
    return {
        "protocol": protocol,
        "accepted_count": accepted_count,
        "duplicate_count": total - accepted_count,
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
