#!/usr/bin/env python3
from datetime import datetime, timezone
import json
import sys


CURRENT_PROTOCOL = "2"


def _occurred_at_utc(receipt):
    timestamp = receipt["occurred_at"]
    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"
    return datetime.fromisoformat(timestamp).astimezone(timezone.utc)


def _receipt_key(receipt, protocol):
    if protocol == "1":
        return receipt["delivery_id"]
    return receipt["account_id"], receipt["delivery_id"]


def _accepted_receipts(receipts, protocol):
    selected = {}
    for position, receipt in enumerate(receipts):
        identity = _receipt_key(receipt, protocol)
        candidate = (_occurred_at_utc(receipt), receipt["record_id"], position, receipt)
        current = selected.get(identity)
        if current is None:
            selected[identity] = candidate
            continue

        current_time, current_record_id, _, _ = current
        candidate_time, candidate_record_id, _, _ = candidate
        if protocol == "1":
            better = (candidate_time, candidate_record_id) < (current_time, current_record_id)
        else:
            better = (candidate_time, candidate_record_id) > (current_time, current_record_id)
            if candidate_time == current_time:
                better = candidate_record_id < current_record_id
        if better:
            selected[identity] = candidate

    return [candidate[3] for candidate in sorted(selected.values(), key=lambda item: item[2])]


def _receipt_counts(q, protocol):
    receipts = q.get("receipts", [])
    accepted = _accepted_receipts(receipts, protocol)
    return {
        "protocol": protocol,
        "accepted_count": len(accepted),
        "duplicate_count": len(receipts) - len(accepted),
    }


def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") in ("count", "summary"):
        protocol = q.get("protocol", CURRENT_PROTOCOL)
        return _receipt_counts(q, protocol)
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
