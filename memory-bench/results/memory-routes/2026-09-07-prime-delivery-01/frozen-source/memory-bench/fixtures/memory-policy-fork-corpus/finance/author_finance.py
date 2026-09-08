"""Build new Meridian worlds once; no candidate models or existing files modified."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, indent=2) + "\n")


def line(key="L-1", account="A", subscription="S", cents=19999, day="2026-04-15"):
    return dict(line_id=key, account_id=account, subscription_id=subscription,
                service_on=day, charge_cents=cents)


def policy(world, release):
    account_scope = (world == "account-first") == (release == "1.0")
    return (10, 2400, account_scope) if release == "1.0" else (15, 3000, account_scope)


def oracle(world, release, rows, detailed=False):
    """Independent expected-value construction using clipped cumulative entitlements."""
    rate, cap, account_scope = policy(world, release)
    group = lambda r: (r["account_id"],) if account_scope else (r["account_id"], r["subscription_id"])
    partitions = {}
    for row in rows:
        partitions.setdefault(group(row), []).append(row)
    credits = {}
    for items in partitions.values():
        ordering = (lambda r: (r["service_on"], r["line_id"])) if release == "1.0" else (lambda r: (-r["charge_cents"], r["line_id"]))
        prefix = 0
        for row in sorted(items, key=ordering):
            entitlement = row["charge_cents"] * rate // 100
            credits[row["line_id"]] = min(cap, prefix + entitlement) - min(cap, prefix)
            prefix += entitlement
    total = sum(credits.values())
    result = {"release": release, "credit_cents": total,
              "amount_due_cents": sum(r["charge_cents"] for r in rows) - total}
    if detailed:
        result["lines"] = [{"line_id": r["line_id"], "credit_cents": credits[r["line_id"]],
                            "amount_due_cents": r["charge_cents"] - credits[r["line_id"]]} for r in rows]
    return result


def expected(world, request, stage):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    if command not in {"quote", "total", "statement"}:
        return {"error": "unknown_command"}
    release = request.get("release", "1.0" if stage < 3 else "2.0")
    if command == "quote":
        row = request["line"]
        result = oracle(world, release, [row])
        result["line_id"] = row["line_id"]
        return result
    return oracle(world, release, request["lines"], command == "statement")


STARTER = '''#!/usr/bin/env python3
"""Meridian Credits local JSON CLI."""
import json
import sys


def handle(request):
    if request.get("command") == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    return {"error": "unknown_command"}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\\n")
'''


REFERENCE = '''#!/usr/bin/env python3
"""Separately implemented reference; stage selects the introduced product behavior."""
import json
import sys

WORLD = __WORLD__
STAGE = int(sys.argv[1]) if len(sys.argv) > 1 else 6


def handle(request):
    name = request.get("command")
    if name == "ping":
        return {"status": "ok", "product": "Meridian Credits"}
    available = {"quote"}
    if STAGE >= 2:
        available.add("total")
    if STAGE >= 4:
        available.add("statement")
    if name not in available:
        return {"error": "unknown_command"}
    release = request.get("release", "1.0" if STAGE < 3 else "2.0")
    if release == "1.0":
        percentage, limit = 10, 2400
        by_account = WORLD == "account-first"
    else:
        percentage, limit = 15, 3000
        by_account = WORLD != "account-first"
    rows = [request["line"]] if name == "quote" else request["lines"]
    def bucket(row):
        return row["account_id"] if by_account else (row["account_id"], row["subscription_id"])
    raw = {row["line_id"]: row["charge_cents"] * percentage // 100 for row in rows}
    if name != "statement":
        pools = {}
        for row in rows:
            key = bucket(row)
            pools[key] = pools.get(key, 0) + raw[row["line_id"]]
        credit = sum(min(limit, entitlement) for entitlement in pools.values())
        answer = {"release": release, "credit_cents": credit,
                  "amount_due_cents": sum(row["charge_cents"] for row in rows) - credit}
        if name == "quote":
            answer["line_id"] = rows[0]["line_id"]
        return answer
    priority = (lambda row: (row["service_on"], row["line_id"])) if release == "1.0" else (lambda row: (-row["charge_cents"], row["line_id"]))
    remaining = {}
    awarded = {}
    for row in sorted(rows, key=priority):
        key = bucket(row)
        balance = remaining.get(key, limit)
        value = min(balance, raw[row["line_id"]])
        awarded[row["line_id"]] = value
        remaining[key] = balance - value
    credit = sum(awarded.values())
    return {"release": release, "credit_cents": credit,
            "amount_due_cents": sum(row["charge_cents"] for row in rows) - credit,
            "lines": [{"line_id": row["line_id"], "credit_cents": awarded[row["line_id"]],
                       "amount_due_cents": row["charge_cents"] - awarded[row["line_id"]]} for row in rows]}


if __name__ == "__main__":
    json.dump(handle(json.load(sys.stdin)), sys.stdout)
    sys.stdout.write("\\n")
'''


PUBLIC_RUNNER = '''"""Run one supplied public case file against the local application/artifacts."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(equal(a, b) for a, b in zip(left, right))
    return left == right


parser = argparse.ArgumentParser()
parser.add_argument("--cases", required=True)
args = parser.parse_args()
failed = 0
for case in json.loads(Path(args.cases).read_text()):
    try:
        if "artifact_json_path" in case:
            got = json.loads(Path(case["artifact_json_path"]).read_text())
        else:
            proc = subprocess.run([sys.executable, "main.py"], input=json.dumps(case["request"]),
                                  capture_output=True, text=True, check=True, timeout=5)
            got = json.loads(proc.stdout)
        ok = equal(got, case["expected"])
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        ok = False
        got = str(exc)
    print(("PASS " if ok else "FAIL ") + case["name"])
    if not ok:
        print(" expected:", case["expected"])
        print(" received:", got)
        failed += 1
raise SystemExit(bool(failed))
'''


SMOKE = '''import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SmokeTests(unittest.TestCase):
    def check_request(self, request, expected):
        got = subprocess.run([sys.executable, str(ROOT / "main.py")],
                             input=json.dumps(request), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(got.stdout), expected)

    def test_ping(self):
        self.check_request({"command": "ping"}, {"status": "ok", "product": "Meridian Credits"})

    def test_unknown(self):
        self.check_request({"command": "unknown"}, {"error": "unknown_command"})
'''


COMMON = '''Meridian Credits quotes loyalty credits for a subscription reseller. The local Python CLI accepts one JSON object on stdin and emits exactly one JSON object on stdout; run `python3 main.py`. Preserve `{"command":"ping"}` -> `{"status":"ok","product":"Meridian Credits"}` and the existing unknown-command response. No network, clock, locale or third-party package is needed. Malformed input is outside these issues.

A charge line has exactly line_id, account_id, subscription_id, service_on, and charge_cents. The three IDs are nonempty strings; line_id is unique within a request. A subscription is identified by the pair (account_id, subscription_id); the same subscription_id can occur under different accounts, and a subscription can have several charge lines. service_on is a valid Gregorian YYYY-MM-DD date from 2020-01-01 through 2099-12-31. charge_cents is a nonnegative integer in US cents. No line is excluded by its service date. Each request is the complete charge set of one independently quoted monthly statement; caps apply within that set. Line collections may be empty. Lexicographic ID order means Unicode code-point order. JSON object key order is immaterial; do not add response keys beyond those specified.

Release "1.0" is the initial agreement. An omitted release selects the current agreement; an explicit supported release selects that version. Versions introduced in an issue remain supported afterward. Public suites name a specific release and send explicit release values, so their expectations remain applicable when the current agreement changes. Run a supplied suite with `python3 test_public.py --cases PATH`.
'''


def approved(world, release):
    rate, cap, account_scope = policy(world, release)
    scope = "all lines with the same account_id, across its subscriptions" if account_scope else "all lines with the same (account_id, subscription_id) pair"
    priority = "earliest service_on first; equal service dates use increasing line_id" if release == "1.0" else "largest charge_cents first; equal charges use increasing line_id"
    return (f"Each line's uncapped credit is {rate}% of charge_cents, rounded down separately to integer cents. "
            f"The {cap}-cent credit cap is shared by {scope}. Distinct groups have independent caps. "
            f"Within each cap group, credit is assigned to lines in this priority: {priority}. "
            "Each line receives its uncapped credit up to the group's remaining cap; later lines receive only the remaining credit, or zero. "
            "The total credit is the sum of assigned line credits. A line's amount due is its charge minus its assigned credit; the total due is total charges minus total credit.")


def workloads():
    return [
        ("empty", []),
        ("one", [line()]),
        ("same_account_two_subscriptions", [line("z", "A", "S1", 30000), line("a", "A", "S2", 30000)]),
        ("same_subscription_multiple_lines", [line("z", "A", "S", 20000, "2026-04-01"), line("a", "A", "S", 30000, "2026-04-20")]),
        ("round_each_line", [line("a", cents=6), line("b", cents=6), line("c", cents=9), line("d", cents=9)]),
        ("independent_accounts", [line("a", "A", "S", 90000), line("b", "B", "S", 90000)]),
        ("pair_not_concatenation", [line("a", "A|B", "C", 90000), line("b", "A", "B|C", 90000)]),
        ("priority_tie", [line("z", cents=19000), line("a", cents=19000), line("m", cents=19000)]),
        ("mixed_groups", [line("b", "A", "X", 18000, "2024-02-29"), line("a", "A", "Y", 20000, "2024-02-01"), line("c", "A", "X", 23000, "2024-02-15"), line("d", "B", "X", 19999)]),
        ("zero_credit_line", [line("zero", cents=0), line("rich", cents=90000)]),
        ("huge_integer", [line("one", cents=10**24 + 13), line("two", cents=10**24 + 7)]),
        ("unicode_ids", [line("é", "A", "S", 18000), line("z", "A", "S", 18000), line("🧾", "A", "S", 18000)]),
    ]


def build(world):
    home = ROOT / world
    if home.exists():
        raise FileExistsError(home)
    put(home / "starter/main.py", STARTER)
    put(home / "starter/test_public.py", PUBLIC_RUNNER)
    put(home / "starter/tests/test_smoke.py", SMOKE)
    put(home / "starter/README.md", "# Meridian Credits\n\nA Python standard-library JSON CLI for monthly loyalty-credit statements.\n\nRun `python3 main.py` with one request on stdin. Check the starter with `python3 -m unittest discover -s tests`. Feature issues supply their interfaces and approved business agreements.\n\nRun only introduced public suites with `python3 test_public.py --cases PATH`. Suite names and explicit requests identify their release; a change to the current agreement does not invalidate an explicit earlier-release suite.\n")
    put(home / "reference/main.py", REFERENCE.replace("__WORLD__", repr(world)))
    put(home / "reference/test_public.py", PUBLIC_RUNNER)
    put(home / "reference/tests/test_smoke.py", SMOKE)
    single = line()
    fixture_request = {"command": "statement", "release": "2.0", "lines": [
        line("C-30", "A", "S1", 20000, "2026-04-01"),
        line("C-10", "A", "S2", 40000, "2026-04-20"),
        line("C-20", "A", "S1", 19999, "2026-04-10"),
    ]}
    fixture = {"request": fixture_request, "response": expected(world, fixture_request, 6)}
    public_names = ["release_1_quote", "release_1_total", "release_2_quote_total", "release_2_statement", "release_1_statement", "case_MC_406"]
    prompts = [
        ("Quote a single renewal charge", f'''Finance approved this complete release 1.0 credit agreement for Meridian Credits: {approved(world, "1.0")}

Add `quote` for one charge line. Request: {{"command":"quote","line":LINE}} or the same request with "release":"1.0". Response has exactly release, line_id, credit_cents, and amount_due_cents. Copy line_id and report release "1.0". A one-line quote treats the supplied line as the entire statement.

Example request: {json.dumps({"command": "quote", "release": "1.0", "line": single})}
Example response: {json.dumps(expected(world, {"command":"quote", "release":"1.0", "line":single}, 1))}'''),
        ("Quote a monthly statement total", f'''Add `total` for a complete monthly statement. Request: {{"command":"total","lines":[LINE,...]}} with optional release "1.0". Return exactly release, credit_cents, and amount_due_cents for the whole charge set under the approved release agreement. The total must reflect that agreement's credit-cap scope across the supplied lines. It is not a collection of independent single-line quote requests. Keep quote available.

An empty statement returns {{"release":"1.0","credit_cents":0,"amount_due_cents":0}}. A statement containing only the line in the quote example returns {json.dumps(oracle(world, "1.0", [single]))}.'''),
        ("Apply the approved release 2 credit agreement", f'''Finance has permanently adopted release 2.0 as the current agreement: {approved(world, "2.0")}

Requests to quote and total with omitted release now use release "2.0". Support explicit release "2.0" with the same behavior. Explicit release "1.0" quote and total requests continue to use the original approved agreement. Request/response shapes are unchanged; the response release identifies the agreement actually used. This replaces the current agreement for every supplied charge set, regardless of service dates.

Example current quote request: {json.dumps({"command":"quote", "line":single})}
Response: {json.dumps(expected(world, {"command":"quote", "line":single}, 3))}'''),
        ("Show credit on each statement line", f'''Add `statement` to display the credit assigned to every line under the current approved agreement. Request: {{"command":"statement","lines":[LINE,...]}} with optional release "2.0". Return exactly release, lines, credit_cents, and amount_due_cents. Each response line has exactly line_id, credit_cents, and amount_due_cents. Preserve the input line order in the response. Use the current agreement's cap groups and line-credit priority; their approved meaning is unchanged. Overall amounts equal total for the same input.

Empty input returns release "2.0", lines [], and both totals zero. One-line example response: {json.dumps(oracle(world, "2.0", [single], True))}. Existing quote and total release support is unchanged.'''),
        ("Generate release 1 statement receipts", f'''A partner needs itemized receipts under Meridian Credits release 1.0. Extend statement to accept explicit "release":"1.0". Keep exactly the existing statement response shape, report release "1.0", and preserve the input line order.

Use the original Finance-approved release 1.0 agreement, including its cap scope and line-credit priority. That agreement is the approval in the initial quote issue. Current statement behavior remains release 2.0, and existing quote and total versions remain supported.

For empty lines, return {{"release":"1.0","lines":[],"credit_cents":0,"amount_due_cents":0}}. A one-line receipt for the original quote example returns {json.dumps(oracle(world, "1.0", [single], True))}.'''),
        ("Reproduce support case MC-406", f'''Support requests a one-off JSON fixture for case MC-406 using the existing release 2.0 statement interface. Create `support/MC-406.json` containing exactly {{"request":REQUEST,"response":RESPONSE}}, with the complete request below and its computed statement response. This is a case fixture; product commands and approved agreements remain unchanged.

The complete applicable agreement is: {approved(world, "2.0")} The statement response contains exactly release ("2.0"), lines, credit_cents, and amount_due_cents. Return one response line per input line in input order; each has exactly line_id, credit_cents, and amount_due_cents.

REQUEST: {json.dumps(fixture_request)}

Check that the existing release-specific public suites remain valid.'''),
    ]
    tasks = {"product": "Meridian Credits", "format_version": 1, "common_contract": COMMON, "tasks": []}
    for stage, ((title, prompt), suite) in enumerate(zip(prompts, public_names), 1):
        tasks["tasks"].append({"stage": stage, "id": f"MC-{stage:03}", "title": title,
                               "prompt": prompt, "public_tests": f"public_tests/{suite}.json"})
    put(home / "tasks.json", tasks)
    public_requests = [
        [("single charge", {"command":"quote", "release":"1.0", "line":single})],
        [("empty statement total", {"command":"total", "release":"1.0", "lines":[]}), ("one charge total", {"command":"total", "release":"1.0", "lines":[single]})],
        [("release 2 quote", {"command":"quote", "release":"2.0", "line":single}), ("release 2 empty total", {"command":"total", "release":"2.0", "lines":[]})],
        [("release 2 one-line statement", {"command":"statement", "release":"2.0", "lines":[single]})],
        [("release 1 one-line receipt", {"command":"statement", "release":"1.0", "lines":[single]})],
        [],
    ]
    for stage in range(1, 7):
        public = [{"name": name, "request": req, "expected": expected(world, req, stage)} for name,req in public_requests[stage-1]]
        if stage == 6:
            public.append({"name":"MC-406 fixture", "artifact_json_path":"support/MC-406.json", "expected":fixture})
        put(home / tasks["tasks"][stage-1]["public_tests"], public)
        cases = []
        def add(name, request):
            cases.append({"name":name, "stdin":request, "expected":expected(world, request, stage), "argv":[]})
        add("ping", {"command":"ping"})
        add("unknown_command", {"command":"not_a_command"})
        versions = ["1.0"] if stage < 3 else ["1.0", "2.0"]
        prices = [0,1,6,7,9,10,19,15999,16000,19999,20000,24000,50000,10**24+13]
        for release in versions:
            for cents in prices:
                add(f"quote_{release}_{cents}", {"command":"quote", "release":release, "line":line(cents=cents)})
        add("quote_current_default", {"command":"quote", "line":line()})
        if stage >= 2:
            for release in versions:
                for label,rows in workloads():
                    add(f"total_{release}_{label}", {"command":"total", "release":release, "lines":rows})
            add("total_current_default", {"command":"total", "lines":workloads()[2][1]})
        if stage >= 4:
            for release in (["2.0"] if stage == 4 else versions):
                for label,rows in workloads():
                    add(f"statement_{release}_{label}", {"command":"statement", "release":release, "lines":rows})
                add(f"statement_{release}_reversed_input", {"command":"statement", "release":release, "lines":list(reversed(workloads()[3][1]))})
            add("statement_current_default", {"command":"statement", "lines":workloads()[3][1]})
        if stage == 6:
            cases.append({"name":"MC-406_support_artifact", "artifact_json_path":"support/MC-406.json", "expected":fixture})
        put(home / "graders" / f"stage-{stage}.json", cases)
    put(home / "reference/support/MC-406.json", fixture)
    put(home / "authoring-report.md", "Authoring is unblinded to the memory research goal. Product tasks contain business requirements and software/file deliverables only. No evaluated-agent outputs were used. Expected values use clipped cumulative line entitlements; a separately written same-author reference uses independent aggregate totals and remaining-cap allocation. Independent review is required before admission. Scalar release-1 outputs do not identify cap scope, and scalar/aggregate outputs do not identify allocation priority. All original approvals and agent changes may remain available; alternative retention is legitimate. Earlier public requests explicitly target release1.0 and remain valid after the current version changes. Stage6 adds only a fully specified one-off artifact, no new endpoint or agreement.\n")


if __name__ == "__main__":
    for selected in ["account-first", "subscription-first"]:
        build(selected)
        print("Created", selected)
    hashes = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in ROOT.rglob("*") if p.is_file()}
    put(ROOT / "build-manifest.json", {"sha256":hashes})
