#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone


def utc_instant(timestamp):
    """Convert the protocol's RFC3339 timestamp to a comparable UTC instant."""
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(timezone.utc)


def select_receipts(receipts, protocol):
    """Select one receipt per delivery identity for the requested protocol."""
    accepted_by_delivery = {}
    for receipt in receipts:
        candidate_key = (utc_instant(receipt["occurred_at"]), receipt["record_id"])
        if protocol == "1":
            identity = receipt["delivery_id"]
        else:
            identity = (receipt["account_id"], receipt["delivery_id"])

        current = accepted_by_delivery.get(identity)
        if current is None:
            accepted_by_delivery[identity] = (candidate_key, receipt)
        elif protocol == "1" and candidate_key < current[0]:
            accepted_by_delivery[identity] = (candidate_key, receipt)
        elif protocol == "2" and (
            candidate_key[0] > current[0][0]
            or (
                candidate_key[0] == current[0][0]
                and candidate_key[1] < current[0][1]
            )
        ):
            accepted_by_delivery[identity] = (candidate_key, receipt)

    return {
        receipt["record_id"]
        for _, receipt in accepted_by_delivery.values()
    }


def receipt_counts(receipts, protocol):
    """Return acceptance counts for a complete receipt set and protocol."""
    accepted_ids = select_receipts(receipts, protocol)

    accepted_count = sum(receipt["record_id"] in accepted_ids for receipt in receipts)
    return {
        "protocol": protocol,
        "accepted_count": accepted_count,
        "duplicate_count": len(receipts) - accepted_count,
    }


def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") in {"count", "summary"}:
        protocol = q.get("protocol", "2")
        return receipt_counts(q["receipts"], protocol)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
