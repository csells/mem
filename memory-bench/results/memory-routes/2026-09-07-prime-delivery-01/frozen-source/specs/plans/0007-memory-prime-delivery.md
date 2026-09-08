# Memory guidance through prime and a startup briefing

Status: pre-run design. Freeze this file and every scored input before inference.

## Question and authorized scope

Does presenting a complete memory procedure through `bd prime`, or supplying that
same procedure at startup, improve voluntary memory handoffs during ordinary
coding work? Separate seeing the procedure from discovering and invoking prime.
The user authorized writing and executing this experiment after discussing those
two delivery choices. Preserve the branch, all existing changes, completed trials,
frozen sources, records and verification results.

The [previous report](../memory-policy-handoff-results-2026-09-07.md) measured
11/40 strict core handoffs, including 9/20 with occasions guidance, but only
10/40 under a preparatory-read interpretation. Its prime output merely pointed
to `AGENTS.md` and the skill. This study tests delivery of that existing guidance;
it does not implement the proposed Memory Bead type or automatically inject
saved memory bodies.

The current [Memory Beads proposal, R8 and R31](https://github.com/gastownhall/beads/issues/5877)
requires generated guidance for selective retrieval and deliberate capture, with
exact commands and no automatic body loading. The legacy interface can simulate
that instructional surface through a custom `.beads/PRIME.md` and
`bd prime --no-memories`. Canonical identity, shared history, structured task
references and proposal conformance remain outside this experiment.

The [live proposal snapshot](../../memory-bench/results/memory-routes/2026-09-07-prime-delivery-verification-01/proposal-5877.json)
records the issue revision consulted (`updatedAt: 2026-09-07T21:23:29Z`).

## Matched delivery conditions

All conditions install exactly the prior occasions `AGENTS.md`, host pointers,
Beads skill and memory reference. All retain the same actual-key catalog behavior,
commands, tools, tasks and model settings. Construct the richer briefing by
mechanically concatenating the existing issue workflow, complete occasions memory
reference and catalog rule; do not introduce new policy facts or new instruction
semantics while changing their delivery.

| Arm                | `bd prime --no-memories` output               | Initial launch message                                                       |
| ------------------ | --------------------------------------------- | ---------------------------------------------------------------------------- |
| `thin-prime`       | Existing pointer to `AGENTS.md` and the skill | Ordinary task assignment                                                     |
| `rich-prime`       | Complete common briefing                      | Ordinary task assignment                                                     |
| `startup-briefing` | Existing thin pointer                         | Complete common briefing, then a separately labeled ordinary task assignment |

The startup arm keeps thin prime so invoking prime does not supply another copy
of the richer intervention. The common briefing is byte-identical to the rich
prime content, checked against actual CLI output before model sessions. Existing
rules and skill references can still repeat material when read. Exposure count,
message role, order, salience, output truncation and context consumption are
properties of these delivery packages, not separately randomized mechanisms.

The task component remains exactly `Work on <actual issue ID>.` Record it
separately from the complete launch message. Do not claim the startup arm's whole
prompt is unchanged. Its briefing is identical for every scored task and contains
no task-specific capture/recall reminders, record keys, governing policy values,
stage numbers or hidden answers. Host adapters receive the same single-message
composition; no host-specific system-prompt override is used.

The agent remains free to determine whether this task calls for memory. No
capture hook, compulsory read, completion guard or hidden-score feedback is added.
Administrative prime reads used for setup or qualification are not agent exposure.

## Coverage and budget

Use six previously qualified exact profiles: Codex Astra (`gpt-6-astra`) and Luna
(`gpt-5.6-luna`), Claude Sonnet (`claude-sonnet-5`) and Haiku
(`claude-haiku-4-5-20251001`), OpenCode Qwen
(`ollama/qwen3-coder:30b-a3b-q8_0`), and zcode GLM (`zai/glm-5.3`).

This purposive selection covers every requested CLI and includes weaker models
within two hosts. The earlier occasions sessions had prime invocations in 12/12
Astra, 10/12 Sonnet, 12/12 GLM, 8/12 Luna, and 0/12 Haiku and Qwen sessions;
Luna also had quota censoring. Fable, Opus, Sol and Terra are not rerun in this
bounded delivery comparison. This is not a model-population sample or an isolated
host-effect comparison.

Six profiles × three arms × two families × six sessions = **216 scored sessions**,
36 lifecycles and 12 lifecycles per arm. There is one lifecycle per cell. Both
families and their two worlds are the unchanged policy-fork corpus. Preserve each
profile's previous world and indexed/search-only family assignment so every arm
has the same legitimate sources and discovery opportunities. Counterbalance the
six possible arm orders across the six profiles; reverse family order for
alternating profiles. No previous result is pooled as a new baseline.

All scored sessions use the existing isolated native-memory condition. The prior
24 normal-memory checks already delimit that question; this study adds no normal
or interactive-memory arm. Existing native settings, auth, CLI/model pins,
Codex high reasoning and Qwen's owned 32K runtime remain explicit in the manifest.

Allow four workers, one sequential worker per model profile, and the existing
420-second session deadline. Claude retains its 30-turn limit and $1.50 stopping
threshold, which is not an invoice cap. The six profiles each have 36 scored
sessions. At prior observed session means, the 72 Claude sessions suggest about
$10.35 reported usage; richer context can increase that, so this is an estimate,
not a cap. Codex and GLM dollar charges remain unavailable, and local Qwen compute
is unpriced. Report actual provider receipts and all unknown costs.

Before scoring, allow **12 explicit delivery qualification sessions**, one
rich-prime and one startup-briefing session for each profile, plus deterministic
scratch CLI checks. Qualification is not adoption credit. Check actual model
identity and launch transport separately from compliance with a diagnostic
marker. A weak model's failure to follow a delivered instruction remains a
behavioral diagnostic; do not silently exclude it. No qualified session or
scored slot is retried, replaced or repurchased after failure.

## Ordinary work and retained state

Each lifecycle retains the existing six tasks: narrow initial capability under
a complete agreement; multi-entity use; permanent revision; detailed current
output; historical output; fully supplied support reproduction. Keep the actual
code, docs, issue history and memories between fresh sessions, including wrong
or missing records. Never seed a perfect note, repair a failed capture or erase
legitimate alternative sources to manufacture dependence.

The first Courier agreement already exists as a project document, while the first
finance approval arrives in an issue. Preserve that known trigger ambiguity:
missing keyed capture is an outcome, but not automatically disobedience of a
rule about newly introduced knowledge. Source-linked partial records can be useful
without satisfying the separate complete-record criterion.

An indexed session receives only keys actually present in its before-snapshot;
the search-only family receives no index. Neither prime nor the startup briefing
contains stored bodies. Agent-authored task completion references remain valid
sources for later direct lookup. They are not experiment-authored memory cues.

## Outcomes and interpretation

Public workflow checks remain separate from hidden artifact grading. Reuse the
independent oracles and safe artifact reader unchanged. Grade complete accumulated
behavior after each stage and the new support attachment separately at stage 6.
Session claims and passing public examples do not substitute for those checks.

For every lifecycle, independently audit:

- Faithful initial capture and preservation of current/history at stages 3, 5
  and 6, including exact scope, identifiers, units, types and necessary structure.
- Actual full prior-record delivery on eligible stages 2, 4 and 5, source of its
  reference, applicability, direct/search route and timing.
- Bulk legacy memory output without an explicit full lookup can establish
  information exposure or use, but does not satisfy either tested retrieval
  route: known-key recall, or search followed by recall. Report it separately.
- Primary preparatory use: full applicable prior knowledge precedes a behavior
  edit or informs genuinely subsequent testing or validation, followed by correct
  accumulated work. A same-session save/readback is not prior use. A substantive
  confirmation after tests is reported separately and receives no primary use
  credit; retain the earlier compatible informed-use score as a secondary measure.
- Source/verification fidelity, unsupported surrounding commentary, historical
  mutation, unnecessary rewrites, duplicate capture and other avoidable work.
- Actual rich guidance exposure: startup delivery or untruncated model-visible
  prime output. Raw administrative reads, receipt size and command success alone
  do not establish model delivery. Record partial/redirected output and compaction.

The primary strict core intersection requires all six correct artifacts, faithful
initial and retained current/history records, primary preparatory use on all three
eligible legs, no unsupported standing/history mutation and no duplicate control
curation. Also report each component, the historical scoring interpretation,
correct alternate-source work, every unsupported saved claim and whether the
control actually had an existing record to duplicate. Core success does not
certify all retained prose or every procedural step.

Primary denominators are all 216 planned sessions, all 36 lifecycles and all 108
eligible retrieval legs. Arm denominators are 72, 12 and 36 respectively. Report
conditional use among applicable entry records separately, including sensitivity
to wrong-version or conflicting records. Cumulative cases and successive sessions
are correlated, not independent reliability trials. No significance or production
reliability claim follows from one lifecycle per cell.

Classify discovery, omission, information loss, retrieval, application, historical
mutation, unsupported provenance and unnecessary work separately from host quota,
turn limits, deadlines and observer limitations. An enabled setting is not proof
of native-memory participation. A received briefing is not proof of understanding.

## Qualification, freeze and execution

Preserve all existing frozen code. Add a new package installer and a narrow new
session/phase orchestrator that reuses existing setup, host adapters, observations,
receipts, snapshots and grading. Document the copied orchestration's source hash
and intentional prompt/evidence differences; use no thread-global monkeypatch.

Before model qualification, validate exact briefing composition, unchanged
non-prime package files, no body leakage from actual scratch prime, safe multiline
prompt transport, model/native/sandbox settings, exclusive output paths,
carry-forward and refusal to restart claimed slots. Use fresh throwaway stores
and existing authentication. Preserve user state and all verification output.

Independently review the plan, package and changed runtime, then freeze source,
binary, profile, briefing and task hashes with all 216 slots before scoring.
Qualification receipts must be present and their limits explicit. Run stages 1–2
first (72 sessions), audit actual exposure/capture/use and review the exact
checkpoint, then continue stages 3–6 (144 sessions) unchanged. A weakness in a
model's behavior does not authorize changing guidance, selecting replacements or
stopping only its unfavorable trials. Concrete infrastructure failures stop that
profile while independent profiles continue; shared frozen-input changes stop all.

Every long process emits START, HEARTBEAT, DONE and measured PROGRESS events and
retains its native job handle. Do not infer a stall from quiet output alone.
No dependent phase starts until the prior completed or failed summary has an
explicit hash-bound internal review. This is an investigator gate under the
user's execution authorization, not another user permission request.

## Deliverables and decision

Publish a user-facing description under `docs/adoption-harness/`, this frozen
design, qualification and verification evidence, all retained trial records,
component and aggregate results, and a final report with exact CLI/model coverage,
costs, blockers, exposure counts and ranked conclusions.

Prefer the smallest delivery that improves faithful handoffs and correct later
work without unnecessary curation. Rich-prime versus thin-prime measures an
additional procedure presentation at the real command. Startup versus rich-prime
measures guaranteed initial availability versus command-mediated availability,
with the documented role/order/repetition differences. Neither alone proves a
specific instruction sentence, exclusive memory causality, a production-ready
Memory type or a bulletproof procedure.
