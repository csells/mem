# Getting agents to save and use Beads memory

**The tested improvement is a concrete handoff procedure: save before completing the task, preserve the information the next task cannot reconstruct, verify the saved record, and retrieve by exact reference or search followed by exact lookup.** In the main comparison it completed all eight direct-lookup tasks and all eight search tasks. Command examples alone completed none of those tasks.

This supports improving the workflow around Memory Beads. It does not establish that the proposed Memory bead type is inherently difficult, or that another storage architecture is needed. These experiments use the existing `bd remember`, `bd recall`, and `bd memories` commands.

**The central recommendation is to make a complete memory handoff fit ordinary bead work and judge it by correct subsequent work.** Adoption counts remain diagnostic. Agents' attempted commands, workarounds, and feedback should shape ergonomics while the user's intent and correctness requirements remain the acceptance criteria.

## What actually ran

**80 real Claude sessions:** 64 in the main comparison, eight diagnostic sessions, and eight pilot sessions. All returned successful CLI terminal results with attributable receipts; artifact failures remain failures. Total CLI token-usage estimate: **$4.6552**, including pilots. These sessions used the existing subscription; this figure is not an additional billing charge.

Pinned environment: primary agent model `claude-sonnet-4-6`, Claude Code **2.1.263**, Homebrew `bd` **1.2.1**, macOS, seed **20260906**. CLI usage records also contain `claude-haiku-4-5-20251001`; the reported totals include that additional usage. Both main policies had native automatic memory disabled, ordinary task-bead instructions, working memory commands, and the same explicit explanation that future checkouts would lose generated files and task notes. This tests instructed preservation through Beads, not spontaneous preference over native memory.

Eight domains covered deployment, CSV export, retries, image export, logging, backups, report formatting, and caching. Each establishment session created a configuration from an approved contract. Three fresh goal sessions received only the actual saved memory: one got its exact key, one got a project/topic cue, and one received the complete configuration directly. Five memories for other projects competed with each target. No missing capture was repaired. Closed task history and earlier workspace files were not transferred.

The independent oracle checked the actual final file's complete JSON tree, field names, scalar types, and values. Receipts separately establish command execution, returned content, and ordering. A prose memory receives an **unknown** literal-JSON capture grade, not an automatic failure. The later artifact and trace review determine what information was usable.

## Main result

| Outcome | Commands and general preservation guidance | Explicit capture/retrieval procedure |
|---|---:|---:|
| Establish task: show, update, close through bd | 8/8 | 8/8 |
| Correct initial configuration | 8/8 | 8/8 |
| Accepted memory write during establishment | 4/8 | 8/8 |
| Correct later configuration with exact key | 0/8 | **8/8** |
| Correct later configuration with search cue | 0/8 | **8/8** |
| Correct configuration when fully supplied | 8/8 | 8/8 |
| Memory reads before acting when fully supplied | 0/8 | 0/8 |
| Additional save/readback after supplied task | 0/8 | **8/8** |
| Estimated usage across 32 sessions | $1.5256 | $1.8270 |
| Median session duration | 21.31 s | 25.85 s |

The three goals in each case share one capture. Their outcomes are not independent repetitions. The [machine-generated report and per-task tables](../memory-bench/results/memory-routes/2026-09-06-final-analysis/report.md) retain all denominators, unknowns, and pilot results separately.

The failures split cleanly:

- **Four omitted capture.** CSV, backups, images, and deployment agents finished the immediate work and closed their task without saving an agreement. Later agents tried the memory commands, found no matching agreement, and declined to invent it. The missing artifact is an end-to-end handoff failure; the later abstention is sensible behavior.
- **Four saved incomplete representations.** Cache, logging, report-format, and retry agents saved the scalar settings under the correct keys, then later retrieved those notes. The notes omitted the original JSON nesting, and the reconstructed files flattened the configuration. The cache note, for example, retained `ttl_seconds=300` and the other settings, but omitted the original `project` plus nested `cache` structure. Retrieval succeeded; the handoff lacked a required part of the contract.

Every protocol direct goal obtained the complete contract through exact recall before writing. Every protocol search goal searched and then recalled the selected key before writing. Compact search excerpts are selection aids; their inability to satisfy the complete-JSON oracle is not a failed search.

## Checks beyond copying JSON

The [CSV challenge](../memory-bench/results/memory-routes/2026-09-06-csv-01/manifest.json) branched an actual protocol capture into four fresh sessions. **All four produced correct configuration and CSV files**: search for the earlier agreement, fully supplied settings, a current delimiter change, and historical reproduction using the original delimiter despite being told the newer one. The CSV oracle inspected encoding/BOM, line endings, delimiters, quoted client text, decimal rounding, and trailing zeroes. These are four diagnostic branches of one capture, not four new adoption trials or a test of stored-version selection.

The [schema control](../memory-bench/results/memory-routes/2026-09-06-schema-01/manifest.json) reused the unchanged cache prose and supplied only the current output schema, without supplying the saved parameter values. Direct lookup then passed. Search recovered the settings and correct nesting but wrote the display name `Catalog API` where the contract required the identifier `catalog-api`. **Result: 1/2 correct.** Prose can carry useful facts; exact identifiers and structure must be available somewhere in the combined memory and current context. This does not justify requiring JSON for every kind of memory.

An auxiliary schema-control flag initially compared the prose body against a returned string containing an extra terminal newline. Both complete bodies were actually observed. The [explicit correction](../memory-bench/results/memory-routes/2026-09-06-schema-01/measurement-correction.json) preserves the original results and hashes, corrects only that observation flag, and leaves both artifact grades unchanged. Eight regression tests cover complete, truncated, altered, and unobserved bodies.

The [permanent-update control](../memory-bench/results/memory-routes/2026-09-06-update-01/run/result.json) explicitly distinguished a standing policy revision from a one-export override. The agent revised the existing key, verified it, and a fresh session recovered the revision without receiving the changed value in its prompt. **Updated memory, update artifact, and fresh goal all passed.** This proves compliance with an explicit revision request in one case; automatic recognition of durable changes remains untested.

## Practitioner input: Atbrace's account

Chris supplied this account in a follow-up conversation. **It is attributed practitioner experience, not independently verified evidence from our investigation.** Atbrace reports collecting more than 150,000 session transcripts to identify unmet tooling needs, workarounds, adoption, and reasons agents take alternative paths. Neither that count nor the adoption claims has been independently verified here; volume alone would not establish representative adoption rates or causation.

He describes agent-facing interfaces shaped by observed behavior, separate human interfaces where useful, and tools that return JSON by default with a readable top-level `answer` plus fuller structured results. Shared conventions cover discovery, authentication, feature discovery, invocation, and feedback. A tools CLI supplies a catalog and per-tool instructions; `CLAUDE.md` points agents there at relevant workflow moments. Every tool accepts `--feedback "<what sucked>"`, with recurring, validated complaints guiding changes. The intended tool becomes the canonical path, and transcripts expose departures from it.

His guiding observation is: “I got tired of fighting to get agents to use things the way I thought they should use them and let the agents be agents.” Chris notes a similar history in Beads: accommodating commands and arguments agents attempted. Both observations support treating usage as design evidence. They do not make every attempted command's semantics correct, or make choosing the intended tool the definition of success.

Atbrace also warns that an agent can preserve a negative judgment about a tool in memory, passing obsolete avoidance advice to later agents. **We did not observe that mechanism in these experiments.** It is a hypothesis for investigation in available transcripts and memories. Our observed omissions and incomplete notes should not be relabeled as tool aversion.

## Smallest useful changes, in priority order

These are recommendations informed by the measured results and the practitioner account. Interface changes, feedback tooling, duplicate prevention, and remembered-avoidance investigations have not been implemented or experimentally validated here.

1. **Use a transcript-and-feedback improvement loop, starting with the evidence already available.** Keep a small review record linking the task, available instructions, attempted command, returned result, saved memory, later action, and final artifact. Add an easy feedback route using existing issue/reporting infrastructure before building a transcript lake. An eventual common `--feedback` convention is a candidate interface, not a demonstrated remedy. Treat complaints as leads: inspect the associated traces, reproduce recurring problems where possible, make one bounded change, and check whether subsequent work improves. Preserve task denominators and unknowns; neither complaints nor command counts alone measure reliability.

Use separate review categories so the improvement addresses the actual failure:

| Stage | What to inspect | What our evidence establishes |
|---|---|---|
| Discovery | Available guidance, catalog/help visits, attempted syntax, and setup errors | Commands were supplied and later used. An absent write alone does not identify a discovery failure. |
| Capture omission | Whether a needed agreement received an accepted, surviving write | Four examples establish sessions saved nothing. |
| Information loss | Whether the saved record retains information absent from later context | Four canonical-key prose notes retained domain settings but omitted required structure. |
| Retrieval | Whether an existing relevant record was found and its body delivered | Both routes recovered those prose notes; incomplete content is not failed retrieval. |
| Application | Delivered content and current context compared with the final artifact | Flattened configurations failed; the schema-control search also substituted a display name for a canonical identifier. Inspect information availability before assigning the cause. |
| Unnecessary work | Ordering and purpose of extra calls, writes, and records | All eight protocol controls acted correctly first, then created another memory and read it back. |

These categories can describe different stages of one case; they are not independent failures to sum. Keep observed events separate from inferred reasons for an agent's choice. Validate actual work rather than treating an adoption count or a successful recall as sufficient.

2. **Bind memory operations to explicit workflow occasions.** At a newly approved durable decision or an explicitly permanent revision, identify what future work cannot recover from ordinary artifacts, save it under a stable reference before task completion, check acceptance, and read the same reference back. When an implementation needs a missing prior agreement, retrieve before acting: `bd recall <key>` for a known reference; otherwise `bd memories '<distinctive word>'`, inspect scope, then recall the matching key. Shorten an empty literal query. Place this guidance where ordinary bead work already directs attention, including a relevant catalog pointer if one exists. The tested package supports these occasions; it does not isolate each clause or demonstrate automatic recognition of durable changes.

3. **Pair a readable response with a faithful record.** Preserve canonical identifiers separately from display names, scope, types, units, values, and required structure whenever later context cannot supply them. Keep a resolvable source and distinguish interpretation from supplied facts. A readable `answer` or preview should explain the result and identify the record; it should not substitute for the exact body. Search can expose candidates and their scope while an explicit lookup supplies the faithful content. JSON as a tool-response envelope is a separate choice from JSON as a memory-body format: prose, source excerpts, and typed configuration snapshots can all be appropriate. Our tests support fidelity, not a universal JSON requirement or a claim that JSON-default responses improve adoption. Several tested notes cited real task IDs with empty descriptions, and two added unsupported default commentary; those remain provenance and explanation limitations despite correct payloads.

4. **Exclude replay from the capture trigger.** Refine the procedure to distinguish establishing or permanently revising an agreement from merely reproducing it. With a complete current specification, perform the task directly; do not automatically save another copy afterward. When an existing reference is known, reuse that identity rather than creating a task-ID alias. Specify whether a change is temporary, permanent, or intentionally historical. The measured problem is eight duplicate saves and their verification reads after correct work, not unnecessary discovery before acting. A future check should retain task correctness while reducing those additional records and calls. This refinement has not yet been tested; automatically suppressing every similar-looking note could erase meaningful scope or revision distinctions.

5. **Improve interface consistency and aliases where traces justify them.** Assess a discoverable catalog, consistent help/authentication/feature discovery, and structured responses before creating separate agent and human products. Separate presentations are useful if they remove observed friction; they should share the same domain semantics and canonical records. Treat repeated attempted commands and arguments as candidates for clearer errors, examples, or unambiguous aliases. Validate the intended meaning before adding a permanent alias; an ambiguous or invented operation should not silently become API behavior. Command aliases can point to one operation without creating duplicate memory records. Make the supported path easy to discover and verify, then inspect departures to learn whether an alternative is necessary or better. Canonical-path adherence remains a diagnostic, not a reason to override the user's intent or relax correctness.

6. **Investigate remembered tool avoidance without assuming it.** If available transcripts or memories contain workaround advice, trace it to the original failure and affected tool version, configuration, circumstances, and evidence. Distinguish a useful compatibility workaround from an obsolete general prohibition. Record those limits and verification status with the advice; a later reassessment should preserve the historical observation while making current applicability clear. Our runs provide no estimate of how common inherited avoidance is. Atbrace's warning justifies looking for it, not claiming it explains the measured failures.

For stronger enforcement after refining the procedure, a **task-completion check for explicitly designated memory-producing work** could require a memory reference and successful write/read receipt. This remains an untested consumer/hook proposal. It belongs around task completion; Memory itself need not acquire ready/claimed/closed states. It can enforce that an explicit write happened, not that an arbitrary statement is true. The core should not synthesize semantic memories from transcripts to satisfy the check.

Vector search and bulk memory injection are lower priorities given these results. Literal search followed by exact lookup worked in every protocol case here. Larger, ambiguous stores could expose different retrieval problems; the current results do not settle those. Keep the existing proposal's explicit body reads and consumer-owned context assembly.

## What research adds

Anthropic explicitly distinguishes memory/instruction context from enforced behavior and points to hooks for blocking actions. That supports the distinction between helpful completion guidance and a mechanical completion check; it is not evidence that our proposed check is effective. [Claude Code memory documentation](https://code.claude.com/docs/en/memory).

A useful analogy is prospective-memory research: Chasteen, Park, and Schwarz found that specific implementation intentions helped humans initiate intended actions without salient cues. It motivates binding memory capture to a concrete occasion. Human findings do not establish the mechanism inside an LLM; our experiment tests the observable workflow. [Original study, 2001](https://pubmed.ncbi.nlm.nih.gov/11760131/).

Letta's 2025 benchmark already separated memory writes, later reads, and updates across cleared histories. The useful move here is applying that separation to ordinary Beads work and grading final artifacts, rather than claiming memory adoption evaluation is new. [Letta methodology](https://www.letta.com/blog/letta-leaderboard/).

## Limits, artifacts, and reproduction

These are small synthetic configuration handoffs using one primary agent model and one seed, with a known reset and six-entry stores. The intervention bundles a capture trigger, stable addressing, representation guidance, readback, and retrieval instructions. It does not identify which sentence caused the improvement, compare against native memory, establish production reliability, test hostile memory, or validate the proposed new Memory type's implementation. Eight successes out of eight are encouraging evidence for these cases, not a 99% reliability guarantee.

An initial four-session protocol pilot exercised the macOS runtime. A separate four-session exploratory case exposed an undisclosed file-reset assumption; the full comparison then disclosed the reset equally to both policies. The remaining planned exploratory slots were deliberately not purchased. Pilots are preserved and excluded from the main comparison.

The [runner](../memory-bench/scripts/memory_routes_experiment.py), [corpus](../memory-bench/membench/runner/memory_routes_corpus.py), [independent artifact grader](../memory-bench/membench/runner/memory_routes_grade.py), and [runtime](../memory-bench/membench/runner/memory_routes_runtime.py) are new experimental files. Stores and model workspaces were disposable; actual captured KV alone crossed session boundaries. Every substantive run retains frozen prompts, source hashes and source copies, receipts, memory snapshots, final workspaces, and results. Interrupted cases cannot be silently repurchased. The drivers are configured for this local macOS installation, not offered as a portable replacement for the shared adoption harness.

From `memory-bench/`, reproduce the main experiment into a **new** output directory:

```bash
.venv/bin/python scripts/memory_routes_experiment.py \
  --out results/memory-routes/new-run --tasks 8 --policies examples,protocol
.venv/bin/python scripts/memory_routes_experiment.py \
  --out results/memory-routes/new-run --tasks 8 --policies examples,protocol \
  --fire --max-cases 16 --workers 2
```

The first command freezes a plan without a model call. A new plan uses the current sources; the saved run used base `052b0ed`. After all model sessions completed, the working branch **`csells/memory-routes-experiments`** was fast-forwarded onto Stephanie's current **`adoption-harness-share` at `1976390`**. Her update also correctly qualifies the original harness's outcome as a qualifying Write rather than verified final-filesystem correctness. Our measured outcomes use the final files.

See the [independent trace audit](memory-routes-trace-audit-2026-09-06.md) and [final verification](../memory-bench/results/memory-routes/verification-1976390/after-fixture-fix/SUMMARY.md). **134 new tests and 46 affected upstream tests pass**, as do full Ruff, Black, strict mypy, and explicit strict checks on all five experimental scripts. TypeScript passed **908 tests** with child-only Git configuration isolation. Two upstream test fixtures needed a small launcher correction to preserve the virtual environment when testing executable paths containing spaces; production code was unchanged by that fix.

The [full baseline Python suite](../memory-bench/results/memory-routes/verification-052b0ed/SUMMARY.md) was not green on this Mac: 4,341 passed, 38 skipped, 42 failed, and 12 had setup errors. Stephanie's update fixes 15 missing-fixture failures, verified by the affected tests. The remaining recorded failures concern existing Linux/path assumptions. The 180-test final run is targeted verification, not a claim that the entire cross-platform suite passed.

## Subsequent lifecycle experiment

The [separate 96-session follow-up](memory-lifecycle-experiments-2026-09-06.md) tested the existing procedure against selective-capture guidance and selective guidance plus completion checks. All three arms produced correct configurations throughout direct/search reuse, permanent revision, supplied reproduction, and historical reproduction. There was no observed incremental correctness benefit. All arms avoided duplicate capture during reproduction, so that improvement cannot be attributed to the selective treatment. Unrequested historical-note rewrites and unsupported explanatory prose remained; checks added administrative overhead. The earlier findings above remain unchanged, and the two experiments are not pooled.
