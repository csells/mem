#!/usr/bin/env python3
import json
import sys

CURRENT_PROTOCOL = "1"
SUPPORTED_PROTOCOLS = ("1",)

def run(q):
    command = q.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command == "count":
        return count(q)
    if command == "summary":
        return summary(q)
    return {"error": "unknown_command"}

def accepted_duplicate_counts(protocol, receipts):
    # Protocol 1 (vendor/protocol-1.md): the pair (account_id, delivery_id)
    # identifies a delivery; the same delivery_id under a different account is
    # a separate delivery. Exactly one receipt per identity is accepted, the
    # rest are duplicates.
    identities = {(r["account_id"], r["delivery_id"]) for r in receipts}
    accepted = len(identities)
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
