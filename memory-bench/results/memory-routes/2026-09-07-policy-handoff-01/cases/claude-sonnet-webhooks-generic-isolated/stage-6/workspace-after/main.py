#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT_PROTOCOL = "2"


def parse_instant(occurred_at):
    text = occurred_at[:-1] + "+00:00" if occurred_at.endswith("Z") else occurred_at
    return datetime.fromisoformat(text)


def count_receipts(receipts, protocol):
    # Protocol 2 scopes delivery identity to (account_id, delivery_id) and
    # prefers the latest instant; protocol 1 scopes to delivery_id alone and
    # prefers the earliest instant. Both tie-break on the smallest record_id.
    prefer_latest = protocol == "2"
    best_by_delivery = {}
    for receipt in receipts:
        identity = (
            (receipt["account_id"], receipt["delivery_id"])
            if prefer_latest
            else receipt["delivery_id"]
        )
        instant = parse_instant(receipt["occurred_at"])
        record_id = receipt["record_id"]
        current = best_by_delivery.get(identity)
        if current is None:
            best_by_delivery[identity] = (instant, record_id)
            continue
        current_instant, current_record_id = current
        is_better = (
            instant > current_instant if prefer_latest else instant < current_instant
        ) or (instant == current_instant and record_id < current_record_id)
        if is_better:
            best_by_delivery[identity] = (instant, record_id)
    winning_record_ids = {record_id for _, record_id in best_by_delivery.values()}
    accepted = [r for r in receipts if r["record_id"] in winning_record_ids]
    return len(accepted), len(receipts) - len(accepted), accepted


def run(q):
    command = q.get("command")
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command == "count":
        accepted_count, duplicate_count, _ = count_receipts(q["receipts"], protocol)
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count,
        }
    if command == "summary":
        accepted_count, duplicate_count, _ = count_receipts(q["receipts"], protocol)
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count,
        }
    if command == "accepted":
        accepted_count, duplicate_count, accepted = count_receipts(q["receipts"], protocol)
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count,
            "receipts": accepted,
        }
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
