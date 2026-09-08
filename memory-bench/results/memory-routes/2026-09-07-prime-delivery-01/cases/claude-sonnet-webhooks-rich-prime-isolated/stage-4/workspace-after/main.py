#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT_PROTOCOL = "2"
SUPPORTED_PROTOCOLS = {"1", "2"}


def parse_instant(occurred_at):
    return datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))


def identity(receipt, protocol):
    if protocol == "2":
        return (receipt["account_id"], receipt["delivery_id"])
    return receipt["delivery_id"]


def select_winners(receipts, protocol):
    """Return the index of the accepted receipt for each identity.

    The winner per identity is the receipt with the latest occurred_at UTC
    instant, tie-broken by the smallest record_id.
    """
    best_by_id = {}
    for index, receipt in enumerate(receipts):
        key_id = identity(receipt, protocol)
        instant = parse_instant(receipt["occurred_at"])
        current = best_by_id.get(key_id)
        if current is None:
            best_by_id[key_id] = (instant, receipt["record_id"], index)
        else:
            best_instant, best_record_id, _ = current
            if instant > best_instant or (
                instant == best_instant and receipt["record_id"] < best_record_id
            ):
                best_by_id[key_id] = (instant, receipt["record_id"], index)
    return {index for _, _, index in best_by_id.values()}


def run(q):
    command = q.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command in ("count", "summary", "accepted"):
        protocol = q.get("protocol", CURRENT_PROTOCOL)
        if protocol not in SUPPORTED_PROTOCOLS:
            return {"error": "unsupported_protocol"}
        receipts = q["receipts"]
        winner_indices = select_winners(receipts, protocol)
        accepted_count = len(winner_indices)
        result = {
            "protocol": protocol,
            "accepted_count": accepted_count,
            "duplicate_count": len(receipts) - accepted_count,
        }
        if command == "accepted":
            result["receipts"] = [
                receipt for index, receipt in enumerate(receipts) if index in winner_indices
            ]
        return result
    return {"error": "unknown_command"}


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
