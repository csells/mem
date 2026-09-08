#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT_PROTOCOL = "2"
SUPPORTED_PROTOCOLS = ("1", "2")

def run(q):
    command = q.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command == "count":
        return count(q)
    if command == "summary":
        return summary(q)
    return {"error": "unknown_command"}

def rfc3339_instant(text):
    # Compare timestamps as UTC instants; explicit offsets may sit on a
    # different calendar date than the Z spelling of the same instant.
    return datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)

def delivery_identity(protocol, receipt):
    if protocol == "2":
        # Protocol 2 (issue trial-ekp, provider adoption): delivery_id alone
        # identifies a delivery across all accounts; the same ID under another
        # account is another receipt of that delivery.
        return receipt["delivery_id"]
    # Protocol 1 (vendor/protocol-1.md): the pair (account_id, delivery_id)
    # identifies a delivery; the same delivery_id under a different account is
    # a separate delivery.
    return (receipt["account_id"], receipt["delivery_id"])

def better_pick(protocol, instant, receipt, incumbent):
    if instant != incumbent[0]:
        return instant < incumbent[0] if protocol == "1" else instant > incumbent[0]
    return receipt["record_id"] < incumbent[1]["record_id"]

def accepted_receipts(protocol, receipts):
    # Exactly one receipt is accepted per delivery identity: the earliest
    # occurred_at instant under protocol 1, the latest under protocol 2;
    # equal instants use the smallest record_id (Unicode code-point order).
    # Accepted receipts are presented in their original input order.
    winners = {}
    for position, receipt in enumerate(receipts):
        key = delivery_identity(protocol, receipt)
        instant = rfc3339_instant(receipt["occurred_at"])
        incumbent = winners.get(key)
        if incumbent is None or better_pick(protocol, instant, receipt, incumbent):
            winners[key] = (instant, receipt, position)
    return [winners[key][1] for key in sorted(winners, key=lambda k: winners[k][2])]

def accepted_duplicate_counts(protocol, receipts):
    accepted = len(accepted_receipts(protocol, receipts))
    return {
        "protocol": protocol,
        "accepted_count": accepted,
        "duplicate_count": len(receipts) - accepted,
    }

def protocol_response(q, compute):
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    if protocol not in SUPPORTED_PROTOCOLS:
        return {"error": "unsupported_protocol"}
    return compute(protocol, q.get("receipts", []))

def count(q):
    return protocol_response(q, accepted_duplicate_counts)

def summary(q):
    return protocol_response(q, accepted_duplicate_counts)

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
