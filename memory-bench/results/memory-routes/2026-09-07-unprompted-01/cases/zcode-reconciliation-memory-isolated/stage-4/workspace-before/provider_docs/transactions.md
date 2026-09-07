# LedgerLake snapshot API, revision 2025-01

The production endpoint is `GET /v1/transactions`. This repository's
`provider.LedgerLake` adapter uses a downloaded response, so development needs
neither credentials nor network access. `list_transactions` returns all matching
rows; this local adapter has no pagination or request limits.

| Argument | Meaning |
| --- | --- |
| `created_from` | Include posting instants equal to or later than this timestamp. |
| `created_to` | Include posting instants strictly earlier than this timestamp. |

Both arguments are timezone-aware ISO 8601 timestamps. The service compares
absolute instants in UTC; a timestamp's written calendar date does not determine
its bucket. Millisecond precision and numeric UTC offsets are supported.

Rows contain unique string `id`, `posted_at`, `kind` (`payment` or `refund`), and
nonnegative integer `amount_cents`. All rows in this product are final postings
in USD. Refund amounts are positive magnitudes. There are no pending statuses,
currency conversions, retries, or duplicate provider rows to account for.

Results are ordered by posting instant, then lexicographically by `id` for ties.

Example request:

```python
client.list_transactions(
    created_from="2025-02-28T00:00:00Z",
    created_to="2025-03-01T00:00:00Z",
)
```

From the bundled snapshot this returns `p-feb-last`, `r-feb-last`, and
`p-offset-feb`. `p-mar-open` is outside the response. The offset-written
`p-offset-feb` was posted at 23:45 UTC on February 28.
