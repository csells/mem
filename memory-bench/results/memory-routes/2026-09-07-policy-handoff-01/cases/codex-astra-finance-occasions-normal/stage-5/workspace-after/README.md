# Meridian Credits

A Python standard-library JSON CLI for monthly loyalty-credit statements.

Run `python3 main.py` with one request on stdin. Check the starter with `python3 -m unittest discover -s tests`. Feature issues supply their interfaces and approved business agreements.

Run only introduced public suites with `python3 test_public.py --cases PATH`. Suite names and explicit requests identify their release; a change to the current agreement does not invalidate an explicit earlier-release suite.

`quote`, `total`, and `statement` accept an explicit `"release":"1.0"` or
`"release":"2.0"`; omitting `release` selects the current agreement, `"2.0"`.
For an itemized receipt, send `{"command":"statement","release":"1.0","lines":[...]}`.
The response contains `release`, `lines`, `credit_cents`, and `amount_due_cents`.
Each receipt line contains `line_id`, `credit_cents`, and `amount_due_cents`,
in input order. Release 1.0 floors each line's 10% credit to integer cents and
shares a 2,400-cent cap across all subscriptions of an account, allocating by
earliest `service_on`, then increasing `line_id`. Empty statements return an
empty line list and zero totals.
