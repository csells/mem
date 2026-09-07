# Memory route trace audit — 2026-09-06

Independent review of completed session traces, captured memory, final artifacts,
and receipt-backed results. All 16 main case summaries equal their four saved leg
results. The main comparison is
[main-02](../memory-bench/results/memory-routes/2026-09-06-main-02/manifest.json);
earlier pilots had different carryover instructions and are not pooled.

| Main outcome                                   |                                     Examples, 8 cases | Protocol, 8 cases |
| ---------------------------------------------- | ----------------------------------------------------: | ----------------: |
| Establish sessions with accepted memory writes |                                                     4 |                 8 |
| Exact complete JSON captured                   | 0; 4 prose representations ungraded by literal oracle |                 8 |
| Direct goal artifact exact                     |                                                     0 |                 8 |
| Search goal artifact exact                     |                                                     0 |                 8 |
| Complete-specification control artifact exact  |                                                     8 |                 8 |
| Controls reading memory before writing config  |                                                     0 |                 0 |
| Additional memory keys created by controls     |                                                     0 |                 8 |

## What actually failed

Examples omitted memory entirely for backups, CSV export, deployment, and image
export. Their direct and search goals could not find the missing agreement and
produced no configuration. Refusing to invent missing values is appropriate;
capture was the failed prerequisite.

Cache, logging, report formatting, and retry queue each received an accepted
canonical-key prose note. These notes retained all five domain settings. Both goal
routes retrieved them, then produced flat configurations that omitted the original
nesting. They failed exact artifact grading at the root object. This is information
loss during capture/reconstruction, not absence of storage or failed retrieval.
See the [cache note](../memory-bench/results/memory-routes/2026-09-06-main-02/cases/cache-seed-20260906-examples/establish/memory.json)
and [direct artifact](../memory-bench/results/memory-routes/2026-09-06-main-02/cases/cache-seed-20260906-examples/direct/workspace/config.json).

Protocol preserved the full approved JSON in all eight cases. All 16 necessary
goal sessions retrieved the complete contract before writing and produced exact
artifacts. Search normally found a preview, then recalled its matching key; an
ungraded preview is not a failed search-to-lookup sequence.

## Control overhead and prose fidelity

All eight protocol controls wrote the supplied configuration first, then saved a
second copy under another key and read it back. These reads were verification of
new writes, not unnecessary retrieval before acting. Seven extra keys used current
task IDs; image export used another project key. The capture trigger needs a
distinction between a new agreement and reproducing an existing one. The
[CSV control stream](../memory-bench/results/memory-routes/2026-09-06-main-02/cases/csv_export-seed-20260906-protocol/unnecessary/stream.jsonl)
shows Write on line 9, remember on line 14, recall on line 16.

All supplied project values in the eight protocol establish notes were correct.
Seven notes cite task IDs, all matching their actual assigned establish task; no
invented task ID was found. Those references identify the session task, but the
task records themselves have empty descriptions: they are not independently
resolvable citations to the supplied contract. Cache adds “not conventional
60/3600” and deployment calls timeout 35 “not a conventional default.” Neither
claim comes from the supplied agreement. They did not change the artifacts, but
literal JSON grading does not certify surrounding explanations or provenance.

## Bounded follow-ups

- [CSV challenge](../memory-bench/results/memory-routes/2026-09-06-csv-01/manifest.json):
  all four actual CSV artifacts and configurations pass. This tests applying
  retrieved settings, current overrides, and historical intent from one successful
  capture. It does not test selecting among stored historical versions. “For
  today's export” makes the unchanged standing memory in the current leg an
  ambiguous update signal, not a preregistered memory-update failure.
- [Schema control](../memory-bench/results/memory-routes/2026-09-06-schema-01/manifest.json):
  unchanged cache prose plus the output schema produces an exact direct artifact.
  Search recovers all five settings but writes project `Catalog API` instead of
  `catalog-api`. Both observe the full prose. An auxiliary equality check wrongly
  rejected the CLI's added terminal newline; the
  [correction sidecar](../memory-bench/results/memory-routes/2026-09-06-schema-01/measurement-correction.json)
  preserves original results and corrects only that flag. Artifact grades stand.
- [Permanent update](../memory-bench/results/memory-routes/2026-09-06-update-01/run/result.json):
  an explicit permanent revision, same-key persistence, and verification instruction
  yield correct revised canonical memory and configuration. A fresh goal recovers
  the changed configuration exactly. This is one instructed update chain.

## Claim boundary

These are eight paired synthetic contracts on one model using legacy bd memory
KV. The three goal branches share each establish capture; they are not independent
adoption trials. Native memory is disabled in the main comparison, and the tested
protocol bundles capture triggers, fidelity, naming, verification, and retrieval
guidance. The results support that complete protocol on these tasks, without
isolating its essential clause or demonstrating a new memory bead type, general
production reliability, or superiority to native memory. They justify preserving
exact identifiers and required structure, explicit durable-change events, stable
references, and selective capture before considering more infrastructure.
