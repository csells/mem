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
    return {"error": "unknown_command"}

def count(q):
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    if protocol not in SUPPORTED_PROTOCOLS:
        return {"error": "unsupported_protocol"}
    receipts = q.get("receipts", [])
    # Protocol 1: (account_id, delivery_id) identifies a delivery; exactly one
    # receipt per identity is accepted, the rest are duplicates.
    identities = {(r["account_id"], r["delivery_id"]) for r in receipts}
    accepted = len(identities)
    return {
        "protocol": protocol,
        "accepted_count": accepted,
        "duplicate_count": len(receipts) - accepted,
    }

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
