#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT_PROTOCOL = "2"
SUPPORTED_PROTOCOLS = ("1", "2")

def parse_occurred_at(text):
    if text[-1] in "Zz":
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)

def select_representatives(q, protocol):
    """Return the accepted representative receipts per delivery identity,
    unchanged and in original input order, plus the total receipt count."""
    receipts = q.get("receipts", [])
    best = {}
    for index, r in enumerate(receipts):
        if protocol == "1":
            # Protocol 1: (account_id, delivery_id) identifies a delivery; the
            # earliest occurred_at UTC instant wins, ties by smallest record_id.
            identity = (r["account_id"], r["delivery_id"])
            rank = (parse_occurred_at(r["occurred_at"]), r["record_id"])
        else:
            # Protocol 2: delivery_id alone identifies a delivery across all
            # accounts; the latest UTC instant wins, ties by smallest record_id.
            # The instant is negated so the smallest rank still wins; epoch
            # seconds at second precision are exact as floats.
            identity = r["delivery_id"]
            rank = (-parse_occurred_at(r["occurred_at"]).timestamp(), r["record_id"])
        if identity not in best or rank < best[identity][0]:
            best[identity] = (rank, index, r)
    # A later receipt can replace an earlier winner for an identity, so restore
    # original input order by index rather than insertion order.
    winners = sorted(best.values(), key=lambda entry: entry[1])
    return [entry[2] for entry in winners], len(receipts)

def protocol_counts(q):
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    if protocol not in SUPPORTED_PROTOCOLS:
        return {"error": "unsupported_protocol"}
    representatives, total = select_representatives(q, protocol)
    return {
        "protocol": protocol,
        "accepted_count": len(representatives),
        "duplicate_count": total - len(representatives),
    }

def accepted_receipts(q):
    # An integration partner exports protocol 1 batches, so accepted serves
    # every supported protocol; omitted protocol still selects the current one.
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    if protocol not in SUPPORTED_PROTOCOLS:
        return {"error": "unsupported_protocol"}
    representatives, total = select_representatives(q, protocol)
    return {
        "protocol": protocol,
        "accepted_count": len(representatives),
        "duplicate_count": total - len(representatives),
        "receipts": representatives,
    }

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") in ("count", "summary"):
        return protocol_counts(q)
    if q.get("command") == "accepted":
        return accepted_receipts(q)
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
