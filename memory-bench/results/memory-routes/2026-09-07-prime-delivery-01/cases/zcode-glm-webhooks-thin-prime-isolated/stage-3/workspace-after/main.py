#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT_PROTOCOL = "2"

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

def protocol2_accepted(receipts):
    # delivery_id alone identifies a delivery across all accounts; the accepted
    # receipt is the latest occurred_at instant, ties broken by smallest record_id.
    winners = {}
    for receipt in receipts:
        key = receipt["delivery_id"]
        rank = (parse_instant(receipt["occurred_at"]), receipt["record_id"])
        held = winners.get(key)
        if held is None or rank[0] > held[0][0] or (rank[0] == held[0][0] and rank[1] < held[0][1]):
            winners[key] = (rank, receipt)
    won = {receipt["record_id"] for _, receipt in winners.values()}
    return [receipt for receipt in receipts if receipt["record_id"] in won]

ACCEPTED_BY_PROTOCOL = {
    "1": protocol1_accepted,
    "2": protocol2_accepted,
}

def receipt_counts(q):
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    accepted_for = ACCEPTED_BY_PROTOCOL.get(protocol)
    if accepted_for is None:
        return {"error": "unsupported_protocol"}
    receipts = q.get("receipts", [])
    accepted_count = len(accepted_for(receipts))
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
        return receipt_counts(q)
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
