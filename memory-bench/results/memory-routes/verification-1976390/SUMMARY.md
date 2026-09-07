# Final-snapshot quality gates

Branch: csells/memory-routes-experiments
Tracked HEAD: 19763909b5a212922730f2273f77b8a09535bd7f
The source hashes recorded before and after every gate match; no concurrent source edits were observed.

| Gate | Result | Evidence |
| --- | --- | --- |
| Full Python ruff check . | Passed | ruff.log, ruff.json |
| Full Python black --check . | Passed, 553 files unchanged | black.log, black.json |
| Full Python mypy --strict | Passed, 264 source files | mypy.log, mypy.json |
| Explicit script mypy --strict --explicit-package-bases scripts/memory_routes_*.py | Passed, 5 source files | scripts-mypy.log, scripts-mypy.json |
| All six test_memory_routes_*.py files | 134 passed | pytest.log, pytest.xml, test-counts.json |
| Four upstream changed test files | 44 passed, 2 failed | pytest.log, pytest.xml, test-counts.json |
| Combined targeted suite | 178 passed, 2 failed, zero skips; 2.90 seconds | pytest.log, pytest.json |

## Two upstream test-environment failures

Both newly added spaced-interpreter-path variants fail before hook behavior is exercised:

- tests/test_bd_receipt_surface.py::test_hook_preserves_settings_and_executes_attributed_shim[True]
- tests/test_native_memory_hook.py::test_redirect_mode_blocks_the_reach_and_names_the_bd_verbs[True]

Their standalone symlink to sys.executable loses virtual-environment discovery. The child process uses the base uv interpreter, where pydantic is absent, and exits on ModuleNotFoundError. The nonspaced variants pass. This is separate from the shell quoting behavior being tested.

interpreter-diagnostic.json contains a minimal reproduction: direct .venv/bin/python retains its venv prefix and finds pydantic; a standalone spaced symlink reverts to the base prefix and cannot find pydantic; a whole-venv-directory alias preserves the environment and imports it. A portable test-only correction is to use a spaced executable /bin/sh shim that execs the shell-quoted original sys.executable with "$@", then point the existing monkeypatch at that shim. No source edits were made by the gate agent.

The 15 prior missing-corpus failures are fixed upstream: all 17 audit tests and all 9 bd_experiment tests now pass.

## TypeScript validation retained

No TypeScript source, tests, dependency manifests, or tool configuration changed since the previous successful complete npm run check (48 files, 908 tests; tsc, eslint, prettier also passed). typescript-unchanged.json records HEAD, branch, all changed tracked paths since 052b0ed, and the working-tree status. Previous complete passing log: /tmp/memory-routes-gates.veUGcH/npm-check-isolated-git.log. It used child-only GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 to avoid the host remote-URL rewrite; user configuration was not changed.

## Scope and preservation

The earlier complete 4,433-test run remains recorded at /tmp/memory-routes-gates.veUGcH/SUMMARY.md. As requested, this final run targeted new and upstream-changed tests rather than repeating unrelated tests whose code did not change. That broader run had existing platform failures described in its report.

This final run used fresh TMPDIR, pytest basetemp, and independent caches in this directory. Child environments omitted bead/model overrides and credentials; PATH excluded Homebrew and user tool directories. The replacement-executable upstream test explicitly restricts its child PATH to its temporary fake binaries. No model calls, real user-store mutations, cleanup, merges, or source edits were performed. Complete output, test fixtures, source hashes, and diagnostic evidence are retained.
