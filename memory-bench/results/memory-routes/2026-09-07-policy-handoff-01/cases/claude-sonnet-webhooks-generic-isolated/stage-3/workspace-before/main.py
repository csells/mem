#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT_PROTOCOL = "1"


def parse_instant(occurred_at):
    text = occurred_at[:-1] + "+00:00" if occurred_at.endswith("Z") else occurred_at
    return datetime.fromisoformat(text)


def count_receipts(receipts):
    best_by_delivery = {}
    for receipt in receipts:
        delivery_id = receipt["delivery_id"]
        instant = parse_instant(receipt["occurred_at"])
        current = best_by_delivery.get(delivery_id)
        if current is None:
            best_by_delivery[delivery_id] = (instant, receipt["record_id"])
            continue
        current_instant, current_record_id = current
        if instant < current_instant or (
            instant == current_instant and receipt["record_id"] < current_record_id
        ):
            best_by_delivery[delivery_id] = (instant, receipt["record_id"])
    accepted_count = len(best_by_delivery)
    return accepted_count, len(receipts) - accepted_count


def run(q):
    command = q.get("command")
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command == "count":
        accepted_count, duplicate_count = count_receipts(q["receipts"])
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count,
        }
    if command == "summary":
        accepted_count, duplicate_count = count_receipts(q["receipts"])
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count,
        }
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
