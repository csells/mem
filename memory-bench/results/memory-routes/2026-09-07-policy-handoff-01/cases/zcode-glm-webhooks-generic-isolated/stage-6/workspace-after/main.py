#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timedelta, timezone

CURRENT_PROTOCOL = "2"

def parse_instant(text):
    # RFC3339, seconds precision, "Z" or explicit ±HH:MM offset; aware datetimes
    # compare as UTC instants across differing offsets.
    if text.endswith("Z"):
        base, offset_minutes = text[:-1], 0
    else:
        sign = -1 if text[-6] == "-" else 1
        offset_minutes = sign * (int(text[-5:-3]) * 60 + int(text[-2:]))
        base = text[:-6]
    naive = datetime.strptime(base, "%Y-%m-%dT%H:%M:%S")
    return naive.replace(tzinfo=timezone(timedelta(minutes=offset_minutes)))

def select_accepted_v1(receipts):
    # Protocol 1: (account_id, delivery_id) identifies a delivery. The earliest
    # occurred_at instant wins, ties break on smallest record_id; accepted
    # receipts keep their original input order.
    winners = {}
    for index, receipt in enumerate(receipts):
        identity = (receipt["account_id"], receipt["delivery_id"])
        rank = (parse_instant(receipt["occurred_at"]), receipt["record_id"])
        if identity not in winners or rank < winners[identity][0]:
            winners[identity] = (rank, index)
    return [receipts[index] for _, index in sorted(winners.values(), key=lambda w: w[1])]

def select_accepted_v2(receipts):
    # Protocol 2: delivery_id alone identifies a delivery across all accounts.
    # The latest occurred_at instant wins, ties break on smallest record_id;
    # accepted receipts keep their original input order.
    winners = {}
    for index, receipt in enumerate(receipts):
        identity = receipt["delivery_id"]
        instant = parse_instant(receipt["occurred_at"])
        if identity not in winners:
            winners[identity] = ((instant, receipt["record_id"]), index)
            continue
        best_instant, best_id = winners[identity][0]
        if instant > best_instant or (instant == best_instant and receipt["record_id"] < best_id):
            winners[identity] = ((instant, receipt["record_id"]), index)
    return [receipts[index] for _, index in sorted(winners.values(), key=lambda w: w[1])]

def counts(protocol, select):
    def handler(request):
        accepted = select(request["receipts"])
        return {
            "protocol": protocol,
            "accepted_count": len(accepted),
            "duplicate_count": len(request["receipts"]) - len(accepted),
        }
    return handler

def details(protocol, select):
    def handler(request):
        accepted = select(request["receipts"])
        return {
            "protocol": protocol,
            "accepted_count": len(accepted),
            "duplicate_count": len(request["receipts"]) - len(accepted),
            "receipts": accepted,
        }
    return handler

PROTOCOLS = {
    "count": {"1": counts("1", select_accepted_v1), "2": counts("2", select_accepted_v2)},
    "summary": {"1": counts("1", select_accepted_v1), "2": counts("2", select_accepted_v2)},
    "accepted": {"1": details("1", select_accepted_v1), "2": details("2", select_accepted_v2)},
}

def run(q):
    command = q.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    versions = PROTOCOLS.get(command)
    if versions is None:
        return {"error": "unknown_command"}
    handler = versions.get(q.get("protocol", CURRENT_PROTOCOL))
    if handler is None:
        return {"error": "unknown_protocol"}
    return handler(q)

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
