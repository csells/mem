# Two-task real-source bd memory pilot corpus

These are constructed parent-context exposure → later task-replay pairs, not recovered historical handoffs. Memory use is an opportunity, not a necessity: the parent code is still available during the goal. The goal requirements are explicitly post-hoc curated descriptions of real changes. Establish packets derive exclusively from exact parent-source excerpts, never gold diffs or added tests.

`manifest.json` freezes commits, committer timestamps, verified ancestry, source blob OIDs/SHA-256, source ranges, original bundle hashes and each prompt/packet hash. `manifest.sha256` freezes the manifest. Each task offers `goal_unbriefed.md` (requirements alone) and `goal_briefed.md` (identical requirements plus the same parent context seen in establish). No no-new-information control has been created.

Agent-visible files are only the selected task's establish/goal prompt and source packet, plus a clean parent checkout. **Do not mount this corpus directory or the preflight snapshots into agent sessions:** `grader-assets/` contains held-out landing test modules and `preflight/` contains answer-revealing failure traces. Copy only explicitly allowed prompt files. A code checkout must be generated from the parent, without repository git history, future tests, or external task artifacts.

Free preflight succeeded using `/home/ds/projects/codeprobe/.venv/bin/python` (Python 3.12.3, pytest 8.4.2, pydantic 2.12.5). No packages or repository environments were modified. Four disposable `git archive` snapshots each received only the landing test modules listed in the manifest. `PYTHONPATH=<snapshot>/src` ensured imports used the correct historical implementation; an import-path probe verified this for every run. Python bytecode writes and pytest cache were disabled. The corpus bundle advertises a Python 3.11 image; this preflight uses the available Python 3.12 interpreter and is not evidence of 3.11 compatibility.

For both raw_tokens and quota_exclusion, all three selected tests failed behaviorally on the parent (exit 1) and passed on the landing (exit 0). Exact commands, environment overrides, working directories, dependency probes, log hashes and exit codes are in `preflight/results.json`. The command shape is:

```
PYTHONPATH=<snapshot>/src PYTHONDONTWRITEBYTECODE=1 /home/ds/projects/codeprobe/.venv/bin/python -m pytest -q -o addopts= -p no:cacheprovider <selected node IDs>
```

The six selected tests represent **two tasks**, not six independent tasks. They validate the selected regression contracts, not all requirements or complete repository health. In particular, the quota prompt requests an all-quota edge case but the three selected FTP tests concern mixed populations and paired scores. Report this limit; broader grading can be preregistered separately before running agents. No model calls or paid experiments were run during curation.
