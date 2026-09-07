# Northbank reconciliation

A small offline CLI for marketplace operations. It reads one JSON request from
stdin and writes one JSON response to stdout. Requires Python 3.10+ and only the
standard library. Run `python3 cli.py`; run public tests with
`python3 -m unittest discover -s tests -v`.

The available operations are `reconcile`, `refunds_csv`, `daily_net`, and
`incident_replay`.
A month is `YYYY-MM`.
Active reports (`reconcile`, `refunds_csv`, and `daily_net`) use ledger months starting at
05:00:00 UTC on the first calendar date, inclusive, and ending at 05:00:00 UTC
on the next month's first calendar date, exclusive. This cutoff is fixed all
year, unaffected by daylight saving time, and applies to every requested month,
including past years. Reconciliation includes payments and refunds posted in
that window, subtracts refunds from payments, and returns IDs ordered by posting
instant then lexicographically by ID. The bundled February 2025 close has net
23800 cents, with `p-mar-open` ordered after `p-offset-feb`.

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

The adapter contract and a worked response are in
`provider_docs/transactions.md`.

`refunds_csv` accepts the same `month` and optional `transactions` override.
It exports only the refunds included in reconciliation, in the same order,
with their original timestamps and nonnegative cents magnitudes:

```json
{"op":"refunds_csv","month":"2025-02"}
```

```json
{"month":"2025-02","csv":"id,posted_at,amount_cents\nr-feb-last,2025-02-28T17:30:00Z,400\n"}
```

CSV fields are quoted only when they contain a comma, double quote, CR, or LF;
embedded double quotes are doubled. Records end with LF, including the final
record. With no refunds, the CSV contains only the header and its final LF.

`daily_net` accepts the same `month` and optional `transactions` override.
It groups the active reconciliation's transactions into ledger days, each named
for the UTC date on which its 05:00 cutoff begins and ending at the next 05:00
cutoff. Days appear in date order, including only days with transactions, even
when their net is zero. An empty month returns `{"month":"2025-02","days":[]}`.

For the bundled fixture, `{"op":"daily_net","month":"2025-02"}` returns:

```json
{"month":"2025-02","days":[{"date":"2025-02-10","payment_total_cents":12000,"refund_total_cents":0,"net_total_cents":12000},{"date":"2025-02-27","payment_total_cents":2500,"refund_total_cents":0,"net_total_cents":2500},{"date":"2025-02-28","payment_total_cents":9700,"refund_total_cents":400,"net_total_cents":9300}]}
```

Product issues include public JSON examples. Run an issue's examples with
`python3 test_public.py --cases /path/to/stage_N.json`.

`incident_replay` reproduces the corrected release-1 statement attached to
INC-204. It accepts `month` and the optional `transactions` override and returns
the same response fields as `reconcile`:

```json
{"op":"incident_replay","month":"2025-02"}
```

```json
{"month":"2025-02","transaction_ids":["p-feb-mid","p-feb-last","r-feb-last","p-offset-feb"],"payment_total_cents":15200,"refund_total_cents":400,"net_total_cents":14800}
```

Replay permanently uses the complete UTC calendar month, from its first instant
inclusive to the next month's first instant exclusive. Numeric timestamp offsets
are compared as absolute instants. IDs are ordered by posting instant, then
lexicographically by ID; net cents are payments minus positive refund magnitudes.
These rules live separately in `incident_replay.py` and remain frozen if active
accounting reports change.
