# Memory lifecycle trace audit — 2026-09-06

All three arms completed four of four cumulative lifecycles with correct configurations at every stage. The added selective instructions and workflow checks showed **no incremental correctness benefit in this run**. They also did not eliminate rewriting of historical prose. These findings describe four paired synthetic tasks per arm, not a production reliability estimate.

This audit reviewed the actual tool traces, memory snapshots, source prompts, carryover, and checked-arm events from [the frozen run][manifest], alongside the [aggregate results][aggregate]. It distinguishes the experiment's literal JSON endpoint from fidelity of the surrounding note and from the work performed by the guard.

## Observed behavior

Each lifecycle had eight fresh sessions: establishment, direct reuse, search reuse, permanent revision, revised direct reuse, revised search reuse, supplied reproduction, and historical reproduction. The twelve lifecycles produced 96 distinct session identities. Actual session settings disabled native automatic memory; native file counts were zero. No session hit a behavioral limit.

| Observation                                                         | Existing protocol | Selective guidance | Selective + checks |
| ------------------------------------------------------------------- | ----------------: | -----------------: | -----------------: |
| Complete successful lifecycles                                      |               4/4 |                4/4 |                4/4 |
| Correct final configurations                                        |             32/32 |              32/32 |              32/32 |
| Reuse sessions reading the correct full payload before config Write |             20/20 |              20/20 |              20/20 |
| Supplied reproductions with zero agent memory calls                 |               4/4 |                4/4 |                4/4 |
| Agent memory reads                                                  |                48 |                 48 |                 50 |
| Accepted memory writes                                              |                16 |                 15 |                 14 |
| Historical bodies rewritten during revision                         |               4/4 |                3/4 |                2/4 |

The reuse denominator includes direct, search, revised direct, revised search, and historical stages. These 60 sessions read relevant content before creating the configuration. Revision sessions recalled the old canonical configuration before changing it. A revised payload read after saving that new payload is a readback, not evidence of discovering a previously stored revision.

Establishment created the two explicitly requested records: current agreement and named `.v1` history. Those writes are intentional snapshots, not duplicate capture. All subsequent noncapture stages left memory unchanged. Every actual snapshot carried forward exactly; there were no repaired targets, extra aliases, removed records, or changes to the five unrelated project decoys. Historical reproduction used v1 successfully while current memory retained v2.

All arms received common prompts explicitly identifying reproduction as an existing agreement rather than a new one. Consequently, the absence of replay writes cannot be attributed to the selective treatment: the old protocol also avoided them. Compared with the preceding experiment, task wording and lifecycle context changed along with the tested instructions.

## Correct JSON did not preserve the historical note

Nine revision sessions rewrote the existing `.v1` body even though only the canonical agreement needed updating:

| Domain       | Existing  | Selective | Checked   |
| ------------ | --------- | --------- | --------- |
| Cache        | Rewritten | Preserved | Preserved |
| CSV export   | Rewritten | Rewritten | Preserved |
| Image export | Rewritten | Rewritten | Rewritten |
| Logging      | Rewritten | Rewritten | Rewritten |

All nine retained the original v1 JSON and source label but changed prose. None recalled the historical body before replacing it; they recalled the still-v1 canonical record and regenerated the archive. These are extra writes to existing keys, not additional aliases or within-session repeated writes to one key. They do not fail the frozen primary endpoint, which checks configuration content and allowed keys rather than historical body immutability.

Three concrete source-fidelity findings matter:

- **Selective image export propagated an unsupported explanation into history.** The initial current note added “not conventional default” to `quality=72`; the initial history note omitted it. The revision rewrote history and introduced that aside there, although the source did not establish a conventional default. Compare [establishment][image-selective-initial], [revision][image-selective-revision], and the [revision trace][image-selective-trace].
- **Selective logging attributed an added comparison to supplied facts.** Both initial notes placed “not the conventional \"info\" default” under “Field notes (supplied facts).” The approved contract supplied `level: "error"`, not a default comparison. Revision removed the comparison from both notes. Rewriting can remove unsupported prose as well as propagate it; the issue is uncontrolled alteration of a historical source record. See [initial notes][logging-selective-initial] and [revised notes][logging-selective-revision].
- **Existing image export supplied an unstated range.** Its notes described quality as compression quality on a “0–100 scale.” That may be a reasonable domain assumption, but the approval did not specify an encoder or range. It is an inference, not a verified sourced fact. See [initial notes][image-existing-initial].

Source labels consistently distinguished initial v1 from permanently revised v2. Those plain labels are not resolvable citations to the originating approval or transcript. Literal JSON success therefore establishes neither the truth of every sentence nor verifiable source attribution.

## The guard performed work without intervening

The checked arm recorded 32 successful close checks and 32 successful host Stop checks, with zero denials and zero corrected sessions. Per-leg event files, configured Stop hooks, and recorded tool calls support real host execution; the traces do not show agents manually invoking the Stop script. Stop events lack the Bash tool attribution fields, so they should not be described as individually attributed model tool calls.

The guard issued **64 whole-memory `memories --json` snapshots plus 32 task queries**, totaling 96 administrative queries and 25.8245 observed check-seconds. These are separate from the table's agent memory calls and are not evidence that the model saw those snapshots. Even the four supplied controls incurred eight whole-memory snapshots and four task queries, after acting, despite zero agent memory reads or writes.

The checked arm made fewer memory writes than existing but two more reads: both totaled 64 agent memory operations, before guard overhead. This small paired sample does not establish an efficiency improvement.

The comparison also bundles additional workflow guidance, knowledge that checks exist, and enforcement. Anticipation could affect behavior, but no observed denial demonstrates a recovery benefit. Constructed negative controls establish mechanical rejection behavior separately; they are not live agent failures within these 96 sessions.

The close/Stop guard checks actual artifact-to-memory consistency and public procedural obligations. It neither prevents every side effect nor enforces historical body immutability or zero duplicates. A wrong-but-consistent configuration can pass it; the separate hidden artifact oracle supplies the correctness test. Scratch receipts and hooks are not a tamper-proof security boundary.

## What this supports

The existing explicit protocol worked through capture, lookup, search, a clearly permanent revision, and requested historical reproduction under these conditions. No additional correctness gain was observed from either added package. This is a ceiling result, not evidence of equivalence or that checks cannot help elsewhere.

The conditions remain narrow: four typed configuration templates, one seed and model, explicit knowledge of what survives a fresh session, a small decoy store, and explicitly named historical snapshots. The tested store was legacy `bd` 1.2.1 key/value memory. The proposed new Memory bead type was absent, native automatic memory was disabled, and manual `.v1` keys did not exercise a native history feature. The run does not establish autonomous selection of what deserves memory, general freeform semantic fidelity, source verification, or reliability across real projects and models.

The strongest unresolved trace finding is that successful retrieval and exact task output can coexist with unnecessary historical rewrites and unsupported prose. Preserve that distinction when deciding what “reliable memory” means.

[manifest]: ../memory-bench/results/memory-routes/2026-09-06-lifecycle-02/manifest.json
[aggregate]: ../memory-bench/results/memory-routes/2026-09-06-lifecycle-final-analysis-02/report.md
[image-selective-initial]: ../memory-bench/results/memory-routes/2026-09-06-lifecycle-02/cases/memory-lifecycle-image_export-seed-20260907-selective/establish/memory.json
[image-selective-revision]: ../memory-bench/results/memory-routes/2026-09-06-lifecycle-02/cases/memory-lifecycle-image_export-seed-20260907-selective/revise/memory.json
[image-selective-trace]: ../memory-bench/results/memory-routes/2026-09-06-lifecycle-02/cases/memory-lifecycle-image_export-seed-20260907-selective/revise/stream.jsonl
[logging-selective-initial]: ../memory-bench/results/memory-routes/2026-09-06-lifecycle-02/cases/memory-lifecycle-logging-seed-20260907-selective/establish/memory.json
[logging-selective-revision]: ../memory-bench/results/memory-routes/2026-09-06-lifecycle-02/cases/memory-lifecycle-logging-seed-20260907-selective/revise/memory.json
[image-existing-initial]: ../memory-bench/results/memory-routes/2026-09-06-lifecycle-02/cases/memory-lifecycle-image_export-seed-20260907-existing/establish/memory.json
