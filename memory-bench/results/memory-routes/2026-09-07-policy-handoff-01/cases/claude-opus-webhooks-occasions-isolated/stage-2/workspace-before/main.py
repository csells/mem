#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT_PROTOCOL = "1"
SUPPORTED_PROTOCOLS = ("1",)

def instant(occurred_at):
    """RFC3339 timestamp (Z or numeric offset) as a comparable UTC instant."""
    return datetime.fromisoformat(occurred_at.replace("Z", "+00:00")).timestamp()

def identity(receipt, protocol):
    """The delivery identity a receipt claims under the given protocol.

    Protocol 1: delivery_id alone identifies a delivery across all accounts.
    """
    return receipt["delivery_id"]

def accepted(receipts, protocol):
    """Indexes of the accepted receipt per identity, in original input order.

    The earliest occurred_at instant wins; equal instants use the smallest
    record_id. Every other receipt for that identity is a duplicate.
    """
    winners = {}
    for index, receipt in enumerate(receipts):
        key = identity(receipt, protocol)
        rank = (instant(receipt["occurred_at"]), receipt["record_id"])
        if key not in winners or rank < winners[key][0]:
            winners[key] = (rank, index)
    return sorted(index for _, index in winners.values())

def count(q):
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    if protocol not in SUPPORTED_PROTOCOLS:
        return {"error": "unsupported_protocol"}
    receipts = q["receipts"]
    accepted_count = len(accepted(receipts, protocol))
    return {
        "protocol": protocol,
        "accepted_count": accepted_count,
        "duplicate_count": len(receipts) - accepted_count,
    }

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") == "count":
        return count(q)
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
