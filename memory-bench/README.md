# memory-bench — agentic memory evaluation harness (Phase-1 skeleton)

Python harness that runs one multi-session benchmark sequence under three
evaluation conditions and captures normalized traces plus core metrics.

## What this measures

The harness answers one question per task family: does accumulated memory change
the agent's *action* in a way that improves outcome, efficiency, or reliability
versus a stateless baseline? A task counts only if memory materially affects
execution: choosing the right tool because a prior session established it,
avoiding a known failure mode, applying a project convention set earlier. Pure
"what did I say earlier?" recall, and tasks solvable equally well without memory,
are out of scope by design.


The dataset is not a flat prompt set. Each benchmark item is an ordered
multi-session sequence (Step 1 → … → Step N → Goal). Every step starts with fresh
context; the persistent memory store is the only thing that survives between
steps.

### The three conditions

Each sequence runs under all three, and the gap between them is the signal:

- **no_memory**: memory disabled. The agent gets only the current step's
  context and its non-memory tools. Establishes stateless performance.
- **oracle_memory**: the harness injects the exact relevant memory. Sets the
  ceiling and proves the task is actually memory-sensitive. If oracle ≈
  no_memory, the task doesn't discriminate and gets redesigned.
- **memory_enabled**: the full memory system runs through its normal retrieve,
  write, and consolidation path. This is the real system's score.

The report reads the gaps directly: `oracle > memory > no_memory` means
retrieval or ranking is leaving gains on the table; `memory < no_memory` means
memory is injecting noise or stale state.

### Metrics

Each trial emits a normalized trace and a metrics bundle. Four core families are
live: **task outcome**, **efficiency** (tokens, tool calls, latency, cost,
retries), **retrieval** (precision/recall/rank, plus **Confusion**
(`distractor_retrieval_rate`) and **Staleness** (`stale_memory_retrieval_rate`)
once a query/top-k arm can surface seeded distractors and superseded entries),
and **retention** (write hit/miss, scope, supersession). The **privacy** (DIV-4)
and **interruption** groups now carry deterministic scorer legs as well; their
semantic fields (sensitivity class, derailment magnitude) stay judge seams left
open for the LLM-as-judge phase.

Concrete memory tools differ across systems (filesystem read/write, MCP
`add_memory`/`search_memories`, vector upsert/search), so every invocation maps
through a single canonical operation set (`read`, `write`, `update`, `delete`,
`search`, `consolidate`, `promote`, `forget`, `classify`, `discard`) before it's
scored. That keeps systems comparable.

## The adoption harness

This README covers the retrieval-quality benchmark: given memory, does the agent do
better work? A second harness in this package answers the prior question, whether the
agent reaches for the memory tool at all. Entry point
`membench/runner/bd_experiment.py`; docs, reference results and a one-pair quickstart
in [`../docs/adoption-harness/`](../docs/adoption-harness/README.md).

## Substrate

Harbor is the execution substrate: a framework for running agent evaluations in
containerized environments against agents and models such as Claude Code. This
harness supplies the dataset, the adapters, and the scorers; Harbor runs them.
`harbor/adapter.py` emits real task-dir shapes and writes each trial's reward to
the verifier path Harbor expects.

## What's here

The Phase-1 **skeleton** — the plumbing, proven end-to-end with a deterministic
reference agent and reference memory systems — is the foundation: Harbor
orchestration, schema validation, deterministic memory-op mapping, and
deterministic metric arithmetic. On top of it now sit the competitive arms, the
§12 metric legs, and the synthetic-world eval track that produces the first
measurable lift. Semantic judgment (the trace-to-memory extractor and
LLM-as-judge scoring) is a documented seam left open for later phases.

| area | module |
|---|---|
| conditions | `membench/schemas/conditions.py` (no_memory / oracle_memory / memory_enabled) |
| system model | `membench/schemas/config.py` (experiment / agent / memory configs) |
| sequence | `membench/schemas/sequence.py` (multi-session sequence + steps) |
| memory events | `membench/schemas/memory_event.py` (10 normalized operations) |
| op mapper | `membench/mapper/memory_op_mapper.py` (concrete tool → canonical op) |
| trace | `membench/schemas/trace.py` |
| metrics | `membench/schemas/metrics.py` (task / efficiency / retrieval / retention; privacy + interruption deterministic legs landed, judge seams open) |
| memory systems | `membench/memory_systems/` (arms: none / oracle / filesystem / lexical / **ours** / consolidating / retention_scheduled; competitive mem0 / a-mem / nat / graphiti landed behind a sync client seam; `builtin` → mem-whi) |
| generators | `membench/generators/` (NeMo synthetic-world → enterprise-workflow materializer, synthetic-task, schema-induction, retention-schedule, interruption) |
| LOO guard | `membench/validity.py` (V1 leakage guard — harness-owned D6 boundary) |
| corpus loader | `membench/corpus.py` (real P1.5 store → `WorkRef` corpus via `mem query --json`) |
| runner | `membench/runner/` (`conditions.py` runs one sequence under 3 conditions; `project.py` runs a project of sequences under one shared store for cross-task continuity) |
| replay | `membench/replay.py` + `membench replay` CLI (failure-triggered arms over the work-audit graph, LOO-bounded) |
| telemetry | `membench/telemetry/` (OTel GenAI spans, primary; ATIF, derived) |
| Harbor adapter | `membench/harbor/adapter.py` |
| report | `membench/report/comparison.py` (3-condition table) + `report/arm_vector.py` (per-arm raw 5-axis) + `report/synthetic_arms.py` (per-arm lift / oracle-gap / Confusion / Staleness over synthetic worlds) |

### Three eval modes

The harness carries three complementary eval objects, each with its own runner:

- **Convention sequence** (`runner/conditions.py`): a multi-session sequence
  with id-based memory, run under the three conditions (none / oracle /
  filesystem). Continuity is the persistent store; leak-safety is structural
  (a step reads only what earlier steps wrote).
- **Synthetic-world arms** (`report/synthetic_arms.py`): a NeMo-seeded
  `EnterpriseWorld` is materialized into memory-dependent sequences where memory
  necessity is true by construction (oracle passes, no-memory cannot). Running
  the arms over them gives the first measurable lift on this harness — memory
  NECESSITY (oracle vs none) and, under `run_project`'s shared store, cross-task
  CONTINUITY (0.062 isolated → 0.188 shared). The `lexical` query/top-k arm also
  trips the Confusion / Staleness metrics (non-zero) where the id-exact arms
  match the oracle (zero). Every fact, distractor, and supersession is authored
  in pure Python and seed-reproducible; NeMo supplies only the cast and prose.
- **Replay bead** (`replay.py`): a closed historical bead `B` (Decision 5). The
  `ours` arm = retrieval-v1 (mem-di8) over the work-audit graph, **failure-
  triggered** (Decision 8), under the harness-owned **LOO guard** (`validity.py`,
  Decision 6/11): the retrievable corpus is bounded to records closed strictly
  before `B.started`, minus `B`'s self / convoy / supersedes-chain / shared-PR
  records. No arm picks the boundary, and every arm's output is re-checked against
  the LOO set (`assert_no_leak`). Both Decision-7 tracks (cross-rig, same-rig) are
  reported. The 5-axis report is **raw, never a weighted composite** (fork 2).

`ours` consumes retrieval-v1 through the `mem retrieve --json` CLI, the single
substrate, consuming the append-only `lessons` payload (D9), never re-distilling
and never adding a second store.

## Run

```bash
# In-process, deterministic, no Docker, no paid API — produces the 3-condition report:
python3 -m membench.cli run-sequence \
  fixtures/sequences/gascity_backend_conventions.json --out reports/

# Emit Harbor task dirs for a real `harbor run` (paid Claude path):
python3 -m membench.cli gen-tasks \
  fixtures/sequences/gascity_backend_conventions.json --out tasks/

# Arms over synthetic worlds — measurable lift + Confusion/Staleness, in-process:
#   from membench.generators import materialize_world
#   from membench.report.synthetic_arms import eval_arms_over_sequences, format_report
#   seqs = materialize_world(world, project, n_tasks=2)   # NeMo-seeded world/project
#   res = eval_arms_over_sequences(seqs, ["none", "oracle", "filesystem", "lexical"])
#   print(format_report("synthetic arms", res))

# Replay arms over the REAL P1.5 store under the LOO guard (the caller names the
# query work — the harness never curates the eval target). `--with-traces`
# attaches P1.6 failure signatures so the `ours` arm fires:
( cd .. && npm run build && node bin/mem build-store --with-traces --store .mem/store.db )
python3 -m membench.cli replay \
  --store ../.mem/store.db --work-id <work_id> --arms none,ours --out reports/

# The `ours` arm and the replay CLI run against the real retrieval-v1 CLI, so
# their integration tests need the TS build at the repo root first (they skip
# gracefully if absent):
( cd .. && npm run build )

pytest -q
```

`membench replay` emits the per-arm raw 5-axis report (`replay_report.{json,md}`)
+ OTel GenAI spans (`replay_spans.json`). On a store built `--with-traces`, the
`ours` arm fires (failure-triggered, D8) and the report shows a real ours-vs-none
retrieval delta on the trace-carrying beads. **Lift** itself (and the held-out set
it needs) is a later, eval-design step, deliberately not made here.

## Boundaries

- The agent under test is Claude (Code / Opus / Sonnet / Haiku) on our own
  account via OAuth, the one approved paid path. It runs through the emitted
  Harbor tasks, not in-process. `ScriptedAgent` is the in-process reference agent
  for the skeleton and tests.
- The no-paid-API rule applies to the **memory** stack: backends, embeddings,
  extractor, and judge stay OSS or self-hosted.
- The TypeScript work-audit graph builder in `../src/` is a **data source**. It
  exports sequences and fixtures as JSON; it is not rewritten here.
- **Competitive arms** (see `../docs/competitive-arms-integration.md`): mem0,
  A-MEM, NAT, and Graphiti are all wired behind the sync `SemanticMemoryClient`
  seam (NAT/Graphiti via the `AsyncClientBridge`). CI runs them against
  deterministic fakes; real-arm provisioning is gated on local Ollama/Qdrant/
  Chroma infra. The §12 metric groups and the ≥10-sequence real dataset have
  also landed.
- **Synthetic-world generator landed**: NeMo worlds → enterprise-workflow
  materializer → memory-dependent sequences, verified on a live local NIM and
  frozen behind a determinism manifest. This is what makes the arms-over-
  synthetic lift and the Confusion/Staleness signal measurable.
- **Still open**: a real embedding-retrieval lane for `lexical`/competitive arms
  (the deterministic token-overlap ranker is the current baseline), the
  trace-to-memory extractor, and the LLM-as-judge scoring that fills the
  remaining semantic seams (privacy class, derailment magnitude, synthesis).
