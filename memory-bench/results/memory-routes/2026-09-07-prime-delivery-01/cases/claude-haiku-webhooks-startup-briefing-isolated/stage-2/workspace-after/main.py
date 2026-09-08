#!/usr/bin/env python3
import json
import sys
from datetime import datetime

def parse_iso8601(timestamp_str):
    """Parse RFC3339 timestamp to a comparable UTC instant."""
    if timestamp_str.endswith('Z'):
        timestamp_str = timestamp_str[:-1] + '+00:00'
    return datetime.fromisoformat(timestamp_str)

def summarize_receipts(receipts):
    """Group receipts by (account_id, delivery_id) and count accepted vs duplicates."""
    deliveries = {}
    for receipt in receipts:
        key = (receipt["account_id"], receipt["delivery_id"])
        if key not in deliveries:
            deliveries[key] = []
        deliveries[key].append(receipt)

    accepted_count = 0
    duplicate_count = 0

    for key, receipt_list in deliveries.items():
        if len(receipt_list) == 1:
            accepted_count += 1
        else:
            sorted_receipts = sorted(
                receipt_list,
                key=lambda r: (parse_iso8601(r["occurred_at"]), r["record_id"])
            )
            accepted_count += 1
            duplicate_count += len(sorted_receipts) - 1

    return accepted_count, duplicate_count

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}

    if q.get("command") == "count":
        protocol = q.get("protocol", "1")
        receipts = q.get("receipts", [])
        accepted_count, duplicate_count = summarize_receipts(receipts)
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count
        }

    if q.get("command") == "summary":
        protocol = q.get("protocol", "1")
        receipts = q.get("receipts", [])
        accepted_count, duplicate_count = summarize_receipts(receipts)
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count
        }

    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
