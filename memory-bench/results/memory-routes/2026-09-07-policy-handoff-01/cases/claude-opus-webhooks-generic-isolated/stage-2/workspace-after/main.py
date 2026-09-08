#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone

CURRENT_PROTOCOL = "1"

def instant(occurred_at):
    """UTC instant for an RFC3339 timestamp with seconds and Z or a numeric offset."""
    text = occurred_at[:-1] + "+00:00" if occurred_at.endswith("Z") else occurred_at
    return datetime.fromisoformat(text).astimezone(timezone.utc)

def identity_1(receipt):
    """Protocol 1: delivery_id alone identifies a delivery across all accounts."""
    return receipt["delivery_id"]

IDENTITY = {"1": identity_1}

def accepted_receipts(receipts, identity):
    """The one accepted receipt per delivery identity, in original input order.

    Earliest occurred_at UTC instant wins; equal instants use the smallest record_id.
    """
    winners = {}
    for index, receipt in enumerate(receipts):
        key = identity(receipt)
        rank = (instant(receipt["occurred_at"]), receipt["record_id"])
        if key not in winners or rank < winners[key][0]:
            winners[key] = (rank, index)
    kept = {index for _, index in winners.values()}
    return [receipt for index, receipt in enumerate(receipts) if index in kept]

def counts(q, protocol):
    """Accepted and duplicate counts under the protocol's delivery identity.

    count reports them for one account's receipts; summary reports them for a
    batch of any number of accounts. The identity contract is the same for both.
    """
    receipts = q["receipts"]
    accepted = accepted_receipts(receipts, IDENTITY[protocol])
    return {
        "protocol": protocol,
        "accepted_count": len(accepted),
        "duplicate_count": len(receipts) - len(accepted),
    }

def run(q):
    command = q.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command in ("count", "summary"):
        protocol = q.get("protocol", CURRENT_PROTOCOL)
        if protocol not in IDENTITY:
            return {"error": "unsupported_protocol"}
        return counts(q, protocol)
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
