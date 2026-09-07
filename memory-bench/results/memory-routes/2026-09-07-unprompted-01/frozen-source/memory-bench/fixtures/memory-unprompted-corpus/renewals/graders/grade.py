#!/usr/bin/env python3
"""External, cumulative black-box business tests. Never import candidate code."""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import sys

HEADER = "customer_id,send_on,credit_cents,amount_due_cents\n"


def account(customer_id="M-17", renewal_on="2026-04-15", plan_cents=19999, completed_years=2, autopay=True):
    return dict(customer_id=customer_id, renewal_on=renewal_on, plan_cents=plan_cents, completed_years=completed_years, autopay=autopay)


def expected_notice(member, policy):
    if policy == "release1":
        offset = 21
        credit = min(member["plan_cents"] // 10, 2400) if member["completed_years"] >= 2 and member["autopay"] else 0
    elif policy == "current":
        offset = 14
        credit = min(member["plan_cents"] * 3 // 20, 3600) if member["completed_years"] >= 3 else 0
    elif policy == "replay":
        offset = 21
        credit = min(member["plan_cents"] // 10, 2400) if member["completed_years"] >= 2 and member["autopay"] else 0
    else:
        raise ValueError(policy)
    return {
        "customer_id": member["customer_id"],
        "send_on": (date.fromisoformat(member["renewal_on"]) - timedelta(days=offset)).isoformat(),
        "credit_cents": credit,
        "amount_due_cents": member["plan_cents"] - credit,
    }


def escaped(value):
    text = str(value)
    return '"' + text.replace('"', '""') + '"' if any(c in text for c in ',"\r\n') else text


def expected_export(members, policy):
    body = HEADER
    for member in members:
        row = expected_notice(member, policy)
        body += ",".join(escaped(row[key]) for key in ("customer_id", "send_on", "credit_cents", "amount_due_cents")) + "\n"
    return {"csv": body, "count": len(members)}


def notice_accounts():
    cases = []
    for years in (0, 1, 2, 3, 4):
        for autopay in (False, True):
            cases.append((f"tenure_{years}_autopay_{autopay}", account(completed_years=years, autopay=autopay)))
    for amount in (0, 1, 6, 7, 9, 10, 11, 749, 750, 751, 19999, 23999, 24000, 24001, 90000):
        cases.append((f"cents_{amount}", account(plan_cents=amount, completed_years=8)))
    for renewal in ("2024-03-01", "2024-03-14", "2025-01-05", "2026-01-01", "2028-02-29"):
        cases.append((f"date_{renewal}", account(renewal_on=renewal, completed_years=3, autopay=False)))
    return cases


def cases_for(stage):
    policy = "release1" if stage < 4 else "current"
    cases = [
        ("ping", {"command": "ping"}, {"status": "ok", "product": "HarborPass"}),
        ("unknown_command", {"command": "not_a_command"}, {"error": "unknown_command"}),
    ]
    for label, member in notice_accounts():
        cases.append(("notice_" + label, {"command": "notice", "account": member}, expected_notice(member, policy)))
    if stage >= 2:
        groups = [
            ("empty", []),
            ("single", [account()]),
            ("order_duplicates", [account(customer_id="Z", completed_years=3, autopay=False), account(customer_id="A"), account(customer_id="Z", plan_cents=90000, completed_years=8)]),
            ("csv_quoting", [account(customer_id=value, completed_years=3) for value in ('A,B', 'A"B', 'A\rB', 'A\nB', ' A ', 'München', 'A\r\nB')]),
            ("tenure_boundaries", [account(completed_years=years, autopay=auto) for years in (1, 2, 3) for auto in (False, True)]),
        ]
        for label, members in groups:
            cases.append(("export_" + label, {"command": "export", "accounts": members}, expected_export(members, policy)))
    if stage >= 3:
        for label, member in notice_accounts():
            cases.append(("support_" + label, {"command": "support_replay", "case_id": "IOS-1842", "account": member}, {"case_id": "IOS-1842", "notice": expected_notice(member, "replay")}))
    if stage >= 5:
        groups = [
            ("empty", "2026-04-01", []),
            ("none", "2026-04-02", [account(), account(renewal_on="2026-04-18")]),
            ("current_only", "2026-04-01", [account(customer_id="old_offset", renewal_on="2026-04-22"), account(customer_id="current_offset", completed_years=3, autopay=False), account(customer_id="other_date", renewal_on="2026-04-08")]),
            ("preserve_order_duplicates", "2026-04-01", [account(customer_id="Z", completed_years=3, autopay=False), account(customer_id="A", completed_years=2), account(customer_id="Z", plan_cents=90000, completed_years=8), account(customer_id="miss", renewal_on="2026-04-16")]),
            ("leap_day", "2024-02-29", [account(renewal_on="2024-03-14", completed_years=3), account(renewal_on="2024-03-13")]),
            ("year_boundary", "2025-12-25", [account(renewal_on="2026-01-08", completed_years=3, autopay=False), account(renewal_on="2026-01-09")]),
        ]
        for label, on, members in groups:
            notices = [expected_notice(member, "current") for member in members]
            notices = [notice for notice in notices if notice["send_on"] == on]
            cases.append(("batch_" + label, {"command": "batch", "on": on, "accounts": members}, {"on": on, "notices": notices, "total_due_cents": sum(notice["amount_due_cents"] for notice in notices)}))
    if stage >= 6:
        for label, member in notice_accounts():
            cases.append(("compat_" + label, {"command": "compat_notice", "release": "1.0", "account": member}, {"release": "1.0", "notice": expected_notice(member, "release1")}))
    return cases


def identical(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(identical(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(identical(a, b) for a, b in zip(actual, expected))
    return actual == expected


def evaluate(project, stage, cli_args=()):
    cases = cases_for(stage)
    failures = []
    for label, request, expected in cases:
        try:
            result = subprocess.run([sys.executable, str(project / "main.py"), *cli_args], input=json.dumps(request), text=True, capture_output=True, cwd=project, timeout=3)
            if result.returncode:
                failures.append({"case": label, "reason": "nonzero_exit", "code": result.returncode, "stderr": result.stderr[:2000]})
                continue
            actual = json.loads(result.stdout)
            if not identical(actual, expected):
                failures.append({"case": label, "expected": expected, "actual": actual})
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            failures.append({"case": label, "reason": type(error).__name__, "message": str(error)})
    return {"stage": stage, "total": len(cases), "passed": len(cases) - len(failures), "failed": len(failures), "failures": failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, type=int, choices=range(1, 7))
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--cli-arg", action="append", default=[])
    args = parser.parse_args()
    result = evaluate(args.project.resolve(), args.stage, args.cli_arg)
    print(json.dumps(result, indent=2))
    return int(result["failed"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())
