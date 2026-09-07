# Ordinary-task experiment: pre-launch verification

No scored model session was used for this verification. Real CLI qualification
remains the preserved eight-session integration run. This checks the newly
admitted tasks, standing package, execution driver, and independent artifact checks.

- **561/561 hidden reference cases** pass through the exact evaluator Python
  runtime and read-only sandbox (`reference-summary.json`, twelve detailed files).
- Independent cross-review also passed 379+6 HarborPass hidden/public examples
  and 182+29 Northbank hidden/public examples. Author validation rejects four
  HarborPass and ten Northbank deliberate defective implementations.
- **82 focused tests pass**, covering hosts, receipts, isolation, exact record
  comparison, nonempty task delivery, retained completed sessions, review coverage,
  exclusive result publication, and frozen-input changes during a final session.
- Ruff and Black pass; configured strict mypy passes on 283 source files; explicit
  strict mypy passes on the four new execution/package/test modules.
- Both rendered Beads skills pass the skill-creator validator. Existing supported
  project entry points and native discovery paths are unchanged.

Initial check logs remain preserved. They found an exception-class naming style
issue and a test importing an implicit module export; both were corrected. The
post-final-session freeze regression first reproduced the independent reviewer's
failure, then passed after checks were added after each session and at phase end.

The external JSON grader checks full structure/types and rejects duplicate fields.
A real isolation test confirms candidate code cannot read hidden answer files or
write the workspace during grading. Earlier application/source history stays
available during agent work. No missing memory is seeded or repaired.

The independently authored corpus is excluded narrowly from library formatter
and typechecker crawls: separate apps/reference/defect variants share module names
and preserve reviewed bytes. Those fixtures have executable reference/mutation
validation instead. The library, runner, and their tests remain checked.

Whole-suite platform limitations remain in the previous
[four-CLI verification](../verification-four-cli-2026-09-07-01/SUMMARY.md).
No claim is made that the existing Python/macOS failures or Git URL-rewrite test
environment issue were repaired. Their full suites were not repeated for this push.

See [admission](../../../../specs/memory-unprompted-admission-2026-09-07.md) for
independent review, control corrections, OpenCode's retained strict-smoke failures,
resource limits, native-memory boundaries, and grading definitions.
