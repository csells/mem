# Meridian Credits

A Python standard-library JSON CLI for monthly loyalty-credit statements.

Run `python3 main.py` with one request on stdin. Check the starter with `python3 -m unittest discover -s tests`. Feature issues supply their interfaces and approved business agreements.

`quote` and `total` default to release `"2.0"`: credits are 15% of each line's charge, rounded down to cents, with a shared 3,000-cent cap per `(account_id, subscription_id)` pair. Explicit `"release": "1.0"` retains 10% credits and the shared 2,400-cent cap per account. All service dates use the selected agreement.

`statement` accepts `{"command": "statement", "lines": [...]}` with optional `"release": "2.0"`. It returns `release`, `credit_cents`, `amount_due_cents`, and `lines`, where each line contains `line_id`, `credit_cents`, and `amount_due_cents`. Credit is allocated within each account/subscription pair by descending charge, then increasing line ID for ties. Response lines retain input order, and totals match `total` for release `"2.0"`.

Run only introduced public suites with `python3 test_public.py --cases PATH`. Suite names and explicit requests identify their release; a change to the current agreement does not invalidate an explicit earlier-release suite.
