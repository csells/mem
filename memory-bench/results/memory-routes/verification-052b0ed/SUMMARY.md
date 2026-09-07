# Quality gates, initial snapshot

Repository: /Users/csells/Code/Forks/sjarmak/mem
Branch: csells/memory-routes-experiments
Tracked base: 052b0ed7d4e595a366840e96b0b06fd04bd161ec (before planned upstream fast-forward).

| Gate | Result | Evidence |
| --- | --- | --- |
| Python ruff check . | Passed | ruff.log and ruff.json |
| Python black --check . | Passed, 546 files | black.log and black.json |
| Python mypy --strict | Passed, 264 source files | mypy.log and mypy.json |
| Python full pytest | 4,341 passed, 38 skipped, 42 failed, 12 errors; 776.63 seconds | pytest.log, pytest.xml, pytest.json |
| npm ci | Passed; fresh node_modules | npm-ci.log |
| npm run check, user Git config | tsc/eslint/prettier passed; 907/908 tests passed | npm-check.log |
| npm run check, child-only isolated Git config | Passed, all 48 test files and 908 tests | npm-check-isolated-git.log |

## Python failure classification

All failing test modules and triggering implementation are preexisting tracked code; no new memory_routes test failed.

- 15 failures: tests.test_audit_bd_actions (7), tests.test_bd_experiment (8). Default fixtures/worlds-tool is absent. Upstream 1976390 changes these modules to generate a private fixture corpus, directly addressing this group; post-merge execution still required.
- 12 failures: tests.test_bd_real_runtime. Bubblewrap is absent on macOS, and runner refuses unsandboxed execution before the behavior under test.
- 12 setup errors: tests.test_bd_component_grade. Fixture asserts bwrap and bd are installed; bwrap is absent.
- 10 failures: tests.test_bd_component_session. Retained component-result.json files all report source destination escapes workspace. bd_component_session.py creates lexical /tmp workspaces and compares destination.resolve() against unresolved cwd. macOS resolves /tmp to /private/tmp, so valid contained destinations fail the check.
- 5 failures: tests.test_beads_ordering_density_linkage (2), tests.test_beads_ordering_followup (3). Tests use /bin/true, which is absent on this macOS host; available executable is /usr/bin/true.

New modules collected at suite start: corpus 13, grader 36, runtime 19: all 68 passed. The parent subsequently modified runtime/experiment code and added tests/report code while the suite ran. Hashes before and after are preserved in pytest.json. This initial run does not certify those later edits; targeted new tests and final static gates remain necessary.

## TypeScript host dependency

Original sole failure: tests/verify-git.test.ts readRemotes expected git@github.com:gastownhall/gascity.git but received https://github.com/gastownhall/gascity.git because host Git configuration rewrites that URL. Running the complete same gate with GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 passed. No user Git configuration was modified.

## Isolation and preservation

Python gates scrubbed BEADS_*, BD_*, DOLT_* and model credential/environment overrides in child processes. pytest used a fresh basetemp, with caches and TMPDIR in this scratch directory. Tests provisioned isolated temporary bead stores; no model calls were launched by this gate run. Logs, XML, temporary fixtures, and metadata are retained. No tracked source edits, merges, cleanup, or user-store resets were performed by the gate agent.

## Upstream changes inspected read-only

Upstream 1976390 modifies AGENTS/docs plus bd_receipt_surface.py, native_memory_hook.py, and four test modules. Besides the missing-fixture fix above, wrappers and hook commands now quote interpreter paths correctly (including spaces/apostrophes). Existing wrapper/hook tests already passed on this host, so the command quoting fix covers latent portability cases rather than an observed failure here. Remaining platform failures above are not addressed in that upstream diff.
