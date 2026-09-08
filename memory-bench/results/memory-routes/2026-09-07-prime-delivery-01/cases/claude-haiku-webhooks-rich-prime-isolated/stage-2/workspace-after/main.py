#!/usr/bin/env python3
import json
import sys
from datetime import datetime

def parse_rfc3339(timestamp_str):
    """Parse RFC3339 timestamp to UTC datetime, handling both Z and numeric offsets."""
    if timestamp_str.endswith('Z'):
        return datetime.fromisoformat(timestamp_str[:-1] + '+00:00')
    return datetime.fromisoformat(timestamp_str)

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}

    if q.get("command") == "count" or q.get("command") == "summary":
        protocol = q.get("protocol", "1")
        receipts = q.get("receipts", [])

        # Track which identity (account_id, delivery_id) has been accepted
        accepted_identities = {}
        accepted_count = 0
        duplicate_count = 0

        for receipt in receipts:
            identity = (receipt["account_id"], receipt["delivery_id"])

            if identity not in accepted_identities:
                # First receipt for this identity - it's accepted
                accepted_identities[identity] = receipt
                accepted_count += 1
            else:
                # Compare with the current accepted receipt
                current_accepted = accepted_identities[identity]

                # Parse timestamps
                current_ts = parse_rfc3339(current_accepted["occurred_at"])
                new_ts = parse_rfc3339(receipt["occurred_at"])

                if new_ts < current_ts:
                    # New receipt has earlier timestamp - replace the accepted one
                    accepted_identities[identity] = receipt
                    duplicate_count += 1  # Old accepted is now a duplicate
                elif new_ts == current_ts:
                    # Same timestamp - compare record_ids (Unicode order)
                    if receipt["record_id"] < current_accepted["record_id"]:
                        accepted_identities[identity] = receipt
                        duplicate_count += 1
                    else:
                        duplicate_count += 1
                else:
                    # New receipt is later - it's a duplicate
                    duplicate_count += 1

        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count
        }

    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
