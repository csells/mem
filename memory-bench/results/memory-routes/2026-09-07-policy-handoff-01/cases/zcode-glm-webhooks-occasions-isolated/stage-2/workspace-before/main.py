#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timedelta, timezone

CURRENT_PROTOCOL = "1"
SUPPORTED_PROTOCOLS = ("1",)

def parse_instant(text):
    """Parse an RFC3339 timestamp (Z or ±HH:MM offset) to a UTC instant."""
    if text[-1] in "Zz":
        body, offset = text[:-1], timedelta(0)
    else:
        body = text[:-6]
        offset = timedelta(hours=int(text[-5:-3]), minutes=int(text[-2:]))
        if text[-6] == "-":
            offset = -offset
    return datetime.strptime(body, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc) - offset

def accepted_receipts(receipts):
    """Protocol 1: one receipt per (account_id, delivery_id) delivery identity.

    The earliest occurred_at UTC instant wins; equal instants use the smallest
    record_id. Accepted receipts keep their original input order.
    """
    best = {}
    for index, receipt in enumerate(receipts):
        key = (receipt["account_id"], receipt["delivery_id"])
        rank = (parse_instant(receipt["occurred_at"]), receipt["record_id"])
        if key not in best or rank < best[key][0]:
            best[key] = (rank, index)
    won = {index for _, index in best.values()}
    return [r for i, r in enumerate(receipts) if i in won]

def count_command(q):
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    if protocol not in SUPPORTED_PROTOCOLS:
        return {"error": "unsupported_protocol"}
    receipts = q.get("receipts", [])
    accepted = accepted_receipts(receipts)
    return {
        "protocol": protocol,
        "accepted_count": len(accepted),
        "duplicate_count": len(receipts) - len(accepted),
    }

def run(q):
    command = q.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command == "count":
        return count_command(q)
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
