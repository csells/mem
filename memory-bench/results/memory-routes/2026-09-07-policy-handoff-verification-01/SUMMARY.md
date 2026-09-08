# Policy-handoff preparation verification

The experiment-specific checks and independent admission passed before scored
launch. The complete repository Python suite is not green on this Mac.

| Check | Observed result |
| --- | --- |
| Adapter/model qualification | 20/20 started and assessed once; all actual requested model/host interfaces worked; 16/20 full diagnostic passes; Haiku and Qwen behavioral failures retained |
| Qualification cost | $1.88067045 reported; Codex and GLM dollar costs unavailable; 403.81 seconds; no timeouts/retries |
| Independent corpus checks | 1922/1922 hidden cases and 142/142 cumulative public examples agree with independent oracles and reference implementations |
| Deliberate corpus defects | Finance 22/22 and Courier 12/12 rejected |
| Targeted model checks | 63 passed after primary-receipt hardening; all 20 saved qualification streams replayed without changing their model/host conclusions |
| Targeted runtime checks | 56 passed; independent reviewer also reran 52 runner/package/model checks |
| Installed skill validation | Both packages valid; real project aliases and references resolve |
| Literal task-cue supplement | Zero memory/Beads/agent-file references in 24 authored task bodies; independent full-context semantic review is the stronger check |
| Ruff | Pass |
| Black | Pass, 617 files |
| Configured strict mypy crawl | Pass, 285 files; excluded experiment scripts also checked explicitly in targeted validation |
| TypeScript default environment | Typecheck/lint/format pass; 907/908 tests pass; existing global Git URL rewrite changes one expected remote URL |
| TypeScript isolated Git configuration | Complete `npm run check` passes, including 908/908 tests; per-process configuration only, user settings preserved |
| Full Python suite | 4814 passed, 44 skipped, 27 failed, 12 errors; 641.32 seconds |

The full Python failures are in existing Beads component/Linux runtime and ordering
test areas. Recorded causes include absent Bubblewrap, Linux `/bin/true`
expectations, and runtime path-containment assumptions on macOS. The scored
experiment uses the separately tested macOS sandbox runner. No safeguards were
disabled to make that suite pass, and this report does not claim a green full suite.
See [the complete log](python-suite.log).

The first skill-validation setup used system Python and failed before installation
because it lacked `toml`; the project virtual environment then passed both checks.
An initial explicit `mypy scripts` crawl reported no files because the repository
intentionally excludes that directory; the configured strict crawl and explicit
file-level checks passed. One subagent independently launched a duplicate broad
pytest run before receiving the root's coordination message; it stopped only its
own run after 17.5 seconds, preserving its output. It made no model calls and does
not replace the completed root suite.

Final independent admission covers 149 exact paths, including transitive guidance,
task worlds, oracles, model profiles, runner, and the frozen design. Its artifacts
are under `../2026-09-07-policy-handoff-qualification-01/verification/independent-final-admission/`.
The final scored manifest is the authority for frozen bytes and scheduled slots.
Qualification is explicit integration testing, not unprompted adoption evidence.

Live inventory at verification: Claude Code 2.1.263, Codex 0.153.4, OpenCode
1.18.20, zcode-app-cli 3.11.2-21/runtime 0.16.5, and legacy bd 1.2.1. Actual
executable paths and observed version output are preserved in [versions.json](versions.json).
