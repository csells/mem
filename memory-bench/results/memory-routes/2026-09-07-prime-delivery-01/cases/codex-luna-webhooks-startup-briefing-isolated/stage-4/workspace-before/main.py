#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone


CURRENT_PROTOCOL = "2"


def _utc_timestamp(value):
    """Parse one of the contract's RFC3339 timestamps as a UTC instant."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _accepted_receipts(receipts, protocol):
    """Choose the single accepted receipt for each protocol delivery identity."""
    selected = {}
    for index, receipt in enumerate(receipts):
        if protocol == "1":
            identity = receipt["delivery_id"]
        else:
            identity = (receipt["account_id"], receipt["delivery_id"])

        candidate = (_utc_timestamp(receipt["occurred_at"]), receipt["record_id"], index, receipt)
        current = selected.get(identity)
        if current is None:
            selected[identity] = candidate
            continue

        timestamp, record_id, _, _ = current
        candidate_timestamp, candidate_record_id, _, _ = candidate
        is_better = (
            candidate_timestamp < timestamp
            if protocol == "1"
            else candidate_timestamp > timestamp
        )
        if candidate_timestamp == timestamp:
            is_better = candidate_record_id < record_id
        if is_better:
            selected[identity] = candidate

    return [entry[3] for entry in sorted(selected.values(), key=lambda entry: entry[2])]

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") in {"count", "summary"}:
        receipts = q["receipts"]
        protocol = q.get("protocol", CURRENT_PROTOCOL)
        accepted = _accepted_receipts(receipts, protocol)
        return {
            "protocol": protocol,
            "accepted_count": len(accepted),
            "duplicate_count": len(receipts) - len(accepted),
        }
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
