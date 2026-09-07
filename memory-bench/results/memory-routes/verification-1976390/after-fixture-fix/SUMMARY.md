# Final quality gates after fixture correction

Branch: csells/memory-routes-experiments
Tracked HEAD: 19763909b5a212922730f2273f77b8a09535bd7f plus the new experiment files and two test-fixture corrections.
All recorded source hashes remained unchanged during each final gate.

| Gate | Result | Evidence |
| --- | --- | --- |
| Full Python ruff check . | Passed | ruff.log, ruff.json |
| Full Python black --check . | Passed, 553 files unchanged | black.log, black.json |
| Full Python mypy --strict | Passed, 264 source files | mypy.log, mypy.json |
| Explicit script mypy --strict --explicit-package-bases scripts/memory_routes_*.py | Passed, 5 source files | scripts-mypy.log, scripts-mypy.json |
| All six test_memory_routes_*.py files | 134 passed | pytest.log, pytest.xml, test-counts.json |
| Four upstream changed test files | 46 passed | pytest.log, pytest.xml, test-counts.json |
| Combined targeted suite | 180 passed, zero failures/skips; 3.28 seconds | pytest.log, pytest.json |
| git diff --check | Passed | No whitespace errors |

## Minimal test-fixture correction

The initial final-snapshot run found two upstream spaced-interpreter cases that failed before testing hook behavior: standalone symlinks to sys.executable lost virtual-environment discovery and could not import pydantic. We reproduced the prefix and import discrepancy; see ../interpreter-diagnostic.json and the original failing ../pytest.log and ../pytest.xml.

The only edits made by this gate agent replace those standalone symlinks with executable /bin/sh launchers that exec the shell-quoted original sys.executable with "$@". This preserves the environment while retaining paths with spaces/apostrophes and the command-quoting assertion. The two edited files are tests/test_bd_receipt_surface.py and tests/test_native_memory_hook.py; fixture-fix.patch records the exact change. Production code and frozen model-run evidence were not edited.

The 15 missing-corpus failures found in the earlier broad run are now resolved by upstream: all 17 audit tests and all 9 bd_experiment tests pass.

## TypeScript result still applies

TypeScript source, tests, dependency manifests, and configuration have not changed since the complete successful npm run check: tsc, eslint, prettier, and all 908 tests in 48 files passed. ../typescript-unchanged.json records the tracked diff and working-tree status before the Python-only fixture correction. Original passing log: /tmp/memory-routes-gates.veUGcH/npm-check-isolated-git.log. That command used child-only GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 to avoid host Git remote-URL rewriting, without modifying user configuration.

## Scope and preservation

The previous full Python run and its existing platform failures remain documented in /tmp/memory-routes-gates.veUGcH/SUMMARY.md. As requested, this final run covers all new tests and the four upstream-changed test files rather than repeating unrelated unchanged tests. It does not claim that the unrelated Linux-only/platform failures in the broad suite are resolved.

All logs, fixtures, source hashes, and earlier failure evidence remain preserved. Fresh TMPDIR, pytest basetemp, and caches were used for the corrected run. Child environments omitted bead/model overrides and credentials; PATH excluded user and Homebrew tool directories. The replacement-executable test itself restricts its child PATH to temporary fake binaries. No model calls, user-store mutations, cleanup, or merges were performed.
