# Policy handoffs during ordinary issue work

Status: pre-run design; model qualification underway. Scored conditions will be
frozen in `2026-09-07-policy-handoff-01/manifest.json` before any scored launch.

## Goal and change from the previous screen

Test whether installed coding agents independently preserve and use durable
project knowledge while implementing ordinary issues, when the capability is
introduced through project rules and a skill. Task requests never tell an agent
to remember, search memories, or look up a memory key. Correct subsequent work
and faithful retained information are the outcomes; command counts diagnose how
the agent got there.

The previous screen did not establish the goal. It produced 100/120 passing
artifacts under its frozen checks, but no initial keyed capture in 12 treatment
lifecycles, and no known-reference direct retrieval. Most follow-ups could reuse
existing code under rules that triggered retrieval only for *missing* knowledge.
Those tasks did not reliably instantiate that trigger. Models were Astra,
Sonnet 4.6, Qwen3 Coder 30B, and GLM 5.3; that was not a model-strength sweep.
See [the completed report](../memory-unprompted-results-2026-09-07.md).

This experiment uses two task families where different approved policies can
produce the same initially observable behavior but require different later work.
An offline [policy-fork probe](../../memory-bench/results/memory-routes/2026-09-07-policy-fork-probe-01/result.json)
found identical scalar results in 72 cases and different expanded behavior in
32/64 cases. This is an author-written construction, not an agent result.

## Bounded comparisons

The main design has **240 slots**: 10 model profiles × 2 guidance packages ×
2 families × 6 fresh sessions. A further **24 slots** check normal host memory
behavior: four anchor profiles × the occasions package × one family × six
sessions. Twenty separate capture/reuse qualification slots establish actual
model access and host operation; they receive no adoption credit. Every planned,
started, failed, blocked, and completed slot remains in the denominator.

| Host | Requested primary models |
| --- | --- |
| Codex | gpt-6-astra, gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna |
| Claude Code | claude-haiku-4-5-20251001, claude-sonnet-5, claude-opus-5, claude-fable-5-1 |
| OpenCode | ollama/qwen3-coder:30b-a3b-q8_0 |
| zcode | zai/glm-5.3 |

The anchor profiles are Astra, Sonnet 5, Qwen, and GLM. Pin observed primary
models, CLI versions, reasoning settings, and native-memory settings. Auxiliary
models are recorded separately. A catalog entry is not proof of authentication.
An authentication, model-identity, or execution-interface failure can block that
profile's scored slots, without silently substituting a model or excluding it.
Behavioral diagnostic failures (for example, omitting a requested marker file)
remain reported but do not disqualify a working weaker model. There are no retries
of started sessions.
Gemini and Copilot are excluded at the user's direction.

This provides within-host model comparisons for Claude and Codex. Different
models across hosts confound host and model effects. Generational differences,
provider defaults, and token budgets also prevent interpreting the model names
as a controlled one-dimensional strength scale.
Counterfactual worlds are matched between guidance arms within each profile, but
vary across profiles for coverage, as does catalog assignment by family. This is
a model sweep and matched guidance comparison, not a causal ranking of model
strength on identical world and route variants.

The **generic** package preserves the earlier memory guidance. The **occasions**
package specifies what memories are for and ties action to observable workflow
occasions: approved durable decisions, verified engineering findings, policy-
dependent implementation, permanent revisions, and historical use. Both use the
same issue workflow, shared skill description, legacy Beads memory backend, and
reference availability. Catalog orientation is a shared addition to both packages;
the generic arm is not a byte-identical replay of the earlier deployment.
This compares the complete guidance packages; it does not isolate individual
sentences, AGENTS.md from skills, or memory from all alternative sources.

## Tasks and admissibility

Each family has two counterfactual worlds, selected by profile and matched
between guidance arms. Both worlds remain valid; agents may naturally preserve
scope in code, docs, issue notes, or memories. We never erase those alternatives.

| Stage | Ordinary issue | Knowledge opportunity |
| --- | --- | --- |
| 1 | Implement a small capability under a complete approved agreement | Capture newly supplied scope and rationale that exceed the narrow implementation |
| 2 | Extend it to multiple entities | Recover the original scope before applying it |
| 3 | Adopt a permanent revised agreement; retain explicit old-version behavior | Revise current knowledge while preserving actual earlier information |
| 4 | Expose itemized/detail output | Recover approved selection/allocation semantics absent from aggregate behavior |
| 5 | Support original-version detail output | Use historical knowledge while leaving the current agreement intact |
| 6 | Produce a fully specified support-case JSON attachment with existing commands | Reproduce without automatically curating another record |

Finance uses shared credit caps and allocation priority. Engineering uses a
vendor's delivery-identity scope and duplicate-selection contract. Initial
scalar/count behavior cannot settle all future scope/priority questions. Hidden
checks include witnesses that separate the two worlds, versions, and priorities.
Public tests intentionally cover interfaces and ordinary examples without
supplying missing scope or selection answers.

Before admission, inspect the entire agent-visible context, compare the two
worlds, execute reference implementations against independent oracles, and
reject deliberate wrong-scope, wrong-version, wrong-priority, and provenance-
irrelevant shortcuts. Task authors know the memory objective; independent review
does not make authorship blind. Publish that limitation and the actual review.
Task bodies contain ordinary domain approvals and issue references, never memory
instructions. Historical reproduction must not restate the missing old policy.

## Deployment and retrieval routes

Each lifecycle receives AGENTS.md, CLAUDE.md and GEMINI.md pointers, a shared
project Beads skill and memory reference, and `bd prime` workflow discovery.
Legacy `bd remember`, `bd memories`, and `bd recall` are available on the isolated
PATH and operate on a fresh scratch store. This does not implement or validate
the proposed Memory bead type.

Reference availability is a declared deployment factor, constant for a lifecycle:
one family per profile is **indexed**, the other **search-only**, counterbalanced
by profile; matched arms receive the same mode. Indexed deployments expose a
fresh session-local catalog through `BEADS_MEMORY_INDEX`, referenced by the
common workflow. It contains only keys actually present in the pre-session store,
including incomplete or wrong records. It contains no memory bodies, expected
answers, or synthetic perfect keys. Search-only deployments provide no catalog.
Agents still choose whether to read full records. Index delivery, index reading,
direct full lookup, search, and full lookup after search are distinct measures.
Indexed direct lookup is lookup from an exposed reference, not spontaneous key
discovery. No hook forces a read, writes a record, or blocks completion for memory.

Only actual retained code, files, issue history, and memory records carry forward.
Never repair captures, fill omissions, remove mistakes, or seed ideal agreements.
Use fresh host sessions and isolate native memory for the main comparison. The
normal check uses each host's actual supported normal behavior and reports
whether that behavior creates or retrieves anything; enabling a setting is not
evidence that native memory participated.

## Execution, grading, and stop conditions

Reuse the existing sandboxed harness, receipts, snapshots, and independent artifact
checks through small model/package/corpus seams. Qualify adapters with tests and
real isolated capture/fresh-reuse CLI checks before scored sessions. Freeze input
hashes, profile settings, schedules, oracle files, package bytes, and bounds before
launch. Four workers maximum; each model session has the established 420-second
deadline and Claude's $1.50 CLI stopping threshold. That threshold is not a hard
invoice cap. Report provider costs where available and unknown costs explicitly.

Run stages 1–2 first (80 slots), inspect execution integrity, then stages 3–6
(160 slots), then normal behavior (24). An execution or model mismatch can block
dependent slots; lack of adoption or wrong work is a result and does not justify
changing conditions. If the frozen design itself is invalid, stop and report
the attempts rather than repair conditions during a cohort.

Public workflow checks remain separate from hidden correctness grading. Read
support artifacts in the same restricted, read-only sandbox used for candidate
execution; reject escaping paths, external symlinks, duplicate JSON keys, and
incorrect types. Grade all accumulated product behavior, not just the latest
feature. Capture and application are independently assessed against approval
sources; agreement between code and memory is not proof of correctness.

## Results and interpretation

Publish a host/model coverage matrix, all planned and assessed denominators,
costs and elapsed time, actual authentication/model blockers, artifact and case
outcomes, record fidelity, retrieval timing, and native-memory observations.
Classify discovery failure, capture omission, information loss, retrieval,
application, historical mutation, unsupported provenance, and unnecessary work
separately. A full body read after implementation differs from a read used to
prepare implementation; administrative snapshots are not agent memory activity.

The strict handoff outcome requires faithful initial capture, faithful revision
and preserved history, correct subsequent work, and a relevant retained-record
read on the eligible retrieval legs. Report alternate-source success separately.
For the supplied one-off control, distinguish duplicate curation from a genuinely
new evidenced finding. Audit surrounding prose, not just machine-readable values.

The following fidelity rubric is frozen before scoring. Facts can be faithfully
expressed in prose, structured data, or complementary records. Exact wording and
a particular JSON schema are not required. A note that contradicts the approved
agreement fails that fact even if the code happens to be right.

| Family | Required retained agreement facts |
| --- | --- |
| Finance release 1 | 10% rounded down per line in integer cents; 2400-cent cap; correct account or account/subscription grouping; earliest service date then line ID priority; allocation consumes the group's remaining cap; applicability is release 1 |
| Finance release 2 | 15% rounded down per line in integer cents; 3000-cent cap; the approved reversed grouping; largest charge then line ID priority; remaining-cap allocation; release 2 is current and explicit release 1 remains historical |
| Courier protocol 1 | Correct global or account-local delivery identity; one accepted receipt per identity; earliest UTC instant, then smallest record ID; retain chosen fields/payload and input order; applicability is protocol 1 |
| Courier protocol 2 | Reversed identity scope; latest UTC instant, then smallest record ID; retain chosen fields/payload and input order; protocol 2 is current and explicit protocol 1 remains historical |

Scope and ordering are independently assessed, since a correct aggregate cannot
certify detail behavior. Approval provenance and verification claims are separate
fields in the audit: cite real issue/document sources, check claimed tests against
receipts, and report unsupported commentary even when all required facts survive.
Initial capture is assessed after stage 1; current and historical fidelity after
stage 3 and again after stages 5–6. A late first capture does not repair the initial
capture score. Missing prior knowledge remains missing until an agent recovers it
through legitimate work; the harness never supplies it.

Eligible retrieval legs are stages 2, 4, and 5. Report two denominators: all such
planned legs, and legs with an applicable record actually retained at entry.
Successful use needs an applicable pre-existing full record read, correct
subsequent artifact, and trace evidence that the read preceded or informed the
work. Separate pre-edit use from post-edit validation. Direct lookup must be
linked to a known reference; search followed by lookup is its own route. Reading
back a just-written record is capture verification, not prior-knowledge reuse.

Report lifecycle outcomes both as components and as their strict intersection.
The intersection requires all six product artifacts, faithful initial/current/
historical knowledge, applicable prior-record use on all three retrieval legs,
no unsupported alteration of standing or historical agreements, and no duplicate
curation in the supplied one-off control. Evidence gaps produce an unverified
component, not a favorable guess. A passing intersection remains one synthetic
lifecycle, not a production reliability estimate.

Rank the smallest useful changes supported by the resulting evidence. A few
synthetic successes cannot establish production reliability, long-horizon
retention, resistance to obsolete workaround advice, concurrency, or correctness
of the proposed new bead type. No result from this bounded study is “bulletproof.”
