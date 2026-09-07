# Public interface checks during memory reuse

Status: completed and independently rechecked; 32/32 artifacts passed.

Baseline and checker each passed 16/16, so this screen found no correctness
advantage from adding the test. All eight capture/revision occasions preserved
the exact policy and rationale; seven also preserved the exact SOURCE string.
One note abbreviated that field while keeping the version elsewhere in prose.
All 24 reproduction tasks made zero memory writes, and all four supplied controls
made zero reads. See the [full findings and recommendations](../../specs/memory-contract-experiments-2026-09-06.md).

The [installed-guidance experiment](MEMORY-E2E.md) found faithful retained
agreements on all eight capture/revision occasions and correct runtime behavior
in all 32 tasks, but 13 components
exported an incomplete policy structure. This follow-up tests whether a public
project test helps agents apply the agreement correctly.

Both conditions receive the same installed AGENTS rules, host imports, Beads
skill, prime orientation, and memory procedure. Both use the same eight-stage
lifecycle: capture, direct reuse, search reuse, permanent revision, revised
direct/search reuse, supplied reproduction, and historical reproduction.
Actual agent-authored follow-up tasks and retained records carry forward.

The sole treatment is `tests/test_component_contract.py`. It runs through the
existing `python3 -m unittest discover -s tests` command and checks the public
component interface: complete POLICY nesting and field types, string SOURCE and
RATIONALE exports, and a callable create_cache. It contains no approved setting
values, source labels, or historical version answers. It checks every matching
component present in the project.

The baseline receives no additional test. No memory rule, completion guard,
prompt wording, or hidden grader changes. Checker changes or removal by agents
remain in their actual workspace and are reported; the harness does not restore
the test. An independent copy of the canonical checker grades saved work without
providing feedback to the agent. Correct structure and correct approved facts
remain separate outcomes.

Offline verification accepted the 19 previously correct target interfaces and
rejected all 13 flattened targets using complete copies of their saved dependency
contexts. Running whole-workspace discovery passed 16/32 snapshots: three correct
targets also had earlier incorrect siblings. This distinction prevents a prior
component's failure from being attributed to the current target.

The new bounded screen schedules 32 fresh sessions: Claude Code 2.1.263 with
`claude-sonnet-4-6` and Codex CLI 0.153.4 with `gpt-6-astra`, each running one
eight-stage lifecycle per condition. Previously verified executable hashes and
real integration-smoke evidence are reused; both CLIs report existing login
state, while inference availability is established only by actual sessions.
The previous three host blockers remain coverage limits and receive no new
trials. Each lifecycle starts with fresh isolated stores and normal native-memory
defaults. Existing user history and global configuration remain untouched.

The [frozen manifest](../../memory-bench/results/memory-routes/2026-09-06-contract-01/manifest.json)
pins the conditions, 300 source/test files, four executables, and the offline
qualification. All 121 relevant tests and the Python static gates passed before
launch. No new model smoke was purchased: every prior smoke input and executable
hash matched the admitted profiles.

All 32 saved artifacts were independently regraded, all 28 memory/source transfers
matched, and all 7,812 previously preserved files remained unchanged. No checker
or earlier project-file mutation occurred. All 33 ordinary unittest invocations
passed; no contract failure followed by repair was observed. The checker was read
before coding in 14/16 treatment sessions, so this package can supply both
executable guidance and test feedback. Their separate effects were not isolated.

Known CLI usage totals $3.6634107 plus unreported dollar costs for 16 Codex
sessions. All planned sessions completed; no interrupted or completed session was
repurchased. The three other host blockers remain explicit coverage limits.

This is a comparison of a public-test package on four correlated lifecycles,
not a production reliability estimate. It continues to use legacy keyed memory
and does not validate the proposed Memory bead type. The
[completed plan](../../specs/plans/archive/0004-memory-public-contract-check.md)
records the frozen conditions and remaining production questions.
