#!/usr/bin/env python3
from datetime import datetime, timezone
import json
import sys


CURRENT_PROTOCOL = "2"


def _utc_timestamp(receipt):
    timestamp = receipt["occurred_at"]
    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"
    return datetime.fromisoformat(timestamp).astimezone(timezone.utc)


def _delivery_identity(receipt, protocol):
    if protocol == "1":
        return receipt["delivery_id"]
    return receipt["account_id"], receipt["delivery_id"]


def _is_better(candidate, current, protocol):
    candidate_time = candidate["timestamp"]
    current_time = current["timestamp"]
    if candidate_time != current_time:
        if protocol == "1":
            return candidate_time < current_time
        return candidate_time > current_time
    return candidate["receipt"]["record_id"] < current["receipt"]["record_id"]


def _receipt_counts(receipts, protocol):
    accepted = _accepted_receipts(receipts, protocol)
    return len(accepted), len(receipts) - len(accepted)


def _accepted_receipts(receipts, protocol):
    winners = {}
    for index, receipt in enumerate(receipts):
        candidate = {"index": index, "receipt": receipt, "timestamp": _utc_timestamp(receipt)}
        identity = _delivery_identity(receipt, protocol)
        current = winners.get(identity)
        if current is None or _is_better(candidate, current, protocol):
            winners[identity] = candidate

    # Keeping the winners in input order is part of the provider contract,
    # even though count and summary only expose their cardinalities.
    accepted = sorted(winners.values(), key=lambda winner: winner["index"])
    return [winner["receipt"] for winner in accepted]


def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if q.get("command") == "accepted":
        protocol = q.get("protocol", CURRENT_PROTOCOL)
        receipts = q["receipts"]
        accepted = _accepted_receipts(receipts, protocol)
        return {
            "protocol": protocol,
            "accepted_count": len(accepted),
            "duplicate_count": len(receipts) - len(accepted),
            "receipts": accepted,
        }
    if q.get("command") in {"count", "summary"}:
        protocol = q.get("protocol", CURRENT_PROTOCOL)
        accepted_count, duplicate_count = _receipt_counts(q["receipts"], protocol)
        return {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": duplicate_count,
        }
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
