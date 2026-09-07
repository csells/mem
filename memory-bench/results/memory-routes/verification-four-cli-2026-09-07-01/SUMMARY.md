# Four-CLI qualification verification — 2026-09-07

Eight explicit integration sessions completed; no scored adoption sessions ran.
The [qualification report](../../../../specs/memory-four-hosts-qualification-2026-09-07.md)
separates working host interfaces from complete smoke adherence and future
ordinary-task adoption. No completed model session was rerun.

## Current checks

| Check                                                     | Result                                               | Evidence                                    |
| --------------------------------------------------------- | ---------------------------------------------------- | ------------------------------------------- |
| Focused host, receipt, isolation, and record-grader tests | 71 passed                                            | `pytest-03.log`, `checks-03.json`           |
| Full Python Ruff                                          | Passed                                               | `ruff-03.log`                               |
| Full Python Black                                         | 605 files unchanged                                  | `black-03.log`                              |
| Configured strict mypy gate                               | Passed, 282 source files                             | `mypy-gate-03.log`                          |
| Explicit strict mypy on six new implementation/test files | Passed                                               | `mypy-targeted-03.log`                      |
| Offline audit                                             | Completed with zero model calls; inputs unchanged    | `audit-02.json`, `audit.log`                |
| Evidence preservation recheck                             | All 992 audit input hashes unchanged                 | `artifact-preservation.json`                |
| Known credential scan                                     | No matches in 1,031 checked evidence files           | `artifact-preservation.json`                |
| Four CLI configuration hashes after sessions              | All match pre-update hashes                          | `preservation.json`                         |
| Task-owned Ollama server                                  | PID absent; existing server still responds           | `preservation.json`                         |
| OpenCode runtime context                                  | 32,768; 38 logged completion entries, none truncated | Original server log and `preservation.json` |

The initial Ruff check found two overlong audit strings, which were wrapped.
The first explicit mypy invocation assigned duplicate module names to scripts;
`--explicit-package-bases` resolved that invocation issue. Strict checking also
found tests referring to imported modules as implicit exports; imports/patch
targets were corrected. Initial failed logs remain beside the passing checks.
The record-grader correction accepts faithful JSON embedded in readable text
without certifying the surrounding prose. The new owned-server startup test
checks that an unready task process is stopped while its log is retained.

## Broader-suite limits

`npm run check` passed TypeScript compilation, lint, and formatting, then reported
**907 tests passed and one failed**. `tests/verify-git.test.ts` expected an SSH
remote URL, while the user's existing global Git rule rewrites GitHub SSH URLs
to HTTPS. The test module passed **8/8** with `GIT_CONFIG_GLOBAL` pointing to a
new empty scratch file and `GIT_CONFIG_NOSYSTEM=1`. No global Git configuration
or test source was changed. See `npm-check.log`, `npm-check.json`, and
`verify-git-isolated.{log,json}`. The original whole-suite invocation remains
failed; the isolated diagnostic is not a replacement whole-suite result.

The complete Python suite was not repurchased. Its preserved
[previous result](../verification-e2e-2026-09-06-02/SUMMARY.md) is 4,678 passed,
44 skipped, 27 failed, and 12 setup errors, with documented macOS/Linux runtime
and path assumptions. This work does not claim those failures are fixed.

## Update evidence

`cli-update-result.json` records the actual before/after update pass and final
versions: Claude 2.1.263, Codex 0.153.4, OpenCode 1.18.20, and zcode-app-cli
3.11.2-21/runtime 0.16.5. Only zcode changed. Individual `cli-update-*.log` files
retain manager responses. The before-configuration hashes are preserved here;
the original logs and rollback binaries remain in the external directory named
by the update result. No rollback binary was added to the repository.

All original experiment results and audit-01 remain unchanged. Audit-02 records
non-OpenCode server-context measurement as null, rather than implying those
allocations were measured. Its operation classification keeps help, failures,
agent actions, and administrative reads distinct. Complete smoke outcomes are
6/8; all four interfaces demonstrate capture/search/full lookup and transfer to
a fresh session. These are explicit tool exercises, not evidence of agents
choosing memory during ordinary tasks.

Publication retains bundled zcode plugin dependency caches locally rather than
committing duplicate native libraries and packages. Original audits retain their
hashes; `publication.json` inventories the omitted cache paths. Task inputs,
agent streams, tool receipts, retained records, native session/model evidence,
and grades are published. A remote checkout therefore cannot recheck the omitted
dependency bytes without the preserved local cache; it can rerun outcome grading.
