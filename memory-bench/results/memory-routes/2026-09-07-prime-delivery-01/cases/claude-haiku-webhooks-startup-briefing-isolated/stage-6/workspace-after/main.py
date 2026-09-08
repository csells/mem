#!/usr/bin/env python3
import json
import sys
from datetime import datetime

def parse_iso8601(timestamp_str):
    """Parse RFC3339 timestamp to a comparable UTC instant."""
    if timestamp_str.endswith('Z'):
        timestamp_str = timestamp_str[:-1] + '+00:00'
    return datetime.fromisoformat(timestamp_str)

def get_grouping_key(receipt, protocol):
    """Get the grouping key for a receipt based on protocol."""
    if protocol == "1":
        return (receipt["account_id"], receipt["delivery_id"])
    else:  # protocol == "2"
        return receipt["delivery_id"]

def summarize_receipts(receipts, protocol="2"):
    """Group receipts based on protocol and count accepted vs duplicates.

    Protocol 1: Groups by (account_id, delivery_id)
    Protocol 2: Groups by delivery_id alone (across all accounts)
    """
    deliveries = {}
    for i, receipt in enumerate(receipts):
        key = get_grouping_key(receipt, protocol)

        if key not in deliveries:
            deliveries[key] = []
        deliveries[key].append((i, receipt))

    accepted_count = 0
    duplicate_count = 0

    for key, receipt_list in deliveries.items():
        if len(receipt_list) == 1:
            accepted_count += 1
        else:
            sorted_receipts = sorted(
                receipt_list,
                key=lambda x: (-parse_iso8601(x[1]["occurred_at"]).timestamp(), x[1]["record_id"])
            )
            accepted_count += 1
            duplicate_count += len(sorted_receipts) - 1

    return accepted_count, duplicate_count

def get_accepted_receipts(receipts, protocol="2"):
    """Get the accepted representatives from each group, in original order."""
    deliveries = {}
    for i, receipt in enumerate(receipts):
        key = get_grouping_key(receipt, protocol)

        if key not in deliveries:
            deliveries[key] = []
        deliveries[key].append((i, receipt))

    accepted_indices = set()
    accepted_count = 0
    duplicate_count = 0

    for key, receipt_list in deliveries.items():
        if len(receipt_list) == 1:
            accepted_indices.add(receipt_list[0][0])
            accepted_count += 1
        else:
            sorted_receipts = sorted(
                receipt_list,
                key=lambda x: (-parse_iso8601(x[1]["occurred_at"]).timestamp(), x[1]["record_id"])
            )
            accepted_indices.add(sorted_receipts[0][0])
            accepted_count += 1
            duplicate_count += len(sorted_receipts) - 1

    # Return accepted receipts in original order
    accepted = [receipt for i, receipt in enumerate(receipts) if i in accepted_indices]

    return accepted, accepted_count, duplicate_count

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}

    if q.get("command") == "count":
        protocol = q.get("protocol", "2")
        receipts = q.get("receipts", [])
        accepted_count, duplicate_count = summarize_receipts(receipts, protocol)
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count
        }

    if q.get("command") == "summary":
        protocol = q.get("protocol", "2")
        receipts = q.get("receipts", [])
        accepted_count, duplicate_count = summarize_receipts(receipts, protocol)
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count
        }

    if q.get("command") == "accepted":
        protocol = q.get("protocol", "2")
        receipts = q.get("receipts", [])
        accepted, accepted_count, duplicate_count = get_accepted_receipts(receipts, protocol)
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count,
            "receipts": accepted
        }

    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
