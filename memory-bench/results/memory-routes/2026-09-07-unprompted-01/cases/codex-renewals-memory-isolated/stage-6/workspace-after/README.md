# HarborPass renewal CLI

HarborPass sells annual memberships. This project is a small local JSON application. It requires Python 3.9 or later and no packages or network access.

Run `python3 main.py` with one JSON request on standard input. The program writes one JSON response to standard output. `{"command":"ping"}` returns `{"status":"ok","product":"HarborPass"}`; an unrecognized command returns `{"error":"unknown_command"}`. JSON key order and surrounding JSON whitespace do not matter.

`{"command":"notice","account":ACCOUNT}` returns one renewal notice. Under the current retention policy, notices are sent 14 calendar days before renewal. Members with at least 3 completed years receive a loyalty credit of 15% of the plan price, rounded down to whole cents and capped at 3600 cents, regardless of autopay. Other members receive zero credit. The amount due is the plan price minus the credit. This policy applies to all notice and export requests regardless of renewal date.

`{"command":"export","accounts":[ACCOUNT,...]}` returns `{"csv":STRING,"count":N}` with one current notice per account, preserving input order and duplicate IDs. The CSV columns are `customer_id,send_on,credit_cents,amount_due_cents`. The header and every row end with LF, including the final row. Fields containing a comma, double quote, CR, or LF are quoted, with internal double quotes doubled; other fields are unquoted. An empty collection returns just the header and its LF with a count of zero.

Run the starter tests with `python3 -m unittest discover -s tests -v`. Each product issue is accompanied by a public JSON examples file. Run those examples with `python3 test_public.py --cases /path/to/stage_N.json`. Feature examples for an earlier stage can become obsolete when a later issue explicitly changes its business requirements; the issue history remains available to explain prior releases.

Accounts use customer_id (nonempty string), renewal_on (valid Gregorian YYYY-MM-DD from 2020-01-01 through 2099-12-31), plan_cents (nonnegative integer US cents), completed_years (nonnegative integer), and autopay (boolean). A notice contains customer_id, send_on, credit_cents, and amount_due_cents. Account collections preserve order and duplicate customer IDs. Inputs to the exercises are well formed. No current clock, locale, or remote data is needed.

`{"command":"support_replay","case_id":"IOS-1842","account":ACCOUNT}` returns `{"case_id":"IOS-1842","notice":NOTICE}` using the approved release 1.0 rules. This case remains fixed at 21 days before renewal, with a 10% credit rounded down and capped at 2400 cents only for autopay members with at least 2 completed years, even when current notice and export policies change. IOS-1842 is the only supported case.

`{"command":"batch","on":"YYYY-MM-DD","accounts":[ACCOUNT,...]}` returns `{"on":"YYYY-MM-DD","notices":[NOTICE,...],"total_due_cents":N}`. It includes complete current notices whose send_on equals on, preserving input order and duplicate IDs. The response copies on unchanged and totals the included amounts due in integer cents. Empty results return an empty notices list and a zero total.

`{"command":"compat_notice","release":"1.0","account":ACCOUNT}` returns `{"release":"1.0","notice":NOTICE}` for archived release 1.0 receipts. As approved in the original notice issue (`trial-qig`), send_on is 21 calendar days before renewal; only autopay members with at least 2 completed years receive 10% of plan_cents, rounded down to whole cents and capped at 2400 cents. Other members receive zero credit, and amount_due_cents is plan_cents minus credit_cents. Release `"1.0"` is the only supported compatibility target. Current notice, export, and batch commands retain the current retention policy; support_replay retains its separate case response.

Implement product issues in their supplied order. Source code, docs, tests, and prior issue text remain available throughout the sequence.
