#!/usr/bin/env python3
import json
import sys
from datetime import datetime

# Protocol 2 is the provider's permanently adopted contract and the approved
# current protocol (issue trial-3id). Protocol 1 remains supported when named
# explicitly.
CURRENT_PROTOCOL = "2"
SUPPORTED_PROTOCOLS = {"1", "2"}


def parse_instant(text):
    """Parse an RFC3339 timestamp (Z or explicit numeric offset) to a UTC instant."""
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def select_protocol(q):
    protocol = q.get("protocol")
    if protocol is None:
        return CURRENT_PROTOCOL
    return protocol if protocol in SUPPORTED_PROTOCOLS else None


def _accepted_receipts(receipts, identity_of, prefer):
    """Keep one receipt per identity, chosen by ``prefer(candidate, current)``.

    Accepted receipts keep their original fields and are returned in original
    input order.
    """
    winners = {}
    for index, receipt in enumerate(receipts):
        identity = identity_of(receipt)
        key = (parse_instant(receipt["occurred_at"]), receipt["record_id"])
        current = winners.get(identity)
        if current is None or prefer(key, current[0]):
            winners[identity] = (key, index)
    accepted_indexes = sorted(index for _, index in winners.values())
    return [receipts[i] for i in accepted_indexes]


def accepted_receipts_v1(receipts):
    """Protocol 1: one accepted receipt per (account_id, delivery_id).

    Earliest occurred_at UTC instant wins; ties use the smallest record_id
    (Unicode code-point order). Accepted receipts keep original input order.
    """
    return _accepted_receipts(
        receipts,
        identity_of=lambda r: (r["account_id"], r["delivery_id"]),
        prefer=lambda key, current: key < current,
    )


def accepted_receipts_v2(receipts):
    """Protocol 2: one accepted receipt per delivery_id across all accounts.

    Latest occurred_at UTC instant wins; equal instants use the smallest
    record_id (Unicode code-point order). Accepted receipts keep original
    input order.
    """

    def prefer(key, current):
        instant, record_id = key
        current_instant, current_record_id = current
        if instant != current_instant:
            return instant > current_instant
        return record_id < current_record_id

    return _accepted_receipts(
        receipts,
        identity_of=lambda r: r["delivery_id"],
        prefer=prefer,
    )


ACCEPTED_RECEIPTS = {
    "1": accepted_receipts_v1,
    "2": accepted_receipts_v2,
}


def dedupe(q):
    """Select the protocol and split receipts into accepted representatives.

    Returns ``(protocol, receipts, accepted)`` or ``(None, None, None)`` when
    the requested protocol is unsupported.
    """
    protocol = select_protocol(q)
    if protocol is None:
        return None, None, None
    receipts = q.get("receipts", [])
    return protocol, receipts, ACCEPTED_RECEIPTS[protocol](receipts)


def dedupe_counts(q):
    """Shared body for count and summary: counts under the selected protocol."""
    protocol, receipts, accepted = dedupe(q)
    if protocol is None:
        return {"error": "unsupported_protocol"}
    return {
        "protocol": protocol,
        "accepted_count": len(accepted),
        "duplicate_count": len(receipts) - len(accepted),
    }


def count(q):
    """Original single-account count command."""
    return dedupe_counts(q)


def summary(q):
    """Cross-account batch summary; same identity contract as count."""
    return dedupe_counts(q)


def accepted(q):
    """Counts plus the accepted representatives, unchanged, in input order.

    Same identity contract and protocol selection as count and summary, so the
    counts always equal summary for the same request.
    """
    protocol, receipts, kept = dedupe(q)
    if protocol is None:
        return {"error": "unsupported_protocol"}
    return {
        "protocol": protocol,
        "accepted_count": len(kept),
        "duplicate_count": len(receipts) - len(kept),
        "receipts": kept,
    }


def run(q):
    command = q.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command == "count":
        return count(q)
    if command == "summary":
        return summary(q)
    if command == "accepted":
        return accepted(q)
    return {"error": "unknown_command"}


if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
