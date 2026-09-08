#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone

CURRENT_PROTOCOL = "1"
SUPPORTED_PROTOCOLS = {"1"}


def parse_instant(occurred_at):
    return datetime.strptime(occurred_at, "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone.utc)


def dedupe(receipts, key_fn):
    best = {}
    for receipt in receipts:
        key = key_fn(receipt)
        instant = parse_instant(receipt["occurred_at"])
        record_id = receipt["record_id"]
        current = best.get(key)
        if current is None or (instant, record_id) < (current[0], current[1]):
            best[key] = (instant, record_id)
    accepted_count = len(best)
    duplicate_count = len(receipts) - accepted_count
    return accepted_count, duplicate_count


def count(receipts):
    return dedupe(receipts, lambda r: r["delivery_id"])


def summary(receipts):
    return dedupe(receipts, lambda r: (r["account_id"], r["delivery_id"]))


def run(q):
    command = q.get("command")
    protocol = q.get("protocol", CURRENT_PROTOCOL)

    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}

    if command == "count":
        if protocol not in SUPPORTED_PROTOCOLS:
            return {"error": "unknown_command"}
        accepted_count, duplicate_count = count(q.get("receipts", []))
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count,
        }

    if command == "summary":
        if protocol not in SUPPORTED_PROTOCOLS:
            return {"error": "unknown_command"}
        accepted_count, duplicate_count = summary(q.get("receipts", []))
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count,
        }

    return {"error": "unknown_command"}


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
