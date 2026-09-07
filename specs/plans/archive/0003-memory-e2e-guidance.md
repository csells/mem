# Memory workflow through installed project guidance

**Status: completed.** The 32-session screen and separate offline action audit
are finished. Production follow-ups remain explicit in the final report.

Authorized 2026-09-06 after publishing the public description and prior evidence
at `8191a3362e72b0bcefa486c91dacfa0eb37a972b` on
`origin/csells/memory-routes-experiments`.

Implement the [public experiment](../../../docs/adoption-harness/MEMORY-E2E.md) and
[design](../../memory-e2e-experiment-proposal-2026-09-06.md) as new modules and fixtures.
Preserve all previous runtime sources, conditions, model sessions, and verification.

1. Install one canonical project Beads skill, shared AGENTS and host imports;
   compare installed delivery with explicit delivery of the same policy.
2. Enable project rules and skills through new isolated host adapters. Keep real
   CLI output unchanged and distinguish subprocess execution from visible content.
3. Use eight runnable feature tasks, actual authored successor tasks, and carried
   source/task/memory state. Independently grade behavior and retained information.
4. Verify package/adapters/grader mechanically, then run at most one bounded
   integration smoke per previously usable host. Freeze admitted profiles, source
   hashes, limits and the 32-slot manifest before scored sessions. Unavailable
   hosts and dependent tasks remain explicit blocked/unrun evidence.
5. Run the admitted screen once; preserve failures and interruptions. Report
   delivery, curation, retrieval, application, history, costs and reliability limits.

Native memory retains each host's default in fresh isolated state. No native
history or credentials enter published evidence. Source and task history remain
available, so correct alternative retrieval routes are reported honestly. This
screen uses legacy keyed memory; production Memory identity/reference/revision
acceptance remains outstanding.

## Implementation and verification

The new package, host adapters, receipt instrumentation, runnable corpus, grader,
and [experiment driver](../../../memory-bench/scripts/memory_e2e_experiment.py) are
implemented. Previous runtime sources and recorded experiments remain unchanged.
The driver provides four actions: `--smoke`, `--freeze`, `--fire`, and `--report`;
only smoke and fire launch models. It is a local research harness using pinned
executables, existing authentication, Python dependencies, and macOS sandboxing,
not a portable turnkey CLI.

Verification before launch passed: 60 focused tests, full Python Ruff/Black checks
(592 files), strict mypy across 278 source files, and explicit checks of the six
new modules/scripts. Package checks cover imports, the shared skill alias,
identical candidate-procedure bytes across arms, absent control-arm registration,
state preservation, and answer exclusion. Real prime checks found no stored
distractor bodies in `bd prime --no-memories` output. The PRIME template is present
in both workspace and isolated store; no capture or completion gate is installed.

Both bounded integration smokes were admitted:

| Host                         | Evidence                                                                                               | Observed instruction access                                | Reported usage estimate |
| ---------------------------- | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------- | ----------------------- |
| Claude / `claude-sonnet-4-6` | [Smoke result](../../../memory-bench/results/memory-routes/2026-09-06-e2e-smoke-claude-01/result.json) | One native `Skill` call and one memory-reference read      | $0.1920176              |
| Codex / `gpt-6-astra`        | [Smoke result](../../../memory-bench/results/memory-routes/2026-09-06-e2e-smoke-codex-01/result.json)  | One explicit skill-file read and one memory-reference read | Unknown                 |

Each smoke produced its exact artifact, retained and recalled the agreement, and
closed the task. These checks do not establish full-lifecycle success or directly
certify automatic rule loading. CLI usage estimates are not additional billed
dollars.

The [32-slot cohort manifest](../../../memory-bench/results/memory-routes/2026-09-06-e2e-01/manifest.json)
is frozen and all 32 sessions completed. It ties 294 source/package hashes and
four executable hashes to both admitted smokes, uses 420-second session limits,
and records a $1.50 Claude CLI cap; Codex has no dollar cap or reported dollar cost.
Ordering is Claude explicit then installed, Codex installed then explicit. Each
lifecycle starts in a fresh isolated workspace/native state and carries actual
state forward under the host's normal native-memory default. The other three
hosts retain their previous blockers without new model rechecks. A started
session is not rerun; missing dependent tasks remain missing.

[parent-launch.json](../../../memory-bench/results/memory-routes/2026-09-06-e2e-01/parent-launch.json)
records the resolved Python 3.13 invocation and environment dependency path. The
resolved executable avoids a denied `pyvenv.cfg` access in the read-only artifact
grader; frozen source and executable bytes are unchanged.

## Completed outcomes

All 32 components passed the tested runtime behavior and exact SOURCE/RATIONALE
checks. Nineteen passed the complete artifact contract: Claude explicit 0/8,
Claude installed 3/8, Codex explicit 8/8, and Codex installed 8/8. The other 13
flattened the required exported POLICY despite accurate retained agreements.
All sessions completed successfully and closed their assigned tasks; those
statuses do not override failed artifact checks.

All four initial capture occasions and four permanent revisions retained exact
approved content. The separately named historical body remained unchanged in
every lifecycle. Claude explicit performed one identical reproduction resave;
there were no other reproduction writes. Fully supplied controls made zero writes
in 4/4 cases and zero reads in 3/4.

The separate [action audit](../../../memory-bench/results/memory-routes/2026-09-06-e2e-01/action-audit-01.json)
preserves all frozen assessments and corrects CLI-action labels posthoc. Four
`remember --help` calls inflated the original 17-write count; actual writes total 13. The original 27 search/list calls comprise 26 queried searches and one
unfiltered listing. Together with 55 full recalls, these account for 82 successful
memory reads. Seventeen help calls, 32 prime calls, and two failed Beads invocations
are reported separately. Codex's smoke likewise has one real write plus help,
not two writes. Input hashes, invocation IDs, and original counters remain in
the audit; 204 session-input hashes and the audit source hash were verified.

The [new offline helper](../../../memory-bench/scripts/memory_e2e_audit.py) passed 24
focused tests plus Ruff, Black, and strict mypy. It performs no model calls and
changes no artifact or capture verdict. The broader suite reported 4,678 passed,
44 skipped, 27 pre-existing failures, and 12 setup errors. The 60 prelaunch checks
and 24 posthoc tests pass; this does not claim a green repository-wide test suite.

The [full report](../../memory-e2e-experiments-2026-09-06.md) and
[trace audit](../../memory-e2e-trace-audit-2026-09-06.md) retain the separate delivery,
capture, retrieval, application, history, and overhead findings. The sample remains
two host/model combinations and four correlated lifecycles on legacy keyed
memory. Three other hosts retain recorded blockers. Installed delivery is not
proven superior, and the actual production Memory type remains unvalidated.
