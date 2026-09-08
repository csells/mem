#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT_PROTOCOL = "1"

def parse_instant(text):
    # RFC3339 with Z or an explicit offset; aware datetimes compare as UTC instants.
    return datetime.fromisoformat(text)

def protocol1_accepted(receipts):
    # (account_id, delivery_id) identifies a delivery; the accepted receipt is
    # the earliest occurred_at instant, ties broken by smallest record_id.
    winners = {}
    for receipt in receipts:
        key = (receipt["account_id"], receipt["delivery_id"])
        rank = (parse_instant(receipt["occurred_at"]), receipt["record_id"])
        if key not in winners or rank < winners[key][0]:
            winners[key] = (rank, receipt)
    won = {receipt["record_id"] for _, receipt in winners.values()}
    return [receipt for receipt in receipts if receipt["record_id"] in won]

def protocol1_counts(q):
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    if protocol != "1":
        return {"error": "unsupported_protocol"}
    receipts = q.get("receipts", [])
    accepted_count = len(protocol1_accepted(receipts))
    return {
        "protocol": protocol,
        "accepted_count": accepted_count,
        "duplicate_count": len(receipts) - accepted_count,
    }

def run(q):
    command = q.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command in ("count", "summary"):
        return protocol1_counts(q)
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
