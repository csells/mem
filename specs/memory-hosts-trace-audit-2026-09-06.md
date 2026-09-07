# Memory hosts trace audit — 2026-09-06

**Final audit: 44 recorded sessions produced 44 exact configurations.** Five of six planned lifecycles completed; one stopped after revision because four real reads lost their attribution markers. Two completed lifecycles unnecessarily rewrote historical prose. Three completed lifecycles satisfied both literal handoff and whole-history preservation. These are separate findings, not a claim of unrestricted reliability.

This audit follows actual prompts, stored bodies, normalized tool results, raw CLI receipts, and native snapshots. It agrees with the [final independent export][report]; all **902 input-file hashes** in its [analysis][analysis] were independently recomputed with zero mismatches. Literal grading does not replace the prose review below.

## Frozen coverage

The [manifest][manifest] schedules **48 sessions in six cumulative lifecycles**, with 72 blocked candidate slots. Each lifecycle has eight fresh sessions. The archive contains 276 source files; every archived hash matched its manifest entry and the current file at this audit.

| Candidate                    | Scored sessions planned | Frozen condition                                                                |
| ---------------------------- | ----------------------: | ------------------------------------------------------------------------------- |
| Claude Code / Sonnet 4.6     |                      24 | Cache and image export isolated; cache with normal native-memory default        |
| Codex / GPT-6 Astra          |                      24 | Same task/mode schedule; configured high reasoning effort and fast service tier |
| Gemini CLI                   |     0; 24 slots blocked | Existing provider authentication reports depleted prepayment credits            |
| OpenCode / local Qwen3 Coder |     0; 24 slots blocked | Matched input was observably truncated; intact task delivery did not qualify    |
| Copilot CLI                  |     0; 24 slots blocked | Installed launcher cannot find the actual CLI executable                        |

OpenCode's failure is a context-delivery blocker, not a measured failure to adopt memory. Its [diagnostic][context] records a 7,301-token request reduced to 2,050 tokens. Reducing the tool set still did not fit the observed input allowance. Gemini did not complete an inference session, and finding a Copilot launcher did not establish that the CLI or an executed model was available.

The [verification record][verification] retains the initial Black formatting failure separately from its passing behavioral/type checks. Its subsequent formatting supplement passed full Black, affected-file Ruff and strict mypy, and the macOS login-shell test. The original 407 focused behavioral tests passed. These checks did not run the unrelated full Python runtime suite again.

## Completed and missing evidence

| Lifecycle                    | Recorded / planned | Exact artifacts | Accepted writes / observed reads | Whole history preserved                                 |
| ---------------------------- | -----------------: | --------------: | -------------------------------: | ------------------------------------------------------- |
| Claude isolated cache        |              8 / 8 |           8 / 8 |                           4 / 12 | No: revision rewrote title                              |
| Claude normal cache          |              8 / 8 |           8 / 8 |                           4 / 12 | No: revision rewrote title                              |
| Claude isolated image export |              8 / 8 |           8 / 8 |                           3 / 12 | Yes                                                     |
| Codex isolated cache         |              8 / 8 |           8 / 8 |                           3 / 14 | Yes                                                     |
| Codex normal cache           |              8 / 8 |           8 / 8 |                           3 / 14 | Yes                                                     |
| Codex isolated image export  |              4 / 8 |           4 / 4 |                            3 / 8 | Unchanged through revision; remaining stages unobserved |

All 44 artifacts, current contracts, and historical JSON contracts are exact. Forty-three sessions have a known successful literal handoff; the remaining revision has correct files and memories but unknown receipt attribution. Its revised direct reuse, revised search, supplied reproduction, and historical reproduction did not run. They remain unobserved, alongside the 72 candidate slots blocked before this cohort.

All **27 observed necessary reproduction stages** returned the complete correct contract through direct recall before the first exact `config.json` Write. This includes **11 search stages** in which a successful matching search result preceded issuing the full recall. The other 16 were direct or historical lookups. These are actual completed tool sequences, not credit for attempted command syntax. Search followed by recall does not prove that the search caused key selection.

Before revision, current and historical values are identical: Claude sometimes selected `.v1`, and Codex read both versions. Those stages alone cannot establish version discrimination. The ten completed revised reuse stages and five completed historical reproductions correctly distinguished current v2 from historical v1. The corresponding three Codex image stages remain unobserved.

## Source fidelity and historical mutation

The manual review covered **six initial captures and six permanent revisions**, including all surrounding approved-record prose. The contracts retain project/scope, exact fields, types, values, applicable units, and supplied source labels. I found no unsupported rationale or fabricated approval provenance. Codex's source descriptions sometimes include the actual assigned task identifier; those identifiers match the prompts. They are attribution labels, not tested durable citation links: old tasks and their source text do not transfer in this experiment.

Two Claude cache revisions nonetheless overwrite the historical note's first line. Both retain the original source label and exact v1 JSON. The complete-body preservation instruction fails in these cases:

| Case           | Before                                                                                                                                                                     | After                                                                                               |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Isolated cache | “Catalog API response cache — historical snapshot v1. This record must not be changed even if the current agreement is revised.”                                           | “Catalog API response cache — approved contract (v1 historical snapshot, unchanged).”               |
| Normal cache   | “Catalog API response cache — historical snapshot v1 (immutable). DO NOT modify this record if the current agreement is revised; update cache.catalog-api.config instead.” | “Catalog API response cache — approved configuration contract (v1 historical snapshot, unchanged).” |

The [isolated revision assessment][claude-revise] and [normal revision assessment][claude-normal-revise] correctly keep literal handoff success separate from `historical_body_preserved: false`. “Unchanged” is supportable for the JSON values, but false for the entire body. Each revision makes two accepted writes where only the current-key write is required. Claude image and all three observed Codex revisions preserve historical bytes. This supports protecting historical records mechanically; adding the explicit preservation sentence did not make preservation universal.

## Attribution halt and command overhead

The first Codex image lifecycle stops after revision because its Python helper uses `subprocess.run(..., capture_output=True).stdout`, discarding stderr and its execution markers. Four successful raw recalls lack a marker in any completed host result. The agent explicitly forwards the write's stderr and prints the newly recalled current body. The revised artifact, saved current contract, and historical body are correct. The [tool trace][codex-revise], [raw receipts][codex-raw], and [halt record][codex-halt] preserve this measurement limitation without repairing attribution or repurchasing the remaining stages.

Across the cohort, **233 execution markers** match actual host tool results. Raw receipts record **77 read invocations**: 72 successful observed reads, four marker-unmatched reads, and one known missing-key probe before Codex's initial cache capture. That probe returns “No memory with key”; the agent subsequently creates and successfully reads both required records. Missing-key probing is not counted as content retrieval.

All **32 observed reproduction stages** make zero accepted memory writes and leave the memory map unchanged. All **five fully supplied controls** make zero agent memory reads as well. There are 20 accepted writes overall: 12 intentional initial current/history writes, six required current revisions, and two unwanted historical rewrites. No additional memory keys are created.

Additional reads are not automatically unnecessary work. Codex's three initial searches read both matching versions; its completed cache revisions read current and historical records before and after updating the current contract. Comparing historical bodies can legitimately verify preservation. The table reports actual observed read counts rather than assigning a waste penalty. No completion guards run here. Ordinary initialization and export queries remain outside agent memory-call counts, so zero guard queries does not mean zero harness work.

## Native memory and evidence integrity

All 24 Claude native snapshots are empty, including the eight normal-mode sessions. All 20 Codex snapshots contain only `memories_1.sqlite`; immutable, read-only inspection finds **zero `stage1_outputs` and zero `jobs` rows** in every snapshot. The database has migration scaffolding, not semantic memory records. No native duplicate capture or native use was observed. This does not establish that native memory never competes with Beads in an established user environment.

Independent re-analysis verifies actual Beads snapshot and native-file carryover, archived source hashes, unique session identities, actual model evidence, and raw receipt correlation. No configuration files, old task records, or repaired targets were transferred. The source archive contains the 276 pinned files; the final export hashes the evidence it consumed. All model execution and prior evidence remain preserved. Claude's 24 sessions report about **$1.5945 in CLI usage estimates**; Codex's 20 sessions have unknown dollar costs. Unknown is not zero or an additional billing claim.

## Boundaries for the final comparison

Only **two host/model combinations** qualified for scored lifecycles. Host and model differ together. Claude deliberately retains the preceding experiment's Sonnet anchor rather than the user's configured Claude model; Codex uses its configured model and reasoning effort. Costs, context capacity, and enforceable resource limits are not matched.

“Normal” means each host's installed native-memory default inside fresh isolated state. Claude's automatic memory is enabled there; Codex's installed memory feature remains off by default. The Codex mode comparison therefore cannot estimate the effect of enabling native memory. Neither condition imports the operator's personal history.

The workflow is strongly instructed and adds source-fidelity and whole-history-body preservation guidance. It tests faithful execution of an explicit handoff workflow, not spontaneous recognition of useful lessons. The two isolated domains and one normal cache lifecycle per host remain a small synthetic sample with correlated stages. The store is legacy `bd` key/value memory; the proposed new Memory bead type is not under test. Prior experiment and preflight outcomes must remain separate from this cohort.

[manifest]: ../memory-bench/results/memory-routes/2026-09-06-hosts-01/manifest.json
[context]: ../memory-bench/results/memory-routes/2026-09-06-host-context-diagnostic-01/REPORT.md
[verification]: ../memory-bench/results/memory-routes/verification-hosts-2026-09-06-01/SUMMARY.md
[report]: ../memory-bench/results/memory-routes/2026-09-06-hosts-final-analysis-01/report.md
[analysis]: ../memory-bench/results/memory-routes/2026-09-06-hosts-final-analysis-01/analysis.json
[claude-revise]: ../memory-bench/results/memory-routes/2026-09-06-hosts-01/cases/claude-isolated-cache/revise/assessment.json
[claude-normal-revise]: ../memory-bench/results/memory-routes/2026-09-06-hosts-01/cases/claude-normal-cache/revise/assessment.json
[codex-revise]: ../memory-bench/results/memory-routes/2026-09-06-hosts-01/cases/codex-isolated-image_export/revise/tool-calls.json
[codex-raw]: ../memory-bench/results/memory-routes/2026-09-06-hosts-01/cases/codex-isolated-image_export/revise/raw-receipts.json
[codex-halt]: ../memory-bench/results/memory-routes/2026-09-06-hosts-01/cases/codex-isolated-image_export/halt.json
