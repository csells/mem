#!/usr/bin/env python3
import json
import sys
from datetime import datetime

def parse_timestamp(timestamp_str):
    # Handle both Z and explicit offset
    if timestamp_str.endswith('Z'):
        timestamp_str = timestamp_str[:-1] + '+00:00'
    return datetime.fromisoformat(timestamp_str)

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}

    if q.get("command") == "count":
        protocol = q.get("protocol", "1")
        receipts = q.get("receipts", [])

        # Track accepted receipts by (account_id, delivery_id) pair
        accepted_by_delivery = {}
        duplicates = 0

        for receipt in receipts:
            account_id = receipt["account_id"]
            delivery_id = receipt["delivery_id"]
            delivery_key = (account_id, delivery_id)

            if delivery_key not in accepted_by_delivery:
                # First receipt for this delivery
                accepted_by_delivery[delivery_key] = receipt
            else:
                # Compare with existing accepted receipt
                existing = accepted_by_delivery[delivery_key]
                existing_time = parse_timestamp(existing["occurred_at"])
                new_time = parse_timestamp(receipt["occurred_at"])

                if new_time < existing_time:
                    # New receipt is earlier, it becomes accepted
                    duplicates += 1
                    accepted_by_delivery[delivery_key] = receipt
                elif new_time == existing_time:
                    # Same time, use smallest record_id
                    if receipt["record_id"] < existing["record_id"]:
                        duplicates += 1
                        accepted_by_delivery[delivery_key] = receipt
                    else:
                        duplicates += 1
                else:
                    # Existing is earlier, new is duplicate
                    duplicates += 1

        return {
            "protocol": protocol,
            "accepted_count": len(accepted_by_delivery),
            "duplicate_count": duplicates
        }

    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
