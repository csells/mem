The first verification run passed all behavioral and type checks. Black found one formatting issue in `membench/runner/memory_host_shell.py`; no maintained source was changed by verification. The parent was notified, and a narrow follow-up will record the correction separately.

| Gate | Result |
| --- | --- |
| Full Python Ruff | Passed |
| Full Python Black check | Failed: shell helper would be reformatted; 579 other files unchanged |
| Strict mypy crawl | Passed: 273 source files |
| Explicit strict mypy for host/lifecycle/routes scripts | Passed: 11 scripts |
| Targeted test collection | Passed: 407 tests |
| Targeted tests | Passed: 407; zero skips, failures, or errors |

Raw logs, collection output, JUnit XML, command lines, and per-gate source hashes are in `gates-01/`. Source hashes stayed constant within each check and across the full run. Test fixtures and caches were created in fresh external scratch; the subprocess PATH excluded Homebrew and personal executable directories.

The final adapters also reparsed the preserved successful Claude and Codex common smokes offline. Both retained their actual model/session identities and identical normalized tool calls, and both passed the tightened admission rule: successful terminal and process, correct artifact, one accepted memory write, two observed reads, direct lookup and search, and no unknown receipt evidence. Their source evidence was unchanged. See `offline-smokes-final-parser.json` and the reproducible `reparse-smokes.py`.

This verification made no model calls, ran no new Beads experiments, and changed no maintained source. Earlier lifecycle verification, all model/smoke artifacts, and previously documented unrelated Python platform failures remain preserved. Unchanged TypeScript retains its prior verification; the unrelated full Python runtime suite was not rerun.

The final formatting supplement passed full Black (580 files unchanged), affected-file Ruff and strict mypy, and the macOS login-shell test (1 passed). Only the shell helper had been formatted before the frozen manifest; no sources changed during verification. Logs and hashes are in `format-supplement-01/`. The original 407 behavioral tests remain green.

Final frozen cohort execution is closed: 44 completed sessions, five finished lifecycles and one attribution halt, with four planned later stages unrun. The independent final analysis consumed 902 inputs, all rehashed without mismatch; all 1,283 prior lifecycle inputs still match as well. Frozen sources/binaries, branch, and HEAD remain unchanged. See `final-evidence-check-01.json`, `preservation-01.json`, and `PRESERVATION-AND-PREFLIGHT-01.md`. Final narrative and trace audits distinguish correct artifacts, two historical rewrites, attribution unknowns, native scaffolding, blocked hosts, and unreported costs. No completed or interrupted model session was repurchased.
