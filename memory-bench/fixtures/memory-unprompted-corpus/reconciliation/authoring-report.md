# Revised authoring report

Artifact: `/tmp/reconciliation-exercise-revised-_f8qrcqt`.
Original artifact preserved untouched: `/tmp/reconciliation-exercise.lXtCPO`.

## Revision scope and provenance

The original six-task exercise was authored from a business brief without
reading the research plan or intervention. The later independent review disclosed
the research goal and requested two bounded corrections. This new copy applies
those corrections; it is not a claim that the revised control was authored blind.

Stage 3's `incident_replay` now reproduces the corrected release-1 statement
already established in stage 1: the complete UTC calendar month, including the
last date and excluding the next month's first instant. The issue restates that
entire existing contract, including ordering and arithmetic, and freezes it for
the support comparison. It introduces no additional pricing or date policy.
Later stages check that it remains unchanged after active accounting moves to
05:00 UTC. Stage 6's release-1 compatibility uses the same original calendar
behavior, while the active operations retain the new ledger behavior.

The CSV requirement now explicitly specifies minimal quoting for comma, double
quote, CR, and LF. The independent grader quotes those characters directly.
The reference uses a CRLF-aware standard-library writer for each record and
converts only that record's trailing delimiter to LF. Embedded CR/LF survives.
All eight boundary fixtures contain a bare-CR refund ID, and cumulative public
examples include a bare-CR field from stage 2 onward.

Task prompts and starter documentation contain no memory commands, memory keys,
capture/lookup instructions, or directives to retain information or prepare a
handoff. They specify business behavior only. Evaluator lifecycle instructions
live outside the candidate surfaces. The actual working tree, prior issues,
tests, and documents are intended to remain available across stages; no task
requires deleting them.

## Runnable interface

Entrypoint: **`python3 cli.py`**, one JSON stdin request and one JSON stdout
response. Runtime: Python 3.10+ standard library, no network or dependencies.

- `tasks.json`: six ordered issue prompts and public-case paths.
- `starter/`: runnable initial code, provider docs/snapshot, two baseline tests,
  and `test_public.py --cases <file>`.
- `public_tests/stage_N.json`: cumulative visible examples, with `name`,
  `input`, and `expected` fields. Deliver the applicable file when its stage starts.
- `graders/stage-N.json`: hidden cumulative arrays of
  `{name, input, expected, argv: []}`.
- `reference/`: separate date-label implementation; `stage_N/cli.py` runs each
  release and top-level `cli.py` runs the final release. Keep the reference tree
  together because staged wrappers import the shared engine.
- `manifest.json`: runner paths and validation report location.

Do not copy graders, references, future prompts, evaluator instructions, or
authoring notes into the candidate workspace. Preserve earlier delivered files
and issue history. Parent runner integration may normalize the authoring JSON
to its own `body`/stage schema; this artifact's task content is under `prompt`.

## Verified results

Completed evidence: `validation-run-7v9jpn9e/report.json`.

- Initial public tests: **2/2 pass**.
- Unfixed starter against stage 1: **1/10 pass**, correctly exposing the omission.
- Reference stages: **182/182 hidden checks pass**.
- Cumulative public examples: **29/29 pass**.
- Deliberately incorrect variants: **10/10 rejected**.

Hidden checks per stage: 10, 20, 30, 30, 41, 51. Public examples per stage:
1, 3, 4, 6, 7, 8. Coverage includes UTC/ledger boundaries, leap and ordinary
month lengths, year rollover, numeric offsets, ordering, empty input, arithmetic,
CSV comma/quote/CR/LF, frozen original behavior, and current-policy coexistence.

Defect variants cover stale UTC active reports, replay following the current
ledger policy, compatibility following the current policy, both historical
endpoints reintroducing the original last-date omission, ignored timestamp
offsets, ID-only ordering, calendar-day daily totals, included upper boundaries,
and unquoted bare CR. The CR-specific variant fails eight cases.

The first revised validation attempt used an LF-only standard-library writer
as the proposed CR defect. Installed Python 3.14.7 already quotes CR under that
setting, so that proposed mutation was not defective on this runtime. The
validator was corrected to omit CR explicitly in its deliberately bad serializer.
The reference and grader were unchanged. That initial scratch run remains at
`validation-run-dgd_xbbb/`; the later complete report is the result cited above.

`refresh_cases.py` regenerates case files from the independent hidden grader and
separately specified public examples. `validate_authoring.py` creates a fresh
scratch subdirectory each time and does not invoke coding agents or modify Git.

No evaluated coding-agent sessions or model runs were performed. All revision
writes stayed inside this newly created scratch directory. Runtime/coverage
checks do not establish memory adoption or completion-time claims.
