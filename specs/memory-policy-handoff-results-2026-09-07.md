# Memory policy handoffs during ordinary coding work

Completed: all 240 main sessions and all 24 separate normal-memory sessions were
started and assessed once. No scored session was retried or replaced, and the
frozen conditions remained unchanged. The experiment demonstrated voluntary
capture and both lookup routes on several CLI/model pairs, but did not establish
reliable handoffs across all tested agents.

The question is whether coding agents independently save and use durable project
knowledge while completing ordinary issues, with the capability introduced by
project rules and a skill. A task that tells the agent to remember or recall does
not answer that question. Every scored session here receives only
`Work on <actual issue ID>.` The experiment-authored issue descriptions contain
product requirements and approvals, without memory commands, memory keys, or
reminders to use memory. Agent-authored issue updates can naturally introduce
such references and remain available in later sessions.

The [deployment description](../docs/adoption-harness/MEMORY-POLICY-HANDOFF.md),
[frozen design](plans/0006-policy-handoff-model-sweep.md), and
[manifest](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/manifest.json)
give the complete setup. The manifest freezes 240 main sessions—ten model profiles,
two guidance arms, two task families, six fresh sessions—and 24 separate normal
host-memory checks. Actual code, documents, issue history, and saved memories,
including mistakes and omissions, carry forward. Original approvals remain
available as legitimate alternative sources.

## Main results: voluntary handoffs worked, but inconsistently

All 240 main sessions were started and assessed once. There were **185/240 correct
accumulated artifacts**, with 17,947/19,220 hidden cases passing. Eleven of 40
six-session lifecycles met the strict core handoff criterion described below.
These successes occurred in three CLIs and six primary model profiles: Codex
Astra and Terra, Claude Sonnet, Opus and Fable, and zcode GLM. OpenCode with the
tested local Qwen model did not produce a complete handoff.

| Main outcome                                              |   Generic guidance | Occasions guidance |
| --------------------------------------------------------- | -----------------: | -----------------: |
| Faithful initial policy capture                           |               2/20 |               9/20 |
| Faithful current and historical agreements after revision | 6/20; 1 unverified |              13/20 |
| Faithful current and historical agreements at the end     | 9/20; 1 unverified |              13/20 |
| Successful prior-record use on eligible legs              |              19/60 |              39/60 |
| Successful direct / search-then-full routes               |             11 / 8 |            19 / 20 |
| All six accumulated artifacts correct                     |              12/20 |              11/20 |
| Strict core handoff                                       |           **2/20** |           **9/20** |
| Correct session artifacts                                 |             95/120 |             90/120 |
| Passing hidden cases                                      |        9,114/9,610 |        8,833/9,610 |
| Correct fully supplied support attachment                 |              19/20 |              18/20 |
| Duplicate curation in the supplied control                |               0/20 |               0/20 |

The occasions package improved observed capture and reuse in this cohort. It did
**not** improve overall artifact correctness. A late capture or successful source
lookup could recover later work, but could not erase an initial omission. All 11
faithful initial captures also completed the strict core handoff. That small,
selected group is encouraging; it does not establish that fixing capture alone
causes every subsequent step to succeed. The strict criterion itself depends on
initial preservation and first reuse.

| CLI / actual primary model                   | Correct artifacts /24 | Initial faithful /4 | Strict core /4 | Successful use /12 | Direct / search successes |             Reported cost |
| -------------------------------------------- | --------------------: | ------------------: | -------------: | -----------------: | ------------------------: | ------------------------: |
| Codex / `gpt-6-astra`                        |                    24 |                   2 |              2 |                 10 |                     5 / 5 |                   Unknown |
| Codex / `gpt-5.6-sol`                        |                    23 |                   0 |              0 |                  7 |                     4 / 3 |                   Unknown |
| Codex / `gpt-5.6-terra`                      |                    19 |                   1 |              1 |                  5 |                     3 / 2 |                   Unknown |
| Codex / `gpt-5.6-luna`                       |                    17 |                   0 |              0 |                  4 |                     2 / 2 |                   Unknown |
| Claude / `claude-haiku-4-5-20251001`         |                     8 |                   0 |              0 |                  0 |                     0 / 0 |                     $2.16 |
| Claude / `claude-sonnet-5`                   |                    19 |                   1 |              1 |                  3 |                     0 / 3 |                     $4.74 |
| Claude / `claude-opus-5`                     |                    24 |                   2 |              2 |                 10 |                     6 / 4 |                    $16.41 |
| Claude / `claude-fable-5-1`                  |                    24 |                   4 |              4 |                 12 |                     6 / 6 |                    $19.52 |
| OpenCode / `ollama/qwen3-coder:30b-a3b-q8_0` |                     3 |                   0 |              0 |                  0 |                     0 / 0 | $0 remote; local unpriced |
| zcode / `zai/glm-5.3`                        |                    24 |                   1 |              1 |                  7 |                     4 / 3 |                   Unknown |

Each row combines both arms and both families. This table is coverage, not a
controlled host or model-strength ranking. Sol, Terra and Luna had respectively
2, 6 and 6 quota-error sessions; Haiku had two turn-limit sessions. Fable's 4/4
core result still contains a surrounding-advice concern discussed below.

Across both arms, **58/120 eligible legs** had successful prior use: 30 direct
lookups and 28 searches followed by full lookup. Of these, 43 reads preceded
product edits, 14 informed subsequent testing or validation, and one supported a
substantive source confirmation after tests had already passed. The last case
is evidence of confirmation, not preparation for implementation.
As a separately labeled timing sensitivity, excluding that post-test confirmation
leaves 57/120 successful use legs and 10/40 complete core lifecycles: 2/20 generic
and 8/20 occasions. These are not replacements for the frozen scores.

There were 66 applicable entry records under the audit's target-version
definition. The conditional 58/66 result excludes known wrong or wrong-version
records and must not be presented as robustness to arbitrary saved memories.
Counting a conflicting record that purported to govern the target version gives
67; adding two topic-related but other-version records gives at least 69.
The all-120 denominator is the primary result. The audit's 61 classified full
target-body reads are also not a census of every actual full memory read: for
example, Terra read a current-version body during historical finance work.

Thirty-two eligible legs produced correct artifacts without verified prior-record
use. Actual code, original approvals, documentation and issue history often
provided legitimate alternative routes. This experiment shows that voluntary
memory use can help; it does not show that every correct implementation needed it.

## Separate normal-memory checks

The four fresh finance lifecycles with occasions guidance completed all 24
sessions: **18/24 correct accumulated artifacts**, 1,227/1,360 passing cases and
24/24 successful host receipts. These results are separate from the main arms.

| Normal anchor   | Correct artifacts /6 | Faithful initial capture | Strict core | Successful prior use /3 | Direct / search successes |
| --------------- | -------------------: | ------------------------ | ----------- | ----------------------: | ------------------------: |
| Codex / Astra   |                    6 | Yes                      | Yes         |                       3 |                     3 / 0 |
| Claude / Sonnet |                    6 | Yes                      | Yes         |                       3 |                     1 / 2 |
| OpenCode / Qwen |                    0 | No                       | No          |                       0 |                     0 / 0 |
| zcode / GLM     |                    6 | Yes                      | Yes         |                       3 |                     0 / 3 |

Three of four retained faithful current and historical agreements throughout
revision and subsequent use. There were 9/12 successful prior-use legs: five
before product edits, three before subsequent testing or validation, and one
post-test source confirmation. In that last case, GLM's final claim that it read
the agreement _before implementing_ contradicted the trace. Excluding post-test
confirmation as a separate timing sensitivity gives 8/12 uses and 2/4 complete
core handoffs, without changing the frozen 9/12 and 3/4 scores.

Sonnet's direct route is especially useful evidence: an earlier agent-authored
issue completion contained the actual saved key. The new session read that issue
and fully recalled the existing record before editing, without a memory search
or an experiment-authored memory reference in its task. Direct lookup therefore
worked through an ordinary retained work reference as well as the experimental
catalog.

All four supplied support attachments were correct, with **0/4 duplicate captures**
and no memory store changes. Qwen's correct attachment coexisted with failing
accumulated behavior. Sonnet unnecessarily searched and fully read the current
agreement for the supplied task. Astra read its required key catalog but no body;
GLM used no memory commands. The control supports avoiding duplicate curation,
not a claim that all memory overhead disappeared.
Three controls began with an existing agreement; Qwen's store was empty, so its
no-duplicate outcome was not an opportunity to test avoidance of an existing copy.

The same prose limits remained in otherwise successful lifecycles. Sonnet's
retained revision note overstated a total-only test as verification of line
priority. Astra twice claimed a note had been saved at issue closure before a
failed write was recovered later in the same session. GLM overstated retrieval
chronology and one test's coverage. Core agreement fidelity and eventual correct
work do not certify every verification or completion claim.

The independent native audit found **zero retained native memory records and zero
observed native-record reads or writes** across these 24 sessions. Sonnet's actual
automatic-memory setting was enabled, but all native snapshots were empty; its
full initial system prompt was not exposed by the CLI stream. Astra retained its
feature-off default, and its native SQLite output and job tables stayed empty.
Qwen had no separate extractor and no retained native records; detailed arbitrary
file reads by one exploration child were not fully observable.

GLM had native memory and use enabled, and its native file-memory instructions
were present in all 111 captured model requests. Automatic extraction was disabled
by the headless runtime, while manual native writes remained possible. Its actual
memory directories stayed empty; retained logs, tool artifacts and runtime
catalogs were separate state. Thus these checks show observed Beads handoffs
alongside normal headless settings, including native guidance for GLM. They do
not establish immunity to competition from accumulated native records, an
enabled-extractor comparison across all hosts, or zero behavioral effect from
native instructions.

The normal sessions reported $1.402738, with costs unavailable for 12/24; local
Qwen compute remains unpriced. Their summed duration was 2,613 seconds and their
approximate CLI span 954 seconds. Across all scored sessions, recorded usage was
$44.2413468 with 132/264 costs unavailable; qualification and investigator compute
are separate. The combined execution total is 203/264 correct artifacts and
19,174/20,580 passing cases, not an additional matched treatment comparison.

## What changed and why these tasks are a better test

The previous unprompted screen produced 100/120 passing artifacts under its frozen
checks but no initial keyed capture in 12 treatment lifecycles and no direct
lookup. Two additional artifact failures were identified post hoc; they are
reported separately rather than changing the original score. Existing code often
already supplied the knowledge needed for the next task, while the guidance asked
for retrieval only when knowledge was missing. That was weak evidence about
preparation for policy-dependent work. See the
[previous report](memory-unprompted-results-2026-09-07.md).

Here, the initial observable behavior is compatible with different approved
agreements. A single-line credit quote cannot distinguish a cap shared by an
account from one shared by a subscription. Later multi-subscription totals need
the approved scope, and itemized statements need allocation priority that totals
do not reveal. The second family similarly distinguishes globally unique delivery
IDs from account-local IDs, then requires the approved duplicate-selection rule
and exact accepted receipts. Hidden checks include scope, version, priority,
Unicode identity, mixed time offsets, and output-order witnesses.

| Session | Product work                                                                      | Durable-knowledge occasion                                        |
| ------- | --------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| 1       | Implement a narrow capability under a complete agreement                          | Preserve approval details beyond the immediate implementation     |
| 2       | Extend it across multiple entities                                                | Apply the original scope                                          |
| 3       | Adopt a permanent revised agreement while retaining explicit old-version behavior | Preserve both current authority and history                       |
| 4       | Produce itemized/detail output                                                    | Apply allocation or selection rules absent from aggregate outputs |
| 5       | Support original-version detail output                                            | Apply historical authority without changing the current agreement |
| 6       | Produce a fully specified support attachment with existing commands               | Reproduce without automatically saving another memory             |

For a concrete example, the actual request `Work on trial-h5o.` assigns
[“Show credit on each statement line”](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/cases/codex-astra-finance-generic-isolated/stage-4/task.json).
Its issue says: “Use the current agreement's cap groups and line-credit priority;
their approved meaning is unchanged.” It specifies the new response shape but
does not repeat the missing priority, name a record, or tell the agent where to
retrieve it. The earlier
[single-charge issue](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/cases/codex-astra-finance-generic-isolated/stage-1/task.json)
contains the complete Finance approval. Both are ordinary domain instructions;
the memory procedure lives in the deployment.

An offline author-written probe found identical scalar outputs in 72 cases and
different expanded behavior in 32/64 cases. This establishes a useful construction,
not an agent result or proof that memory is the only possible source. Agents can
retain policy in implementation, documentation, or issues; the experiment does
not erase those alternatives to manufacture dependence.

There is an important trigger limitation. The finance approval arrives in the
first issue; the Courier provider agreement is already a bundled document.
GLM explicitly declined to duplicate that document in the occasions arm. Its
missing initial memory is a failed capture outcome under the frozen rubric, but
not unambiguous evidence that it disobeyed a rule about _newly introduced_ durable
decisions. Initial capture and source durability must be reported separately.

## Rules, skills, discovery, and the intended product experience

Each project installs `AGENTS.md`, `CLAUDE.md` and `GEMINI.md` pointers, a shared
Beads skill under `.agents/skills/beads`, its `.claude/skills` alias, a memory
reference, and `.beads/PRIME.md`. The issue workflow is shared between arms. The
agent has real legacy `bd remember`, `bd memories`, and `bd recall` commands on an
isolated PATH, operating on its scratch Beads store. This tests a deployment
procedure over legacy commands; it does **not** validate the proposed Memory bead
type.

The generic arm asks for useful durable capture and retrieval when needed
knowledge is missing. The occasions arm describes what memories are for and ties
them to explicit workflow moments: newly approved durable decisions, permanent
revisions, verified reusable findings, and implementation governed by earlier
agreements. It requires preserving exact scope and operational details, separates
approval from inference, and says a readback verifies storage rather than truth.
Historical reproduction and a new consumer are not themselves new agreements.

Both arms share the expanded Beads skill description and catalog orientation.
Thus the generic arm is not a byte-identical rerun of the previous deployment.
This comparison tests complete guidance packages; it cannot isolate the effect of
AGENTS.md from the skill or identify the effect of one added sentence.

An indexed lifecycle exposes `BEADS_MEMORY_INDEX`, containing only the keys
actually retained before the session. It contains no bodies, invented keys, or
perfect seed records. The other family uses search-only discovery; assignments
are matched between arms within each profile. A key discovered through this index
can support direct full lookup. Search followed by full lookup is a different
route. Looking at the catalog, reading a search preview, and reading the complete
record are separate observations.

The rule requests `bd prime --no-memories` for workflow orientation, but no harness
hook forces it, forces recall, captures a record, or blocks completion. Hidden
artifact checks never become agent feedback or the next task's instructions.
This is close to an install-and-work experience: standing rules and skill
discovery introduce the capability, while normal issues supply the occasions.
The environment-variable catalog and legacy memory backend are experimental
integration surfaces, not proof of a finished product interface.

Issue adoption and memory adoption also have different opportunity structures.
The task explicitly names a work issue, so reading and closing that issue are
naturally salient. It does not name a memory. Memory use requires the agent to
recognize a durable decision or a dependency on earlier authority, decide that a
record is useful, and select the appropriate source. Raw command-count comparisons
between these workflows are diagnostic, not causal evidence that one instruction
format is better.

In the main cohort, 220/240 sessions successfully invoked issue `show`, 205/240
invoked `update`, and 204/240 invoked `close`. By comparison, 76/240 made a memory
write and 126/240 made some memory read. Those read counts include search and
same-session readback, not just useful prior knowledge. The richer semantic
audit, rather than this frequency comparison, establishes the 58 successful
prior-use legs.

## Hosts, qualification, and isolation

All ten model/host interfaces completed real isolated qualification calls with
actual primary-model evidence. Sixteen of twenty complete diagnostic workflows
passed. Haiku and Qwen's behavioral failures were retained instead of screening
out weaker models. These explicitly directed integration checks receive no
unprompted-adoption credit. Gemini and Copilot were excluded at the user's
direction.

The binaries were pinned after the requested updates: Claude Code 2.1.263,
Codex 0.153.4, OpenCode 1.18.20, zcode-app-cli 3.11.2-21 with runtime 0.16.5,
and Beads 1.2.1. The coverage table above must be read as exact CLI/model pairs.
Different models across hosts confound host and model effects. Within Codex,
reasoning effort is fixed to high; Claude uses host/model defaults. Qwen runs
locally through Ollama with a 32K context. These are not matched inference budgets
or a causal ranking of model strength. Worlds and discovery routes also vary
across profiles, while remaining matched within each profile's two guidance arms.
There is one lifecycle per profile/arm/family cell, not repeated estimates for
each setting. Sessions within a lifecycle depend on prior outputs, and cumulative
hidden cases repeat behavior across stages; those case counts are coverage, not
thousands of independent reliability trials.
Primary-model identity is distinguished from auxiliary model usage reported by a
host; a configured auxiliary model alone does not establish that it was invoked.

| Host        | Main sessions                                | Normal-memory check                                                         |
| ----------- | -------------------------------------------- | --------------------------------------------------------------------------- |
| Claude Code | Automatic memory disabled                    | Automatic memory enabled in fresh isolated storage                          |
| Codex       | Memory feature, generation, and use disabled | Installed feature-off default retained                                      |
| OpenCode    | No separate automatic extractor configured   | Same native behavior                                                        |
| zcode       | Memory feature and use disabled              | Normal headless settings; this runtime disables extraction in headless mode |

The four normal anchors are Astra, Sonnet, Qwen, and GLM. “Normal” means supported
headless behavior in a fresh project, without unrelated user instructions,
plugins, or existing native records. It is not a test of the user's accumulated
interactive environment. Settings and file creation alone do not prove native
memory participated. Existing authentication and global configuration are
preserved.

## What counts as success

The artifact grader checks all accumulated product behavior after every session,
including the support attachment at session 6. Passing inherited cases does not
prove new work happened, and a correct support attachment can coexist with other
wrong accumulated behavior. Those measures are reported separately.

Manual audits compare actual retained bodies with the approvals. Prose, structured
data, and complementary records can all be faithful. Exact identifiers, scope,
units, types, order, version, and necessary structure must survive; JSON is not
universally required. An incomplete note may still contain useful information
for a particular task, so applicability and completeness have separate scores.

This all-facts retention rubric is stricter than every potentially useful memory
design. A faithful source pointer followed by a correct source lookup can help
carry an agreement even when its body omits details. Such notes remain partial
under this frozen rubric, and their successful uses are reported separately.
Details absent from a note are not necessarily lost from the entire retained
project. A source-linked memory design deserves its own evaluation; it was not a
separate treatment here.

Eligible prior-use legs are sessions 2, 4, and 5. Successful use requires a full
applicable pre-existing record delivered to the model, correct subsequent work,
and trace evidence that the read preceded or informed that work. A newly written
record's readback is not prior reuse. When an earlier session already implemented
the requested behavior, a prior read can inform validation; it is distinguished
from pre-edit retrieval. Original sources remaining available prevent exclusive
causal attribution to memory.

The frozen strict intersection requires all six correct artifacts, faithful
initial capture, faithful current and historical agreements at sessions 3/5/6,
successful prior use on all three eligible legs, no unsupported alteration of
standing or historical agreements, and no duplicate curation in the supplied
control. A late first capture does not repair an initial omission. Unknown evidence
is not scored favorably. This strict outcome still does not certify every
surrounding sentence or complete adherence to every procedural instruction.

Source and verification claims are audited independently. A note can preserve the
right policy while overstating what a test proved. Aggregate-only assertions
cannot establish per-line allocation or which duplicate receipt was selected.
An engineering convention chosen by the agent is not automatically a fabricated
external approval, and a dated implementation snapshot is not automatically false
when later code changes.

The two family reviewers are unblinded agents involved in corpus development and
review, not independent human annotators. The finance reviewer authored that
corpus; the Courier reviewer independently cross-reviewed its construction.
They check saved outputs against independent domain oracles, inspect model-visible
traces and retained records, and preserve corrections in supplements. Root
aggregation cross-checks their artifact scores and recalculates the strict
intersection from its components.

## Completed first checkpoint

All 80 sessions in stages 1–2 were started and assessed once. The
[checkpoint review](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/phases/phase1/REVIEW.md)
records 59/80 correct artifacts and 1882/2340 passing hidden cases. Generic guidance
produced 2/20 faithful initial policy captures; occasions guidance produced 9/20.
All 11 complete governing records available at the first reuse were read before
editing and followed by correct work: five direct routes and six search-then-full
routes. Useful non-policy notes, partial records, late captures, and original-source
recovery are not counted as complete initial handoffs.

Fourteen Codex sessions reported quota errors, twelve before tool work and two
after work began; the latter two left passing artifacts. Both arms had seven
such sessions. These remain in planned denominators and are availability failures,
not voluntary memory decisions. Later scheduled calls succeeded, contradicting a
provisional shared-block assumption; the original markers and correction are
preserved. No failed trial was retried, replaced, or repurchased.

## Execution and observer limitations

Four workers and a 420-second deadline bound each session. Claude also has the
existing adapter's 30-turn limit and $1.50 CLI stopping threshold; the latter is
not a universal invoice cap. Turn exhaustion is separate from provider quota,
wall-clock timeout, and voluntary completion. Phases are reviewed against
their exact completed summary before continuation; no scored input is changed
during the run. Administrative before/after memory snapshots are two real reads
per assessed session and are separate from agent memory activity.

Reported costs are CLI-reported provider usage, not the user's total invoice.
Unknown Codex/GLM charges, local Qwen compute, and investigation/auditor-agent
compute remain unpriced. Qualification costs are separate from scored sessions.
Summed session durations are not elapsed wall time; the approximate CLI span uses
recorded launches plus durations and includes gaps between phases.

The main sessions reported **$42.8386088**, with dollar costs unavailable for
120/240 sessions. Their summed session duration was 25,296 seconds; the approximate
first-launch-to-last-completion span was 7,911 seconds. The twenty qualification
calls separately reported $1.88067045, with ten costs unavailable. All main slots
finished assessment, but only 223/240 had the frozen host-success flag: fourteen
quota reports, two turn-limit reports and the one observer exception below remain
separate from product correctness. There were no wall-clock timeouts or narrowly
classified infrastructure faults in the main cohort.

Codex's normalized aggregate tool output sometimes omits leading chunks that are
present in its retained model-facing rollout. Audits use that full evidence;
the rollout also preserves rejected invocations absent from normalized tool-call
lists. Frozen visibility counters remain lower bounds. Conversely, a full raw Beads
receipt does not certify full model delivery if the agent pipes it through
`head`, `grep`, or another truncating operation.

Some shell heredocs hit the throwaway sandbox's temporary-file restriction.
Agents often recovered with another supported write method. These execution
observations remain in the evidence; they are not new business agreements or
evidence that permanent tool-avoidance advice should be saved.

One Qwen finance session completed after OpenCode compaction, but the frozen
observer rejected a synthetic continuation message and events following a
completed step. All 34 actual assistant rows matched the requested Qwen model;
the unmatched message was explicitly marked as synthetic compaction continuation.
The original host-success flag remains false with an appended adjudication. This
is an observer limitation, not evidence of an unrequested model switch. No
adapter was changed or session rerun during the cohort.

## Failure classes and retained-information limits

| Class               | Observed evidence                                                                                                           | Implication                                                                                                       |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Discovery           | 66 rejected Beads invocations, including 42 whose first argument was `memory`                                               | Improve command discovery and evaluate unambiguous read aliases; these are attempts, not 66 distinct agents       |
| Capture omission    | Only 13/40 initial stores contained any record; 11 held a faithful policy and two held other findings                       | Initial retention is a major bottleneck; distinguish empty output from censored execution opportunity             |
| Information loss    | Partial or shorthand records omitted necessary operational details; one retained finance interpretation remained unverified | Check the complete agreement independently, while crediting useful partial and source-linked retrieval separately |
| Retrieval           | Both direct and search routes worked, but agents sometimes bypassed available notes or read the wrong version               | Actual delivery, applicability and timing matter more than a command acknowledgment                               |
| Application         | Sonnet preserved and reused a false identity rule; Haiku treated inherited code as approval                                 | Storage and code agreement cannot certify authority                                                               |
| Historical mutation | One main lifecycle acquired unsupported standing/history claims; later correction was incomplete                            | Preserve provenance and distinguish a permanent revision from historical reproduction                             |
| Unnecessary work    | No duplicate capture in 40 supplied controls, but extra catalogs, reads, help attempts and commentary rewrites remained     | Zero duplicate writes does not mean zero memory overhead                                                          |

The controls yielded 37/40 correct support attachments. They were checked
independently of accumulated product behavior. The only control that changed its
memory store was Fable's generic finance session: it saved a newly discovered
public-test fixture mechanism. That was a real reusable finding, not another copy
of the supplied policy. However, the note generalized one case-specific approval
into a wider support-file convention and attributed that convention to the issue.
This is an unsupported advice/provenance concern even though its standing and
historical business agreements remained faithful. Thus **11/40 strict core
successes do not mean 11 lifecycles with every saved sentence certified**.
Thirty of the 40 main controls began with some retained record; ten stores were
empty. Zero observed duplicates therefore does not represent 40 repeated
opportunities to avoid copying an existing agreement.

Other audits found premature test-success wording later made true by actual
correction, ambiguous scope in a historical verification paragraph, partial
`head`/`grep` readbacks, and an unsupported final claim that a test file had run
tests when direct execution ran zero. These differ from a false governing policy,
but they prevent a broad claim of faithful retained prose or full procedural
compliance. Readback can verify storage; only comparison with actual approval
and execution evidence can verify those claims.

Qwen's failures included incorrect work as well as missing memories. In one
finance task it fitted a public example with division by seven and invented an
old cap; 19/70 hidden cases passed. Later context compaction repeated the invented
cap within that session. This was not cross-session Beads capture. Literal
tool-call-looking text without an executed tool call also occurred. These results
do not isolate OpenCode as the cause: the host and this local model were tested
together, with one 32K runtime context condition.

### Storage and retrieval can work while the authority check fails

Sonnet's occasions Courier session 2 invented account-local delivery identity
although the provider's available protocol-1 agreement required global identity.
It implemented the wrong scope, saved it, and read it back. In session 3, it read
that complete prior body before editing and retained the same wrong historical
scope. It then expanded the note into a claim that identity was unchanged across
versions and that the new approval changed only acceptance timing. The actual
revision reversed identity scope as well. The original provider document and
older issues remained available but were not read in that session.

This is observed inheritance and reinforcement of an unsupported agreement, not
merely a wrong note surviving in storage. Existing code contained the same error,
so exclusive causation by memory is not established. Independent artifact checks
rejected the historical behavior even though the code and note agreed. The
[session-3 audit](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/audits/webhooks-phase2-dtp3je6j/claude-sonnet-webhooks-occasions-isolated-3.json)
records the actual read, edits, source omissions, and expanded false provenance.
This is a domain-policy failure; it is not evidence that we observed inherited
tool-avoidance advice.

At session 5, Sonnet finally reread the original provider contract and corrected
historical accepted receipts to global identity. Historical summaries still used
the wrong account-local identity. The rewritten memory included correct versioned
rules but retained a contradictory unchanged-identity heading and mislabeled an
old issue's provenance. The subsequent support attachment was correct while all
13 historical-summary failures persisted. This was a partial recovery, not an
unchanged wrong note and not a repaired lifecycle.

### A direct lookup supplied a real information gap

Astra's generic finance session 4 read the actual key catalog and then the full
standing record before adding itemized statements. The previous aggregate code
and README retained rates and caps but not the current per-line allocation
priority. The memory supplied largest-charge-first and line-ID ordering; the
agent did not reopen the original approval. All 70 hidden cases passed, and new
tests actually asserted line-level allocation. Original issues remained another
possible source, so this is trace-supported useful direct retrieval, not proof
that no other route could succeed. Its initial capture omission still makes this
lifecycle fail the strict initial-to-final handoff criterion. See the
[source and trace audit](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/audits/finance-phase2-4vuoff9t/codex-astra-finance-generic-isolated-4.audit.json).

### Code and public examples can be mistaken for the agreement

Haiku's occasions finance session 5 did not reopen the original approval. It
treated inherited code as the historical agreement and called the approved
shared cap a per-line cap. Empty and single-line public examples passed, but only
70/83 cumulative hidden cases passed. This was an application and authority
failure with no keyed capture, rather than a failed attempt to retrieve a stored
record. The fully supplied support attachment subsequently passed its own check,
while historical product behavior remained wrong.

## Practitioner input and proposed improvements

The [research memo](research/memory-policy-handoff-spinal-tap-2026-09-07.md)
records the design influences. Human implementation-intention research motivated
observable workflow occasions, without assuming its results transfer to LLMs.
[Gollwitzer, 1999](https://bpb-us-e1.wpmucdn.com/wp.nyu.edu/dist/c/6235/files/2019/02/gollwitzer-1999-implementation-intentions.pdf).
Decision records motivated explicit status, rationale, and preserved history.
[Nygard's ADR proposal](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
MemoryArena motivated checking dependencies across interactions; its built-in
retrieval/update loop is not evidence of voluntary adoption from standing rules.
[MemoryArena, section 3](https://arxiv.org/html/2602.16313v1).

Atbrace's account of a 150,000-plus transcript collection, tool adoption, shared
CLI conventions, readable JSON answers, a tool catalog, and a feedback switch is
an attributed practitioner observation. Those scale and adoption claims were not
independently verified here. His account supports an improvement method worth
adopting: inspect actual work and departures from the intended path, classify
failures, try a bounded change, and judge correct subsequent work. It does not
prove a specific memory interface.

Our receipts contain actual attempted memory-command spellings and rejected
arguments. They are evidence for improving discovery and considering compatible
read aliases. Ambiguous or invented write semantics should not automatically
become permanent API surface. Separate agent and human interfaces should earn
their complexity by improving actual work.

Remembered tool avoidance is a hypothesis for future transcript and memory
investigation, not an observed result of this cohort. Workaround advice should
carry the tool version, circumstances, and supporting evidence so that later
agents can reassess it. A transient sandbox failure does not by itself justify
a permanent avoidance policy.

## Ranked improvements and the simplest supported procedure

1. **Use the tested occasions package as a pilot baseline.** Introduce memory
   alongside issue work in `AGENTS.md`, host pointers and the shared Beads skill.
   Say what durable knowledge is for and when it should be captured or consulted.
   Keep ordinary task descriptions free of memory reminders. This is the smallest
   tested change with better observed capture and reuse, although it is not a
   demonstrated improvement in overall code correctness or a guarantee across
   the tested models.
2. **Make the authority and version easy to inspect.** Keep a readable preview
   alongside the faithful record, preserving exact identifiers, scope, types,
   units, order and historical status where later context cannot supply them.
   Separate approved policy from implementation summaries, test claims and
   inferred conventions. Compare disagreements with the approval source; do not
   treat agreement between code and memory, or a successful readback, as proof.
   These safeguards were already requested by the successful package but were
   not followed consistently. A compact source-linked or snapshotted approval
   record is a promising further design, not a separately validated treatment.
3. **Resolve the first-capture occasion without demanding duplicate documents.**
   Newly approved knowledge should be retained before task completion. For an
   already durable project agreement, explicitly deciding whether to index or
   link it could avoid both omission from discovery and copying it into several
   mutable authorities. That indexing/backfill occasion needs another bounded
   test; the current result does not prove mandatory duplicate prose helps.
4. **Keep reproduction cheap.** Retrieve a full applicable record when prior
   authority is needed: use an actual known key directly, otherwise search and
   then read the complete result. A fully supplied reproduction, new consumer,
   or historical example is not by itself a reason to save again or rewrite
   history. Preserve a genuinely new reusable finding if one occurs, without
   promoting a one-off instruction into a project-wide rule. The zero-duplicate
   controls support this distinction, while their extra reads show room to
   reduce unnecessary work.
5. **Use transcripts and feedback to improve the interface.** Classify discovery,
   omission, information loss, retrieval, application, mutation and unnecessary
   work separately. Review attempted commands and validated complaints before
   adding aliases or separate human/agent surfaces. Judge changes by faithful
   retained information and correct later work. Adoption counts are diagnostics.

The simplest procedure supported by the successful examples is: **before changing
behavior governed by an earlier agreement, inspect the applicable record and its
authority; before closing newly approved durable work, preserve a faithful,
versioned handoff; for revisions, retain the old agreement as history; for a
reproduction, use the right version without creating another agreement.** Keep
that procedure in the standing deployment, not in each task prompt.

The next validation should test a capable model through OpenCode to separate its
host from the Qwen result, then replicate on more ordinary projects with genuinely
new decisions and already documented agreements. Source-linked retention,
interactive native memory, concurrent revisions and the proposed Memory bead
type each remain distinct untested changes. They were not added to this frozen
run. No deterministic completion guard is justified as a correctness certificate:
earlier experiments already showed that a guard can accept a wrong artifact and
a wrong memory that agree with each other.

## Verification and evidence

The [verification record](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-verification-01/SUMMARY.md)
preserves corpus/oracle agreement, 34 rejected deliberate mutants, adapter and
package checks, static checks, and the broader repository test outcomes. The
full Python run had 4814 passes, 44 skips, 27 failures, and 12 errors, with the
reported failures in unchanged environment-dependent tests. Root TypeScript
checks passed all 908 tests with Git configuration isolated per process; the
default invocation exposed the existing global URL-rewrite interaction. No
global configuration or safety boundary was weakened to obtain those results.

The final integrity audit checked all 264 results, exact task-only prompts,
frozen issue descriptions, unchanged guidance, actual-key catalogs, exact memory
carry-forward and execution ancestry. All 442 source hashes, seven binary hashes
and four profile hashes matched. No duplicate host session IDs were found.
There were 528 administrative memory snapshot reads, separate from agent work.
The owned local model server exited with its phase; existing server settings and
user configuration were preserved. The pre-run plan remains frozen rather than
being rewritten to match outcomes.

The evidence can be followed from these entry points:

- [Mechanical results and all 264 slots](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/final/mechanical.json),
  [integrity audit](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/final/integrity.json),
  [workflow counts](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/final/workflow-counts.json), and
  [rejected command attempts](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/final/command-feedback.json).
- [Combined semantic components](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/final/semantic.json),
  with main and normal modes separate and source hashes for every lifecycle;
  aggregation independently rechecks all 264 artifact flags and every strict
  intersection against its component judgments.
- [Main finance audit](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/audits/finance-phase2-4vuoff9t/PHASE2-FINAL-1788817181805661000.md)
  and [Courier audit index](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/audits/webhooks-phase2-dtp3je6j/AUDIT-INDEX-FINAL.json),
  which retain detailed source, delivery, timing, provenance and correction records.
- [Normal semantic audit](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/audits/finance-normal-dc9klsr0/normal-final-1788818087242974000.json)
  and [independent native-memory audit](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/audits/webhooks-phase2-dtp3je6j/normal-native-memory-final-1788818086124610000.json).
- [Qualification admission](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-qualification-01/qualification-admission.md),
  [main conclusion review](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/audits/webhooks-phase2-dtp3je6j/main-conclusions-review-1788817554468960000.json),
  and the [recorded critique feedback](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-01/audits/spinal-tap-feedback-2026-09-07.md).

These small synthetic lifecycles do not establish production reliability,
long-horizon retention, concurrent revision behavior, resistance to inherited
obsolete advice, or reliability of the proposed Memory bead type. Successful
examples establish feasibility within the tested deployment, not “bulletproof”
behavior across coding agents.
