# Meridian Credits

A Python standard-library JSON CLI for monthly loyalty-credit statements.

Run `python3 main.py` with one request on stdin. Check the starter with `python3 -m unittest discover -s tests`. Feature issues supply their interfaces and approved business agreements.

`quote` accepts one `line`; `total` accepts a `lines` array representing a complete monthly statement. Both default to release `"2.0"`: 15% credit rounded down per line, capped at 3,000 cents per `(account_id, subscription_id)` pair. Explicit `"release":"1.0"` retains 10% credit rounded down per line, capped at 2,400 cents per account across subscriptions. Service dates do not select the release.

Run only introduced public suites with `python3 test_public.py --cases PATH`. Suite names and explicit requests identify their release; a change to the current agreement does not invalidate an explicit earlier-release suite.

`statement` accepts a `lines` array with omitted release or `"release":"2.0"` and returns `release`, `credit_cents`, `amount_due_cents`, and `lines`. Each response line contains `line_id`, `credit_cents`, and `amount_due_cents`, in input order. Within each account/subscription pair, credit goes to the largest charge first, then increasing line ID for equal charges, until the cap is exhausted. Statement totals match `total` for the same input; an empty statement returns an empty array and zero totals.
