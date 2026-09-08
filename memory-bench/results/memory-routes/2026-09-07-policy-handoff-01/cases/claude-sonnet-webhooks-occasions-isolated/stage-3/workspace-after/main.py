#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone

CURRENT_PROTOCOL = "2"
SUPPORTED_PROTOCOLS = {"1", "2"}


def parse_instant(occurred_at):
    return datetime.strptime(occurred_at, "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone.utc)


def dedupe(receipts, key_fn, protocol):
    latest_wins = protocol == "2"
    best = {}
    for receipt in receipts:
        key = key_fn(receipt)
        instant = parse_instant(receipt["occurred_at"])
        record_id = receipt["record_id"]
        current = best.get(key)
        if current is None:
            best[key] = (instant, record_id)
            continue
        current_instant, current_record_id = current
        if latest_wins:
            preferred = instant > current_instant or (
                instant == current_instant and record_id < current_record_id
            )
        else:
            preferred = instant < current_instant or (
                instant == current_instant and record_id < current_record_id
            )
        if preferred:
            best[key] = (instant, record_id)
    accepted_count = len(best)
    duplicate_count = len(receipts) - accepted_count
    return accepted_count, duplicate_count


def count(receipts, protocol):
    return dedupe(receipts, lambda r: r["delivery_id"], protocol)


def summary(receipts, protocol):
    return dedupe(receipts, lambda r: (r["account_id"], r["delivery_id"]), protocol)


def run(q):
    command = q.get("command")
    protocol = q.get("protocol", CURRENT_PROTOCOL)

    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}

    if command == "count":
        if protocol not in SUPPORTED_PROTOCOLS:
            return {"error": "unknown_command"}
        accepted_count, duplicate_count = count(q.get("receipts", []), protocol)
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count,
        }

    if command == "summary":
        if protocol not in SUPPORTED_PROTOCOLS:
            return {"error": "unknown_command"}
        accepted_count, duplicate_count = summary(q.get("receipts", []), protocol)
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count,
        }

    return {"error": "unknown_command"}


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
