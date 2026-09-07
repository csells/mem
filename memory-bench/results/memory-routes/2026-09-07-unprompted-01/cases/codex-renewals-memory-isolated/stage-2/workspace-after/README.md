# HarborPass renewal CLI

HarborPass sells annual memberships. This project is a small local JSON application. It requires Python 3.9 or later and no packages or network access.

Run `python3 main.py` with one JSON request on standard input. The program writes one JSON response to standard output. `{"command":"ping"}` returns `{"status":"ok","product":"HarborPass"}`; an unrecognized command returns `{"error":"unknown_command"}`. JSON key order and surrounding JSON whitespace do not matter.

`{"command":"notice","account":ACCOUNT}` returns one renewal notice. For release 1.0, notices are sent 21 calendar days before renewal. Members with autopay enabled and at least 2 completed years receive a loyalty credit of 10% of the plan price, rounded down to whole cents and capped at 2400 cents. Other members receive zero credit. The amount due is the plan price minus the credit.

`{"command":"export","accounts":[ACCOUNT,...]}` returns `{"csv":STRING,"count":N}` with one current notice per account, preserving input order and duplicate IDs. The CSV columns are `customer_id,send_on,credit_cents,amount_due_cents`. The header and every row end with LF, including the final row. Fields containing a comma, double quote, CR, or LF are quoted, with internal double quotes doubled; other fields are unquoted. An empty collection returns just the header and its LF with a count of zero.

Run the starter tests with `python3 -m unittest discover -s tests -v`. Each product issue is accompanied by a public JSON examples file. Run those examples with `python3 test_public.py --cases /path/to/stage_N.json`. Feature examples for an earlier stage can become obsolete when a later issue explicitly changes its business requirements; the issue history remains available to explain prior releases.

Accounts use customer_id (nonempty string), renewal_on (valid Gregorian YYYY-MM-DD from 2020-01-01 through 2099-12-31), plan_cents (nonnegative integer US cents), completed_years (nonnegative integer), and autopay (boolean). A notice contains customer_id, send_on, credit_cents, and amount_due_cents. Account collections preserve order and duplicate customer IDs. Inputs to the exercises are well formed. No current clock, locale, or remote data is needed.

Implement product issues in their supplied order. Source code, docs, tests, and prior issue text remain available throughout the sequence.
