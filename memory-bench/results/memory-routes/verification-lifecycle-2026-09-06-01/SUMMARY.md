# Lifecycle final verification

Branch: `csells/memory-routes-experiments`. Tracked HEAD: `19763909b5a212922730f2273f77b8a09535bd7f` plus current uncommitted lifecycle/report work. Every recorded source hash stayed unchanged during each final gate. The eight checked active driver/runtime files also match the `2026-09-06-lifecycle-02` frozen manifest (`frozen-active-source-check.json`).

| Gate | Result | Raw evidence |
| --- | --- | --- |
| Full Python `ruff check .` | Passed | `final-external-temp/ruff.log`, `.json` |
| Full Python `black --check .` | Passed; 564 files unchanged | `final-external-temp/black.log`, `.json` |
| Full Python `mypy --strict` crawl | Passed; 267 source files | `final-external-temp/mypy.log`, `.json` |
| Explicit strict mypy, package bases | Passed; 4 scripts | `final-external-temp/scripts-mypy.log`, `.json` |
| Targeted pytest | 287 passed; zero failures, errors or skips; 9.30 seconds | `final-external-temp/pytest.log`, `.xml`, `.json` |

The explicit script check covers `memory_lifecycle_experiment.py`, `memory_lifecycle_gate_smoke.py`, `memory_lifecycle_report.py`, and the modified `memory_routes_experiment.py`. The full mypy crawl retains the repository's documented exclusions; the explicit script check closes the relevant new-script gap.

The targeted suite covers every `tests/test_memory_routes_*.py` and `tests/test_memory_lifecycle_*.py`, plus `test_bd_receipt_surface.py`, `test_native_memory_hook.py`, and `test_bd_real_metrics.py`. Per-module counts are in `test-counts.json`; the precise command arguments and source hashes before/after each command are in each JSON receipt. The exporter author froze its two files before this final pass.

## Earlier attempts preserved

`active/` first passed all static checks and had 269 passing tests plus two verification-environment failures: this verification script placed pytest's temporary workspaces inside the source repository. The sandbox correctly refuses to allow any repository descendant, so both tests stopped at that guard. No application source was changed. `active-external-temp/` repeated the same non-report checks with fresh `/private/tmp` scaffolding and passed all 271 tests. The final pass added all 16 report tests and passed 287/287. Original logs and both verifier scripts are retained.

Earlier verification remains at `../verification-1976390/SUMMARY.md`, its `after-fixture-fix/SUMMARY.md`, and `../verification-052b0ed/SUMMARY.md`. The previous whole Python suite's unrelated macOS/Linux dependency failures were not rerun and are not claimed fixed. TypeScript is unchanged from its prior successful complete check (908 tests in 48 files, plus tsc/eslint/prettier); that result is retained, not rerun.

The primary lifecycle run is `2026-09-06-lifecycle-02`. The earlier `lifecycle-01` frozen plan is preserved; its tuple/list serialization refusal happened before any model calls. These verification checks do not spend model budget or alter those run artifacts.

## Isolation and scope

The final commands used a fresh external scratch directory, isolated caches/config/TMPDIR and pytest basetemp, and child PATH restricted to this project's virtual environment plus system executable directories. Child environments omitted model credentials and Beads/Dolt overrides, preserved HOME, and isolated Git configuration. The tests supply their own fake CLIs and temporary fixtures; the real macOS Seatbelt check passed. No source files were formatted or fixed, no user data/store was mutated, and no cleanup was performed. Raw logs, XML, fixtures, source hashes, and all prior verification remain available.

## Reporter label-only follow-up validation

The authorized reporter wording update replaces “No redundant curation” with “No writes/changes” and explains its applicability to reproduction. Its author reran 16 report tests plus owned Ruff, Black and explicit strict mypy; all passed. Raw logs, XML and source hashes were copied unchanged into `reporter-label-verification/`. This preserves the preceding 287-test result and adds validation of the two changed reporter/test files.

The refreshed `2026-09-06-lifecycle-final-analysis-02/analysis.json` matches all 1,283 input hashes and the updated, verified reporter hash `99bc3fe40689acbfc6832444544ee29cf4f833974278149af4aef619ca19f987`. All 5,457 numeric leaves and every non-provenance field are identical to the original analysis; only `generated_at` and `reporter_sha256` differ. See `final-analysis-02-provenance.json`. No tests or models were rerun for this independent comparison. The parent’s planned labeled addition to `specs/memory-routes-experiments-2026-09-06.md` is an expected second authorized baseline change; the earlier baseline snapshot remains preserved.

The post-follow-up baseline check is complete: 3,322 of 3,324 pre-existing files are unchanged. Exactly the two authorized files differ: `memory_routes_experiment.py` and the old narrative. The old narrative’s entire original 21,876 bytes remain an exact prefix; only 764 bytes were appended. See `final-baseline-after-followup.json`.
