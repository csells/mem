# HarborPass renewal CLI

HarborPass sells annual memberships. This project is a small local JSON application. It requires Python 3.9 or later and no packages or network access.

Run `python3 main.py` with one JSON request on standard input. The program writes one JSON response to standard output. Currently `{"command":"ping"}` returns `{"status":"ok","product":"HarborPass"}`; an unrecognized command returns `{"error":"unknown_command"}`. JSON key order and surrounding JSON whitespace do not matter.

Use `{"command":"notice","account":ACCOUNT}` to generate a renewal notice. Release 1.0 sends notices 21 calendar days before renewal. Members with autopay enabled and at least 2 completed years receive a 10% loyalty credit, rounded down to whole cents and capped at 2400 cents. Other members receive no credit. The amount due is the plan price minus the credit.

Use `{"command":"export","accounts":[ACCOUNT,...]}` to export the current notices as `{"csv":STRING,"count":N}`. The CSV columns are `customer_id,send_on,credit_cents,amount_due_cents`, with a header and LF after every row, including the last. Fields containing commas, double quotes, CR, or LF are quoted, with internal quotes doubled. Input order and duplicate IDs are preserved; an empty collection returns just the header and its LF with count 0.

Use `{"command":"support_replay","case_id":"IOS-1842","account":ACCOUNT}` to reproduce the approved iOS release 1.0 preview as `{"case_id":"IOS-1842","notice":NOTICE}`. This case always uses the release 1.0 rules above, even when the current notice and export policies change. IOS-1842 is the only supported case.

Run the starter tests with `python3 -m unittest discover -s tests -v`. Each product issue is accompanied by a public JSON examples file. Run those examples with `python3 test_public.py --cases /path/to/stage_N.json`. Feature examples for an earlier stage can become obsolete when a later issue explicitly changes its business requirements; the issue history remains available to explain prior releases.

Accounts use customer_id (nonempty string), renewal_on (valid Gregorian YYYY-MM-DD from 2020-01-01 through 2099-12-31), plan_cents (nonnegative integer US cents), completed_years (nonnegative integer), and autopay (boolean). A notice contains customer_id, send_on, credit_cents, and amount_due_cents. Account collections preserve order and duplicate customer IDs. Inputs to the exercises are well formed. No current clock, locale, or remote data is needed.

Implement product issues in their supplied order. Source code, docs, tests, and prior issue text remain available throughout the sequence.
