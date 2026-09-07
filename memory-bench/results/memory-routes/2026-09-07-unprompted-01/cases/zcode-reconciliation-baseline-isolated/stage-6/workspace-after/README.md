# Northbank reconciliation

A small offline CLI for marketplace operations. It reads one JSON request from
stdin and writes one JSON response to stdout. Requires Python 3.10+ and only the
standard library. Run `python3 cli.py`; run public tests with
`python3 -m unittest discover -s tests -v`.

The available operations are `reconcile`, `refunds_csv`, `daily_net`,
`incident_replay`, and `release1_reconcile`.
A month is `YYYY-MM`. The active reports, `reconcile` and `refunds_csv`, use
the finance ledger month: it starts at 05:00:00 UTC on the month's first
calendar date (included) and ends at 05:00:00 UTC on the first calendar date
of the next month (excluded). The cutoff is fixed at 05:00 UTC all year;
daylight saving time does not change it. Include the payments and refunds
posted inside that window, subtract refunds from payments, and return IDs
ordered by posting instant then lexicographically by ID. `incident_replay`
and `release1_reconcile` keep the original complete UTC calendar month
described below.

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

`refunds_csv` exports the refund detail behind a reconciliation: the refunds
belonging to that month's reconcile result, in the same posting-instant/ID
order, as CSV with header `id,posted_at,amount_cents` and one final LF. Fields
are quoted only when they contain a comma, double quote, CR, or LF. It accepts
the same `transactions` override.

```json
{"op":"refunds_csv","month":"2025-02"}
```

Response:

```json
{"month":"2025-02","csv":"id,posted_at,amount_cents\nr-feb-last,2025-02-28T17:30:00Z,400\n"}
```

`daily_net` decomposes a month's reconcile into ledger days. A ledger day
carries the calendar date on which its 05:00 UTC cutoff begins and lasts until
the next 05:00 UTC cutoff, so an instant before 05:00 UTC falls on the prior
date. Days with no included transactions are omitted; a day whose refunds equal
its payments stays with `net_total_cents` 0. Days are ordered by date and an
empty month returns `days: []`. It accepts the same `transactions` override.

```json
{"op":"daily_net","month":"2025-02"}
```

Response:

```json
{"month":"2025-02","days":[{"date":"2025-02-10","payment_total_cents":12000,"refund_total_cents":0,"net_total_cents":12000},{"date":"2025-02-27","payment_total_cents":2500,"refund_total_cents":0,"net_total_cents":2500},{"date":"2025-02-28","payment_total_cents":9700,"refund_total_cents":400,"net_total_cents":9300}]}
```

`incident_replay` is a frozen reproduction of the corrected release-1 statement
attached to incident INC-204, for support comparisons. It returns reconcile's
response shape over the complete UTC calendar month — posting instants at or
after 00:00 UTC on the month's first calendar date and strictly before 00:00
UTC on the next month's first calendar date, compared as absolute instants in
UTC. Unlike the active reports, this behavior stays fixed even if `reconcile`
or `refunds_csv` change later. It accepts the same `transactions` override and
does not modify the other operations.

```json
{"op":"incident_replay","month":"2025-02"}
```

Response:

```json
{"month":"2025-02","transaction_ids":["p-feb-mid","p-feb-last","r-feb-last","p-offset-feb"],"payment_total_cents":15200,"refund_total_cents":400,"net_total_cents":14800}
```

`release1_reconcile` reproduces the archived release 1 report, shipped after
the February omission was fixed and before the 05:00 UTC ledger cutoff was
introduced. It returns `reconcile`'s response shape, ordering, and positive
refund magnitudes over the complete UTC calendar month — posting instants at
or after 00:00 UTC on the month's first calendar date and strictly before
00:00 UTC on the next month's first calendar date, compared as absolute
instants in UTC. Like `incident_replay`, this behavior stays fixed even if
the active reports change later, and all report operations coexist for the
same requested month and transaction input. It accepts the same
`transactions` override.

```json
{"op":"release1_reconcile","month":"2025-02"}
```

Response:

```json
{"month":"2025-02","transaction_ids":["p-feb-mid","p-feb-last","r-feb-last","p-offset-feb"],"payment_total_cents":15200,"refund_total_cents":400,"net_total_cents":14800}
```

Input guarantees: valid month years 2000–2099; unique IDs; valid timezone-aware
timestamps with `Z` or numeric offsets and at most millisecond precision;
`kind` is `payment` or `refund`; integer cents are nonnegative. Unknown extra
row fields may be ignored. Invalid-input behavior is outside this exercise.
No success logs belong on stdout. JSON key order is immaterial.

The adapter contract and a worked response are in
`provider_docs/transactions.md`.

Product issues include public JSON examples. Run an issue's examples with
`python3 test_public.py --cases /path/to/stage_N.json`.
