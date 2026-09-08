#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone


def _occurred_at_utc(receipt):
    timestamp = receipt["occurred_at"].replace("Z", "+00:00")
    return datetime.fromisoformat(timestamp).astimezone(timezone.utc)


def _count_receipts(receipts):
    accepted = {}
    for receipt in receipts:
        delivery_id = receipt["delivery_id"]
        current = accepted.get(delivery_id)
        if current is None:
            accepted[delivery_id] = receipt
            continue

        candidate_key = (_occurred_at_utc(receipt), receipt["record_id"])
        current_key = (_occurred_at_utc(current), current["record_id"])
        if candidate_key < current_key:
            accepted[delivery_id] = receipt

    accepted_count = len(accepted)
    return {
        "protocol": "1",
        "accepted_count": accepted_count,
        "duplicate_count": len(receipts) - accepted_count,
    }

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") == "count":
        return _count_receipts(q["receipts"])
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
