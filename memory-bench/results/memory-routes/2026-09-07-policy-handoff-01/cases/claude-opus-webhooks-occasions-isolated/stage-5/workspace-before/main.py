#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT_PROTOCOL = "2"
SUPPORTED_PROTOCOLS = ("1", "2")

def instant(occurred_at):
    """RFC3339 timestamp (Z or numeric offset) as a comparable UTC instant."""
    return datetime.fromisoformat(occurred_at.replace("Z", "+00:00")).timestamp()

def identity(receipt, protocol):
    """The delivery identity a receipt claims under the given protocol.

    Protocol 1: delivery_id alone identifies a delivery across all accounts.
    Protocol 2: the pair (account_id, delivery_id) identifies a delivery, so the
    same delivery_id under another account is a separate delivery.
    """
    if protocol == "1":
        return receipt["delivery_id"]
    return (receipt["account_id"], receipt["delivery_id"])

def rank(receipt, protocol):
    """Ordering key for one identity's receipts; the smallest key is accepted.

    Protocol 1 accepts the earliest occurred_at instant and protocol 2 the
    latest; both break equal instants with the smallest record_id.
    """
    moment = instant(receipt["occurred_at"])
    return (moment if protocol == "1" else -moment, receipt["record_id"])

def accepted(receipts, protocol):
    """Indexes of the accepted receipt per identity, in original input order.

    Every other receipt for that identity is a duplicate.
    """
    winners = {}
    for index, receipt in enumerate(receipts):
        key = identity(receipt, protocol)
        order = rank(receipt, protocol)
        if key not in winners or order < winners[key][0]:
            winners[key] = (order, index)
    return sorted(index for _, index in winners.values())

def counts(q):
    """Accepted and duplicate totals for a batch of receipts.

    Serves count and summary: both report totals over the whole supplied set
    under the selected protocol's delivery identity, so they agree on a batch.
    """
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

def details(q):
    """The accepted receipts themselves, alongside the same totals as count.

    Takes its totals from counts, so accepted reports what count and summary
    report for the same request; the receipts are those accepted ones, returned
    unchanged and in original input order.
    """
    totals = counts(q)
    if "error" in totals:
        return totals
    receipts = q["receipts"]
    picked = accepted(receipts, totals["protocol"])
    return {**totals, "receipts": [receipts[index] for index in picked]}

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") in ("count", "summary"):
        return counts(q)
    if q.get("command") == "accepted":
        return details(q)
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
