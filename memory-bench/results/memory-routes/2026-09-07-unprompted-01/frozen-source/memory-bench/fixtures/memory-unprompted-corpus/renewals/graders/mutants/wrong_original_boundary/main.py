#!/usr/bin/env python3
"""Business reference, written separately from the external grade oracle."""
import argparse
import csv
from dataclasses import dataclass
from datetime import date, timedelta
from io import StringIO
import json
import sys


@dataclass(frozen=True)
class Offer:
    lead_days: int
    minimum_years: int
    percent: int
    maximum_cents: int
    requires_autopay: bool

    def notice(self, account):
        eligible = account["completed_years"] >= self.minimum_years
        eligible = eligible and (account["autopay"] or not self.requires_autopay)
        discount = account["plan_cents"] * self.percent // 100
        discount = min(discount, self.maximum_cents) if eligible else 0
        return make_notice(account, self.lead_days, discount)


RELEASE_ONE = Offer(21, 3, 10, 2400, True)
RETENTION_OFFER = Offer(14, 3, 15, 3600, False)


def make_notice(account, lead_days, credit):
    renewal = date.fromisoformat(account["renewal_on"])
    return {
        "customer_id": account["customer_id"],
        "send_on": (renewal - timedelta(days=lead_days)).isoformat(),
        "credit_cents": credit,
        "amount_due_cents": account["plan_cents"] - credit,
    }


def csv_record(values):
    # A CRLF-aware writer quotes embedded CR as well as LF. Only the record's
    # trailing delimiter is converted; embedded customer-ID newlines survive.
    stream = StringIO(newline="")
    csv.writer(stream, lineterminator="\r\n").writerow(values)
    return stream.getvalue()[:-2] + "\n"


def handle(request, stage):
    command = request["command"]
    current = RELEASE_ONE if stage < 4 else RETENTION_OFFER
    if command == "ping":
        return {"status": "ok", "product": "HarborPass"}
    if command == "notice" and stage >= 1:
        return current.notice(request["account"])
    if command == "export" and stage >= 2:
        columns = ["customer_id", "send_on", "credit_cents", "amount_due_cents"]
        lines = [csv_record(columns)]
        for member in request["accounts"]:
            result = current.notice(member)
            lines.append(csv_record([result[column] for column in columns]))
        return {"csv": "".join(lines), "count": len(request["accounts"])}
    if command == "support_replay" and stage >= 3:
        member = request["account"]
        return {"case_id": "IOS-1842", "notice": RELEASE_ONE.notice(member)}
    if command == "batch" and stage >= 5:
        selected = []
        total = 0
        for member in request["accounts"]:
            result = current.notice(member)
            if result["send_on"] == request["on"]:
                selected.append(result)
                total += result["amount_due_cents"]
        return {"on": request["on"], "notices": selected, "total_due_cents": total}
    if command == "compat_notice" and stage >= 6:
        return {"release": "1.0", "notice": RELEASE_ONE.notice(request["account"])}
    return {"error": "unknown_command"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=int, choices=range(1, 7), default=6)
    args = parser.parse_args()
    json.dump(handle(json.load(sys.stdin), args.stage), sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
