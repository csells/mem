"""Black-box stage checks. Expected memberships are authored explicitly."""

import argparse
import calendar
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys


def row(key, kind, when, cents):
    return {"id": key, "kind": kind, "posted_at": when, "amount_cents": cents}


def summary(month, rows):
    payments = sum(r["amount_cents"] for r in rows if r["kind"] == "payment")
    refunds = sum(r["amount_cents"] for r in rows if r["kind"] == "refund")
    return {"month": month, "transaction_ids": [r["id"] for r in rows],
            "payment_total_cents": payments, "refund_total_cents": refunds,
            "net_total_cents": payments - refunds}


def csv_response(month, selected):
    def escaped(value):
        value = str(value)
        if any(character in value for character in ',"\r\n'):
            return '"' + value.replace('"', '""') + '"'
        return value

    output = ["id,posted_at,amount_cents\n"]
    for r in selected:
        if r["kind"] == "refund":
            output.append(",".join(escaped(r[key]) for key in ("id", "posted_at", "amount_cents")) + "\n")
    return {"month": month, "csv": "".join(output)}


def day(date, pay, refund):
    return {"date": date, "payment_total_cents": pay,
            "refund_total_cents": refund, "net_total_cents": pay - refund}


def boundary_case(month):
    year, number = map(int, month.split("-"))
    last = calendar.monthrange(year, number)[1]
    begin = datetime(year, number, 1, tzinfo=timezone.utc)
    following = begin + timedelta(days=last)
    next_date = following.date().isoformat()
    first_date = begin.date().isoformat()
    last_date = f"{month}-{last:02d}"
    middle_date = month + "-15"
    entries = [
        row("previous", "payment", (begin - timedelta(milliseconds=1)).isoformat(), 97),
        row("start", "payment", first_date + "T00:00:00Z", 100),
        row("early", "refund", first_date + "T04:59:59.999Z", 20),
        row("opening", "payment", first_date + "T05:00:00Z", 300),
        row("middle", "refund", middle_date + "T12:00:00Z", 40),
        row("aa-last", "payment", last_date + "T00:00:00Z", 30),
        row("last", "refund", last_date + "T00:00:00Z", 50),
        row("zz-last", "refund", last_date + "T00:00:00Z", 10),
        row('r,"quoted\nid', "refund", last_date + "T18:00:00Z", 11),
        row("bare\rcarriage", "refund", last_date + "T19:00:00Z", 17),
        row("offset", "refund", next_date + "T00:30:00+01:00", 60),
        row("late", "payment", last_date + "T23:59:59.999Z", 600),
        row("next-midnight", "payment", next_date + "T00:00:00Z", 700),
        row("next-early", "refund", next_date + "T04:59:59.999Z", 80),
        row("next-opening", "payment", next_date + "T05:00:00Z", 900),
    ]
    by_id = {r["id"]: r for r in entries}
    calendar_ids = ["start", "early", "opening", "middle", "aa-last", "last", "zz-last", 'r,"quoted\nid', "bare\rcarriage", "offset", "late"]
    ledger_ids = ["opening", "middle", "aa-last", "last", "zz-last", 'r,"quoted\nid', "bare\rcarriage", "offset", "late", "next-midnight", "next-early"]
    # Reverse the provider input so relying on incoming order cannot pass.
    return {
        "input": list(reversed(entries)),
        "calendar": [by_id[key] for key in calendar_ids],
        "ledger": [by_id[key] for key in ledger_ids],
        "replay": [by_id[key] for key in calendar_ids],
        "daily": {"month": month, "days": [
            day(first_date, 300, 0), day(middle_date, 0, 40),
            day(f"{month}-{last - 1:02d}", 30, 60), day(last_date, 1300, 168),
        ]},
    }


def cases(stage):
    active = "ledger" if stage >= 4 else "calendar"
    operations = ["reconcile"]
    if stage >= 2:
        operations.append("refunds_csv")
    if stage >= 3:
        operations.append("incident_replay")
    if stage >= 5:
        operations.append("daily_net")
    if stage >= 6:
        operations.append("release1_reconcile")
    for month in ["2025-02", "2024-02", "2025-04", "2025-07", "2025-12", "2026-01", "2025-03", "2025-11"]:
        data = boundary_case(month)
        for op in operations:
            request = {"op": op, "month": month, "transactions": data["input"]}
            if op == "refunds_csv":
                expected = csv_response(month, data[active])
            elif op == "incident_replay":
                expected = summary(month, data["replay"])
            elif op == "release1_reconcile":
                expected = summary(month, data["calendar"])
            elif op == "daily_net":
                expected = data["daily"]
            else:
                expected = summary(month, data[active])
            yield f"{op}/boundaries/{month}", request, expected
    for op in operations:
        request = {"op": op, "month": "2025-02", "transactions": []}
        if op == "refunds_csv":
            expected = csv_response("2025-02", [])
        elif op == "daily_net":
            expected = {"month": "2025-02", "days": []}
        else:
            expected = summary("2025-02", [])
        yield f"{op}/empty", request, expected

    fixture_calendar = [
        row("p-feb-mid", "payment", "2025-02-10T12:00:00Z", 12000),
        row("p-feb-last", "payment", "2025-02-28T00:00:00Z", 2500),
        row("r-feb-last", "refund", "2025-02-28T17:30:00Z", 400),
        row("p-offset-feb", "payment", "2025-03-01T00:45:00+01:00", 700),
    ]
    fixture_ledger = fixture_calendar + [row("p-mar-open", "payment", "2025-03-01T00:00:00Z", 9000)]
    fixture_active = fixture_ledger if stage >= 4 else fixture_calendar
    for op in operations:
        request = {"op": op, "month": "2025-02"}
        if op == "refunds_csv":
            expected = csv_response("2025-02", fixture_active)
        elif op == "incident_replay":
            expected = summary("2025-02", fixture_calendar)
        elif op == "release1_reconcile":
            expected = summary("2025-02", fixture_calendar)
        elif op == "daily_net":
            expected = {"month": "2025-02", "days": [
                day("2025-02-10", 12000, 0), day("2025-02-27", 2500, 0), day("2025-02-28", 9700, 400),
            ]}
        else:
            expected = summary("2025-02", fixture_active)
        yield f"{op}/bundled-snapshot", request, expected

    if stage >= 5:
        zero_rows = [
            row("p", "payment", "2025-02-11T12:00:00Z", 25),
            row("r", "refund", "2025-02-12T00:00:00-04:00", 25),
            row("r2", "refund", "2025-02-12T05:00:00Z", 7),
            row("zero", "payment", "2025-02-13T05:00:00Z", 0),
        ]
        yield "daily_net/zero-and-negative-days", {"op": "daily_net", "month": "2025-02", "transactions": zero_rows}, {
            "month": "2025-02", "days": [day("2025-02-11", 25, 25), day("2025-02-12", 0, 7), day("2025-02-13", 0, 0)],
        }


def grade(stage, candidate):
    all_cases = list(cases(stage))
    results = []
    for name, request, expected in all_cases:
        try:
            result = subprocess.run([sys.executable, str(candidate / "cli.py")],
                                    input=json.dumps(request), capture_output=True, text=True,
                                    cwd=candidate, timeout=5)
            if result.returncode != 0:
                raise AssertionError(f"CLI exit {result.returncode}: {result.stderr.strip()}")
            actual = json.loads(result.stdout)
            if json.dumps(actual, sort_keys=True) != json.dumps(expected, sort_keys=True):
                raise AssertionError(f"expected {expected!r}; got {actual!r}")
            results.append({"name": name, "passed": True})
        except (OSError, subprocess.TimeoutExpired, ValueError, AssertionError) as error:
            results.append({"name": name, "passed": False, "detail": str(error)})
    return {"stage": stage, "passed": sum(r["passed"] for r in results),
            "total": len(results), "ok": all(r["passed"] for r in results), "cases": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=int, choices=range(1, 7), required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    report = grade(args.stage, args.candidate.resolve())
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["ok"] else 1)
