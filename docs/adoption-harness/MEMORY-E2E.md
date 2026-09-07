# End-to-end Memory Beads experiment

**Status: completed, 32/32 sessions across four lifecycles.** All 32 components
passed the tested runtime behavior, while 19 passed the complete artifact contract.
The initial description was published at `8191a33` before implementation. This is
a separate experiment from the [paired adoption harness](README.md); that README's
run commands still execute the paired experiment.

The question is whether an agent receiving an ordinary task assignment can
discover the installed Beads workflow, preserve an approved durable decision,
author a useful reference to it, and use the actual retained knowledge correctly
in later work. The test covers delivery and discovery as well as storage,
retrieval, application, and unnecessary curation.

## Completed results

| Host   | Delivery  | Complete artifacts | Runtime behavior | Actual memory writes |
| ------ | --------- | -----------------: | ---------------: | -------------------: |
| Claude | Explicit  |                0/8 |              8/8 |                    4 |
| Claude | Installed |                3/8 |              8/8 |                    3 |
| Codex  | Explicit  |                8/8 |              8/8 |                    3 |
| Codex  | Installed |                8/8 |              8/8 |                    3 |

The 13 artifact failures exported a flattened `POLICY`, omitting required outer
structure, despite faithful retained agreements and correct tested cache behavior.
All 32 preserved the exact named source and rationale in their components. Correct
memory retrieval did not ensure complete application of the public interface.

All four initial capture occasions and all four permanent revisions retained the
exact approved policy, source, and rationale. Each initial occasion preserved a
current record and an original snapshot; those are not eight independent captures.
All four historical bodies remained unchanged. Claude explicit made one
unnecessary identical resave during reproduction, creating no new identity or
body change. All four fully supplied controls made zero memory writes; three also
made zero memory reads. Claude explicit searched and recalled the supplied
agreement anyway.

The [offline action audit](../../memory-bench/results/memory-routes/2026-09-06-e2e-01/action-audit-01.json)
records **13 actual memory writes and 82 successful memory reads**: 26 queried
searches, one unfiltered list, and 55 full recalls. It also records 17 help calls,
32 prime calls, and two failed Beads invocations. These are operation counts;
queries may return no candidates, additional reads may verify prior work, and
shell failures before Beads starts are separate. Installed Claude's revised
search found its record through listing after an empty literal query for `list`.
That is list-and-recall success, not successful filtered search.

This audit is an explicit posthoc measurement correction. The frozen counter
mistook four successful `remember --help` requests for writes and counted the
unfiltered list as a queried search. A separate
[`memory_e2e_audit` helper](../../memory-bench/scripts/memory_e2e_audit.py)
reclassifies recorded arguments and CLI responses, identifies each correction by
invocation ID and input hashes, and preserves the original counters and all
artifact/capture verdicts. Its 204 session-input hashes and own source hash were
verified. The two smokes remain separate from the 32-slot cohort; Codex's smoke
made one real write plus a help request, not two writes.

See the [full experiment report](../../specs/memory-e2e-experiments-2026-09-06.md)
and [trace audit](../../specs/memory-e2e-trace-audit-2026-09-06.md) for delivery,
actual task references, command detours, source fidelity, costs, and limitations.
The arm differences are descriptive results from four correlated lifecycles,
not a reliability estimate or proof that installed delivery is superior.

## A small matched screen

The frozen screen has **32 session slots**: one eight-stage lifecycle in each of
two delivery arms on each of the two previously usable hosts, Claude Code and
Codex. One bounded integration smoke per host preceded the screen.

| Arm                | How the procedure reaches the agent                                                                                            |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| Explicit delivery  | The complete candidate procedure appears in the initial prompt.                                                                |
| Installed delivery | The prompt supplies only the task assignment; project rules, prime, the Beads skill, and task inspection deliver the workflow. |

Both arms use the same seeded task requirements, procedure semantics, tools,
memory-body exclusion, native-memory setting, and grading. The actual authored
successor tasks are retained outputs and can differ between arms. The explicit arm keeps ordinary issue guidance
and tool help but does not also register or automatically load the candidate
memory procedure through skills or prime. This compares two delivery packages;
it cannot isolate the effect of one rule, hook, or skill description. Earlier
cohorts remain historical evidence, not a matched control.

The [cohort manifest](../../memory-bench/results/memory-routes/2026-09-06-e2e-01/manifest.json)
freezes availability, models, 294 source/package hashes, four executable hashes,
ordering, resource limits, and interruption handling. Its inputs match both
admitted smokes. Claude uses `claude-sonnet-4-6`; Codex uses `gpt-6-astra`. Each
session has a 420-second limit; Claude also has a $1.50 CLI usage cap. Codex does
not report a dollar cost or enforce that dollar cap.

Gemini's billing blocker, Copilot's missing CLI, and OpenCode's context-delivery
blocker remain recorded from the previous preflight; they were not rechecked by
new model calls. Blocked or interrupted slots stay in the accounting. No user
credentials, global configuration, models, or servers were changed to repair
those blockers.

## Verified integration and local execution

The [Claude smoke](../../memory-bench/results/memory-routes/2026-09-06-e2e-smoke-claude-01/result.json)
and [Codex smoke](../../memory-bench/results/memory-routes/2026-09-06-e2e-smoke-codex-01/result.json)
both produced the exact smoke artifact, retained its agreement, recalled it, and
closed the task. Claude made one native `Skill` call and one memory-reference
read. Codex explicitly read the skill file and its memory reference once each;
that is manual file loading, not a native skill invocation. These are integration
checks, not evidence that the full lifecycle works. Claude's reported smoke usage
estimate was $0.1920176; Codex's dollar cost is unknown. The estimate is not a claim
of additional subscription billing.

Before launch, 60 focused tests passed, as did full Python Ruff/Black checks
(592 files), strict mypy across 278 source files, and explicit checks of the six
new modules/scripts. The checks cover package isolation, imports and aliases,
receipt handling, real task bodies, and independent grading. Prime checks with
stored distractor records confirmed their bodies were absent from output.

The posthoc audit adds 24 passing focused tests. The broader Python suite reported
4,678 passed, 44 skipped, 27 pre-existing failures, and 12 setup errors; the full
suite is not green. These results remain separate from the passing experiment
checks and are recorded with the final verification evidence.

The implementation is a locally runnable research harness, with pinned local CLI
paths, existing authentication, Python dependencies, and macOS sandbox support.
It is not a portable turnkey CLI. From `memory-bench/`, the entry module is
[`scripts.memory_e2e_experiment`](../../memory-bench/scripts/memory_e2e_experiment.py).
It accepts exactly one action and an `--out` directory:

| Action                                            | Purpose                                                                                                           |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `--smoke claude` or `--smoke codex`               | Run one installed-package integration smoke in a new output directory; launches a model.                          |
| `--freeze --claude-smoke PATH --codex-smoke PATH` | Validate the supplied smoke hashes and create a new frozen cohort directory.                                      |
| `--fire`                                          | Execute admitted cases from that directory's manifest, preserving started sessions and failures; launches models. |
| `--report`                                        | Append numbered JSON and Markdown summaries of saved case results without launching models.                       |

The [parent launch record](../../memory-bench/results/memory-routes/2026-09-06-e2e-01/parent-launch.json)
records the actual resolved Python invocation and dependency path. Launch uses the
same Python 3.13 interpreter and environment dependencies through its resolved
executable: the read-only feature grader denied access to `pyvenv.cfg` when invoked
through the virtual-environment path. This launch adjustment changed no frozen
source or executable bytes. New runs need their own output directories; the completed
cohort is preserved as evidence.

## One shared project package

The installed arm receives one package in each disposable project fixture:

```text
AGENTS.md                               # short workflow occasions and skill pointer
CLAUDE.md                               # @AGENTS.md
GEMINI.md                               # @./AGENTS.md
.agents/skills/beads/SKILL.md             # canonical Beads workflow
.agents/skills/beads/references/memory.md # detailed memory branch
.claude/skills/beads                     # symlink to the canonical skill
.beads/PRIME.md                          # compact orientation and skill routing
```

The same PRIME text is also installed in the isolated store's `.beads/PRIME.md`,
because the instrumented real `bd` runs with `-C` pointing to that store. The
explicit arm receives ordinary issue rules and prime orientation, with the
candidate memory procedure supplied only in its prompt. It registers no candidate
memory skill. Both arms use the exact same detailed memory-procedure bytes.

Host entries share the same instructions; they are not five separately maintained
procedures. Verify imports, discovery, and actual content delivery against the
installed versions. A file's presence or an ordinary Markdown link does not prove
that it was loaded. Record native skill activation separately from an agent
explicitly reading the skill file.

The skill covers ordinary issue work and explains when to enter its memory
workflow: an absent prior agreement, a newly approved reusable decision, or a
permanent correction. Preserve exact identifiers, scope, values, types, units,
structure, and source where relevant. Keep a readable preview and distinguish
approved facts from interpretation. Use faithful prose for prose knowledge and
structured data for structured agreements. Not every memory needs JSON, and
completing a task does not by itself justify another memory.

Issue claiming and closure apply to the work. Memory records provide durable
knowledge with a separate lifecycle. This implementation installs no automatic
capture or completion-blocking hook; those would be additional interventions.

### Prime must not supply the answers

For the legacy packaging test, use the real **`bd prime --no-memories`** command.
In installed `bd` v1.2.1, a custom `.beads/PRIME.md` replaces workflow text but does
not suppress appended memory bodies. `--no-memories` suppresses them;
`--memories-only` takes precedence over that flag and must not be combined with it
here.

The current package uses the project rule's explicit command path for startup or
context restoration. Any later startup or compaction hook must preserve the same
exclusion. Prime output is checked with stored distractors before model calls.
Injecting stored bodies automatically would bypass the retrieval routes the
experiment is intended to measure.

## Put the requirements in real tasks

The ordinary user request is approximately `Work on <task-id>`. Detailed feature
requirements, approval evidence, and the intended use of references belong in
the actual task body. Routine task requests do not supply capture keys or memory
coaching.

The fixture is a small runnable Python cache project with independently testable
behavior. Agents implement sibling components governed by a shared approved
policy. Its eight fresh agent sessions cover:

1. Initial approval and implementation.
2. Reuse through an agent-authored task reference.
3. Reuse by searching for the agreement.
4. A permanent revision.
5. Direct reuse of the revised agreement.
6. Search-based reuse of the revised agreement.
7. Reproduction with the complete agreement supplied.
8. Historical reproduction.

The producing agent must author a real follow-up task that explains the policy's
relevance and refers to the memory it actually created. Grade that task, the
returned identity, and the later handoff separately. An omitted memory, task, or
reference remains omitted; the harness must not manufacture it for the next
session.

Search tasks include plausibly overlapping notes and different wording of the
same agreement. The permanent-revision task supplies the project, scope, and
approved change, but **no memory key, ID, or link**. It tests whether the agent
searches, fully recalls the existing record, and updates that identity without
creating a duplicate. Grade the revised content and historical preservation
independently of record selection.

Carry actual project files, task history, Beads records, and condition-appropriate
native memory forward. Each lifecycle starts with a fresh isolated workspace and
native state; each host's normal native-memory default remains intact. Do not erase
source evidence to force memory use. A later agent may correctly recover an
agreement from an earlier task, specification, or
code. That is a task success through an alternative source, not a demonstrated
memory handoff. Report whether memory was necessary for each task.

## Measurement and interpretation

Independent hidden expectations grade the resulting feature behavior. Separate
checks assess retained information, source fidelity, record identity, historical
immutability, and the quality of agent-authored references.

Traces must distinguish rules delivered, skill reached, task inspected, capture
attempted and retained, search results seen, full record delivered, information
applied, and current or historical state changed. Agent narration is not a receipt;
unknown attribution stays unknown. Automatic and harness reads are counted
separately from agent reads. Additional reads may be legitimate verification and
are not automatically waste.

The new isolated adapters enable project rules and skills while preserving the
previous adapters and frozen experiments. Smoke traces distinguish observed skill
access from automatic rule loading, which is not directly certified. Receipts
record real subprocess execution separately from complete output seen somewhere
in the session; neither alone proves that the model used the information.

Report attempts, recorded sessions, complete lifecycles, blocked or unrun stages,
known and unknown costs, and instruction/tool overhead. Eight stages sharing one
capture are correlated observations, not eight independent reliability trials.
Use transcripts to explain failures before changing the package; retest a changed
package as a new cohort.

## What this cannot establish

This screen can exercise legacy keyed memory in `bd`. Its task references remain
text, and its historical notes remain mutable. It cannot validate the proposed
production Memory type's structured Bead References, canonical identity,
immutable revisions, revision pins, stale-write protection, or production
provenance. A shim is not that implementation.

The later production test must run the same author-to-executor handoff against
the actual Memory interface. This small screen first asks whether the shipped
workflow can be discovered and used through ordinary issue work. It is not a
claim of production reliability or spontaneous recognition of every useful
lesson.

The [design proposal](../../specs/memory-e2e-experiment-proposal-2026-09-06.md)
records the host documentation, candidate instructions, and remaining production
requirements.
