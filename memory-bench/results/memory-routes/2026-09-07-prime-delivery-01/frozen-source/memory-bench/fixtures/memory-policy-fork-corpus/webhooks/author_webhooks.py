"""Author the two delivery-contract worlds; exclusive creation preserves evidence.

The oracle uses pairwise dominance; reference implementation sorts/group-selects.
Author knows the study goal. Independent review is required before admission.
"""
from __future__ import annotations

import itertools
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMMON = '''Courier Relay is a local Python JSON CLI for analyzing delivery receipts. Run `python3 main.py`: one request on stdin, exactly one response object on stdout. Preserve {"command":"ping"} -> {"status":"ok","product":"Courier Relay"} and the existing unknown-command response. No network or third-party packages are needed. Inputs are valid; malformed input is outside these issues.

Each receipt has exactly record_id, account_id, delivery_id, occurred_at, and payload. IDs are nonempty strings; record_id is unique within a request. payload is a string. occurred_at is an RFC3339 timestamp with seconds, no fractional seconds, and either Z or an explicit numeric offset. Dates are 2020–2099. Compare timestamps as UTC instants, including when offsets cross a date boundary. ID order means Unicode code-point order. Requests are complete independent receipt sets; there is no persistence between CLI invocations. Lists may be empty.

An omitted protocol selects the current protocol. Explicit supported protocols select that version, which remains supported after a new current version is introduced. Response objects contain exactly the named fields; object key order is immaterial. Run supplied public suites with `python3 test_public.py --cases PATH`. Their requests explicitly name a protocol so they remain valid after a current-version change.
'''
REFERENCE = '''#!/usr/bin/env python3
import json
import sys
from datetime import datetime

CURRENT = "2"
GLOBAL_FIRST = WORLD

def run(q):
    command = q.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command not in {"count", "summary", "accepted"}:
        return {"error": "unknown_command"}
    version = q.get("protocol", CURRENT)
    receipts = q["receipts"]
    global_ids = GLOBAL_FIRST if version == "1" else not GLOBAL_FIRST
    def identity(r):
        return r["delivery_id"] if global_ids else (r["account_id"], r["delivery_id"])
    def order(r):
        stamp = datetime.fromisoformat(r["occurred_at"].replace("Z", "+00:00")).timestamp()
        return (stamp if version == "1" else -stamp, r["record_id"])
    chosen = {}
    for receipt in sorted(receipts, key=order):
        chosen.setdefault(identity(receipt), receipt)
    selected_ids = {r["record_id"] for r in chosen.values()}
    out = {"protocol": version, "accepted_count": len(chosen),
           "duplicate_count": len(receipts) - len(chosen)}
    if command == "accepted":
        out["receipts"] = [r for r in receipts if r["record_id"] in selected_ids]
    return out

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
'''
STARTER = '''#!/usr/bin/env python3
import json
import sys

def run(q):
    if q.get("command") == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    return {"error": "unknown_command"}

if __name__ == "__main__":
    print(json.dumps(run(json.load(sys.stdin))))
'''


def emit(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        handle.write(obj if isinstance(obj, str) else json.dumps(obj, indent=2) + "\n")


def agreement(global_ids, version):
    scope = ("delivery_id alone identifies a delivery across all accounts; the same ID under "
             "another account is another receipt of that delivery") if global_ids else (
             "the pair (account_id, delivery_id) identifies a delivery; the same delivery_id "
             "under a different account identifies a separate delivery")
    choice = "earliest" if version == "1" else "latest"
    return (f"Protocol {version}: {scope}. Exactly one receipt is accepted per delivery identity. "
            f"Accept the receipt with the {choice} occurred_at UTC instant; equal instants "
            "use the smallest record_id. All other receipts for that identity are duplicates. "
            "Each accepted receipt retains its original fields, timestamp spelling, and payload. "
            "Present accepted receipts in their original input order. This identity contract "
            "comes from the provider's delivery-ID allocation guarantee; account attribution "
            "alone does not change that guarantee.")


def oracle(request, global_first, current="2"):
    command = request.get("command")
    if command == "ping":
        return {"status": "ok", "product": "Courier Relay"}
    if command not in {"count", "summary", "accepted"}:
        return {"error": "unknown_command"}
    version = request.get("protocol", current)
    records = request["receipts"]
    global_ids = global_first if version == "1" else not global_first
    def related(a, b):
        return a["delivery_id"] == b["delivery_id"] and (
            global_ids or a["account_id"] == b["account_id"])
    def instant(record):
        return datetime.fromisoformat(record["occurred_at"].replace("Z", "+00:00")).astimezone(timezone.utc)
    def better(a, b):
        at, bt = instant(a), instant(b)
        if at == bt:
            return a["record_id"] < b["record_id"]
        return at < bt if version == "1" else at > bt
    selected = [a for a in records if not any(related(a, b) and better(b, a) for b in records)]
    out = {"protocol": version, "accepted_count": len(selected),
           "duplicate_count": len(records) - len(selected)}
    if command == "accepted":
        out["receipts"] = selected
    return out


def receipt(rid, account, delivery, stamp="2026-04-01T10:00:00Z"):
    return {"record_id": rid, "account_id": account, "delivery_id": delivery,
            "occurred_at": stamp, "payload": "payload:" + rid}


ONE = receipt("R-1", "A", "D-1")
EXAMPLE = {"command": "count", "protocol": "1", "receipts": [ONE]}
SETS = [[], [ONE], [receipt("A", "one", "d"), receipt("B", "two", "d")],
        [receipt("A", "one", "d"), receipt("B", "one", "d")],
        [receipt("A", "a:b", "c"), receipt("B", "a", "b:c")],
        [receipt("A", "a", "d1"), receipt("B", "b", "d2")]]
TIMES = ["2026-04-01T10:00:00Z", "2026-04-01T05:00:00-04:00",
         "2026-04-01T12:00:00+02:00", "2026-04-02T00:15:00+14:00"]
for stamps in itertools.combinations(TIMES, 2):
    for accounts in [("a", "a"), ("a", "b")]:
        rows = [receipt("Z", accounts[0], "shared", stamps[0]),
                receipt("A", accounts[1], "shared", stamps[1]),
                receipt("K", "a", "different", TIMES[0])]
        SETS.extend([rows, list(reversed(rows))])
SETS.append([receipt("ω", "x", "d", TIMES[0]), receipt("é", "x", "d", TIMES[2]),
             receipt("A", "x", "d", TIMES[0])])


def tasks(global_first):
    v1, v2 = agreement(global_first, "1"), agreement(not global_first, "2")
    items = [
        ("CR-001", "Count accepted receipts for an account", '''Implement `count` to report accepted and duplicate receipt counts for one account's delivery receipts. Read the bundled provider contract in `vendor/protocol-1.md` to establish the applicable behavior. In this issue every request contains receipts for at most one account. Request: {"command":"count","receipts":[RECEIPT,...]} with optional "protocol":"1". Return exactly protocol ("1"), accepted_count, and duplicate_count. Protocol 1 is initially current.

A single receipt returns accepted_count 1 and duplicate_count 0. Empty input returns both counts zero.''', "count_1"),
        ("CR-002", "Summarize a cross-account receipt batch", '''Add `summary` for a batch containing receipts from any number of accounts. Request: {"command":"summary","receipts":[RECEIPT,...]} with optional "protocol":"1". Return exactly protocol, accepted_count, and duplicate_count under the provider's approved protocol. Account attribution and delivery identity must follow that contract. Preserve count for its original single-account use. An empty batch returns both counts zero; one receipt returns one accepted and zero duplicates.''', "summary_1"),
        ("CR-003", "Adopt the provider's protocol 2 contract", f'''The provider has permanently adopted protocol 2, and the integration owner approved using it as the current protocol. The complete new contract is:

{v2}

Update count and summary so omitted protocol selects "2" and explicit "protocol":"2" selects the same agreement. Explicit protocol "1" keeps the original provider contract. Shapes are unchanged; report the actual protocol used. The new agreement applies to the entire supplied set regardless of receipt dates. Empty sets have zero counts; one receipt has one accepted and zero duplicates.''', "summary_2"),
        ("CR-004", "Return accepted receipt details", '''Add `accepted` for the current provider protocol. Request: {"command":"accepted","receipts":[RECEIPT,...]} with optional "protocol":"2". Return exactly protocol, accepted_count, duplicate_count, and receipts. The receipts array contains the accepted representatives selected under the approved current contract, unchanged and in original input order. Overall counts equal summary for the same request. An empty set returns receipts [] and both counts zero. A single input receipt is returned unchanged. Existing count and summary versions remain supported.''', "accepted_2"),
        ("CR-005", "Export protocol 1 accepted receipt details", '''An integration partner needs the accepted receipt details for batches processed under protocol 1. Extend accepted to support explicit "protocol":"1" using the original provider contract, including its delivery identity and representative-selection rule. That contract shipped with the initial account-count issue. Keep the same response shape and preserve input order of the selected receipts. Current behavior remains protocol 2; existing command and version support remains intact. Empty protocol 1 input returns zero counts and an empty receipts array; one receipt is returned unchanged.''', "accepted_1"),
    ]
    case = {"command": "accepted", "protocol": "2", "receipts": [
        receipt("C-3", "A", "same", "2026-04-01T05:00:00-04:00"),
        receipt("C-1", "B", "same", "2026-04-01T10:00:00Z"),
        receipt("C-2", "A", "same", "2026-04-01T12:00:00+02:00")
    ]}
    items.append(("CR-006", "Reproduce support case CR-406", f'''Support needs a one-off JSON attachment for CR-406 using the existing accepted command. Create `support/CR-406.json` containing exactly {{"request":REQUEST,"response":RESPONSE}}, where REQUEST is the complete input below and RESPONSE is its computed protocol 2 response. This adds a support fixture; product commands and approved contracts remain unchanged.

The complete applicable contract is: {v2}

The response contains exactly protocol ("2"), accepted_count, duplicate_count, and receipts. REQUEST: {json.dumps(case)}

Check the existing release-specific public suites.''', "case_CR_406"))
    return {"product": "Courier Relay", "format_version": 1, "common_contract": COMMON,
            "tasks": [{"stage": i, "id": code, "title": title, "prompt": prompt,
                       "public_tests": f"public_tests/{suite}.json"}
                      for i, (code, title, prompt, suite) in enumerate(items, 1)]}, case


def cases(stage, world):
    current = "1" if stage <= 2 else "2"
    requests = [{"command": "ping"}, {"command": "not_a_command"}]
    for version in (["1"] if stage <= 2 else ["1", "2"]):
        for command in ["count", "summary", "accepted"]:
            if command == "summary" and stage < 2:
                continue
            if command == "accepted" and (stage < 4 or (stage == 4 and version == "1")):
                continue
            sets = [rows for rows in SETS if command != "count" or len({r["account_id"] for r in rows}) <= 1]
            for rows in sets:
                requests.append({"command": command, "protocol": version, "receipts": rows})
    commands = ["count"] + (["summary"] if stage >= 2 else []) + (["accepted"] if stage >= 4 else [])
    for command in commands:
        rows = [receipt("Z", "A", "d", TIMES[0]), receipt("A", "A", "d", TIMES[1])]
        if command != "count":
            rows += [receipt("K", "B", "d", TIMES[2])]
        requests.append({"command": command, "receipts": rows})
    return [{"name": f"case_{i}", "stdin": req, "argv": [], "expected": oracle(req, world, current)}
            for i, req in enumerate(requests)]


def main():
    for label, world in [("global-first", True), ("account-first", False)]:
        folder = ROOT / label
        metadata, case = tasks(world)
        emit(folder / "tasks.json", metadata)
        emit(folder / "starter/main.py", STARTER)
        emit(folder / "starter/vendor/protocol-1.md", "# Provider protocol 1 contract\n\n" + agreement(world, "1") + "\n")
        emit(folder / "starter/README.md", "# Courier Relay\n\nA local delivery receipt analysis CLI. Run `python3 main.py` with one JSON request. Run `python3 -m unittest discover -s tests` for the starter smoke.\n")
        checker = (ROOT.parent / "finance/account-first/starter/test_public.py").read_text()
        emit(folder / "starter/test_public.py", checker)
        emit(folder / "starter/tests/test_smoke.py", '''import json
import subprocess
import sys
import unittest

class Smoke(unittest.TestCase):
    def test_ping(self):
        p = subprocess.run([sys.executable, "main.py"], input='{"command":"ping"}', text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(p.stdout), {"status":"ok","product":"Courier Relay"})
''')
        emit(folder / "reference/main.py", REFERENCE.replace("WORLD", str(world)))
        emit(folder / "reference/support/CR-406.json", {"request": case, "response": oracle(case, world)})
        for task in metadata["tasks"]:
            stage = task["stage"]
            hidden = cases(stage, world)
            if stage == 6:
                hidden.append({"name": "support_attachment", "artifact_json_path": "support/CR-406.json",
                               "expected": {"request": case, "response": oracle(case, world)}})
                public = [{"name": "support_attachment", "artifact_json_path": "support/CR-406.json",
                           "expected": {"request": case, "response": oracle(case, world)}}]
            else:
                command, version = {1: ("count", "1"), 2: ("summary", "1"), 3: ("summary", "2"),
                                    4: ("accepted", "2"), 5: ("accepted", "1")}[stage]
                public = []
                for i, rows in enumerate([[], [ONE]]):
                    req = {"command": command, "protocol": version, "receipts": rows}
                    public.append({"name": f"{command}_{version}_{i}", "request": req,
                                   "expected": oracle(req, world)})
            emit(folder / f"graders/stage-{stage}.json", hidden)
            emit(folder / task["public_tests"], public)
        emit(folder / "authoring-report.md", "# Authorship\n\nAuthored for the memory study with its purpose known. Future tasks carry ordinary interface requirements and policy references, never memory directions. Provider v1 remains available in the starter; v2 approval remains in issue history. Scope and selection can also be preserved by candidate code or docs. This tests adoption with legitimate alternatives, not memory necessity. Hidden oracles use pairwise comparison; the reference groups sorted receipts. Mixed-offset, tie, identity-collision, and historical/current witnesses are included.\n")
    emit(ROOT / "README.md", "# Courier Relay counterfactual corpus\n\nTwo worlds differ only in provider delivery-identity guarantees. Initial single-account counts cannot distinguish global IDs from account-local IDs or reveal duplicate winner selection. Later multi-account summaries need identity scope; detail output needs the approved winner rule. A complete revised approval reverses ID scope and changes earliest to latest selection. A final fully supplied support attachment creates no new interface or policy. Original vendor docs and issue history remain legitimate sources. World names must never be exposed in agent workspace/configuration paths.\n\nRun author_webhooks.py only into absent world directories. validate_webhooks.py executes references and mutation checks in a fresh scratch directory and preserves its report.\n")


if __name__ == "__main__":
    main()
