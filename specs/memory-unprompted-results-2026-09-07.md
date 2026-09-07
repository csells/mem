# Ordinary-task Memory Beads: four-host results

Status: all **120 scheduled sessions were started once and assessed**: 96 main
and 24 normal-native, across 20 lifecycles. One normal OpenCode session reached
the frozen process deadline. No trial was repeated or repaired. The frozen suite
passes **100/120 artifacts and 5366/6004 cases**; main and normal results remain
separate below. With the uniform posthoc supplement, 98/120 artifacts pass all
checks actually applied. These finite checks do not certify every contract case.

The standing rules/skill package produced unprompted capture and later
search-based use on Codex and zcode. It did **not** establish reliable adoption
on all four profiles, and no agent followed a known memory reference directly
in either phase. All twelve initial treatment capture opportunities were
missed. Correct task completion was much more common than a complete memory
handoff, and some saved notes contained false advice or unsupported provenance.

## What was tested

The goal was autonomous memory selection during ordinary coding work: useful
capture, fresh-session direct lookup or search followed by full lookup, faithful
application, permanent revisions, historical reproduction, and avoiding duplicate
capture when the task supplies its requirements. The four requested CLIs were
included; Gemini and Copilot were excluded by the user.

This corrects the earlier investigation's task-cue error. The installed-guidance
and public-checker experiments prescribed memory handoffs inside issue bodies.
Their results remain guided-workflow evidence. This cohort's initial business
drafts were authored without seeing the memory intervention. Final stage-3 control
revisions occurred after the objective was disclosed; this was not final-byte
blinding. Reviewers then examined the complete task/package inputs before launch.
The rejected earlier task design
was a negative control. No scored issue supplied memory keys, capture or lookup
instructions, or a request to prepare a memory handoff. Every launch prompt was
only `Work on <actual issue ID>.`

Two independently authored projects each have six fresh-session tasks:

| Stage | HarborPass renewals                                           | Northbank reconciliation                                |
| ----- | ------------------------------------------------------------- | ------------------------------------------------------- |
| 1     | Implement approved renewal notice/credit policy               | Fix exclusive UTC month boundaries                      |
| 2     | Add renewal CSV export                                        | Add ordered refund CSV export                           |
| 3     | Add a fully specified original-policy support replay          | Add a fully specified corrected incident replay         |
| 4     | Permanently change current notice/credit policy               | Move active ledger months to fixed 05:00 UTC boundaries |
| 5     | Add current-policy batch notices                              | Add current-policy daily ledger totals                  |
| 6     | Add release-1 compatibility without changing current behavior | Add original-month release-1 reconciliation             |

The six-stage labels are evaluator metadata. The agents saw ordinary features,
bug reports, requirements, and public examples. Actual code, documentation, issue
history, tests, and saved records carried forward without repair. Other sources
remained legitimate: this was not a memory-necessity ablation. Agent-created
references were preserved and their later exposure inspected separately.

The main comparison is 4 hosts × 2 guidance arms × 2 projects × 6 stages =
**96 sessions in 16 lifecycles**. The checkpoint's first 48 sessions were retained,
not repeated. Another 24 sessions use the memory arm on HarborPass, one fresh
lifecycle per host, under its normal headless native-memory settings. Stages in
one lifecycle are correlated; they are not independent reliability trials.

## Rules, skills, and tool delivery

Both arms received a real, isolated legacy `bd` 1.2.1 store and the same issue
workflow: prime, show the assigned issue, mark it in progress, implement and
verify, then close it. The memory arm added a generic AGENTS section:

> Before finishing work that establishes a useful durable decision, fact, or
> lesson, preserve it in Beads when it would help later work or be costly to
> rediscover. When implementing work that depends on missing project knowledge,
> retrieve the applicable record: follow a known reference directly, or search
> and inspect the full result.

The rest links the memory procedure and says reproducing an existing agreement
does not by itself justify another save. The Beads skill gains memory-related
discovery text and a reference to detailed capture/retrieval/revision instructions.
See the exact [AGENTS addition](../memory-bench/fixtures/memory-unprompted-package/memory-routing.md),
[skill addition](../memory-bench/fixtures/memory-unprompted-package/memory-skill-routing.md),
and [procedure](../memory-bench/fixtures/memory-unprompted-package/memory.md).

Canonical AGENTS.md is imported by CLAUDE.md and discovered natively by the other
three profiles. `.agents/skills/beads` supplies the shared skill, with a
`.claude/skills/beads` alias. The two arms use the same `bd prime --no-memories`
orientation; prime does not feed memory bodies. There is no completion guard or
task-specific hook. Native skill calls and explicit reference reads are recorded
separately; an available link is not assumed to have been opened.

This difference from issue guidance matters: issue work has an immediate object
and a concrete start/finish sequence. Memory asks the agent to judge future value
and missing knowledge, then follow another reference. Code and issue history
often already answer the task. This explains a plausible source of friction;
the comparison does not isolate that explanation from other causes. Codex's
initial omissions despite reading the procedure show that delivery alone is
insufficient.

The tool uses `bd remember <body> --key <key>`, `bd memories <query>`, and
`bd recall <key>`. Search matches literal substrings in keys/bodies. Keys are
mutable notes; historical keys are conventions, not immutable revisions. The
proposed new Memory bead type, updated prime, and rules-only/skills-only variants
were **not tested**.

## CLI/model coverage and isolation

All four CLIs were updated or verified current before qualification and frozen
before this cohort. Existing authentication was exercised in real isolated
smokes; installation alone was not treated as working access.

| CLI           | Version                           | Actual primary model              | Main native-memory setting                                    |
| ------------- | --------------------------------- | --------------------------------- | ------------------------------------------------------------- |
| Claude Code   | 2.1.263                           | `claude-sonnet-4-6`               | Automatic memory disabled                                     |
| Codex         | 0.153.4                           | `gpt-6-astra`                     | Memory disabled in fresh profile                              |
| OpenCode      | 1.18.20                           | `ollama/qwen3-coder:30b-a3b-q8_0` | No configured automatic extractor; fresh session XDG database |
| zcode-app-cli | 3.11.2-21, bundled runtime 0.16.5 | `zai/glm-5.3`                     | Native-memory features disabled; headless extraction disabled |

Claude's actual cost receipts also include auxiliary Haiku 4.5 usage. zcode's
configured helper remains documented in the pinned profile. Thus these are
host/model/profile combinations, not a controlled comparison of CLI hosts using
one model. OpenCode used the existing local-provider choice on a task-owned
Ollama server with actual 32768-token context, client context 32768/output 8192;
the user's existing server was not modified. No paid model substitution was made.

Each lifecycle had fresh scratch code/store/profile state; each stage a fresh
conversation. Declared native files and actual project state carried forward.
The agents could edit their scratch work but could not read the hidden grader or
the user's real data. Global configuration, personal histories, authentication,
existing model servers, and previous experiment evidence were preserved.

Full interfaces, permissions, model receipts, native switches, and smoke outcomes
are in the [inventory](memory-four-hosts-inventory-2026-09-07.md) and
[qualification report](memory-four-hosts-qualification-2026-09-07.md).

## Main measured outcomes

All 96 slots started once, completed, and were assessed. No timeout, infrastructure
fault, repaired capture, replacement trial, or frozen-input change occurred.
All frozen cases pass for **79/96 artifacts**, totaling **3965/4488 cases**.
Eleven of 16 lifecycles pass every stage's frozen artifact checks.

| Host/model            | Baseline artifacts | Memory-arm artifacts | Initial memory-arm capture | Permanent-revision capture |
| --------------------- | -----------------: | -------------------: | -------------------------: | -------------------------: |
| Claude / Sonnet 4.6   |              12/12 |                10/12 |                        0/2 |                        0/2 |
| Codex / gpt-6-astra   |              12/12 |                12/12 |                        0/2 |                        2/2 |
| OpenCode / local Qwen |               3/12 |                 6/12 |                        0/2 |                        0/2 |
| zcode / GLM-5.3       |              12/12 |                12/12 |                        0/2 |                        2/2 |
| Total                 |              39/48 |                40/48 |                        0/8 |                        4/8 |

The matched baseline also has 0/8 initial and 0/8 revision captures. Main
treatment records have 11 acknowledged saves across 10 sessions: two Codex saves
and nine zcode saves, producing ten keys with one historical-note update. These
are diagnostic counts, not eleven correct memory handoffs. One raw receipt counter
counts `remember --help` as a write; the accepted-action classification and trace
audit exclude that help request.

The four revision captures are first standing-policy records, not demonstrated
updates of an earlier captured standing record. zcode also updates one earlier
historical note's implementation description. Initial capture omission prevents
claiming the complete initial-capture → standing-record revision lifecycle.

| Observed retrieval route                                        | Memory-arm eligible reuse tasks | All-arm eligible reuse tasks |
| --------------------------------------------------------------- | ------------------------------: | ---------------------------: |
| Search followed by full existing-record lookup and correct work |                            3/24 |                         3/48 |
| Known-reference direct lookup and correct work                  |                            0/24 |                         0/48 |

Eligible reuse tasks are stages 2, 5, and 6. The three search handoffs are Codex
HarborPass stages 5/6 and zcode Northbank stage 5. The two Codex consumers share
one producer and are not independent capture replications. Two additional zcode
stage-4 revision sessions searched and fully read historical notes before
implementing correctly. Same-session save verification is excluded from reuse.
Correct work also had accessible code/issues, so this does not prove memory
caused correctness. Naturally authored issue-close key attributions did not
produce observed direct lookup or an explicit later lookup instruction.
These are planned reuse-slot denominators, not 24/48 observed known-reference
opportunities. Zero direct use leaves adoption unvalidated; it does not show an
inability to execute lookup when explicitly given a reference.

A uniform **posthoc** timestamp-offset case passes 32/40 applicable Northbank
artifacts. Five OpenCode treatment artifacts order timestamps lexically instead
of by absolute instant. Three OpenCode baseline artifacts lack CSV export after
an agent rolled back earlier scratch code. Two treatment artifacts passed the
frozen suite, so **77/96 artifacts pass all checks actually applied**. Frozen
grades remain unchanged; this exposes a finite test-coverage gap, not an altered
oracle. The supplement used all applicable saved artifacts, read-only isolated
copies, the pinned runtime, and independent references, without model calls.

One OpenCode session has `host_success=false` despite exit 0. A synthetic
compaction-continuation message appears after a completed step and lacks an
assistant-model table row; adjacent actual assistant messages carry pinned Qwen
rows. Preserve that stream validation/provenance limitation separately from the
independently failed artifact. It is not evidence that all 96 host streams passed
validation. No isolation, delivery, or oracle defect requiring a new cohort was
found.

## Failure distinctions that change the recommendation

- **Discovery/delivery:** Claude loaded the Beads skill in all 24 main sessions but did not
  open its memory reference. OpenCode sometimes emitted skill/tool markup as
  plain text or stopped after planning. Availability is not execution. In one
  late Claude task, invented `bd memory search` syntax failed, and
  `bd memories list` searched for the literal word `list` in an empty store.
- **Capture omission:** 0/8 initial treatment captures, although agents often
  retained the knowledge in code, README text, and issue-close reasons. Absent
  notes make record fidelity unassessable; they do not imply total knowledge loss.
- **Retrieval:** Codex searched for `finance` and `ledger`, missing its existing
  Northbank record because those substrings were absent. It then implemented
  correctly from other sources. Search miss, no full read, and successful
  alternative-source work are separate observations.
- **Application:** Claude's treatment batch task read correct current-policy code
  but regressed it to satisfy obsolete public examples, despite the README's
  snapshot warning. The compatibility task inherited the current-policy failures.
  This was not application of a bad retrieved memory: its store was empty.
- **Historical mutation:** OpenCode changed frozen historical behavior or rolled
  earlier implementation out of its scratch workspace. These actual mistakes
  carried forward. zcode updated one historical note's implementation description
  while preserving its business facts; this is not the same failure.
- **Information and provenance:** zcode's CSV note contains correct business
  requirements plus a false claim that Python's LF-configured CSV writer cannot
  quote CR. Two public-test notes overstate executed verification; one also
  attributes the daily report to the wrong stage. Correct code and exact readback
  did not certify those claims. Some permanent implementation-location prose
  became stale after later compatibility work.
- **Unnecessary work:** the 16 main supplied-reproduction slots contain no
  confirmed duplicate capture. zcode's two treatment saves added a newly fixed
  endpoint scope or were its first capture of that knowledge. No-write controls
  on hosts that never captured anything are weak evidence of good selectivity.
  The harness's 192 administrative memory snapshots are not agent retrieval.

OpenCode's broader coding/tool-use failures make this a weak profile for isolating
memory ergonomics. All 505 recorded main Ollama truncation counters were zero;
there is no observed server truncation explaining the failures. That does not
exclude client compaction effects or establish a cause. Keep this coverage row;
do not generalize from this local model to every OpenCode configuration.

The false CSV claim was independently checked on the pinned Python 3.14.7 runtime.
Its writer quotes CR with an LF line terminator. Current
[Python documentation](https://docs.python.org/3.14/library/csv.html#csv.QUOTE_MINIMAL)
supports that behavior. A [historical CPython issue](https://github.com/python/cpython/issues/67044)
documents an earlier defect; its existence does not prove where this agent got
the advice. Later sessions saw truncated previews but did not read the full false
rationale or demonstrably rely on it. This is observed misleading avoidance
advice, not demonstrated inherited tool avoidance.

## Normal-native check

All 24 frozen slots were assessed: **21/24 artifacts and 1401/1516 cases pass**.
Three of four lifecycles pass every stage. This is one memory-arm HarborPass
lifecycle per host, not an additional matched baseline comparison.

| Host     | Artifact passes | Initial capture | Revision-stage capture | Eligible prior full-record reads |
| -------- | --------------: | --------------: | ---------------------: | -------------------------------: |
| Claude   |             6/6 |             0/1 |                    0/1 |                              0/3 |
| Codex    |             6/6 |             0/1 |                    1/1 |                2/3, before edits |
| OpenCode |             3/6 |             0/1 |                    0/1 |                              0/3 |
| zcode    |             6/6 |             0/1 |                    1/1 |        1/3, after implementation |

Both captures at the revision stage are first standing-policy records. Codex
searches and fully reads its record before implementing stages 5/6 correctly.
Its additional stage-6 note adds a newly requested compatibility contract and
actual issue provenance; numerical overlap is not by itself duplicate curation.
zcode saves a first, scoped historical note in the supplied stage-3 control, then
a faithful current note at stage 4 without reading the prior body. At stage 5,
it searches and reads the current note **after** implementation, using it to
validate test supersession and avoid another save. Its stage 6 uses ordinary
issue history and code, without memory calls. No direct known-reference lookup
occurs. No confirmed duplicate capture occurs in the four supplied controls.

Claude produces correct work using code while its Beads store stays empty. Its
late commentary overclaims what a zero-price public case proves about credit
eligibility; the independent artifact checks pass, and no such claim is saved.
zcode's historical note keeps correct business facts but contains an implementation
delegation statement that becomes stale after the revision. Record fidelity and
surrounding prose remain distinct from numerical configuration correctness.

OpenCode's stage 4 changes the frozen replay to current policy while leaving CSV
export on old policy; stage 5 adds the requested batch but inherits those errors.
Stage 4 exits 0 without a valid completion marker. Stage 6 reaches the 420-second
deadline, exits -9, and passes 56/103 artifact cases. It remains a timed-out trial,
with its partial work carried into the final evidence and no replacement.
Normal host validation succeeds in 22/24 sessions, separately from 21/24 artifacts.

Claude actually enables automatic memory, but all six native-after directories
are empty and no useful native read/write is observed. Codex's normal default
keeps memory off: its initialized SQLite files have zero generated memory records
and jobs. OpenCode has no configured automatic extractor and its native-after
directories are empty. zcode enables normal feature/use switches, but headless
extraction stays disabled; retained rollout/startup/tool/cache files are not
demonstrated useful memory, and no native record reads are observed. Continuity
is evidenced by successive native-after snapshots and copy-forward code, not
an unrecorded native-before snapshot. This is neither a common native-memory
on/off test nor the user's personalized installed histories.

Across both phases, initial treatment capture is **0/12** and revision-stage
first capture **6/12**. Of 36 treatment eligible reuse tasks, six read prior full
records and produce correct artifacts: five before edits, one afterward for
validation/deduplication. Across all arms that is 6/60 planned reuse tasks.
Two additional main revision reads remain separate. All eight prior-record-reading
sessions use search; none demonstrates the known-reference direct route. These
counts describe timing/use and outcomes, not exclusive causal dependence on memory.
The 240 administrative snapshots are excluded from agent retrieval.

## Costs and verification

| Host     | Main reported dollars | Normal reported dollars | Interpretation                                                                   |
| -------- | --------------------: | ----------------------: | -------------------------------------------------------------------------------- |
| Claude   |            $5.4149662 |              $1.2164945 | $6.6314607 total CLI list-price accounting, including $0.0288240 auxiliary Haiku |
| Codex    |           Unavailable |             Unavailable | Usage receipts retained; subscription charge not emitted                         |
| OpenCode |             $0 remote |               $0 remote | Local compute unpriced                                                           |
| zcode    |           Unavailable |             Unavailable | Provider usage retained; dollar charge not emitted                               |

There is no verified combined invoice total. Qualification costs are separate
(Claude $0.35065). Claude's actual total exceeded the pre-launch $5.26
qualification-based estimate. Its receipts give list prices, not verified
subscription charges. Detailed per-host token units and native observations are
in the [cost/native audit](../memory-bench/results/memory-routes/2026-09-07-unprompted-01/audits/claude-codex-_jux3wgj/COMPLETE_CROSS_PHASE_COST_NATIVE.md)
and per-session result files. Zero reported dollars does not mean free execution.
Phase wall times were 26.26 minutes for checkpoint, 34.97 for continuation, and
13.54 for normal (74.77 minutes combined, excluding review gaps and qualification).

Each model process had a 420-second deadline; postprocessing can add elapsed
time. The final OpenCode normal session reached that deadline. Claude had a $1.50 CLI stopping threshold per session, not a guaranteed
invoice cap. No automatic retry, new authentication, or billing change was used.

Before launch, 82 focused package/adapter/runner tests passed, the independent
references passed 561/561 cases on the actual Python runtime inside the read-only
sandbox, both skill packages validated, and 14 deliberate candidate defects were
rejected. The reference implementations were authored separately from candidate
outputs by the task authors and cross-reviewed; they were not written by a third
independent reference author. Relevant Ruff, Black, and mypy checks passed. The
[pre-launch verification](../memory-bench/results/memory-routes/verification-unprompted-2026-09-07-01/SUMMARY.md)
links the detailed checks and earlier whole-suite platform/Git-environment failures;
this report does not claim the entire repository suite was green. Runtime hashes
were checked before/after every session and phase. Independent reviewers checked
artifacts, retained records, provenance, call order, and evidence hashes.

## Smallest useful changes, ranked

These are proposals informed by the results, not improvements already validated
by this cohort.

1. **Put the memory decision in ordinary issue completion.** Agents already
   produce useful close reasons and documentation. Give that existing workflow
   one short occasion to save newly approved durable knowledge or a permanent
   revision, with an explicit no-change path for reproduction. Test a concise
   integrated close/capture workflow before adding a larger optional manual.
   Keep correctness checks independent: matching a memory and an artifact does
   not prove either one right.
2. **Make applicable records easy to find and address.** Preserve naturally
   created issue-to-memory references; consider stable references in ordinary
   issue closure and a project-scoped catalog in prime. Provide a clear fallback
   after literal search misses. This could enable direct lookup without task
   hints, but updated prime/catalog behavior needs a separately frozen test.
3. **Improve the record, not just acknowledgment.** Keep exact scope, identifiers,
   units, types, and structure where needed, with a readable answer/preview.
   Separate durable business knowledge from volatile implementation locations.
   Put runtime/version, circumstances, and actual evidence beside workaround
   advice. Avoid unsupported universal prescriptions. Do not mandate JSON for
   every memory; these prose notes often preserve business facts well.
4. **Use transcripts and feedback to repair the right failure.** Classify missed
   capture, discovery, search, information loss, application, mutation, and
   overhead independently. Attempted commands are useful interface evidence;
   ambiguous commands and typos should not automatically become permanent API
   aliases. Qualify the actual host/model profile's tool and coding behavior
   before attributing every failure to memory design.
5. **Validate the improved package on fresh independent tasks.** Retain actual
   mistakes, compare both guidance arms, observe both routes, and keep the
   supplied-information control. Only after that screen should rules/skills
   ablations and the real new Memory bead type be compared. Do not retune this
   cohort's inputs or reclassify its failures into successes.

Atbrace's account supports the transcript/feedback direction as an attributed
practitioner observation. His reported 150,000-plus transcripts and adoption
claims were not independently verified here. Agent-facing JSON with a readable
`answer`, a consistent catalog, feedback, and separate human interfaces are
plausible ergonomics to assess pragmatically. They do not certify semantics or
override the user's intended behavior. His warning about remembered tool
avoidance motivated a hypothesis; our record audit establishes misleading
advice, but not a downstream avoidance policy caused by that advice.

The simplest procedure supported **in part** is: consult relevant saved knowledge
when project context is missing; search then read the full record, or follow a
known reference; implement and verify the user's task independently; save only
new durable knowledge or a permanent change, with faithful scope and evidence;
read back the save; leave standing agreements alone during historical or fully
supplied reproduction. The main run demonstrates some capture/search handoffs
under that procedure. It does not establish initial capture reliability, the
direct route, uniform four-profile adoption, causal task benefit, production
reliability, or the proposed Memory bead type. It is not bulletproof.

Earlier guided-protocol successes remain useful evidence that explicit procedures
can improve faithful capture and retrieval. Their supplied-information controls
also revealed duplicate curation after already-correct work. Those results are
not pooled with this cohort: they answer a different question. The product goal
remains a complete handoff that fits ordinary Beads work, measured by faithful
information and correct subsequent work rather than adoption counts alone.

## Evidence

The [frozen manifest](../memory-bench/results/memory-routes/2026-09-07-unprompted-01/manifest.json)
contains the schedule, identities, hashes, and source snapshot. The
[admission report](memory-unprompted-admission-2026-09-07.md) documents independent
task review and executable verification. The
[checkpoint](../memory-bench/results/memory-routes/2026-09-07-unprompted-01/CHECKPOINT.md)
and [main review](../memory-bench/results/memory-routes/2026-09-07-unprompted-01/MAIN-REVIEW.md)
remain immutable intermediate reports. Per-session prompts, issues, transcripts,
receipts, before/after artifacts, retained notes, native files, and grades are in
the [cohort](../memory-bench/results/memory-routes/2026-09-07-unprompted-01/).
Independent audit files preserve semantic judgments separately from mechanical
scores and the posthoc supplement. All final runtime/profile hashes match the
freeze. There are no unassessed or blocked slots. Three host-validation failures
(one main, two normal) and one timeout remain in the denominators. The requested
reliable initial capture, complete standing-record revision lifecycle, unprompted
direct route, and new-type validation remain unmet research goals.
