#!/usr/bin/env python3
import json
import sys
from datetime import datetime

def parse_timestamp(ts_str):
    return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))

def summarize_receipts(protocol, receipts):
    if not receipts:
        return {"protocol": protocol, "accepted_count": 0, "duplicate_count": 0}

    deliveries = {}
    for receipt in receipts:
        if protocol == "1":
            key = (receipt["account_id"], receipt["delivery_id"])
        else:
            key = receipt["delivery_id"]
        if key not in deliveries:
            deliveries[key] = []
        deliveries[key].append(receipt)

    accepted_count = 0
    duplicate_count = 0

    for receipts_for_delivery in deliveries.values():
        accepted = min(
            receipts_for_delivery,
            key=lambda r: (parse_timestamp(r["occurred_at"]), r["record_id"])
        )
        accepted_count += 1
        duplicate_count += len(receipts_for_delivery) - 1

    return {"protocol": protocol, "accepted_count": accepted_count, "duplicate_count": duplicate_count}

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}

    if q.get("command") == "count":
        protocol = q.get("protocol", "2")
        receipts = q.get("receipts", [])
        return summarize_receipts(protocol, receipts)

    if q.get("command") == "summary":
        protocol = q.get("protocol", "2")
        receipts = q.get("receipts", [])
        return summarize_receipts(protocol, receipts)

    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
