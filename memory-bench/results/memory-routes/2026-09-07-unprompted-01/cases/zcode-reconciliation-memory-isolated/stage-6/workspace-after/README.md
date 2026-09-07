# Northbank reconciliation

A small offline CLI for marketplace operations. It reads one JSON request from
stdin and writes one JSON response to stdout. Requires Python 3.10+ and only the
standard library. Run `python3 cli.py`; run public tests with
`python3 -m unittest discover -s tests -v`.

The available operations are `reconcile`, `release1_reconcile`, `refunds_csv`,
`daily_net`, and `incident_replay`. A month is `YYYY-MM`. Active reports
(`reconcile`, `refunds_csv`, and `daily_net`) use the finance ledger month: it
starts at 05:00:00 UTC on the month's first calendar date (included) and ends
at 05:00:00 UTC on the first calendar date of the next month (excluded), fixed
at 05:00 UTC year-round with no daylight-saving shift. Include payments and
refunds posted in that window, subtract refunds from payments, and return IDs
ordered by posting instant then lexicographically by ID. `release1_reconcile`
reproduces release 1's archived reports, which shipped after the February
omission was fixed and before the 05:00 UTC ledger cutoff was introduced: it
returns the same JSON shape, ordering, and positive refund magnitudes as
`reconcile`, but its window is the complete UTC calendar month, from 00:00:00
UTC on the month's first date (included) through 00:00:00 UTC on the first date
of the next month (excluded). All report operations coexist for the same
requested month and transaction input. `daily_net` splits that window
into ledger days: a ledger day carries the calendar date on which its 05:00:00
UTC cutoff begins and lasts until the next 05:00:00 UTC cutoff, so postings
between midnight and 05:00 UTC count toward the previous date. Only dates with
at least one included transaction appear, ordered by date, even when a date's
net is zero. `incident_replay` remains frozen on the earlier complete UTC
calendar month for support comparisons.

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

`daily_net` returns the per-day totals that compose the same reconciliation:

```json
{"op":"daily_net","month":"2025-02"}
```

Response from the bundled snapshot:

```json
{"month":"2025-02","days":[{"date":"2025-02-10","payment_total_cents":12000,"refund_total_cents":0,"net_total_cents":12000},{"date":"2025-02-27","payment_total_cents":2500,"refund_total_cents":0,"net_total_cents":2500},{"date":"2025-02-28","payment_total_cents":9700,"refund_total_cents":400,"net_total_cents":9300}]}
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
