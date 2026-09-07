# Public interface checks during memory reuse

**Both conditions produced 16/16 correct artifacts. This screen found no
correctness advantage from adding the public checker.** All 32 sessions finished,
all required runtime behaviors and exact artifact exports passed, and all issues
closed. The checker rejected all 13 malformed targets from the previous run
offline, but no live session presented it with a failing interface to repair.

The memory handoff was less uniform than the artifact scores: all eight initial
capture/permanent-revision occasions preserved the exact policy and rationale;
**7/8 also preserved the exact required SOURCE text**. One initial note shortened
the source label while retaining the version elsewhere. That imperfect original
was carried forward unchanged. All 24 reproduction tasks made zero memory writes,
and all four fully supplied controls made zero memory reads as well.

Evidence: [frozen manifest](../memory-bench/results/memory-routes/2026-09-06-contract-01/manifest.json),
[outcomes](../memory-bench/results/memory-routes/2026-09-06-contract-01/outcomes-01.json),
[action audit](../memory-bench/results/memory-routes/2026-09-06-contract-01/action-audit-01.json),
[memory trace audit](../memory-bench/results/memory-routes/2026-09-06-contract-01/memory-trace-audit-02.md),
[checker trace audit](../memory-bench/results/memory-routes/2026-09-06-contract-01/checker-trace-audit-02.md),
and [independent artifact recheck](../memory-bench/results/memory-routes/2026-09-06-contract-01/final-evidence-audit-01.json).
The [public description](../docs/adoption-harness/MEMORY-CONTRACT-CHECK.md) explains
the intervention and its relation to the preceding installed-guidance experiment.

## What was held fixed

Both conditions used the existing installed AGENTS rules, CLAUDE/GEMINI imports,
project Beads skill, detailed memory procedure, and `bd prime --no-memories`
orientation. The initial request remained `Work on <actual-issue-id>.` The
harness-authored stage bodies matched; actual agent-authored successor issues
could differ and were carried forward without repair.

The sole initial treatment was `tests/test_component_contract.py`. It checks the
public POLICY nesting, field types, string SOURCE/RATIONALE exports, and callable
factory through ordinary unittest discovery. It contains no approved values or
source-label answers. The existing independent hidden grader still checks exact
approved fields and runtime behavior. There is no memory completion guard or
capture hook, and no extra task instruction to use the checker.

Each condition implements eight sibling Python cache components over the provided
engine: establish an approved agreement; direct reuse; search reuse; permanent
revision; revised direct reuse; revised search; fully supplied reproduction; and
historical reproduction. Actual notes, source, tests, issue history, authored
references, and native records survive between fresh sessions. Four competing
memories are initially present. The agent chooses its own target memory keys.
Missing or imperfect records are never replaced with perfect answers.

Existing code and issue history are legitimate alternative sources. Agents often
read them, and some authored tasks repeat settings. Correct work plus observed
memory retrieval does not establish that memory was necessary or the sole source.
This is a workflow comparison, not a test of causal dependence on memory alone.

## CLI/model coverage and outcomes

| Host/model               | Condition | Complete artifacts | Exact initial capture | Exact permanent revision | Historical body preserved | Reproduction writes |
| ------------------------ | --------- | -----------------: | --------------------: | -----------------------: | ------------------------: | ------------------: |
| Claude Code / Sonnet 4.6 | Baseline  |                8/8 |                   1/1 |                      1/1 |             1/1 lifecycle |    0 across 6 tasks |
| Claude Code / Sonnet 4.6 | Checker   |                8/8 |      0/1 exact SOURCE |                      1/1 |             1/1 lifecycle |    0 across 6 tasks |
| Codex / GPT-6 Astra      | Checker   |                8/8 |                   1/1 |                      1/1 |             1/1 lifecycle |    0 across 6 tasks |
| Codex / GPT-6 Astra      | Baseline  |                8/8 |                   1/1 |                      1/1 |             1/1 lifecycle |    0 across 6 tasks |

Exact capture here requires the complete typed policy and literal supplied
SOURCE/RATIONALE strings. The four initial captures and four revisions are eight
capture occasions; successive availability checks are not independent captures.

| Installed candidate     | Verified profile / existing route                                      | Coverage in this screen                                             |
| ----------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Claude Code 2.1.263     | `claude-sonnet-4-6`; existing subscription authentication              | 16/16 sessions, observed model matches                              |
| Codex CLI 0.153.4       | `gpt-6-astra`, high reasoning; existing ChatGPT authentication         | 16/16 sessions, observed model matches                              |
| Gemini CLI 0.55.1       | Previous credential reached provider; successful model not established | Prior depleted-credit/HTTP 429 blocker; no new trial                |
| OpenCode 1.18.15        | Previous local Ollama/Qwen route executed model turns                  | Prior verified prompt truncation at allocated context; no new trial |
| GitHub Copilot launcher | VS Code wrapper present; actual CLI/authentication unverified          | Prior missing underlying CLI; no new trial                          |

The three remaining blockers are documented in the
[host coverage audit](memory-hosts-coverage-audit-2026-09-06.md), including the
OpenCode context diagnostic. They are coverage limits, not additional scheduled
slots or failed memory trials in this 32-session screen. No user configuration,
server setting, billing state, or global data was changed to bypass them.

Both admitted executables, their versions, and existing login status were checked
before launch. Earlier real isolated smokes were reused only after their complete
source and executable hashes matched; no additional smoke was purchased. Actual
sessions then established inference availability. Claude and Codex use different
models, so differences between them combine host and model effects. Requested
Codex fast tier is not independently certified.

Normal native-memory defaults ran in fresh isolated state: Claude automatic
memory enabled, Codex memories disabled by default. User history and personal
configuration were not imported. All 16 Claude native snapshots are empty; all 16
Codex native databases have zero memory outputs and jobs. No nonempty WAL was
present. This does not test competition with accumulated native memory,
compaction recovery, or inherited tool-avoidance advice.

## Separate failure classifications

**Discovery and capture omission.** Both hosts reached the installed workflow.
Claude invoked the native Beads skill in all 16 sessions; Codex explicitly read
the skill file in all 16. All sessions ran prime. Automatic AGENTS loading remains
indirectly observed through files and behavior. No new agreement or permanent
revision was omitted, and all eight actual direct follow-up tasks existed with
real keys and applicability instructions. Not every historical copy received an
immediate separate readback, even when its retained body was correct.

**Information fidelity.** Claude checker initially stored:

```text
Approved catalog-api response-cache policy (v1).
Source: Architecture approval CACHE-17 (2026-09-06).
```

The required literal SOURCE was:

```text
Architecture approval CACHE-17 (2026-09-06), version v1
```

Its complete nested policy and rationale were exact. The approval identifier,
date, and version remained present, so factual version loss was not demonstrated.
The frozen literal-source verdict remains failed. Direct and historical work read
earlier code containing the complete SOURCE and produced exact artifacts. Those
successes cannot certify that the abbreviated Source field alone was sufficient.
Revision saved exact v2 metadata, while the historical snapshot preserved the
original abbreviation. Faithful history can therefore retain an imperfect capture.

**Retrieval.** All eight named direct stages fully recalled the applicable real
key before implementation. All eight named search stages queried and then fully
recalled the selected record before implementation. All 16 artifacts passed.
Historical reproduction also obtained complete retained content in 4/4 cases:
three used recall; Claude checker obtained the full snapshot body through
`bd memories 'v1-snapshot' --json`, without a separate recall. This is an alternate
full-content route, not a missing retrieval. A command name alone does not establish
whether its response contains a preview or the whole record.

**Application and checker use.** All 32 artifacts satisfy the complete independent
contract, including runtime behavior and exact source/rationale exports. All 32
canonical target and whole-workspace checks pass. The checker was explicitly read
before component creation in 14/16 treatment stages, after creation in one, and
not separately read in one. Its readable assertions can guide implementation, so
the treatment combines executable guidance and test feedback.

There were 33 ordinary unittest invocations across 32 stages, all passing. In the
final Codex baseline stage, the agent added tests after a failed heredoc and ran
the suite again; this was added coverage after shell recovery, not a component
repair. No contract-test failure followed by a relevant edit and passing rerun
was observed. Every first recorded component definition already had nested POLICY.
Claude checker authored component tests in three stages versus eight in its
baseline; that is a work-pattern difference, not an established quality or causal
effect. Agents changed neither the checker nor earlier project files.

**Historical mutation.** All four lifecycle histories remained byte-identical
after their actual capture, and historical reproduction left standing v2 intact.
Claude checker copied its original current note verbatim to its newly authored
historical key before revision. The frozen grader infers history identities from
exact content, so its history status is unknown/false for that abbreviated note.
The trace audit separately establishes the real history identity from the
agent's references and commands, then verifies its bytes. No original grade is
overwritten. Wording such as “immutable snapshot” expresses intended preservation;
legacy keyed notes remain mechanically editable.

**Unnecessary work and recovery.** All 24 reproduction tasks made zero memory
writes, including the four supplied controls with zero reads. Each lifecycle made
three actual writes: current capture, historical capture, and permanent revision.
The two intentionally distinct original/current and historical records are not
duplicate curation merely because their contents initially match.

Claude recovered from four failed CLI attempts: `bd memory get` twice, a recall
using approval label `CACHE-17` as a key, and `bd memories show`. A literal `list`
query also returned no matches before listing/JSON discovery recovered. These are
interface friction with successful recovery. Codex separately encountered four heredoc
temporary-file failures before Beads executed and recovered through other forms.
Those shell failures are adapter overhead, not phantom memory writes or lost notes.
Programmatic readback/consistency checks also account for some extra recalls;
execution counts do not mean each result was independently shown to the model.

## Offline proof, costs, and verification

The [offline qualification](../memory-bench/results/memory-routes/2026-09-06-contract-check-static-01/evidence.json)
accepted all 19 previously correct target interfaces and rejected all 13 flattened
targets, preserving 585 original inputs. Whole-workspace discovery passed 16/32
old snapshots because three correct targets had earlier incorrect siblings. The
checker deliberately accepts structurally valid wrong facts; hidden approved-value
grading remains separate. These are detector checks, not demonstrations of an
agent repairing a detected failure.

| Group           | Successful memory reads | Queries | Listings | Full recalls | Actual writes | CLI usage estimate |
| --------------- | ----------------------: | ------: | -------: | -----------: | ------------: | -----------------: |
| Claude baseline |                      19 |      10 |        0 |            9 |             3 |         $1.9128924 |
| Claude checker  |                      22 |      13 |        1 |            8 |             3 |         $1.7505183 |
| Codex checker   |                      16 |       5 |        0 |           11 |             3 |            Unknown |
| Codex baseline  |                      20 |       6 |        0 |           14 |             3 |            Unknown |

The corrected totals are 77 reads and 12 writes. Four `remember --help` calls
explain 16 raw reported writes versus 12 real writes; help/list semantics also
explain the raw read/search discrepancies. The bounded auditor classifies 16 help
calls and leaves one root `bd --help` invocation unknown. Its raw output plainly
shows root usage; the trace audit records that additional help interpretation
without altering the automatic verdict. No uncertain root-help call is counted
as a memory operation. The harness also took two administrative memory snapshots
per session; those were not delivered to the agent.

Known usage is **$3.6634107 plus unreported dollar costs for 16 Codex sessions**.
These are CLI estimates, not invoices or subscription charges. Earlier experiments
and smokes retain their separate costs. There were no new smokes, reruns,
interrupted attempts, unrun slots, or out-of-profile models. Conditions ran
sequentially: Claude baseline, Claude checker, Codex checker, Codex baseline;
the limits were 420 seconds per session and a requested $1.50 cap enforced only
by Claude. Timing and cost differences here are descriptive, not efficiency effects.

[Prelaunch verification](../memory-bench/results/memory-routes/verification-contract-2026-09-06-01/SUMMARY.md)
passed all 121 relevant tests plus full Ruff, Black, and strict mypy, with an
explicit strict check of the new driver. The independent post-run recheck copied
all 32 saved workspaces to fresh scratch and reran artifact and canonical public
checks under read-only sandboxing: every verdict matched. All 28 memory/source
transfers matched, 300 frozen live source/test files and four executables matched,
all native copies matched their actual originals, and 1,273 recheck inputs remained
unchanged. SQLite inspection used immutable read-only connections.

A [separate preservation check](../memory-bench/results/memory-routes/2026-09-06-contract-01/final-preservation-01.json)
also matched all 300 archived source copies and all 7,812 previously preserved
files. The trace audits retain their first diagnostic drafts: memory audit 02
marks route checks inapplicable outside their assigned stages; checker audit 02
uses the full saved host rollout where normalized output omitted an earlier
`cat` result. Neither correction changes a model run, artifact, or frozen grade.

The previous full Python suite's 4,678 passes, 44 skips, 27 failures, and 12 setup
errors remain documented macOS/Linux assumptions; that unchanged suite was not
repeated or declared green. TypeScript is unchanged from its prior complete passing
verification. No frozen runtime or earlier experiment artifact was edited.

## Smallest useful changes, ranked

1. **Keep the installed, selective handoff procedure.** Shared AGENTS routing,
   thin host imports, a Beads skill with a memory branch, and prime orientation
   reached both tested hosts through normal issue work. Capture newly approved
   durable knowledge or a permanent revision before closing; retrieve missing
   prior agreements before implementing; use fully supplied agreements directly.
   Preserve actual references and avoid resaving merely because knowledge was used.
2. **Preserve the record the next task actually needs.** Keep exact scope,
   canonical identifiers, structure, types, units, and provenance. When downstream
   work requires a literal source export, retain that complete field beside the
   readable preview. Check capture against the approved source, not just against
   an artifact generated by the same agent. The observed abbreviated label is a
   reason to distinguish literal fidelity from factual availability, not to force
   every prose memory into JSON or add a universal memory-read guard.
3. **Use ordinary independent project tests for application requirements.** The
   public checker catches the known structural fault and is a small usable project
   test. This matched screen does not establish that it improves agent outcomes,
   because baseline also passed 16/16 and no live repair was needed. Keep approved
   facts and provenance grading independent; shape checks cannot certify them.
4. **Improve concrete interface and adapter friction.** Investigate a coherent
   issue-like lookup interface and validated aliases for attempted commands. Keep
   search versus listing explicit; avoid silently redefining valid query terms.
   A full-record JSON response can satisfy retrieval without a redundant command.
   Make normal heredoc use work in isolated host adapters before another comparison.
   These interface/adapter changes are proposals, not implemented treatments here.
5. **Validate the actual Memory bead type next.** Use real identity/reference
   integrity, protected historical revisions, and stale-write handling rather than
   relying on immutable-sounding prose. Clear the three host blockers, then repeat
   matched handoffs on distinct task families, longer work, accumulated native
   memory, and compaction. Another small prompt variation on this same fixture
   would leave the main production questions unanswered.

Atbrace's transcript collection, adoption claims, JSON conventions, and feedback
loop remain attributed practitioner observations; their scale and effectiveness
were not independently verified here. The useful application is ongoing trace
review that separates discovery, omission, information fidelity, retrieval,
application, history, and extra work. Attempted commands are design evidence,
not an obligation to add every imagined API. Separate agent/human presentations
are useful when they remove observed friction while exposing the same faithful
record. Remembered tool avoidance remains an unobserved hypothesis; workaround
advice should carry version, circumstances, and evidence.

The simplest supported procedure is: read the issue and its intended scope/version;
use a complete supplied agreement directly, otherwise retrieve the full applicable
record by actual key or search; preserve only new or permanently revised approved
knowledge, check its retained content, and protect history; cite the real record in
dependent work; verify the resulting artifact before closing. This sample supports
that practical workflow on two host/model profiles. Four correlated lifecycles,
one synthetic task family, alternative exact sources, and legacy mutable notes
do not establish production reliability or validate the proposed Memory bead type.
