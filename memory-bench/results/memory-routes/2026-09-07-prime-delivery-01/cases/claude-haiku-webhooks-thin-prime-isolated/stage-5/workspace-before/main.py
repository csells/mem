#!/usr/bin/env python3
import json
import sys
from datetime import datetime

def parse_rfc3339(timestamp_str):
    timestamp_str = timestamp_str.replace('Z', '+00:00')
    return datetime.fromisoformat(timestamp_str)

def count_receipts(receipts, protocol="2"):
    if not receipts:
        return {"accepted_count": 0, "duplicate_count": 0}

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

    for delivery_receipts in deliveries.values():
        if len(delivery_receipts) == 1:
            accepted_count += 1
        else:
            accepted = min(
                delivery_receipts,
                key=lambda r: (-parse_rfc3339(r["occurred_at"]).timestamp(), r["record_id"])
            )
            accepted_count += 1
            duplicate_count += len(delivery_receipts) - 1

    return {
        "accepted_count": accepted_count,
        "duplicate_count": duplicate_count
    }

def get_accepted_receipts(receipts, protocol="2"):
    if not receipts:
        return [], 0, 0

    deliveries = {}
    original_indices = {}

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
    accepted_receipts = {}

    for delivery_receipts in deliveries.values():
        if len(delivery_receipts) == 1:
            original_index, receipt = delivery_receipts[0]
            accepted_receipts[original_index] = receipt
            accepted_count += 1
        else:
            accepted_original_index, accepted_receipt = min(
                delivery_receipts,
                key=lambda r: (-parse_rfc3339(r[1]["occurred_at"]).timestamp(), r[1]["record_id"])
            )
            accepted_receipts[accepted_original_index] = accepted_receipt
            accepted_count += 1
            duplicate_count += len(delivery_receipts) - 1

    result = [accepted_receipts[i] for i in sorted(accepted_receipts.keys())]
    return result, accepted_count, duplicate_count

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") == "count":
        protocol = q.get("protocol", "2")
        receipts = q.get("receipts", [])
        result = count_receipts(receipts, protocol)
        result["protocol"] = protocol
        return result
    if q.get("command") == "summary":
        protocol = q.get("protocol", "2")
        receipts = q.get("receipts", [])
        result = count_receipts(receipts, protocol)
        result["protocol"] = protocol
        return result
    if q.get("command") == "accepted":
        protocol = q.get("protocol", "2")
        receipts = q.get("receipts", [])
        accepted_list, accepted_count, duplicate_count = get_accepted_receipts(receipts, protocol)
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count,
            "receipts": accepted_list
        }
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
