#!/usr/bin/env python3
import json
import sys
from datetime import datetime

def parse_rfc3339(timestamp_str):
    timestamp_str = timestamp_str.replace('Z', '+00:00')
    return datetime.fromisoformat(timestamp_str)

def count_receipts(receipts):
    if not receipts:
        return {"accepted_count": 0, "duplicate_count": 0}

    deliveries = {}

    for receipt in receipts:
        key = (receipt["account_id"], receipt["delivery_id"])
        if key not in deliveries:
            deliveries[key] = []
        deliveries[key].append(receipt)

    accepted_count = 0
    duplicate_count = 0

    for delivery_receipts in deliveries.values():
        if len(delivery_receipts) == 1:
            accepted_count += 1
        else:
            accepted = min(
                delivery_receipts,
                key=lambda r: (parse_rfc3339(r["occurred_at"]), r["record_id"])
            )
            accepted_count += 1
            duplicate_count += len(delivery_receipts) - 1

    return {
        "accepted_count": accepted_count,
        "duplicate_count": duplicate_count
    }

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") == "count":
        protocol = q.get("protocol", "1")
        receipts = q.get("receipts", [])
        result = count_receipts(receipts)
        result["protocol"] = protocol
        return result
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
