#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timedelta, timezone

CURRENT_PROTOCOL = "2"
SUPPORTED_PROTOCOLS = ("1", "2")

def parse_instant(text):
    """Parse an RFC3339 timestamp (Z or ±HH:MM offset) to a UTC instant."""
    if text[-1] in "Zz":
        body, offset = text[:-1], timedelta(0)
    else:
        body = text[:-6]
        offset = timedelta(hours=int(text[-5:-3]), minutes=int(text[-2:]))
        if text[-6] == "-":
            offset = -offset
    return datetime.strptime(body, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc) - offset

def outranks(protocol, rank, incumbent):
    """Whether rank displaces the incumbent best rank for one identity."""
    instant, record_id = rank
    incumbent_instant, incumbent_record_id = incumbent
    if instant != incumbent_instant:
        return instant > incumbent_instant if protocol == "2" else instant < incumbent_instant
    return record_id < incumbent_record_id

def accepted_receipts(receipts, protocol):
    """One receipt per delivery identity, in original input order.

    Protocol 1: identity is (account_id, delivery_id); the earliest
    occurred_at UTC instant wins. Protocol 2: delivery_id alone identifies a
    delivery across accounts; the latest occurred_at UTC instant wins. Equal
    instants use the smallest record_id. See vendor/protocol-1.md and
    vendor/protocol-2.md.
    """
    best = {}
    for index, receipt in enumerate(receipts):
        key = receipt["delivery_id"] if protocol == "2" else (receipt["account_id"], receipt["delivery_id"])
        rank = (parse_instant(receipt["occurred_at"]), receipt["record_id"])
        if key not in best or outranks(protocol, rank, best[key][0]):
            best[key] = (rank, index)
    won = {index for _, index in best.values()}
    return [r for i, r in enumerate(receipts) if i in won]

def batch_summary(q):
    """Counts for a receipt batch, shared by count and summary.

    summary takes a batch from any number of accounts; count keeps its
    original single-account use. Identity and acceptance follow
    vendor/protocol-1.md and vendor/protocol-2.md.
    """
    protocol = q.get("protocol", CURRENT_PROTOCOL)
    if protocol not in SUPPORTED_PROTOCOLS:
        return {"error": "unsupported_protocol"}
    receipts = q.get("receipts", [])
    accepted = accepted_receipts(receipts, protocol)
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
        return batch_summary(q)
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
