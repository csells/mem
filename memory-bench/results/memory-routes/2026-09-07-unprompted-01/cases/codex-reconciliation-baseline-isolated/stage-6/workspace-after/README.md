# Northbank reconciliation

A small offline CLI for marketplace operations. It reads one JSON request from
stdin and writes one JSON response to stdout. Requires Python 3.10+ and only the
standard library. Run `python3 cli.py`; run public tests with
`python3 -m unittest discover -s tests -v`.

The available operations are `reconcile`, `refunds_csv`, `daily_net`,
`incident_replay`, and `release1_reconcile`.
A month is `YYYY-MM`. For `reconcile`, `refunds_csv`, and `daily_net`, a ledger month starts
at 05:00:00 UTC on its first calendar date (included) and ends at 05:00:00 UTC
on the next month's first calendar date (excluded). This fixed cutoff applies
to every requested month, including past years, without daylight saving changes.
Include payments and refunds posted in that window, subtract refunds from
payments, and return IDs ordered by posting instant then lexicographically by ID.
The bundled February 2025 reconciliation has a net of 23800 cents, with
`p-mar-open` ordered after `p-offset-feb`.

```json
{"op":"reconcile","month":"2025-02"}
```

The default input is `fixtures/ledgerlake_snapshot.json`. Requests may instead
include `transactions`, an array with the same row shape as the snapshot. An
empty array means no rows. This override is part of the supported CLI contract
and makes customer examples reproducible without editing files.

```json
{"op":"reconcile","month":"2025-02","transactions":[{"id":"p-1","kind":"payment","posted_at":"2025-02-12T12:00:00Z","amount_cents":1250}]}
```

Response:

```json
{"month":"2025-02","transaction_ids":["p-1"],"payment_total_cents":1250,"refund_total_cents":0,"net_total_cents":1250}
```

Input guarantees: valid month years 2000–2099; unique IDs; valid timezone-aware
timestamps with `Z` or numeric offsets and at most millisecond precision;
`kind` is `payment` or `refund`; integer cents are nonnegative. Unknown extra
row fields may be ignored. Invalid-input behavior is outside this exercise.
No success logs belong on stdout. JSON key order is immaterial.

Use `refunds_csv` to export the refunds included in a month's reconciliation,
in the same posting-instant/ID order. It accepts the same `transactions` override.
Amounts are positive cents magnitudes and original timestamp strings are preserved.
CSV fields are quoted only when they contain a comma, double quote, CR, or LF;
embedded double quotes are doubled. Records end with LF, including the final
record. A month with no refunds returns only the header and LF.

```json
{"op":"refunds_csv","month":"2025-02"}
```

```json
{"month":"2025-02","csv":"id,posted_at,amount_cents\nr-feb-last,2025-02-28T17:30:00Z,400\n"}
```

Use `daily_net` to break the active month's reconciliation into daily payment,
refund, and net totals. It accepts the same optional `transactions` override.
Each ledger day begins at 05:00 UTC on its labeled date and ends at the next
05:00 UTC cutoff, excluded. Days appear in date order, including only dates with
at least one included transaction, even when their net or all amounts are zero.
An empty month returns `"days": []`.

```json
{"op":"daily_net","month":"2025-02"}
```

```json
{"month":"2025-02","days":[{"date":"2025-02-10","payment_total_cents":12000,"refund_total_cents":0,"net_total_cents":12000},{"date":"2025-02-27","payment_total_cents":2500,"refund_total_cents":0,"net_total_cents":2500},{"date":"2025-02-28","payment_total_cents":9700,"refund_total_cents":400,"net_total_cents":9300}]}
```

Use `incident_replay` to reproduce the corrected release-1 statement attached to
INC-204. It accepts `month` and the optional `transactions` override and returns
the same response fields as `reconcile`. Its frozen rules include posting instants
at or after the first date's midnight UTC and strictly before the next month's
first midnight UTC, including the entire final calendar date. Numeric timestamp
offsets are compared as absolute UTC instants. IDs sort by posting instant, then
lexicographically by ID; net cents are payments minus positive refund magnitudes.
These rules remain fixed even if active accounting reports change later.

```json
{"op":"incident_replay","month":"2025-02"}
```

```json
{"month":"2025-02","transaction_ids":["p-feb-mid","p-feb-last","r-feb-last","p-offset-feb"],"payment_total_cents":15200,"refund_total_cents":400,"net_total_cents":14800}
```

Use `release1_reconcile` to reproduce archived release 1 customer reports. It
accepts `month` and the optional `transactions` override. Its UTC calendar month
includes midnight on the first date and all later postings before midnight on
the next month's first date. It uses the same response fields, posting-instant/ID
ordering, and positive refund magnitudes as `reconcile`.

```json
{"op":"release1_reconcile","month":"2025-02"}
```

```json
{"month":"2025-02","transaction_ids":["p-feb-mid","p-feb-last","r-feb-last","p-offset-feb"],"payment_total_cents":15200,"refund_total_cents":400,"net_total_cents":14800}
```

The adapter contract and a worked response are in
`provider_docs/transactions.md`.

Product issues include public JSON examples. Run an issue's examples with
`python3 test_public.py --cases /path/to/stage_N.json`.
