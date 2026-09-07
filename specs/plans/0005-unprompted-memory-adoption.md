# Ordinary coding work with standing memory guidance

Status: revised on 2026-09-07 for Claude Code, Codex, OpenCode, and zcode.
The user confirms all four work and explicitly excludes Gemini and Copilot.
Eight integration sessions are complete; no scored sessions have launched.
All four interfaces worked; OpenCode did not pass every diagnostic instruction.
See the [qualification report](../memory-four-hosts-qualification-2026-09-07.md).
The user authorized running the comparison. The independent corpus and final
profiles have passed [admission](../memory-unprompted-admission-2026-09-07.md);
the runner freezes exact bytes and all 120 slots before inference.

## Goals

Establish a practical, repeatable workflow in which each of the four coding-agent
CLIs, while implementing ordinary features and fixes:

1. Independently identifies and saves useful durable decisions, facts, and lessons
   because of standing project rules and skills, without task-specific memory cues.
2. Uses its actual saved knowledge in fresh sessions through both direct lookup
   and search with full-record inspection, and produces correct subsequent work.
3. Preserves the information needed for that work, handles permanent revisions
   and historical compatibility correctly, and avoids duplicate capture when
   reproducing a fully supplied agreement.
4. Does this through the intended project installation: AGENTS.md, supported host
   entry points, a shared Beads skill, and the real memory-capable CLI.

Success requires measured capture, retrieval, faithful records, and correct work
on each requested host. Merely exposing commands, counting calls, or completing
tasks with other sources does not establish this complete goal. Both retrieval
routes remain requirements; the experiment cannot manufacture their use through
task prompts. Unobserved routes leave the goal partly unvalidated.

## The question and the earlier mistake

Do agents doing ordinary coding work choose to save useful knowledge in Beads
and use it correctly in later fresh sessions because of installed project rules
and skills, without task-specific instructions to use memory?

The preceding installed-guidance and public-checker experiments did not answer
that question. Their launch prompts said `Work on <issue-id>`, but the issue
bodies prescribed durable retention, preservation of original approvals, and
referenced follow-ups. In the public-checker cohort, all eight actual direct
follow-ups requested recall; six included literal `bd recall` commands. Those
instructions were part of the experimental input even when an earlier agent
authored them. The experimenter optimized a guided handoff and then made a
broader adoption claim than that treatment supported.

Their measured results remain useful evidence about guided capture, retrieval,
application, and interface checking. All frozen inputs, transcripts, outputs,
grades, and verification records remain unchanged. This plan replaces the
adoption design, not the previous evidence.

## The smallest useful comparison

Use the same real issue workflow and memory-capable `bd` build in two arms:

| Arm            | Installed instructions                                                                                     |
| -------------- | ---------------------------------------------------------------------------------------------------------- |
| Issue baseline | Current issue rules and skill; ordinary tool help/catalog remains available. No added memory workflow.     |
| Memory package | The same issue workflow plus generic memory occasions in AGENTS and a memory reference in the Beads skill. |

The treatment is the complete deployable rules/skill package. This first
comparison cannot tell us whether rules alone or skills alone are sufficient.
Those ablations become useful after the package demonstrates adoption.

Tasks request software behavior only. No request to save, recall, retain an
agreement, preserve a memory, create a knowledge reference, or prepare a memory
handoff belongs in a scored task. No task names a memory key or instructs the
agent to create a later task that does. Agents may independently create such
artifacts; preserve and analyze them, but do not substitute them for the frozen
scored tasks.

If an agent independently adds a memory-lookup instruction to a later scored
issue or comment, preserve it and classify that later session as instructed
reuse. Keep it separate from adoption under clean task instructions.

The standing package may explain these general occasions:

- Save a newly approved durable decision or useful finding before finishing work
  when it would help later work or be costly to rediscover. Check for an existing
  record first. Preserve scope, identifiers, types, units, and rationale where
  relevant; distinguish evidence from inference. Existing code or documentation
  does not make a useful, concise knowledge record inherently redundant.
- When work depends on missing project knowledge, consult the appropriate record.
  Follow a known reference directly; otherwise search and inspect the full result.
- A permanent change updates the standing knowledge without inventing historical
  facts. Reproducing an existing result does not by itself justify another save.

Keep detailed syntax in the skill and tool help. Faithful prose is acceptable;
JSON is required only where the application's public contract requires it. A
readable search preview should accompany, rather than replace, the faithful body.

## Tasks and state

An independent task author has drafted customer-list, renewal-notice, and support
ticket CLI work without seeing the memory intervention. These drafts are inputs
to task review, not a frozen corpus. Select two unrelated families and write
six ordinary tasks per family:

Admission selected independently authored HarborPass renewals and Northbank
reconciliation. Their original drafts, revised controls, cross-review findings,
and executable verification are recorded in the admission report. The examples
below describe the design; the frozen corpus is authoritative for actual tasks.

Stage labels and measurement opportunities below are evaluator metadata, never
text supplied to an agent. Ordinary project names, release identifiers, and
business requirements are allowed; memory keys and storage instructions are not.

| Stage | Business work                                                                               | Measurement opportunity                                                      |
| ----- | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| 1     | Implement a feature after a concrete product decision or relevant discovery.                | Does the agent select and faithfully capture useful knowledge?               |
| 2     | Extend the product in a way related to that earlier work.                                   | Does it independently retrieve relevant memory and apply it correctly?       |
| 3     | Implement a fully specified reproduction of existing behavior.                              | Does it avoid duplicate capture and needless curation?                       |
| 4     | Change a permanent business requirement.                                                    | Does standing knowledge reflect the revision faithfully?                     |
| 5     | Add another feature affected by the changed behavior.                                       | Does later work use current knowledge rather than a stale note?              |
| 6     | Add a compatibility feature that produces an older externally specified format or behavior. | Can it implement historical behavior without changing the current agreement? |

For example, initial renewal work can specify notices seven days before renewal;
a later task can add a calendar export; another changes the default lead to
fourteen days; a subsequent task adds daily batches. A legacy export can require
compatibility with the earlier product release. None should tell the agent where
to obtain knowledge or what to remember. These examples still need blind review
and public-contract tests before admission.

A less direct reuse pair is: "Fix reconciliation dropping transactions on the
last day of a selected month," followed in a fresh session by "Add filtered
refund CSV export." Investigation of the first bug can establish that the
provider's date upper bounds are exclusive and use UTC. The second task names
neither that finding nor its source. Provider docs, the old fix, tests, and logs
remain accessible. A faithful memory can make the finding easier to recover;
its necessity must not be assumed. This is a reviewer-proposed candidate that
still needs independent task admission, not an already validated task.

Every stage starts a fresh conversation. Preserve the actual repository, issue
history, tests, memory records, and declared native state within its lifecycle.
Separate lifecycles and arms start in new scratch directories. No original data
is cleared, and no failed capture is repaired, supplied, or silently skipped.

Code and issue history are legitimate sources. A correct solution from them is
a coding success, not proof of memory use. A task solved without Beads is not
automatically a policy failure. Select some tasks where prior rationale or a
discovery would help and cannot simply be read from a configuration constant;
do not manufacture necessity by deleting earlier code or hiding available tools.
Record alternative-source use explicitly.

Direct lookup and search are observed choices, not names of task stages. Report
both against all scheduled reuse tasks, then descriptively against actual
reference-exposure opportunities. Missing references remain outcomes. If a host
never chooses direct lookup, that route remains unvalidated; we cannot rescue
the claim by inserting a key or scoring only successful references. Search that
already returns a full body differs from preview search followed by lookup.

## Delivery and the four requested hosts

Install one canonical project AGENTS file, the shared Beads skill/reference, and
compact prime orientation. CLAUDE.md and the other in-scope host entry points must
use their verified supported import or discovery mechanism. A Markdown link's
presence does not prove it was loaded. Distinguish native skill discovery from
an agent manually opening the skill file.

Hold public workflow checks constant between arms. Do not inject memory bodies
through prime, add a completion guard, supply task-specific reminders through a
hook, or expose hidden answer checks. A guard that forces capture would change
the adoption question again.

The [four-host inventory](../memory-four-hosts-inventory-2026-09-07.md) records
the current interfaces and separates user-confirmed availability from harness
qualification. The earlier five-host inventory remains historical evidence.

| Host        | Qualification work                                                                                                                                                                   |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Claude Code | Verify the project-enabled adapter, pinned model, instruction delivery, and real tool operations.                                                                                    |
| Codex       | Verify the project-enabled adapter, pinned model, instruction delivery, and real tool operations.                                                                                    |
| OpenCode    | Qualify the current model/profile, effective context, project instructions, skills, and structured receipts. An older Qwen profile's truncation is not a verdict on the working CLI. |
| zcode       | Qualify its own headless interface, model configuration, instruction/skill loading, native memory, and structured receipts.                                                          |

Do not change global configuration, an existing model server, authentication, or
billing to make a coverage row disappear. Complete independent adapter work while
blocked. Keep all four requested rows even if an adapter has a qualification
failure. Gemini and Copilot are excluded by user choice, not failed coverage
rows. A version command or credential's presence does not certify working
inference under the experiment's isolated profile.

Record CLI path, version, binary hash, requested and observed model, reasoning
settings, effective context, permissions, and token/time limits. Use the same
model across hosts where existing authenticated routes permit it; otherwise
attribute differences to host plus model, not the CLI alone. Never silently
substitute a model after a failure.

The main matched comparison disables native memory only through verified
host-supported settings, with fresh isolated state and receipts. An unverifiable
disable is a coverage limit, not an assertion that native memory was off. A
separate bounded check uses each host's normal memory settings in fresh isolated
state, preserving whatever it produces between stages. This tests fresh defaults,
not competition with the user's accumulated personal memories.
The normal-native check has one arm and cannot estimate a native-memory effect.
Where normal defaults already disable native memory, it is a same-configuration
replication, not an on/off comparison.

## Qualification before model runs

1. Freeze ordinary task titles, bodies, comments, source fixtures, public tests,
   and independent complete-work graders before tuning the memory package.
   Task authors see business requirements, not desired memory actions or routes.
2. Have an independent reviewer inspect every agent-visible surface, including
   imports, prime, skill examples, bootstrap text, tool responses, and task
   history. A forbidden-word scan is supplemental; semantic retention and handoff
   cues count even without the word "memory". This review must reject the old
   `_follow_up` task design as a negative test.
3. Validate adapters locally for isolation, real error handling, interruption
   accounting, and model/usage receipts. Fake executable tests must not be able
   to fall through to a real tool. Keep answer grading outside the agent sandbox.
4. Run one isolated two-session integration smoke per newly qualified host/package.
   Explicit tool exercises may appear in a smoke, but smoke outcomes do not count
   as unprompted adoption. Reuse an existing smoke only when its complete inputs
   and executable identity still match. Do not rebuy a failed or interrupted run.
5. Freeze the admitted identities, exact package and task bytes, randomized or
   counterbalanced arm order, resource limits, native settings, cost accounting,
   and every planned slot before launching the scored cohort.

Proposed maximum: **96 main sessions** = four hosts × two arms × two families ×
six fresh sessions. The first three stages provide a **48-session checkpoint**;
if the design remains frozen, those sessions are retained parts of the full 96,
not repeated trials. Stop to report a design/adapter failure; a repaired design
requires a new cohort identity, not overwritten evidence. Add **24 normal-native
sessions** = four hosts × one memory-package arm × one family × six stages.
Four integration smokes of two fresh sessions each are separate (up to eight CLI
sessions). They test harness operation and may explicitly exercise tools; none
counts as adoption evidence. The scored-session bounds are proposed, not a claim
that adapters or the corpus are already qualified.

Before launch, report enforceable per-host limits and a cost estimate. CLI usage
estimates, actual charges, subscription usage, local inference, and unknown costs
must remain separate. A dollar cap unsupported by a CLI cannot be claimed as
enforced. Record any integration CLI inference separately from scored sessions.

## What counts as evidence

Grade independent executable behavior and the complete public artifact contract.
Separately inspect actual retained records, returned bodies, source evidence,
and changes to current and historical knowledge. Do not accept an artifact and a
memory merely because they agree with each other. Do not equate command counts,
agent claims, or administrative grader reads with agent adoption.

Report discovery/delivery failure, capture omission, information loss, retrieval
failure, incorrect application, unsupported provenance, historical mutation, and
unnecessary work separately. A shortened source string with all facts elsewhere
is a literal-fidelity difference, not automatically loss of the underlying fact.
Distinguish a justified new lesson from duplicate curation in the supplied control.

Keep all planned denominators: blocked, started, interrupted, completed, and
assessed sessions; capture opportunities; eligible reuse tasks; and independent
lifecycles. Never treat six correlated stages as six independent reliability
trials. No automatic retries, answer repairs, or posthoc task selection.

Before claiming repeatability, run unchanged guidance on further independently
authored tasks and repeated fresh lifecycles. Reserve unused task families for
that validation if the initial screen is used to improve the package. A passing
screen is evidence for its particular hosts, models, tasks, and native settings,
not a production reliability estimate.

The package's adoption claim remains unsupported on a host if no faithful capture
or relevant subsequent Beads use occurs. Complete work using code alone remains
a valid task outcome. Capture plus retrieval plus correct work demonstrates a
successful handoff, but does not establish that memory caused correctness when
other sources supplied the same facts.

A later, separately labelled causal diagnostic can fork actual retained records
into new consumer workspaces with and without access to those records. Never seed
perfect answers; keep mistakes and the original workspace. Such a diagnostic can
test the value of retained knowledge but cannot replace this ordinary-work test.

## How this maps to Memory Beads

The smallest useful product change remains a discoverable, shared workflow:
ordinary issue work exposes a short memory route; a skill explains selective
capture and faithful retrieval; the CLI makes the resulting record understandable
and addressable. Agents choose when to use it. Observe attempted commands and
feedback before extending aliases; an invented command is design evidence, not
an automatic obligation to support ambiguous semantics forever.

The previous runs used legacy `remember`/`memories`/`recall`. Freeze the actual
tool interface for this new run. If the proposed Memory bead type and its native
identity, references, and revision semantics are not implemented in that build,
this remains a workflow adoption test, not validation of that type. A simulated
interface must be labelled a prototype, and production claims require a later
run against the real implementation.

Atbrace's transcript-and-feedback approach supports investigating agents' actual
choices. His reported transcript volume and adoption outcomes remain attributed
practitioner observations, not verified evidence here. Remembered tool avoidance
is a hypothesis to inspect in available records; these experiments have not
observed it. Workaround advice should retain version, circumstances, and evidence.

Anthropic's [agent-evaluation guidance](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
supports checking outcomes and transcripts, balancing required and unnecessary
behavior, and separating the model from its harness. [MemoryArena](https://arxiv.org/abs/2602.16313)
motivates evaluating memory alongside later actions across sessions. Neither
source validates this proposed corpus or shows that our task cues were acceptable.

The correction to our research process is specific: **review the complete
agent-visible task context as experimental input before spending on a cohort.**
Standing rules are the intended intervention. Instructions hidden in issue work
must not become a second intervention that makes the intended question disappear.
