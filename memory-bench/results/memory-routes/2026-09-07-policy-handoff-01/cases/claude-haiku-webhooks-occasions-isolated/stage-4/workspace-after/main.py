#!/usr/bin/env python3
import json
import sys
from datetime import datetime

def parse_timestamp(timestamp_str):
    # Handle both Z and explicit offset
    if timestamp_str.endswith('Z'):
        timestamp_str = timestamp_str[:-1] + '+00:00'
    return datetime.fromisoformat(timestamp_str)

def process_receipts_protocol_1(receipts):
    # Protocol 1: (account_id, delivery_id) pair
    accepted_by_delivery = {}
    accepted_order = []
    duplicates = 0

    for idx, receipt in enumerate(receipts):
        account_id = receipt["account_id"]
        delivery_id = receipt["delivery_id"]
        delivery_key = (account_id, delivery_id)

        if delivery_key not in accepted_by_delivery:
            accepted_by_delivery[delivery_key] = receipt
            accepted_order.append(idx)
        else:
            existing = accepted_by_delivery[delivery_key]
            existing_time = parse_timestamp(existing["occurred_at"])
            new_time = parse_timestamp(receipt["occurred_at"])

            if new_time > existing_time:
                accepted_by_delivery[delivery_key] = receipt
                duplicates += 1
            elif new_time == existing_time:
                if receipt["record_id"] < existing["record_id"]:
                    accepted_by_delivery[delivery_key] = receipt
                duplicates += 1
            else:
                duplicates += 1

    return accepted_by_delivery, duplicates, accepted_order

def process_receipts_protocol_2(receipts):
    # Protocol 2: delivery_id alone identifies a delivery
    accepted_by_delivery = {}
    accepted_order = []
    duplicates = 0

    for idx, receipt in enumerate(receipts):
        delivery_id = receipt["delivery_id"]

        if delivery_id not in accepted_by_delivery:
            accepted_by_delivery[delivery_id] = receipt
            accepted_order.append(idx)
        else:
            existing = accepted_by_delivery[delivery_id]
            existing_time = parse_timestamp(existing["occurred_at"])
            new_time = parse_timestamp(receipt["occurred_at"])

            if new_time > existing_time:
                accepted_by_delivery[delivery_id] = receipt
                duplicates += 1
            elif new_time == existing_time:
                if receipt["record_id"] < existing["record_id"]:
                    accepted_by_delivery[delivery_id] = receipt
                duplicates += 1
            else:
                duplicates += 1

    return accepted_by_delivery, duplicates, accepted_order

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}

    if q.get("command") == "count":
        protocol = q.get("protocol", "2")
        receipts = q.get("receipts", [])

        if protocol == "1":
            accepted_by_delivery, duplicates, _ = process_receipts_protocol_1(receipts)
        else:
            accepted_by_delivery, duplicates, _ = process_receipts_protocol_2(receipts)

        return {
            "protocol": protocol,
            "accepted_count": len(accepted_by_delivery),
            "duplicate_count": duplicates
        }

    if q.get("command") == "summary":
        protocol = q.get("protocol", "2")
        receipts = q.get("receipts", [])

        if protocol == "1":
            accepted_by_delivery, duplicates, _ = process_receipts_protocol_1(receipts)
        else:
            accepted_by_delivery, duplicates, _ = process_receipts_protocol_2(receipts)

        return {
            "protocol": protocol,
            "accepted_count": len(accepted_by_delivery),
            "duplicate_count": duplicates
        }

    if q.get("command") == "accepted":
        protocol = q.get("protocol", "2")
        receipts = q.get("receipts", [])

        if protocol == "1":
            accepted_by_delivery, duplicates, accepted_order = process_receipts_protocol_1(receipts)
        else:
            accepted_by_delivery, duplicates, accepted_order = process_receipts_protocol_2(receipts)

        accepted_receipts = [receipts[idx] for idx in accepted_order]

        return {
            "protocol": protocol,
            "accepted_count": len(accepted_by_delivery),
            "duplicate_count": duplicates,
            "receipts": accepted_receipts
        }

    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
