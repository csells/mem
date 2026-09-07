# Independent reference

`python3 cli.py` runs the final, six-stage product. `stage_1/cli.py` through
`stage_6/cli.py` run the contract at each release, sharing `engine.py` one
directory above. Keep this reference tree together when moving it.

This implementation does not import the starter or provider adapter. It
normalizes each posting to UTC, assigns a calendar or ledger date, and selects
matching date labels. Incident replay and release-1 compatibility both use the
complete UTC calendar month, including after the active ledger cutoff changes.
The reference's fixture is its own copy of the published starter snapshot.

The graders independently spell out expected memberships and daily amounts;
they do not invoke this implementation to obtain expected responses.
