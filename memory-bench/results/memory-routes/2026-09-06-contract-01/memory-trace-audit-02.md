# Independent memory trace audit: public contract screen

The completed cohort contains 32 recorded sessions in four correlated eight-stage lifecycles. All requested and observed model IDs match: Claude Code / `claude-sonnet-4-6` and Codex / `gpt-6-astra`. The 32 actual host session IDs are unique, with one recorded session per planned slot. This audit made no model calls and changed no frozen sources or prior results.

The [authoritative machine-readable audit](memory-trace-audit-02.json) preserves original counters and invocation IDs alongside corrected interpretation. It verifies 1,693 input hashes and all 300 archived source hashes. Artifact success below reports the unchanged frozen grades; the separate parent-owned artifact audit executes the saved components independently.

| Host | Condition | Full artifacts | Literal capture / revision | Actual writes (raw) | Queries / lists / recalls | Help | Failed bd |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| claude | baseline | 8/8 | 2/2 | 3 (3) | 10 / 0 / 9 | 1 | 2 |
| claude | checker | 8/8 | 1/2 | 3 (3) | 13 / 1 / 8 | 1 | 2 |
| codex | checker | 8/8 | 2/2 | 3 (5) | 5 / 0 / 11 | 8 | 0 |
| codex | baseline | 8/8 | 2/2 | 3 (5) | 6 / 0 / 14 | 7 | 0 |

There are **eight capture occasions: four initial approvals and four permanent revisions**. Exact policy and rationale were retained in 8/8; complete literal source text in 7/8. This denominator is separate from 32 tasks and from the 12 actual writes. Current and historical records serve different purposes; their initial matching bodies do not make them redundant copies. All 24 reuse/control stages made zero writes or memory changes. All four supplied controls made zero memory reads.

## Exact source fidelity and preserved history

Claude checker’s initial note stored `Source: Architecture approval CACHE-17 (2026-09-06).` instead of the required complete string `Architecture approval CACHE-17 (2026-09-06), version v1`. The introduction still identified `(v1)`. This is a literal SOURCE-field defect, with version metadata redistributed rather than demonstrably lost. Its policy JSON and rationale were exact. The current v2 note later contained every exact approval field.

At revision, Claude checker copied the original shortened note byte-for-byte into its newly authored `catalog-api.response-cache.v1-snapshot` before updating the current key. The other three lifecycles created `.v1` snapshots during establishment. Actual commands and authored issue references establish these roles independently of the literal grader. All four historical bodies remained unchanged after their creation. The checker’s historical literal-source failure persists; it is not evidence of missing history or a historical rewrite.

Existing component code exposing the exact SOURCE was visibly read in Claude checker’s direct, search and historical reuse. Its successful final exports therefore do not establish that the abbreviated memory field alone was sufficient. The manual prose review found no invented approval or setting in the eight capture/revision occasions. Claude baseline’s claim that its snapshot is “immutable” describes an instruction; legacy Beads does not mechanically enforce that protection.

## Retrieval and overhead

Both versions’ assigned direct routes used full recall in 8/8 stages; the assigned search routes used a query returning the selected key followed by full recall in 8/8. Historical reuse delivered a complete saved body in 4/4: three by recall, and Claude checker by `bd memories v1-snapshot --json`. That returned JSON value equals the actual historical note and appeared at tool index 15 before component Write 19. Its lack of a separate recall is a command-route difference, not missing body delivery. All 20 memory-dependent reuse stages exposed the complete selected saved body before component creation; existing code and issues remained alternative sources.

Across the cohort: **77 successful reads = 34 queries + 1 list + 42 recalls; 12 actual writes; 17 help calls; 32 prime calls; 4 failed Beads commands**. Four `remember --help` calls explain raw writes of 16. One `recall --help` and one `memories --help` explain raw reads of 79. The unfiltered historical list is distinct from the empty literal `memories list` query. The existing bounded helper classifies one root-only `bd --help` invocation as unknown; this audit explicitly interprets its observed Usage output as help, preserving the helper result.

The four failed Beads commands are recoverable Claude discovery errors: two `bd memory get` attempts, one approval-label recall, and one `bd memories show KEY`. Four additional Codex heredoc attempts failed before Beads executed: checker establish/revision and baseline revision/historical. These shell failures are counted separately. Baseline revision’s repeated recalls include Python-internal comparisons; they are not seven distinct model-visible deliveries. Extra reads can verify history or consistency and are not automatically unnecessary.

Every prior regular workspace file remained byte-identical across the stages. Agent counts exclude harness administration: 64 whole-memory snapshots and 32 task snapshots, plus the 32 agent-invoked `prime --no-memories` calls. There was no new completion guard. Native SQLite was not opened by this audit; native-state findings belong to the separate immutable inspection.

## Stage evidence

Reads below are successful execution counts, not inferred model use. `Q/L/R` separates query, unfiltered list and recall. A dash in capture means no capture opportunity.

| Host / condition | Stage | Writes | Q/L/R | Capture literal |
| --- | --- | ---: | ---: | --- |
| claude-baseline | establish | 2 | 2/0/1 | pass |
| claude-baseline | direct | 0 | 0/0/1 | — |
| claude-baseline | search | 0 | 2/0/1 | — |
| claude-baseline | revise | 1 | 1/0/3 | pass |
| claude-baseline | revised_direct | 0 | 0/0/1 | — |
| claude-baseline | revised_search | 0 | 2/0/1 | — |
| claude-baseline | supplied | 0 | 0/0/0 | — |
| claude-baseline | historical | 0 | 3/0/1 | — |
| claude-checker | establish | 1 | 2/0/1 | SOURCE abbreviated |
| claude-checker | direct | 0 | 0/0/1 | — |
| claude-checker | search | 0 | 3/0/1 | — |
| claude-checker | revise | 2 | 1/0/3 | pass |
| claude-checker | revised_direct | 0 | 0/0/1 | — |
| claude-checker | revised_search | 0 | 3/0/1 | — |
| claude-checker | supplied | 0 | 0/0/0 | — |
| claude-checker | historical | 0 | 4/1/0 | — |
| codex-checker | establish | 2 | 1/0/2 | pass |
| codex-checker | direct | 0 | 0/0/1 | — |
| codex-checker | search | 0 | 1/0/1 | — |
| codex-checker | revise | 1 | 1/0/4 | pass |
| codex-checker | revised_direct | 0 | 0/0/1 | — |
| codex-checker | revised_search | 0 | 1/0/1 | — |
| codex-checker | supplied | 0 | 0/0/0 | — |
| codex-checker | historical | 0 | 1/0/1 | — |
| codex-baseline | establish | 2 | 2/0/2 | pass |
| codex-baseline | direct | 0 | 0/0/1 | — |
| codex-baseline | search | 0 | 1/0/1 | — |
| codex-baseline | revise | 1 | 1/0/7 | pass |
| codex-baseline | revised_direct | 0 | 0/0/1 | — |
| codex-baseline | revised_search | 0 | 1/0/1 | — |
| codex-baseline | supplied | 0 | 0/0/0 | — |
| codex-baseline | historical | 0 | 1/0/1 | — |

## Scope and correction

Both conditions finished 16/16 full artifacts. This cohort shows no incremental correctness benefit for the checker; it does not prove the checker ineffective. Four lifecycles in one task family are not a production reliability estimate. The trials used legacy Beads 1.2.1, with the proposed Memory type absent, and retain three other hosts’ previous coverage blockers. Capture, retrieval, source fidelity, application correctness and workflow overhead remain separate outcomes.

`memory-trace-audit-01.json` is preserved. Version 02 corrects only one diagnostic’s applicability: the joint query/recall field is now explicitly not applicable outside assigned search stages. Counts, capture/source checks, historical comparisons and artifact outcomes are unchanged.
