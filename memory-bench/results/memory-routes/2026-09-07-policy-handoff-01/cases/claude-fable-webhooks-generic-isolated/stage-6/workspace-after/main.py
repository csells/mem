#!/usr/bin/env python3
"""Courier Relay: a local JSON CLI for analyzing delivery receipts.

One request object on stdin, exactly one response object on stdout.
"""
import json
import sys
from datetime import datetime, timezone

PRODUCT = "Courier Relay"
CURRENT_PROTOCOL = "2"
SUPPORTED_PROTOCOLS = ("1", "2")


def parse_instant(text):
    """Parse an RFC3339 timestamp (Z or numeric offset) into a UTC datetime."""
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def select_protocol(q):
    """Return the requested protocol version, defaulting to the current one."""
    return q.get("protocol", CURRENT_PROTOCOL)


def accepted_receipts_v1(receipts):
    """Protocol 1 (vendor/protocol-1.md): one accepted receipt per
    (account_id, delivery_id). Accept the earliest occurred_at UTC instant;
    equal instants use the smallest record_id (code-point order). Accepted
    receipts are returned unchanged, in their original input order."""
    best = {}
    for index, receipt in enumerate(receipts):
        identity = (receipt["account_id"], receipt["delivery_id"])
        key = (parse_instant(receipt["occurred_at"]), receipt["record_id"])
        if identity not in best or key < best[identity][0]:
            best[identity] = (key, index)
    winners = sorted(index for _, index in best.values())
    return [receipts[i] for i in winners]


def accepted_receipts_v2(receipts):
    """Protocol 2 (vendor/protocol-2.md): delivery_id alone identifies a
    delivery across all accounts. Accept the latest occurred_at UTC instant;
    equal instants use the smallest record_id (code-point order). Accepted
    receipts are returned unchanged, in their original input order."""
    best = {}
    for index, receipt in enumerate(receipts):
        identity = receipt["delivery_id"]
        instant = parse_instant(receipt["occurred_at"])
        record_id = receipt["record_id"]
        if identity in best:
            best_instant, best_record_id, _ = best[identity]
            later = instant > best_instant
            tie_wins = instant == best_instant and record_id < best_record_id
            if not (later or tie_wins):
                continue
        best[identity] = (instant, record_id, index)
    winners = sorted(index for _, _, index in best.values())
    return [receipts[i] for i in winners]


def accepted_receipts(protocol, receipts):
    """Dispatch to the per-version acceptance rule, or None if unsupported."""
    if protocol == "1":
        return accepted_receipts_v1(receipts)
    if protocol == "2":
        return accepted_receipts_v2(receipts)
    return None


def analyze(q):
    """Shared body of count, summary, and accepted: select the protocol and
    the accepted representatives. Delivery identity is protocol-specific:
    protocol 1 uses (account_id, delivery_id); protocol 2 uses delivery_id
    alone across all accounts. An omitted protocol selects CURRENT_PROTOCOL.
    Returns (protocol, receipts, accepted); accepted is None if the protocol
    is unsupported."""
    protocol = select_protocol(q)
    receipts = q.get("receipts", [])
    return protocol, receipts, accepted_receipts(protocol, receipts)


def receipt_counts(q):
    """Shared body of count and summary: exactly protocol, accepted_count,
    and duplicate_count under the selected protocol."""
    protocol, receipts, accepted = analyze(q)
    if accepted is None:
        return {"error": "unsupported_protocol"}
    return {
        "protocol": protocol,
        "accepted_count": len(accepted),
        "duplicate_count": len(receipts) - len(accepted),
    }


def count(q):
    """Original single-account count; same contract as summary."""
    return receipt_counts(q)


def summary(q):
    """Cross-account batch summary under the provider's approved protocol."""
    return receipt_counts(q)


def accepted(q):
    """Counts plus the accepted receipts themselves (issue trial-zee): exactly
    protocol, accepted_count, duplicate_count, and receipts. Counts equal
    summary for the same request; receipts are the accepted representatives
    under the selected protocol, unchanged and in original input order.
    Explicit "protocol":"1" (issue trial-0o0) exports the representatives
    under the original provider contract in vendor/protocol-1.md; an omitted
    protocol stays on CURRENT_PROTOCOL."""
    protocol, receipts, representatives = analyze(q)
    if representatives is None:
        return {"error": "unsupported_protocol"}
    return {
        "protocol": protocol,
        "accepted_count": len(representatives),
        "duplicate_count": len(receipts) - len(representatives),
        "receipts": representatives,
    }


def run(q):
    command = q.get("command")
    if command == "ping":
        return {"status": "ok", "product": PRODUCT}
    if command == "count":
        return count(q)
    if command == "summary":
        return summary(q)
    if command == "accepted":
        return accepted(q)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
