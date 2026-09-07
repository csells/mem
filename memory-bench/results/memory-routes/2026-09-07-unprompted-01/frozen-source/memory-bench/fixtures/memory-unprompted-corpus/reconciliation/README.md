# Northbank reconciliation exercise

Six accumulating business issues for an offline Python CLI. Begin with a copy
of `starter/`, deliver prompts from `tasks.json` in stage order, and retain the
working tree and all previous task history throughout. The candidate command
is `python3 cli.py`, with one JSON stdin request and one JSON stdout response.

`manifest.json` describes runner paths. Hidden black-box cases are in
`graders/stage-1.json` through `stage-6.json`. Each is a JSON array of objects
with `name`, `input`, `expected`, and `argv` fields. `input` is the complete
stdin JSON object; `expected` is the complete parsed stdout object. Compare
JSON structure and scalar types exactly; object key order is immaterial.

Keep graders, reference code, future task prompts, and authoring notes outside
the candidate's context. Earlier task prompts, code, fixtures, and documents
remain available after delivery. No step requires deleting earlier information.

Each issue has a public examples file in `public_tests/stage_N.json`. Deliver
that file at its stage; the starter's `test_public.py` executes it. Older public
files remain available, and explicit later policy changes may supersede their
active-report expected values.

For a local check, run:

```sh
python3 graders/grade.py --stage 1 --candidate /path/to/candidate
python3 validate_authoring.py
```

The validation script creates a fresh `validation-run-*` directory on each
invocation, tests the public starter behavior, checks that the reported bug is
detectable, checks every staged reference and public example, and rejects ten deliberately
incorrect implementations. It does not launch a coding agent or modify Git.
