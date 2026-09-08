# Memory guidance through prime or startup: results

Execution and semantic auditing are finished: **196 of 216 planned sessions were
assessed, with 120 correct artifacts and one strict handoff across 36 planned
lifecycles**. Twenty sessions were left unassessed under the frozen stop rules;
another twenty assessed sessions had provider denials without model generation.
No claimed session was rerun or replaced.

**More prominent delivery of the same instructions did not establish reliable
memory handoffs.** Each arm produced three complete initial captures. Successful
capture and both retrieval routes occurred during ordinary issue work in several
profiles, but OpenCode/Qwen and Claude/Haiku produced no complete initial captures
or successful prior-memory uses. Other profiles also omitted captures, lost required details,
missed existing notes through search, and sometimes changed unsupported policy or
provenance. The experiment does not establish a winning delivery surface.

The sole strict success was GLM's startup-briefing Finance lifecycle. Its thin and
rich Finance lifecycles did not finish after a timeout triggered the profile stop
rule. **That unmatched success cannot establish a startup advantage.** This tests
delivery of memory instructions, not prime selecting project-relevant memory
headers or bodies, and not the proposed new Memory bead type.

## Final outcomes

| Delivery         | Correct artifacts / assessed | Complete initial captures / assessed opportunities | Preparatory routed uses / planned legs | Uses with complete faithful entries | Strict handoffs / planned lifecycles |
| ---------------- | ---------------------------: | -------------------------------------------------: | -------------------------------------: | ----------------------------------: | -----------------------------------: |
| Thin prime       |                        39/62 |                                               3/11 |                                  12/36 |                                   9 |                                 0/12 |
| Rich prime       |                        38/64 |                                               3/11 |                                   9/36 |                                   6 |                                 0/12 |
| Startup briefing |                        43/70 |                                               3/12 |                                  12/36 |                                   8 |                                 1/12 |
| All              |                      120/196 |                                               9/34 |                                 33/108 |                                  23 |                                 1/36 |

Each arm planned 72 sessions and 12 initial captures. Thirty-one lifecycles have
six assessments; 26 have model work in all six sessions. Twelve lifecycles have
all six artifacts correct. Only one meets the intersection of correct work,
faithful initial/current/historical retention, all three preparatory prior-use
legs, no unsupported agreement mutation and no duplicate control capture. The
secondary informed-use interpretation and the stricter sensitivity excluding
flagged saved claims both leave that count at one. Neither certifies every
completion-message claim or every procedure step.

Initial capture was **9 complete, 2 incomplete and 23 absent** among 34 assessed
opportunities. After permanent revision, 7/33 assessed lifecycles retained the
complete current and historical agreement; after historical work and the supplied
control, that was 8/31 at each checkpoint. Later source recovery and correction
do not retroactively repair a failed initial handoff. Complete records can span
explicitly scoped notes; individual historical keys sometimes remain incomplete.

The 33 successful preparatory uses comprise **16 direct lookups and 17 searches
followed by full lookup**. Ten used only partial applicable knowledge, including
current-regression or version-support information while authoritative sources
supplied the historical agreement. Those ten are not full-agreement retrievals.
Of 108 planned legs, 98 were assessed and 88 had model work. Under the declared
broad applicability rubric, 38 of those 88 began with an applicable prior entry
and 33 used it successfully; 26 began with a complete faithful required entry and
23 used it successfully. This conditional performance does not remove the missing
and incomplete captures from the end-to-end denominator.

No duplicate capture occurred in **26 controls with model work**. Thirteen had an
existing record available to duplicate and thirteen entered with an empty store.
Six controls nevertheless performed unnecessary memory discovery or reads.
Support attachments were correct in 25/26 controls with model work, while only
13/26 had correct accumulated product behavior. Across all planned controls,
25/36 attachments were correct, five were assessed after provider denial and five
were unassessed. Zero duplication does not mean zero unnecessary work or correct
implementation.

Independent semantic review found unsupported standing/historical agreement
mutation in three lifecycles and flagged saved provenance or commentary in nine.
The latter includes repeated observations of inherited claims; the 37 detailed
findings are not 37 independent incidents. Metadata ambiguities and unsupported
final-response-only claims remain separately annotated. In particular, a Pacific
date and a UTC issue-creation date are not treated as a proved contradiction.

The [mechanical summary](../memory-bench/results/memory-routes/2026-09-07-prime-delivery-verification-01/final-mechanical.json),
[semantic summary](../memory-bench/results/memory-routes/2026-09-07-prime-delivery-verification-01/final-semantic-corrected.json),
and [conditional denominators](../memory-bench/results/memory-routes/2026-09-07-prime-delivery-verification-01/final-behavior-denominators-corrected.json)
bind these figures to original results and independent audits. Hidden checks
passed 13,134/15,554 assessed cases; 17,298 cases were planned. These accumulated
cases and successive sessions are correlated, not independent reliability trials.

## CLI and model outcomes

| CLI / pinned primary model                   | Assessed / planned | Sessions with model work | Correct artifacts / assessed | Complete initial captures / assessed | Prior uses (complete-entry subset) | Strict handoffs / planned |
| -------------------------------------------- | -----------------: | -----------------------: | ---------------------------: | -----------------------------------: | ---------------------------------: | ------------------------: |
| Codex / `gpt-6-astra`                        |              34/36 |                       14 |                        14/34 |                                  6/6 |                              7 (7) |                       0/6 |
| Codex / `gpt-5.6-luna`                       |              30/36 |                       30 |                        29/30 |                                  0/5 |                              5 (2) |                       0/6 |
| Claude / `claude-sonnet-5`                   |              30/36 |                       30 |                        25/30 |                                  0/5 |                              9 (3) |                       0/6 |
| Claude / `claude-haiku-4-5-20251001`         |              36/36 |                       36 |                        14/36 |                                  0/6 |                              0 (0) |                       0/6 |
| OpenCode / `ollama/qwen3-coder:30b-a3b-q8_0` |              36/36 |                       36 |                         8/36 |                                  0/6 |                              0 (0) |                       0/6 |
| zcode / `zai/glm-5.3`                        |              30/36 |                       30 |                        30/30 |                                  3/6 |                            12 (11) |                       1/6 |

Each profile planned 18 eligible prior-use legs. Astra's twenty rejected turns
are not twenty observed decisions to ignore memory. GLM's 30 correct artifacts
include the timeout session, whose actual retained implementation passed 70/70
checks. Correct artifacts did not prevent its documented Courier policy mutation
or prove the timed-out CLI session completed normally. Sonnet captured faithful
knowledge later despite no complete initial captures. Haiku and Qwen also had
ordinary application failures, including tasks where policy was fully supplied.

These are particular host/model combinations. Different models, local inference,
limits and helper behavior prevent attribution to the host alone. Sol, Terra,
Opus and Fable were in the preceding investigation, not this bounded six-profile
comparison. Gemini and Copilot remain outside the requested four-host scope.

## Delivery, cost and practical conclusion

| Observation                              | Thin prime | Rich prime | Startup briefing |
| ---------------------------------------- | ---------: | ---------: | ---------------: |
| Assessed sessions                        |         62 |         64 |               70 |
| Verified full CLI prime output           |         33 |         32 |               52 |
| Verified full memory-reference file read |         30 |         14 |               25 |
| Complete briefing supplied at startup    |          0 |          0 |               70 |

Only the rich arm's prime output contains the full procedure; the other prime
outputs are pointers. Startup content was exactly echoed in retained host records
for 46/70 submissions; missing echo is unverified, not proof of absent delivery.
Submission or echo is not understanding or generation. Some sessions read both
prime and the reference; counts are not additive. Full-output matching is bounded
to observed formats and checked against raw traces. Across the run, fourteen
Haiku sessions invoked the native Beads skill with prime arguments without
executing the CLI command; a Sonnet session invoked both. Four Qwen sessions emitted only
textual tool-call imitations, so model output existed without executed work.

The ancestry audit counted 1,235 actual Beads executions, including 50 failures
and zero unknown ancestors. Unavailable namespaces and invented flags, plus four
empty-body saves, supply concrete interface feedback. There were 118 successful
prime calls and 117 sessions with full output; one rich-prime invocation was
truncated. All 118 actual prime executions passed `--no-memories`; their entire
receipt outputs exactly matched the intended thin or rich instructions, with no
appended memory bodies. The custom override alone is not claimed to suppress
memory injection. These counts diagnose exposure and friction, not successful handoffs.

Reported scored usage totals **$10.5592762**: Sonnet $7.1070418 and Haiku
$3.4522344. Ninety-four assessed sessions lack dollar receipts; Qwen reports zero
provider dollars but local compute is unpriced. Qualification adds $0.2510229,
with six sessions lacking dollar receipts. These are reported CLI costs, not a
complete invoice or the cost of investigator auditing. Arm costs cannot identify
prompt efficiency given different completed coverage and provider censoring.

The evidence supports retaining a shared procedure, exact commands and issue
references as useful workflow components. It does **not** support deploying a
larger prime/startup prompt as the reliability fix. The smallest next changes are
to clarify first introduction of reusable approval, improve failed-search
handling, verify captured facts against their source, and restrain later curation.
The ranked proposals below are not yet validated fixes. Relevant memory-header
selection at prime remains a separate, untested intervention.

## Completed first-phase checkpoint

The 68 assessable initial/reuse sessions are complete: 58 correct artifacts and
1,891/1,989 accumulated hidden checks. Four of the 72 planned first-phase slots
remain infrastructure-censored. All 68 have independent semantic audits and
unchanged actual-record carry-forward checks. No completed six-stage lifecycle
verdict is available at this checkpoint.

| Delivery         | Correct artifacts / assessed sessions | Faithful initial captures / assessed opportunities | Preparatory routed uses / assessed opportunities | Uses with complete faithful entries |
| ---------------- | ------------------------------------- | -------------------------------------------------- | ------------------------------------------------ | ----------------------------------- |
| Thin prime       | 19/22                                 | 3/11                                               | 4/11                                             | 3                                   |
| Rich prime       | 18/22                                 | 3/11                                               | 4/11                                             | 3                                   |
| Startup briefing | 21/24                                 | 3/12                                               | 3/12                                             | 3                                   |

Each arm planned 24 first-phase sessions and 12 initial/use opportunities. The
thin and rich arms each have two censored sessions from one missing lifecycle.
Across assessed initial sessions, nine retained a complete agreement, two retained
incomplete notes, and 23 retained nothing. The eleven successful prior-use legs
include four direct lookups and seven search-then-recall paths; two used partial
notes and needed other sources for the full agreement. A direct lookup can follow
an agent-authored issue reference even in the search-only catalog deployment.

All three delivery conditions produced the same count of complete initial
captures and complete-entry uses. This is a small checkpoint comparison, not
evidence of equivalent production reliability. Reported scored usage so far is
$3.1153868, with 34 sessions lacking dollar receipts and local compute unpriced;
qualification costs are separate. The
[mechanical](../memory-bench/results/memory-routes/2026-09-07-prime-delivery-verification-01/phase1-mechanical.json),
[semantic](../memory-bench/results/memory-routes/2026-09-07-prime-delivery-verification-01/phase1-semantic.json),
and [integrity](../memory-bench/results/memory-routes/2026-09-07-prime-delivery-verification-01/phase1-integrity.json)
records preserve these denominators and the known raw Codex configuration
deviation. The second phase carries all actual records forward without repairs.

The phase-one workflow audit found 47 successful prime executions, with full
output verified in 46 sessions. Only 13 of 22 assessed rich-prime sessions
received its full CLI output; one additional invocation truncated it. The
startup briefing was submitted in all 24 assessed startup sessions. Thin-prime
output and reads of the separately installed procedure are tracked separately.
Thus the rich arm tests a command agents must choose to execute and read; it does
not guarantee exposure merely by installing the file. Six Haiku sessions
substituted a native skill invocation for that command.

Phase 2 subsequently encountered nineteen Codex usage-limit rejections and one
revoked-refresh-token rejection without model work. Astra then stopped on missing
file-backed authentication before a new session launched, leaving that claim and
its dependent session unassessed. Finally, GLM's rich-prime Finance stage 4 timed
out; the missing terminal identity triggered the frozen infrastructure stop rule,
leaving six later sessions unrun. Those events and the original twelve censored
slots account for the final twenty unassessed slots. Provider-denied turns are
assessed from their actual retained files without assigning voluntary behavior.

## Question and comparison

Does the existing memory procedure produce more complete handoffs when agents
receive it through `bd prime`, or directly in a common startup briefing? The
[frozen design](plans/0007-memory-prime-delivery.md) and
[user-facing description](../docs/adoption-harness/MEMORY-PRIME-DELIVERY.md)
describe the same experiment. The preceding
[policy-handoff report](memory-policy-handoff-results-2026-09-07.md) supplies
context; its completed trials are not pooled into this comparison.

Every condition installs project `AGENTS.md`, host instruction pointers, the
Beads skill, and its occasions-based memory reference. The three arms differ in
how they present that standing guidance:

| Arm              | Prime output               | Initial user message                              |
| ---------------- | -------------------------- | ------------------------------------------------- |
| Thin prime       | Pointer to rules and skill | `Work on <actual issue ID>.`                      |
| Rich prime       | Complete common briefing   | `Work on <actual issue ID>.`                      |
| Startup briefing | Same thin pointer          | Common briefing, then the separately labeled task |

The 4,206-byte briefing combines existing issue rules, the complete memory
procedure, and the catalog rule. It is identical across tasks and byte-identical
between rich prime and startup. The startup arm deliberately changes the full
user message. It adds no task-specific memory key, capture reminder, policy fact,
or hidden answer. Receiving it is a delivery intervention, not a test of natural
prime discovery. Role, position, repetition, output visibility, and added context
remain properties of these packages rather than independently tested mechanisms.

Prime provides workflow guidance; `bd ready` discovers tasks and `bd show` reads
their details. The legacy implementation uses `.beads/PRIME.md` and
`bd prime --no-memories`. No saved memory body is injected automatically. This
simulates the instructional part of
[Memory Beads proposal R8/R31](https://github.com/gastownhall/beads/issues/5877),
not the proposed Memory type, canonical identities, immutable revisions, shared
history, or automatic selection of relevant memory headers or bodies.

## Ordinary tasks and retained information

Two projects each supply six ordinary coding tasks in fresh sessions: a narrow
initial capability under a complete agreement; multi-entity use; a permanent
revision; detailed current output; historical output; and fully supplied one-off
support reproduction. Independent checks grade accumulated behavior after each
stage and the support attachment separately. The original narrow implementation
and public examples do not reveal every policy boundary later tasks require.

All actual code, documents, issues, and memories carry forward, including wrong
implementation, incomplete notes, and missing captures. Legitimate approval
sources remain available. A correct implementation recovered from those sources
counts as correct work, but does not establish memory use or exclusive memory
causality. The Courier project's first agreement already exists in a vendor
document; failure to create an initial keyed note is not automatically
disobedience of a rule about newly introduced knowledge.

The indexed deployment exposes only keys actually present before the session.
The search-only deployment provides no index. A record key written by an agent
into issue completion context remains a legitimate direct-lookup reference.
Administrative before/after reads and setup prime calls are investigator work,
not voluntary agent retrieval.

## Coverage and isolation

The planned schedule contains 216 sessions: six profiles × three arms × two
projects × six stages. That is 36 lifecycles, 12 per arm, and 108 eligible prior-use
legs. Each cell has one lifecycle. The six possible arm orders are
counterbalanced across profiles; family order alternates. Each profile retains
the preceding study's project world and catalog assignment across all arms.

| Host        | Primary model                                  | Native-memory condition                                                                                         |
| ----------- | ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Codex       | `gpt-6-astra`, `gpt-5.6-luna`                  | Automatic memory generation and use disabled; isolated `CODEX_HOME`; fixed high effort and default service tier |
| Claude Code | `claude-sonnet-5`, `claude-haiku-4-5-20251001` | Automatic memory disabled; fresh directory; project rules and skills enabled                                    |
| OpenCode    | `ollama/qwen3-coder:30b-a3b-q8_0`              | No separate automatic extractor configured; isolated local runtime and project state                            |
| zcode       | `zai/glm-5.3`                                  | Native memory feature/use disabled; headless extraction disabled                                                |

The executables retain the
[verified versions](../memory-bench/results/memory-routes/2026-09-07-policy-handoff-verification-01/versions.json):
Claude Code 2.1.263, Codex 0.153.4, OpenCode 1.18.20, zcode-app-cli 3.11.2-21
with runtime 0.16.5, and legacy `bd` 1.2.1. Their frozen binary hashes are checked
throughout execution. Installed executables alone did not qualify these hosts;
the real authenticated delivery sessions did.

Existing authentication is used only through the qualified isolated adapters.
User plugins, global instructions, and unrelated project state are excluded.
Actual primary model identity is checked in host receipts. Codex disables
multi-agent delegation; OpenCode's small-model setting matches its primary;
Claude helper usage and zcode's retained GLM lite profile require separate actual
usage inspection. A primary-model pin alone does not identify every helper call.

The final audit found Sonnet receipts with Haiku helper usage, already included
in the reported cost. Four OpenCode Explore children performed 52 tools under
the same pinned Qwen. Parent usage totals 8,842,593 input and 115,547 output
tokens; children add 388,534 and 5,946 separately. Compaction usage is included in
the parent total; automatic title-helper usage remains unobserved. These are
accumulated workload counters, not directly comparable tokenizer units or a
causal estimate of guidance overhead.

One Qwen session retained a false `host_success` verdict because the frozen
observer rejected normal intermediate compaction and treated a synthetic user
continuation as a missing assistant model. Raw stream/database evidence verifies
the actual pinned assistant models and a generic continuation without a memory
cue. The original false verdict and incorrect 92/161 artifact remain unchanged.
Haiku reached its configured turn limit once. GLM's deadline failure has real
generated work and a correct artifact, but no terminal receipt; its partial
native request usage is not substituted for a full-session total.

All 64 assessed Codex native databases had zero extraction and job rows. The
580 current-session zcode model-I/O records showed GLM 5.3/main and no observed
lite model; runtime files alone do not establish native-memory participation.
The [final workflow audit](../memory-bench/results/memory-routes/2026-09-07-prime-delivery-01/audits/workflow-2alw5dw6/final-workflow-review-1788832361529065000.md)
preserves actual generation, helper usage, missing observations, instruction
exposure and native settings separately from semantic success.

Four workers execute each profile sequentially. Sessions retain the 420-second
deadline; Claude retains 30 turns and a $1.50 stopping threshold, which is not an
invoice cap. Other hosts do not enforce that dollar threshold. This comparison
adds no normal-memory sweep: the earlier study's 24 normal-condition sessions
remain separate evidence with their documented limits.

## What counts as success

Independent semantic review checks faithful initial capture, current and
historical retention, applicability, exact full reads, timing, unsupported saved
claims, historical mutation, and duplicate curation. Exact identifiers, scope,
units, types, structure, and exceptions matter when a later agent cannot recover
them from the implementation. Faithful prose is acceptable; JSON is not required
for every kind of knowledge.

The primary prior-use score requires a full applicable existing record through
direct `bd recall`, or search followed by recall, before a behavior edit or
genuinely subsequent validation, followed by correct accumulated work. A
same-session save/readback is not prior use. A confirmation only after tests is a
separate secondary measure. Legacy bulk output can expose complete information
without meeting either tested route; it is reported separately.

Strict core success requires all six correct artifacts, faithful initial and
retained current/history records, all three primary prior-use legs, no unsupported
standing/history mutation, and no duplicate capture during supplied reproduction.
The component scores remain visible. Even this intersection does not certify
every sentence of saved prose or every provenance claim.

In the inherited rubric, the mutation criterion concerns standing or historical
agreements. Unsupported verification commentary is still flagged separately
even when the business agreement survives faithfully. Report a stricter
sensitivity requiring no flagged saved claims alongside the frozen core score;
do not silently change the primary criterion after seeing outcomes. A GLM
consumer-session rewrite illustrates the distinction: its policy remained
correct, but it claimed coverage of per-line ordering from tests that asserted
only aggregate totals.

Startup submission, a matching actual host user-message record, untruncated rich
prime output, and a full procedure file read are separate observations. Native
skill invocation with `prime` as an argument is not a CLI prime execution.
Command counts are diagnostics, not success scores.

For supplied reproduction, report the support attachment separately from the
accumulated product. A correct attachment can coexist with older product errors.
Also report whether an existing memory was available to duplicate: doing no
curation with an empty store is weaker evidence of duplicate avoidance. An agent
can perform unnecessary searches and readbacks without creating a duplicate.

Execution-ancestry receipts include descendant `bd` calls. Normalized parent
streams can omit earlier outputs from Codex multi-command calls and tools run
by OpenCode children. Raw rollouts and read-only exports of the isolated host's
parent and descendant sessions supplement those streams. Child model and usage
receipts are inspected separately; parent-only usage can omit delegated work.

## Verification and operational deviations

All twelve explicit delivery qualifications passed across the six profiles.
Actual scratch prime output matched the intended briefing and excluded sentinel
memory bodies. These deliberately explicit checks establish working interfaces,
not voluntary adoption. Qualification reported $0.2510229, with six sessions
lacking dollar receipts and local compute unpriced.

The original manifest freezes 450 source inputs, seven executable hashes, four
profile hashes, briefing text, and all 216 slots. Initial verification recorded
76 passing targeted/shared tests plus Ruff, Black, and strict mypy. The reusable
runtime, grading, and original manifest remain unchanged.

A supervisor stdout-pipe failure interrupted the original phase. Six results
survived; one completed Astra turn was assessed from its original transcript and
artifacts without inference, with OS exit unknown and the infrastructure fault
explicit. Two slots had been claimed before launch. They and their dependent
stages are never restarted: twelve planned sessions remain censored.

The first continuation used detached execution with stdout/stderr directly to an
exclusive regular file. It stopped at 28 assessed sessions because the live
Codex TOML file changed bytes. Independent review established that the frozen
adapter replaces both settings it reads and ignores the remaining configuration.
The second continuation checks those effective conditions while recording raw
hash changes; all other frozen checks remain exact. The old text delta and writer
are unknown. Neither continuation restored or edited user configuration.

Both deviations, original failures, prior results, independent reviews, and
continuation plans remain in the
[cohort evidence](../memory-bench/results/memory-routes/2026-09-07-prime-delivery-01/).
The [terminal phase summary](../memory-bench/results/memory-routes/2026-09-07-prime-delivery-01/recovery-02/phase2/summary.json)
records `stopped_with_new_fault`: 128 second-phase assessments, 196 overall, and
no shared-input fault. The original continuation ceiling was 204; the later
authentication and timeout stops left 196. The supervisor and read-only watcher
have exited. No profile override or replacement run was performed.

Primary reporting retains all planned denominators. The predeclared subset
excluding the two originally censored profile/project cells has 172/180 assessed
sessions, 27/30 fully assessed lifecycles and one strict success. Excluding the
recovered Astra/Finance cell as well leaves 154/162 sessions, 24/27 fully assessed
lifecycles and the same success. Neither subset finished as a complete matched
comparison after the later failures; neither replaces the missing observations.

Final read-only checks verified all 450 source hashes, seven executable hashes,
196 exact memory carry-forwards, 264 preceding-study results and 68 protected
first-phase results. The only raw profile mismatch remains the reviewed Codex
configuration change. The [integrity report](../memory-bench/results/memory-routes/2026-09-07-prime-delivery-verification-01/final-integrity.json)
and [preservation check](../memory-bench/results/memory-routes/2026-09-07-prime-delivery-verification-01/final-preservation-corrected.json)
retain the evidence. An initial preservation report used slot IDs as file paths;
its false missing-path findings are preserved alongside the corrected,
manifest-resolved check. No underlying result changed.

Session and cumulative-case observations are correlated. This small synthetic
sample cannot establish production reliability, an isolated host effect, or a
bulletproof procedure.

The stores are small synthetic lifecycle histories. This run does not test a
large memory corpus, ranking among many near-matches, long delays, concurrent
writers, source deletion, or stale cross-project advice. It tests delivery of
standing instructions, not prime's automatic selection of relevant memory
headers or bodies. Strong performance here would still need those separate
production checks.

## Observed mechanisms to retain in the final interpretation

These examples concern completed individual sessions; they do not rank the arms.

- **Faithful capture and selective use can happen during ordinary issue work.**
  Astra's finance initial sessions saved the complete approved agreement in each
  delivery condition, including rules beyond the narrow implementation. Its
  subsequent finance sessions read that prior record before editing and passed
  all 30 accumulated checks. Astra's Courier thin-prime sequence also searched,
  recalled the full prior agreement, and implemented the reuse task correctly.
  Original approvals were consulted too, so this is observed memory use without
  exclusive-memory causal attribution. GLM's Finance thin-prime reuse followed a
  key from actual issue-completion context and directly recalled it even in the
  search-only catalog deployment. Agent-authored references can therefore connect
  ordinary issue work to later direct lookup without an experiment-authored cue.
- **The capture occasion can be interpreted too narrowly.** Sonnet's initial
  finance thin-prime session said there were “no durable policy decisions beyond
  what's already specified in the issue, so no new memory is needed.” It had
  received thin prime but had not opened the detailed memory procedure. In the
  next session it read that procedure, searched an empty store, recovered the
  original approval, implemented correctly, and saved a faithful note. That is
  useful subject-driven late capture; it does not retroactively satisfy initial
  capture or prior-memory use. Sonnet's startup initial session also explicitly
  declined capture, describing the first implementation as a one-off feature of
  an already specified agreement. It searched the empty memory store and had the
  complete procedure supplied in its startup input. Thus the ambiguity also appears when the detailed
  guidance is supplied; delivery alone does not explain it.
- **Readback can faithfully preserve a wrong decision.** Sonnet's startup
  finance reuse session searched an empty store but did not find the original
  closed approval issue. It inferred a policy, implemented it, and saved that
  inference. Both code and note rounded grouped charges instead of rounding each
  line, and the note omitted allocation priority. Public and manual checks
  passed; independent grading caught the error (29/30). The agent repaired a
  shell-induced text corruption and checked its readback, while the policy error
  remained. That actual wrong note carries forward. Storage fidelity and
  agreement between code and memory cannot substitute for source correctness.
  In the subsequent revision session, the agent read that wrong note, preserved
  its wrong historical behavior, and repeated the false historical contrast in
  its new current record. This is observed propagation of incorrect remembered
  history; it does not establish inherited tool avoidance. Its historical task
  later invented and saved a new allocation rule after opening the wrong source
  issue, despite the real approval appearing in a closed-inclusive list. That
  task failed four of 83 accumulated checks. This is harmful historical curation,
  not just a missing note.
- **A skill name and a CLI command can be confused.** Several Haiku sessions
  invoked the native Beads skill with `prime --no-memories` as its argument. The
  returned skill body is evidence of skill discovery, not rich-prime delivery.
  Both the attempted interface and the actual output must be retained in the
  audit.
- **Correct historical work can still damage standing guidance.** GLM's startup
  Courier lifecycle produced correct artifacts and used direct recall before
  current and historical work. During historical implementation, however, it
  rewrote the standing agreement with a blanket obligation on every future
  supported protocol version. Independent audit flags this as beyond the
  approval's scope: the task authorizes the current two versions, while earlier
  command support was version-specific. The required current/historical facts
  remain faithful; the flag concerns the added future obligation. Its supplied reproduction then succeeded
  without memory calls or duplicate capture. These distinct outcomes require
  separate artifact, mutation, and unnecessary-work scores.
- **Some failures occur before meaningful memory work.** Four Qwen sessions
  ended with textual tool-call imitations and no executed calls. Raw host events,
  command receipts, and the isolated host database corroborate that finding.
  Other sessions performed real coding but inferred incorrect policy boundaries.
  These cannot all be labeled memory retrieval failures.
- **A delivered procedure and a successful lookup still permit information
  loss.** Sonnet's rich-prime Courier revision read the richer guidance and an
  existing note, then saved a claim that both protocols select the latest receipt.
  The original protocol requires the earliest. Its notes also omitted required
  presentation details, while the count-only artifact passed. Its historical task
  later corrected the wrong policy against original sources and passed all 161
  checks. That repair gets no successful prior-handoff credit for the conflicting
  note; it does not make the earlier capture faithful. Required facts eventually
  became complete across its retained map while an individual historical key and
  inherited source attribution still had documented limitations.
- **An empty search result does not mean the memory is absent.** Luna's
  rich-prime Courier detail task received the full prime output, searched with
  `accepted receipt protocol duplicate summary`, and found nothing even though
  the current record existed. It did not shorten the literal-substring query or
  recall that record. The artifact still passed all 130 checks through inherited
  implementation and other sources. This is a retrieval miss with correct work,
  distinct from both capture omission and successful memory use. Its Finance
  thin-prime detail task repeated the pattern with a long multi-concept query:
  a complete current record existed, but the agent reported none after the empty
  search and recovered the actual closed approvals instead (70/70 correct).

The detailed evidence is preserved in the independent
[finance audit](../memory-bench/results/memory-routes/2026-09-07-prime-delivery-01/audits/finance-cp3z5hwq/),
[Courier audit](../memory-bench/results/memory-routes/2026-09-07-prime-delivery-01/audits/courier-begfwz8d/),
and [workflow audit](../memory-bench/results/memory-routes/2026-09-07-prime-delivery-01/audits/workflow-2alw5dw6/).

## Practitioner observations and proposed improvements

Atbrace's account is useful design input, not an experimental result. He reports
using a large transcript collection and recurring tool feedback to discover
workarounds, unmet needs, and agent preferences; its size and adoption claims
were not independently verified here. His preferences for consistent tool
conventions, readable answers alongside structured results, and interfaces
shaped by attempted commands are hypotheses for improving ergonomics.

This study's actual traces can support that improvement loop. They distinguish
missed procedure delivery, explicit capture refusal, missing information,
retrieval, incorrect application, and work that never reached tool execution.
They also preserve rejected issue-command forms and the subsequent corrections.
Those attempts are design evidence; they do not establish that every invented
argument should become supported semantics.

Remembered tool avoidance remains an untested hypothesis. A refusal to create a
memory is not evidence that an earlier agent stored an avoidance policy. Any
future workaround record should identify version, circumstances, evidence, and
when to recheck it. No inherited stale avoidance claim is made from this run.

The smallest useful changes suggested by the audited traces are below. These are
proposals for a subsequent condition, not changes to this frozen experiment or
validated fixes.

1. **Clarify the capture occasion before adding more delivery surfaces.** First
   introduction of a reusable approved agreement is different from reproduction
   of supplied facts for one case. An approval can be fully specified in today's
   issue and still contain durable scope beyond today's feature. The shared rule
   should say to preserve that scope before completing its first implementation
   or permanent revision. For an agreement already maintained in a project
   document, make the product choice explicit: a useful source-linked memory may
   improve discovery, but copying its whole body merely to count a save is not
   automatically valuable. Keep unchanged consumers and one-off reproduction
   outside automatic capture.
2. **Make recovery of missing or conflicting policy concrete.** Keep direct full
   lookup for a known relevant key and search followed by full lookup otherwise.
   If neither provides the required agreement, read authoritative documents and
   closed approval issues before inferring policy from code. The observed working
   issue-discovery path is `bd list --all` or `bd list --status closed`, followed
   by `bd show <id>`; the default list can hide the approval. Reading a similarly
   named issue is insufficient. Verify its actual project, version and approval
   scope. State an unresolved gap instead of saving an invented agreement.
   The observed long-query misses also justify testing search that accepts
   agents' natural multi-term queries, or empty-result feedback that states the
   literal matching rule and offers a shorter query. The present instructions
   already explain substring matching; repeating them did not prevent these
   misses. Such an interface change remains untested here.
3. **Check the record against the approval, not just its own readback.** Retain
   exact identifiers, scope, versions, units, structure and exceptions. Give the
   faithful record a readable opening and actual source reference. Separate
   approved policy, implementation inference and validation evidence. Readback
   confirms what storage retained; it cannot certify truth. Preserve structured
   agreements structurally and use faithful prose when prose fits. Neither JSON
   formatting nor matching code and memory is a correctness guarantee.
4. **Restrain curation after the handoff exists.** A permanent revision merits a
   current-record update with required historical facts preserved. Historical
   reproduction or another consumer ordinarily does not. Leave governing records
   alone unless the work establishes an authorized change or a source-supported
   correction. Do not add future obligations, retrofit provenance or rewrite
   history to describe the latest implementation. A fully supplied support task
   should not automatically search, save and read back another note.
5. **Use one procedure with clear host entry points and useful error feedback.**
   Project rules and host pointers identify the occasions; the skill supplies
   the procedure; prime can expose that same procedure. Distinguish executing
   `bd prime` in a shell from loading a native Beads skill. Make unsupported
   command feedback point to the actual verbs. Attempted aliases are design
   evidence, but ambiguous or invented semantics should not automatically become
   permanent API surface. Use the completed outcomes to reject unsupported
   superiority claims and guide a further delivery comparison. One lifecycle per
   cell, with provider censoring, cannot establish a generally winning surface.

Separate agent and human interfaces pragmatically. A stable machine-readable tool
envelope with a readable `answer` or preview can accompany a faithful record;
that does not require every memory body to be JSON. A human view can emphasize
review and source history while the CLI emphasizes discovery and exact lookup.
Neither interface split nor the proposed envelope was tested here, so neither
should displace the smaller occasion and source-checking changes on this evidence.

The practical handoff to pursue is: identify whether ordinary issue work depends
on an earlier agreement; read the applicable complete record and resolve any
source conflict; implement and verify the requested behavior; then capture the
first introduction of a reusable approved agreement, a permanent revision or a
source-supported reusable finding, preserving its
source and scope. Link the actual saved key from issue completion. Historical
work uses the historical agreement; supplied reproduction leaves the standing
agreement alone. The experiment demonstrates individual parts of this procedure
across hosts. Its repeated end-to-end reliability must be judged by the completed
lifecycle intersection, not inferred from those examples.

Use the transcript-and-feedback loop to evaluate these changes: classify missed
discovery, capture omission, information loss, retrieval, application, historical
mutation and unnecessary work separately. Keep provider failures outside
behavioral interpretations. Track faithful retained information and correct later
work as the outcomes; adoption counts explain departures. This accommodates
agents' observed workflow without weakening the user's approved intent.
