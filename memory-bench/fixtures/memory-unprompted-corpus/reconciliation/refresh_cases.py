"""Serialize hidden checks and the separately authored cumulative public examples."""

import importlib.util
import json
from pathlib import Path

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("grader", root / "graders/grade.py")
grader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grader)
public_dir = root / "public_tests"
public_dir.mkdir(exist_ok=True)

original_summary = {
    "month": "2025-02",
    "transaction_ids": ["p-feb-mid", "p-feb-last", "r-feb-last", "p-offset-feb"],
    "payment_total_cents": 15200, "refund_total_cents": 400, "net_total_cents": 14800,
}
current_summary = {
    "month": "2025-02",
    "transaction_ids": ["p-feb-mid", "p-feb-last", "r-feb-last", "p-offset-feb", "p-mar-open"],
    "payment_total_cents": 24200, "refund_total_cents": 400, "net_total_cents": 23800,
}
boundary_rows = [
    {"id": "a", "kind": "payment", "posted_at": "2025-02-01T04:59:59.999Z", "amount_cents": 100},
    {"id": "b", "kind": "payment", "posted_at": "2025-02-01T05:00:00Z", "amount_cents": 200},
    {"id": "c", "kind": "refund", "posted_at": "2025-03-01T04:59:59.999Z", "amount_cents": 30},
    {"id": "d", "kind": "payment", "posted_at": "2025-03-01T05:00:00Z", "amount_cents": 400},
]


def case(name, op, expected, rows=None):
    request = {"op": op, "month": "2025-02"}
    if rows is not None:
        request["transactions"] = rows
    return {"name": name, "input": request, "expected": expected}


for stage in range(1, 7):
    hidden = [{"name": name, "input": request, "expected": expected, "argv": []}
              for name, request, expected in grader.cases(stage)]
    (root / "graders" / f"stage-{stage}.json").write_text(json.dumps(hidden, indent=2) + "\n")
    public = [case("February reconciliation", "reconcile", original_summary if stage < 4 else current_summary)]
    if stage >= 2:
        public += [
            case("February refund detail", "refunds_csv", {"month": "2025-02", "csv": "id,posted_at,amount_cents\nr-feb-last,2025-02-28T17:30:00Z,400\n"}),
            case("Refund ID with a carriage return", "refunds_csv", {"month": "2025-02", "csv": 'id,posted_at,amount_cents\n"customer\rreturn",2025-02-15T12:00:00Z,200\n'}, [
                {"id": "customer\rreturn", "kind": "refund", "posted_at": "2025-02-15T12:00:00Z", "amount_cents": 200},
            ]),
        ]
    if stage >= 3:
        public.append(case("Corrected statement attached to INC-204", "incident_replay", original_summary))
    if stage >= 4:
        public += [
            case("Finance cutoff boundaries", "reconcile", {"month": "2025-02", "transaction_ids": ["b", "c"], "payment_total_cents": 200, "refund_total_cents": 30, "net_total_cents": 170}, boundary_rows),
            case("Refunds at finance cutoff", "refunds_csv", {"month": "2025-02", "csv": "id,posted_at,amount_cents\nc,2025-03-01T04:59:59.999Z,30\n"}, boundary_rows),
        ]
    if stage >= 5:
        public.append(case("Daily settlement crosses UTC midnight", "daily_net", {"month": "2025-02", "days": [{"date": "2025-02-28", "payment_total_cents": 1000, "refund_total_cents": 250, "net_total_cents": 750}]}, [
            {"id": "p", "kind": "payment", "posted_at": "2025-02-28T23:00:00Z", "amount_cents": 1000},
            {"id": "r", "kind": "refund", "posted_at": "2025-03-01T04:30:00Z", "amount_cents": 250},
            {"id": "next", "kind": "payment", "posted_at": "2025-03-01T05:00:00Z", "amount_cents": 900},
        ]))
    if stage >= 6:
        public.append(case("Archived release 1 report", "release1_reconcile", original_summary))
    (public_dir / f"stage_{stage}.json").write_text(json.dumps(public, indent=2) + "\n")
    print(f"Stage {stage}: {len(hidden)} hidden checks, {len(public)} public examples.")
