#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone

CURRENT_PROTOCOL = "2"

def instant(occurred_at):
    """UTC instant for an RFC3339 timestamp with seconds and Z or a numeric offset."""
    text = occurred_at[:-1] + "+00:00" if occurred_at.endswith("Z") else occurred_at
    return datetime.fromisoformat(text).astimezone(timezone.utc)

def identity_1(receipt):
    """Protocol 1: delivery_id alone identifies a delivery across all accounts."""
    return receipt["delivery_id"]

def identity_2(receipt):
    """Protocol 2: (account_id, delivery_id) identifies a delivery, so the same
    delivery_id under a different account is a separate delivery."""
    return (receipt["account_id"], receipt["delivery_id"])

def rank_1(receipt):
    """Protocol 1 acceptance order: earliest UTC instant, then smallest record_id."""
    return (instant(receipt["occurred_at"]), receipt["record_id"])

def rank_2(receipt):
    """Protocol 2 acceptance order: latest UTC instant, then smallest record_id.

    The instant is negated as epoch seconds so that the smallest rank still wins.
    """
    return (-instant(receipt["occurred_at"]).timestamp(), receipt["record_id"])

PROTOCOLS = {"1": (identity_1, rank_1), "2": (identity_2, rank_2)}

# count and summary exist in both provider versions; accepted was introduced for
# the current one and extended to protocol 1 for the integration partner.
SUPPORTED = {"count": {"1", "2"}, "summary": {"1", "2"}, "accepted": {"1", "2"}}

def accepted_receipts(receipts, identity, rank):
    """The one accepted receipt per delivery identity, in original input order.

    Among the receipts sharing an identity, the smallest rank is accepted.
    """
    winners = {}
    for index, receipt in enumerate(receipts):
        key = identity(receipt)
        order = rank(receipt)
        if key not in winners or order < winners[key][0]:
            winners[key] = (order, index)
    kept = {index for _, index in winners.values()}
    return [receipt for index, receipt in enumerate(receipts) if index in kept]

def counts(q, protocol):
    """Accepted and duplicate counts under the protocol's delivery identity.

    count reports them for one account's receipts; summary reports them for a
    batch of any number of accounts. The identity contract is the same for both.
    """
    receipts = q["receipts"]
    identity, rank = PROTOCOLS[protocol]
    accepted = accepted_receipts(receipts, identity, rank)
    return {
        "protocol": protocol,
        "accepted_count": len(accepted),
        "duplicate_count": len(receipts) - len(accepted),
    }

def accepted(q, protocol):
    """The same counts as summary, plus the accepted receipts themselves.

    Each accepted receipt is returned unchanged, in original input order.
    """
    receipts = q["receipts"]
    identity, rank = PROTOCOLS[protocol]
    kept = accepted_receipts(receipts, identity, rank)
    return {
        "protocol": protocol,
        "accepted_count": len(kept),
        "duplicate_count": len(receipts) - len(kept),
        "receipts": kept,
    }

def run(q):
    command = q.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command in SUPPORTED:
        protocol = q.get("protocol", CURRENT_PROTOCOL)
        if protocol not in SUPPORTED[command]:
            return {"error": "unsupported_protocol"}
        if command == "accepted":
            return accepted(q, protocol)
        return counts(q, protocol)
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
