# Memory handoffs across coding agents

**The explicit handoff procedure produced correct configurations in all 44
executed sessions across Claude Code/Sonnet 4.6 and Codex/GPT-6 Astra. It still
failed to preserve historical prose in two revisions.** One Codex lifecycle halted
because ordinary Python subprocess use defeated receipt attribution; four later
stages remain unobserved. Three other installed CLI candidates had concrete
availability or context-delivery blockers. This is useful evidence for a procedure,
not universal reliability or validation of the new Memory bead type.

The preceding 96-session experiment and this bounded extension are now reported.
The [independent results](../memory-bench/results/memory-routes/2026-09-06-hosts-final-analysis-01/report.md)
and [trace audit](memory-hosts-trace-audit-2026-09-06.md) preserve their separate
samples, failures, unknowns, and original denominators.

The practical question is whether an approved decision can survive a complete
handoff: capture it faithfully, find the appropriate agreement in a fresh session,
apply it correctly, revise the standing agreement only when authorized, and
reproduce old or fully supplied behavior without changing memory unnecessarily.
Issuing a memory command is useful diagnostic evidence, but is not the endpoint.

The [earlier 80-session investigation](memory-routes-experiments-2026-09-06.md)
already separated these failure modes. With command examples alone, four establish
sessions saved nothing; four saved canonical-key prose that omitted required
structure. Both retrieval routes recovered those prose notes, but later
configurations were flattened incorrectly. The explicit protocol achieved 8/8
exact captures, 8/8 direct goals, and 8/8 search goals. Its eight supplied-information
controls did correct work first, then unnecessarily saved another memory and read
it back. That was duplicate curation, not unnecessary discovery before acting.
A schema control also recovered the exact configuration from prose in its direct
leg, while its search leg confused a display name with the canonical identifier.
Prose is not inherently unusable; incomplete handoffs and mistaken application
are distinct from failing to discover memory.

The [previous experiment](memory-lifecycle-experiments-2026-09-06.md) produced
96/96 correct configurations across 12 lifecycles. All 72 reproduction sessions
made zero memory writes, including 12 fully supplied controls with zero agent
memory calls. However, nine of the twelve permanent revisions unnecessarily
rewrote historical prose. One propagated unsupported commentary. The public
completion guard accepted all 32 natural sessions in the checked arm and also
accepted a deliberately wrong artifact and memory that agreed with each other.
The independent hidden-answer grader rejected that counterexample. Consistency
alone cannot certify an approved fact.

This extension retains the selective procedure and adds explicit instructions to
preserve approved source content, label interpretations, and leave the historical
body unchanged after its initial capture. The package is tested together; the
design has no matched arm without the added guidance, so it cannot establish an
incremental benefit over the previous procedure or isolate one sentence's effect.
No completion guard runs in this extension. Public workflow checks remain
separate shadow diagnostics.
The harness still takes memory snapshots and queries task state for transfer and
grading; these administrative reads are not model-issued memory calls or evidence
that a retrieved record reached the agent.

| Installed candidate     | Verified model and existing route                                                   | Scored coverage                                                             |
| ----------------------- | ----------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Claude Code 2.1.263     | `claude-sonnet-4-6`; existing subscription credentials                              | 24/24 sessions executed; all three lifecycles finished                      |
| Codex CLI 0.153.4       | `gpt-6-astra`, high reasoning, requested fast tier; existing ChatGPT authentication | 20/24 sessions executed; two lifecycles finished, one halted after revision |
| Gemini CLI 0.55.1       | Existing API key reaches the provider; no concrete successful model verified        | 24 candidate slots blocked by depleted prepaid credits, HTTP 429            |
| OpenCode 1.18.15        | Existing local Ollama 0.32.9 / `qwen3-coder:30b-a3b-q8_0`                           | 24 candidate slots blocked by demonstrated prompt truncation                |
| GitHub Copilot launcher | VS Code wrapper exists; actual CLI and authentication unverified                    | 24 candidate slots blocked because the launcher cannot find the CLI         |

Claude deliberately uses the preceding experiment's Sonnet anchor, which differs
from the user's configured Claude model. Codex uses the configured model and
reasoning effort. Thus these are host/model combinations, not a controlled test
of host effects. The requested Codex fast tier is not independently confirmed by
its captured events. Models, executable hashes, sources, prompts, seed 20260908,
240-second session timeouts, and requested $0.75 session budgets were frozen
before scored calls. Only Claude enforces that dollar budget through its CLI.
At most two lifecycles run concurrently, with at most one per host.

The [frozen manifest](../memory-bench/results/memory-routes/2026-09-06-hosts-01/manifest.json)
contains six lifecycles / 48 planned sessions and retains the other 72 blocked
candidate slots. Each lifecycle has eight fresh sessions: initial capture, direct
reuse, search followed by full lookup, permanent revision, revised direct reuse,
revised search, fully supplied reproduction, and historical reproduction. Cache
and image-export contracts include nested structure, exact identifiers, scalar
types, units, and competing other-project records. Current and historical keys
are explicitly supplied when capture is required. This does not test spontaneous
discovery that a lesson deserves storage.

Only the actual complete memory map crosses sessions, including mistakes and
omissions. No configuration files, conversation transcripts, old task history, or
repaired answers cross the boundary. The hidden approved contracts remain outside
the model sandbox. Native records, when enabled, travel separately and are checked
against the actual previous snapshot.

Normal mode means installed native-memory defaults in fresh isolated state.
Claude's automatic memory is enabled there, matching its documented default.
[Claude memory settings](https://code.claude.com/docs/en/memory#enable-or-disable-auto-memory).
Codex's installed `memories` feature defaults to off and remains off in normal
mode; the isolated condition also
explicitly disables generation and use. The Codex comparison therefore cannot
measure the effect of enabling native memory. Neither mode imports the user's
personal instructions or history. Database creation alone is not a semantic
memory capture, and a saved file alone does not establish delivery or use.

Five lifecycles reached all eight stages; the sixth stopped after four completed
model sessions. Every executed session had the requested actual model, a successful
terminal result and process exit, and an exact configuration. The independent
report validated 902 evidence inputs, including archived source hashes, actual
host/session identities, raw receipt mappings, and retained-record transfers.

| Outcome                                                  |    Claude / Sonnet 4.6 |                Codex / GPT-6 Astra |
| -------------------------------------------------------- | ---------------------: | ---------------------------------: |
| Exact configurations, executed sessions                  |                  24/24 | 20/20; four planned sessions unrun |
| Complete initial current + historical captures           |                    3/3 |                                3/3 |
| Correct permanent revision and retained typed contracts  |                    3/3 |                                3/3 |
| Direct reuse, initial and revised, with full lookup      |                    6/6 |             5/6 planned; one unrun |
| Search delivered before correct full lookup and reuse    |                    6/6 |             5/6 planned; one unrun |
| Historical reproduction with current v2 retained         |                    3/3 |             2/3 planned; one unrun |
| Fully supplied reproduction with zero agent memory calls |                    3/3 |             2/3 planned; one unrun |
| Historical body rewritten during revision                |                    2/3 |                                0/3 |
| Whole lifecycle including immutable history              | One passed, two failed |            Two passed, one unknown |
| CLI usage estimate for executed sessions                 |             $1.5944654 |                 Unknown for all 20 |

The remaining four unrun slots are revised direct, revised search, supplied, and
historical reproduction in Codex's isolated image-export lifecycle. They are
neither successes nor functional failures. Of the 44 executed stages, 43 have
fully attributable procedural evidence and one has unknown read attribution.
The literal configuration and both retained typed-contract checks pass in all 44.

The failure classifications are distinct:

- **Capture omission and information loss:** none in six initial captures or six
  revisions. Review of those records found no unsupported explanatory prose.
  This means fidelity to the synthetic supplied facts and source labels, not
  certification of arbitrary prose or a resolvable production approval citation.
- **Retrieval and application:** all 27 completed reproductions needing memory
  obtained the appropriate full contract before the configuration write. All 11
  search stages delivered search results before issuing full lookup. Correct
  artifacts remain separate from command ordering and inferred model attention.
- **Historical mutation:** both Claude cache revisions rewrote the historical
  title, including replacing an explicit immutable label with an “unchanged”
  description. The historical JSON and source label survived. Claude image and
  all three Codex revisions preserved the entire old body. More explicit prose
  instructions did not eliminate this defect.
- **Unnecessary work:** all 32 completed reproduction stages made zero memory
  writes; all five supplied controls made zero memory reads as well. The two
  historical rewrites are unwanted curation. Additional reads sometimes checked
  history before and after revision, so their presence alone is not waste.
- **Measurement failure:** four raw read invocations in one Codex revision lost
  their host-attribution markers. That is separate from a missing record or a
  wrong configuration, and caused the lifecycle halt described below.

Neither host saved substantive native-memory records. Claude's snapshots were
empty; all 20 Codex snapshots had zero memory outputs and jobs in the native
database, which contained scaffolding. Thus the normal-default checks establish
behavior in fresh state, not successful competition with accumulated native
memories or native-memory capture/retrieval quality.

Claude's cost estimate comprises $0.9399713 for 16 isolated sessions and $0.6544941
for eight normal-default sessions. Median recorded durations were 22.67 and
22.80 seconds respectively; Codex's were 25.39 and 29.71 seconds. Durations include
some evidence collection after the model process, and cost differences are
descriptive rather than demonstrated efficiency effects. Token usage is retained
per model/session in the independent analysis; Codex does not emit a dollar cost.

The [separate preflight audit](../memory-bench/results/memory-routes/verification-hosts-2026-09-06-01/PRESERVATION-AND-PREFLIGHT-01.md)
retains nine launches, including failed attempts: two Claude, four Codex, two
OpenCode, and one billing-blocked Gemini invocation. Its known estimate is
$0.1214118. **The new cross-host work therefore has a $1.7158772 known estimate,
plus unreported costs.** OpenCode's emitted provider cost is zero, with local
compute and title-helper usage unmeasured; five preflight session dollar costs
are unknown. These are CLI usage estimates, not invoice or subscription charges.
The prior 96-session run's separate estimate remains $5.5352622.

The failed preflights remain evidence. Codex's first common smoke exposed macOS
login-shell PATH reordering, which selected the global `bd` instead of the scratch
wrapper. Claude's first common smoke exposed attribution lost when a help result
was piped through `head`. Both were corrected and passed new isolated smokes
before this cohort was frozen; neither failed attempt was overwritten. Unique
execution markers associate real shell results with raw memory receipts. A
marker proves attribution, not delivery of any content truncated from that result.

The scored Codex image-export revision exposed another measurement limitation:
Python subprocess calls captured both streams and forwarded only stdout, dropping
four read invocations' stderr receipt markers. The revised artifact and retained
records are independently checkable; exact attribution of those reads is unknown
under the frozen rule. That lifecycle halted after its revision and was not
repurchased. The two untouched Codex lifecycles continued independently with the
same conditions. Both the successful literal outputs and the unavailable procedural
evidence are retained. A future adapter needs a transport that
survives ordinary programmatic subprocess use; changing the current evidence rule
after seeing this case would invalidate the frozen comparison.

OpenCode completed real model/tool turns, but the common smoke produced no
configuration and invented a task HTTP endpoint. Its existing Ollama runtime
logged a 7,301-token request reduced to 2,050 tokens within a 4,096-token total
context. A no-inference diagnostic reduced the interface to four tools; system
and user text alone still counted 2,121 tokens, before another 2,375 tokens of tool
schemas and template overhead. This is a verified input-delivery blocker, not a
memory-specific behavioral verdict. The advertised model maximum of 262,144 is
not the actual allocated context. The existing OpenAI-compatible Ollama route
does not support a request-level context override. No server, model, or global
configuration was changed. See the [preserved diagnostic](../memory-bench/results/memory-routes/2026-09-06-host-context-diagnostic-01/REPORT.md)
and [Ollama's context configuration documentation](https://docs.ollama.com/api/openai-compatibility#setting-the-context-size).

Gemini's existing credential is present and reaches the provider; the blocker is
billing, not an assertion that the user is unauthenticated. Its single invocation
retried internally and was interrupted after 120 seconds with no terminal model
result. Copilot's wrapper exited zero after requesting installation and reporting
the missing executable. Exit status and executable presence are insufficient
availability checks. The [coverage audit](memory-hosts-coverage-audit-2026-09-06.md)
and [inventory](memory-hosts-inventory-other-2026-09-06.md) distinguish each case.

The smallest useful improvements, ranked by engineering judgment from these
findings, are below. Preview fields, immutable versions, and new enforcement
behavior are proposals, not tested treatments in this cohort.

1. Make the memory handoff part of ordinary bead completion when work creates or
   permanently revises an approved durable agreement. At the start of dependent
   work, retrieve an absent prior agreement. State whether a task establishes,
   revises, or reproduces behavior; a fully supplied reproduction needs neither
   another capture nor a memory lookup.
2. Preserve the source details a later session cannot reconstruct: canonical
   identifiers, scope, types, values, units, structure, and approval provenance.
   Pair a faithful record with a readable preview or top-level `answer`. Exact
   configuration JSON belongs in these memories because JSON is the approved
   contract; this is not evidence that every kind of memory should be JSON.
3. Protect old versions and separate interpretation from approval. Update the
   standing reference only for a permanent revision. Immutable versions or checks
   against the actual prior body would make historical preservation stronger than
   an instruction alone. For capture fidelity, compare against the approved
   source where available, not merely against the agent's own generated artifact.
4. Improve the interface from real traces and feedback. Keep command discovery,
   exact lookup, scoped search, and full-record retrieval predictable. Attempted
   arguments are design evidence; validate their intended meaning before adding
   permanent aliases. A separate agent interface is useful when it removes a
   demonstrated obstacle; maintain a human-readable view of the same record.
5. Use completion enforcement selectively where missing capture has demonstrated
   cost. Missing/incomplete records and readback failures deserve checks, but the
   previous natural trials showed no guard intervention or incremental correctness
   benefit. Do not add memory reads to every supplied reproduction just to run a
   generic guard. Continue independent checks of actual subsequent work. Before
   another comparative cohort, fix and smoke-test attribution through ordinary
   Python subprocess capture without requiring agents to cater to the measurement
   system. Then unblock the three missing host profiles and validate the actual
   Memory type on broader ordinary tasks.

Atbrace's account supports the transcript-and-feedback approach as an attributed
practitioner observation. His claimed transcript volume and adoption were not
independently verified here. Our traces independently demonstrate why capture
omission, information loss, retrieval, application, historical mutation, and
unnecessary work need separate classifications. His warning about remembered
tool avoidance is a hypothesis to investigate in available records; we did not
observe it. Workaround advice should retain version, circumstances, and evidence
so a later agent can reassess it instead of inheriting an obsolete prohibition.

The simplest procedure supported for correct subsequent work in these trials is:

> Before completing a newly approved durable decision or permanent revision,
> save the complete approved agreement under its canonical project/scope key.
> Preserve exact structure and identifiers; distinguish approved facts from
> interpretations. Check the write acknowledgment, then read back and compare
> with the approved source. Keep historical versions unchanged.
>
> Before implementing an absent prior agreement, use `bd recall <key>` if its
> reference is known. Otherwise use `bd memories '<distinctive word>'`, check
> project/scope, then recall the matching key in full before acting. Apply that
> agreement's actual values and types. If the required agreement is missing or
> incomplete, report what is missing instead of guessing.
>
> Reproducing an agreement does not create or revise memory. Use the requested
> historical version for historical work; leave the standing agreement intact.
> When the complete contract is supplied for reproduction, use it directly.

These commands exercise legacy `bd` 1.2.1 keyed memories. None of these runs
validates the proposed production Memory bead type, automatic recognition of
durable lessons, large ambiguous stores, concurrent writers, adversarial records,
long-term drift, or unrestricted production reliability. The stages share
retained state and are correlated; successful stages must not be counted as that
many independent reliability trials. The normal-default sample is particularly
small and does not recreate a user's established native-memory history.

[Verification](../memory-bench/results/memory-routes/verification-hosts-2026-09-06-01/SUMMARY.md)
passed 407 targeted tests, full Ruff, strict mypy, and the final full Black check;
the formatting supplement also passed the macOS shell-path test. Actual isolated
Claude and Codex smokes passed capture, search, full recall, artifact and task
closure checks before scored calls. Earlier unrelated Python platform failures
remain documented. Unchanged TypeScript retains its prior verification. No
production memory feature was installed, and the existing branch, uncommitted
work, user state, and preceding experiment evidence were preserved.
