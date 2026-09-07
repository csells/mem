import json
from pathlib import Path

root = Path(__file__).parent
common = (
    "Work in the supplied Python CLI project. Keep its JSON stdin/stdout entrypoint, "
    "the transactions input override, and the bundled fixtures usable. Input guarantees "
    "and ordering rules are in README.md. Preserve previously delivered operations "
    "unless this issue explicitly changes their business behavior. "
    "No network or third-party packages are needed."
)

issues = [
    ("recon-101", "February close is missing posted transactions", """
Finance's February 2025 reconciliation does not match its LedgerLake statement.
The CLI reports a net of 12000 cents from the bundled snapshot. Operations has
verified that p-feb-last, r-feb-last, and p-offset-feb are finalized February
postings and belong in the close. Investigate the discrepancy and fix reconcile
for complete UTC calendar months, including other month lengths and year rollover.

For {"op":"reconcile","month":"2025-02"}, the response must be:
{"month":"2025-02","transaction_ids":["p-feb-mid","p-feb-last","r-feb-last","p-offset-feb"],"payment_total_cents":15200,"refund_total_cents":400,"net_total_cents":14800}

p-mar-open belongs to March. The same rules must apply to caller-provided
transactions. Keep the existing response shape and add a regression check.
"""),
    ("recon-102", "Export the refunds included in a close", """
Add op refunds_csv so support can send accounting the refund detail behind a
reconciliation. It accepts month and the same optional transactions override.
Include exactly the refunds belonging to that month's reconcile result, in the
same posting-instant/ID order. A refund's amount is its positive cents magnitude.

Return exactly {"month":<requested month>,"csv":<CSV string>} with header
id,posted_at,amount_cents. Use comma-separated CSV with minimal double-quote
escaping: quote a field only if it contains a comma, double quote, CR, or LF;
double any double quotes inside quoted fields. Use LF line endings,
and one final LF. Preserve each original posted_at string. Empty output is the
header plus LF. A payment must never appear in the CSV.

For {"op":"refunds_csv","month":"2025-02"}, return:
{"month":"2025-02","csv":"id,posted_at,amount_cents\\nr-feb-last,2025-02-28T17:30:00Z,400\\n"}

The existing reconcile operation stays available.
"""),
    ("recon-103", "Replay the incident export for support comparisons", """
Support needs a frozen reproduction of the corrected release-1 statement
attached to incident INC-204. Add op incident_replay with month and the optional
transactions override. Reproduce the corrected reconciliation already delivered:
include posting instants at or after 00:00 UTC on the month's first calendar date
and strictly before 00:00 UTC on the next month's first calendar date. Compare
absolute instants in UTC, including when posted_at uses a numeric offset.
For February 2024 the upper cutoff is March 1 at 00:00 UTC; for December 2025 it
is January 1, 2026 at 00:00 UTC. Include the entire final calendar date.

Return reconcile's exact response shape: month, transaction_ids,
payment_total_cents, refund_total_cents, and net_total_cents. Order the IDs by
posting instant, then lexicographically by ID. Sum payments and positive refund
magnitudes separately; net is payments minus refunds. This endpoint permanently
reproduces that corrected statement's behavior even if active accounting reports
change later. It does not change reconcile or refunds_csv.

For {"op":"incident_replay","month":"2025-02"}, return:
{"month":"2025-02","transaction_ids":["p-feb-mid","p-feb-last","r-feb-last","p-offset-feb"],"payment_total_cents":15200,"refund_total_cents":400,"net_total_cents":14800}
"""),
    ("recon-104", "Move active closes to the finance ledger's 05:00 cutoff", """
Finance is permanently changing the meaning of a month in active reports. A
ledger month starts at 05:00:00 UTC on its first calendar date (included), and
ends at 05:00:00 UTC on the first calendar date of the next month (excluded).
The cutoff is fixed at 05:00 UTC all year; daylight saving time does not change
it. Reconcile and refunds_csv must both use this meaning for every requested
month, including months in past years. Keep their response shapes unchanged.

Example caller-provided rows for month 2025-02:
a payment of 100 cents at 2025-02-01T04:59:59.999Z is excluded;
b payment of 200 cents at 2025-02-01T05:00:00Z is included;
c refund of 30 cents at 2025-03-01T04:59:59.999Z is included;
d payment of 400 cents at 2025-03-01T05:00:00Z is excluded.
With IDs a,b,c,d respectively, reconcile returns:
{"month":"2025-02","transaction_ids":["b","c"],"payment_total_cents":200,"refund_total_cents":30,"net_total_cents":170}
The refund CSV contains only c. With the bundled snapshot the new February net
is 23800 cents and p-mar-open appears after p-offset-feb.

incident_replay remains frozen under its previously specified contract.
"""),
    ("recon-105", "Show daily net settlement inside an active close", """
Add op daily_net with month and the optional transactions override. Return the
daily payment, refund, and net totals that compose the active ledger-month
reconciliation. A ledger day carries the calendar date on which its 05:00 UTC
cutoff begins and lasts until the next 05:00 UTC cutoff. Use the active finance
month definition. Include only dates with at least one included transaction,
even if that date's net is zero, ordered by date. An empty month has days: [].

Return exactly:
{"month":<requested month>,"days":[{"date":"YYYY-MM-DD","payment_total_cents":<integer>,"refund_total_cents":<integer>,"net_total_cents":<integer>},...]}

Example for month 2025-02: payment p of 1000 cents posted at
2025-02-28T23:00:00Z and refund r of 250 cents posted at
2025-03-01T04:30:00Z both belong to ledger day 2025-02-28. A payment of 900
cents at 2025-03-01T05:00:00Z belongs to the next month and is absent. Output:
{"month":"2025-02","days":[{"date":"2025-02-28","payment_total_cents":1000,"refund_total_cents":250,"net_total_cents":750}]}

Previously delivered operations remain available with their established behavior.
"""),
    ("recon-106", "Reproduce the release 1 customer reconciliation", """
A customer is matching archived reports from release 1, shipped after the
February omission was fixed and before the 05:00 ledger cutoff was introduced.
Add op release1_reconcile with month and the optional transactions override.
It must reproduce that release's complete UTC calendar-month reconciliation:
include 00:00 UTC on the first date and every later posting in that UTC month;
exclude 00:00 UTC on the first date of the next month. Use the same JSON shape,
ordering, and positive refund magnitudes as reconcile.

For {"op":"release1_reconcile","month":"2025-02"}, return:
{"month":"2025-02","transaction_ids":["p-feb-mid","p-feb-last","r-feb-last","p-offset-feb"],"payment_total_cents":15200,"refund_total_cents":400,"net_total_cents":14800}

Active reconcile, refunds_csv, and daily_net continue to use the 05:00 UTC
ledger cutoff. incident_replay continues to reproduce the corrected statement
attached to INC-204. All report operations must coexist for the same requested
month and transaction input.
"""),
]

tasks = []
for number, (issue_id, title, body) in enumerate(issues, 1):
    tasks.append({
        "stage": number,
        "id": issue_id,
        "title": title,
        "prompt": common + "\n\n" + body.strip(),
        "public_tests": "public_tests/stage_" + str(number) + ".json",
        "grader": "python3 graders/grade.py --stage " + str(number) + " --candidate <working-directory>",
    })

(root / "tasks.json").write_text(json.dumps({
    "product": "Northbank reconciliation",
    "language": "python",
    "entrypoint": "python3 cli.py",
    "protocol": "one JSON stdin request; one JSON stdout response; exit 0 on valid requests",
    "tasks": tasks,
}, indent=2) + "\n")
print("Wrote six sequential issues.")
