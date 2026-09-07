# Northbank reconciliation

A small offline CLI for marketplace operations. It reads one JSON request from
stdin and writes one JSON response to stdout. Requires Python 3.10+ and only the
standard library. Run `python3 cli.py`; run public tests with
`python3 -m unittest discover -s tests -v`.

The available operations are `reconcile` and `refunds_csv`. A month is `YYYY-MM`. The product's
initial contract is the complete UTC calendar month: include payments and
refunds posted in that month, subtract refunds from payments, and return IDs
ordered by posting instant then lexicographically by ID. The current release
has a customer-reported discrepancy under investigation.

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

The adapter contract and a worked response are in
`provider_docs/transactions.md`.

Product issues include public JSON examples. Run an issue's examples with
`python3 test_public.py --cases /path/to/stage_N.json`.
