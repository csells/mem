# mem — Agent Operating Notes

> The **intention + failure-mode-prevention** layer for agents working in this repo.
> It holds only what lives nowhere else; everything general is referenced, not copied.
> Keep it under ~120 lines.

## Architecture orientation (LikeC4-derived)

@architecture/exports/orient.md

_A mechanically-derived high-altitude map of this rig's subsystems (from the LikeC4 model). Orient off it — names every container/component, its purpose, delivery state, and exact source path — then targeted-read the files it points at instead of grep-walking. Regenerated daily by the city `likec4-orient-refresh` order; for symbol-level depth hand a source link to an Explore/CodeGraph agent._

## What this project is

`mem` turns the dolt bead spine plus agent transcripts into a queryable
work-audit graph, so retrieval and the memory-bench eval can learn from past
work without leaking answers. Invariants that must hold:

- **The work-audit graph is the source of truth.** SQLite + FTS5 sidecar at
  `.mem/store.db` (`src/cli/store.ts`), schema version `SCHEMA_VERSION`
  (`src/store/schema.ts`). Every projected column is rebuilt from the
  `work_records.record` JSON on upsert; never write projections directly.
- **Three tables are append-only and non-regenerable** — `lessons`,
  `memory_events`, and producer-source `provenance_events` — deliberately no
  foreign key to `work_records`; lesson citations are snapshotted at append
  time, never joined live (`src/store/schema.ts`). There is no in-place schema
  migration: a version bump means rebuilding from the bead spine, and a rebuild
  cannot regenerate these tables. Rebuild with `mem rebuild`, which round-trips
  all three mechanically (export-all → fresh build → import-all); the manual
  pairs `export/import-lessons`, `export/import-memory-events`, and
  `export/import-provenance-events` remain for surgical use
  (README §Building the store).
- **Deterministic signal is mechanical, never model judgment.** Build/test/lint
  outcomes are parsed from tool output by runner matching
  (`src/parse/runners.ts`) and format-anchored `file:line` extractors
  (`src/parse/error-extractors.ts`). Do not add semantic/keyword heuristics to
  this layer; the model is reserved for semantic annotation only (task-type
  residue classification, root-cause extraction).
- **Temporal leave-one-out is load-bearing for eval validity.** Retrieval only
  sees records closed strictly before the target work started (the reader's
  strict `closedBefore` in `src/store/reader.ts`) and excludes convoy
  siblings, PR/branch sharers (`src/retrieve/exclusions.ts`), and supersedes
  chains via the reader's recursive closure. Weakening any exclusion leaks the
  answer into the eval context.
- **Trace resolution depends on the working directory.** `--with-traces`
  shells `gc session logs` (`src/ingest/trace-resolve.ts`), which loads
  `city.toml` from the cwd; run full rebuilds from `/home/ds/gas-city`.
  Gotcha: run from this repo, a missing `city.toml` exits 0 with zero traces
  resolved; no error is raised. Default (flagless) builds are spine-only and
  fast; keep them that way.
- **CLI contract:** the entrypoint is `./bin/mem` (runs `dist/`, so build
  first); `--json` emits the envelope `{apiVersion, cmd, ok, data?, errors?}`
  (`src/schemas/envelope.ts`).

## Quality gates

CI (`.github/workflows/ci.yml`) and `.pre-commit-config.yaml` mirror each
other; run the gates green before claiming done:

- Python (`memory-bench/`): `ruff check`, `black --check`, `mypy --strict`,
  `pytest`
- TypeScript (root): `npm run check` = `tsc --noEmit` + eslint + prettier
  `--check` + vitest

## Failure-mode preventions

<!-- Append-only log of "don't do X here, it breaks Y" lessons from real incidents.
     One line each: the prevention, then the consequence it avoids. -->

- **Never read a non-zero git exit as an answer.** Only `merge-base
  --is-ancestor` exit 1 means "not an ancestor"; 128/ENOENT/signal are faults,
  not verdicts. Use `provenance.ts`'s `isAncestor` / `isAncestorOrNull`, never a
  fresh `try/catch` around the git call — a swallowed 128 fabricates a verdict
  in the very gate built to catch fabrications. (Cost is realized: the
  swallow-128 defect was fixed twice — 0985d82 in `landedContent`, then 77bacd0
  under mem-y2x7n — after the guard had been re-derived into three hand-rolled
  copies that mem-y2x7n finally collapsed into `provenance.ts`.)
- **Never feed a shell loop's worklist on stdin when its body launches agents or
  subprocesses.** Bind the worklist to a dedicated file descriptor and redirect
  child stdin, or the first child can consume the remaining rows and make a
  multi-group run exit 0 after one group.
- **Never leave real tools on PATH when testing a replacement executable.** A
  broken shebang can make shell lookup fall through to the real tool and mutate
  live data; restrict the child PATH to test binaries and use a temporary cwd.

## Where to look (references)

- **Why work records, pipeline, data model, store-building:** `README.md`
- **System design:** `ARCHITECTURE.md`
- **Decision records (oracle curation, gate verdicts):** `docs/`
