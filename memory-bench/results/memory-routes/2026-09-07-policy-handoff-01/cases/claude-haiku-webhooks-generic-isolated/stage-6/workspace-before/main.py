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

def get_accepted_receipts(protocol, receipts):
    if not receipts:
        return {"protocol": protocol, "accepted_count": 0, "duplicate_count": 0, "receipts": []}

    deliveries = {}
    for i, receipt in enumerate(receipts):
        if protocol == "1":
            key = (receipt["account_id"], receipt["delivery_id"])
        else:
            key = receipt["delivery_id"]
        if key not in deliveries:
            deliveries[key] = []
        deliveries[key].append((i, receipt))

    accepted_count = 0
    duplicate_count = 0
    accepted_indices = set()

    for receipts_for_delivery in deliveries.values():
        accepted_idx, accepted_receipt = min(
            receipts_for_delivery,
            key=lambda x: (parse_timestamp(x[1]["occurred_at"]), x[1]["record_id"])
        )
        accepted_indices.add(accepted_idx)
        accepted_count += 1
        duplicate_count += len(receipts_for_delivery) - 1

    accepted_receipts = [receipt for i, receipt in enumerate(receipts) if i in accepted_indices]
    return {"protocol": protocol, "accepted_count": accepted_count, "duplicate_count": duplicate_count, "receipts": accepted_receipts}

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

    if q.get("command") == "accepted":
        protocol = q.get("protocol", "2")
        receipts = q.get("receipts", [])
        return get_accepted_receipts(protocol, receipts)

    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
