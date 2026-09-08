#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone


def utc_instant(timestamp):
    """Convert the protocol's RFC3339 timestamp to a comparable UTC instant."""
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(timezone.utc)


def count_receipts(receipts):
    """Return protocol-1 acceptance counts for a complete receipt set."""
    accepted_by_delivery = {}
    for receipt in receipts:
        candidate_key = (utc_instant(receipt["occurred_at"]), receipt["record_id"])
        delivery_id = receipt["delivery_id"]
        current = accepted_by_delivery.get(delivery_id)
        if current is None or candidate_key < current[0]:
            accepted_by_delivery[delivery_id] = (candidate_key, receipt)

    accepted_ids = {receipt["record_id"] for _, receipt in accepted_by_delivery.values()}
    accepted_count = sum(receipt["record_id"] in accepted_ids for receipt in receipts)
    return {
        "protocol": "1",
        "accepted_count": accepted_count,
        "duplicate_count": len(receipts) - accepted_count,
    }

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") == "count":
        return count_receipts(q["receipts"])
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
