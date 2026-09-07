# Whole Python suite after E2E implementation

The full suite completed in 605.47 seconds: **4,678 passed, 44 skipped, 27 failed,
12 setup errors**. All 60 new `test_memory_e2e_*` tests passed. Raw output is in
`pytest.log`; `launch.json`, `result.json`, and `audit.json` preserve the invocation,
exit status, and source checks. Temporary test files and pytest cache use the
fresh external directory recorded in `launch.json`; no cleanup was performed.

The failing test modules are byte-identical to Stephanie's `1976390` base. Their
failure classifications match the earlier
[whole-suite verification](../verification-052b0ed/SUMMARY.md):

- Ten component-session failures: retained `component-result.json` reports
  `source destination escapes workspace`; the old runtime compares resolved
  macOS `/private/tmp` destinations with a lexical `/tmp` workspace.
- Twelve real-runtime failures and twelve component-grade setup errors: Linux
  Bubblewrap is unavailable on this macOS host. The runtime refuses unsandboxed
  execution, and the grading fixture requires `bwrap`.
- Five ordering-CLI failures: tests name `/bin/true`, which is absent here;
  `/usr/bin/true` is the available path.

These failures are not claimed fixed. No frozen experiment source was changed.
All 294 source/package hashes still match the cohort manifest after the suite.
The earlier full Ruff, Black and strict-mypy checks and isolated real CLI smokes
remain recorded in [verification-e2e-2026-09-06-01](../verification-e2e-2026-09-06-01/).
TypeScript remains unchanged from its previously recorded complete passing check;
that result was retained rather than rerun.
