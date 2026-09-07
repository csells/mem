# Memory lifecycle experiment

Source: `/Users/csells/Code/Forks/sjarmak/mem/memory-bench/results/memory-routes/2026-09-06-lifecycle-02`. Model: `claude-sonnet-4-6`.
Observed 96 distinct session identities across 96 planned sessions.
Counts are true/false/unknown and retain every planned session. Whole-lifecycle success requires all eight actual handoffs; passing a procedural check does not establish that the configuration is correct.

| Arm | Lifecycles T/F/? | Initial current + v1 T/F/? | Sessions recorded/planned | Observed cost USD | Cost known/planned | Median seconds |
|---|---|---|---:|---:|---:|---:|
| existing | 4/0/0 | 4/0/0 | 32/32 | 1.8342 | 32/32 | 22.84 |
| selective | 4/0/0 | 4/0/0 | 32/32 | 1.8179 | 32/32 | 23.41 |
| checked | 4/0/0 | 4/0/0 | 32/32 | 1.8831 | 32/32 | 24.14 |

| Arm | Stage | Artifact T/F/? | Current T/F/? | v1 T/F/? | Objective T/F/? | Shadow check T/F/? | Guarded completion T/F/? | Lookup T/F/? | Search T/F/? | Before-Write read T/F/? | Writes | No redundant curation T/F/? |
|---|---|---|---|---|---|---|---|---|---|---|---:|---|
| existing | establish | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/0/4 | 4/0/0 | 0/4/0 | 0/4/0 | 8 | 0/4/0 |
| existing | direct | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/0/4 | 4/0/0 | 0/4/0 | 4/0/0 | 0 | 4/0/0 |
| existing | search | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/0/4 | 4/0/0 | 4/0/0 | 4/0/0 | 0 | 4/0/0 |
| existing | revise | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/0/4 | 4/0/0 | 0/4/0 | 4/0/0 | 8 | 0/4/0 |
| existing | revised_direct | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/0/4 | 4/0/0 | 0/4/0 | 4/0/0 | 0 | 4/0/0 |
| existing | revised_search | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/0/4 | 4/0/0 | 4/0/0 | 4/0/0 | 0 | 4/0/0 |
| existing | supplied | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/0/4 | 0/4/0 | 0/4/0 | 0/4/0 | 0 | 4/0/0 |
| existing | historical | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/0/4 | 4/0/0 | 0/4/0 | 4/0/0 | 0 | 4/0/0 |
| selective | establish | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/0/4 | 4/0/0 | 0/4/0 | 0/4/0 | 8 | 0/4/0 |
| selective | direct | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/0/4 | 4/0/0 | 0/4/0 | 4/0/0 | 0 | 4/0/0 |
| selective | search | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/0/4 | 4/0/0 | 4/0/0 | 4/0/0 | 0 | 4/0/0 |
| selective | revise | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/0/4 | 4/0/0 | 0/4/0 | 4/0/0 | 7 | 0/4/0 |
| selective | revised_direct | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/0/4 | 4/0/0 | 0/4/0 | 4/0/0 | 0 | 4/0/0 |
| selective | revised_search | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/0/4 | 4/0/0 | 4/0/0 | 4/0/0 | 0 | 4/0/0 |
| selective | supplied | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/0/4 | 0/4/0 | 0/4/0 | 0/4/0 | 0 | 4/0/0 |
| selective | historical | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/0/4 | 4/0/0 | 0/4/0 | 4/0/0 | 0 | 4/0/0 |
| checked | establish | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/4/0 | 0/4/0 | 8 | 0/4/0 |
| checked | direct | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/4/0 | 4/0/0 | 0 | 4/0/0 |
| checked | search | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0 | 4/0/0 |
| checked | revise | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/4/0 | 4/0/0 | 6 | 0/4/0 |
| checked | revised_direct | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/4/0 | 4/0/0 | 0 | 4/0/0 |
| checked | revised_search | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0 | 4/0/0 |
| checked | supplied | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/4/0 | 0/4/0 | 0/4/0 | 0 | 4/0/0 |
| checked | historical | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 4/0/0 | 0/4/0 | 4/0/0 | 0 | 4/0/0 |

| Arm | Stage | Same-key repeated writes | Delta added/removed/changed | Correct payload before Write T/F/? | Behavioral limit T/F/? |
|---|---|---:|---|---|---|
| existing | establish | 0 | 8/0/0 | 0/4/0 | 0/4/0 |
| existing | direct | 0 | 0/0/0 | 4/0/0 | 0/4/0 |
| existing | search | 0 | 0/0/0 | 4/0/0 | 0/4/0 |
| existing | revise | 0 | 0/0/8 | 1/3/0 | 0/4/0 |
| existing | revised_direct | 0 | 0/0/0 | 4/0/0 | 0/4/0 |
| existing | revised_search | 0 | 0/0/0 | 4/0/0 | 0/4/0 |
| existing | supplied | 0 | 0/0/0 | 0/4/0 | 0/4/0 |
| existing | historical | 0 | 0/0/0 | 4/0/0 | 0/4/0 |
| selective | establish | 0 | 8/0/0 | 0/4/0 | 0/4/0 |
| selective | direct | 0 | 0/0/0 | 4/0/0 | 0/4/0 |
| selective | search | 0 | 0/0/0 | 4/0/0 | 0/4/0 |
| selective | revise | 0 | 0/0/7 | 0/4/0 | 0/4/0 |
| selective | revised_direct | 0 | 0/0/0 | 4/0/0 | 0/4/0 |
| selective | revised_search | 0 | 0/0/0 | 4/0/0 | 0/4/0 |
| selective | supplied | 0 | 0/0/0 | 0/4/0 | 0/4/0 |
| selective | historical | 0 | 0/0/0 | 4/0/0 | 0/4/0 |
| checked | establish | 0 | 8/0/0 | 0/4/0 | 0/4/0 |
| checked | direct | 0 | 0/0/0 | 4/0/0 | 0/4/0 |
| checked | search | 0 | 0/0/0 | 4/0/0 | 0/4/0 |
| checked | revise | 0 | 0/0/6 | 0/4/0 | 0/4/0 |
| checked | revised_direct | 0 | 0/0/0 | 4/0/0 | 0/4/0 |
| checked | revised_search | 0 | 0/0/0 | 4/0/0 | 0/4/0 |
| checked | supplied | 0 | 0/0/0 | 0/4/0 | 0/4/0 |
| checked | historical | 0 | 0/0/0 | 4/0/0 | 0/4/0 |

| Arm | Close checks | Stop checks | Blocked close / stop | Intervened sessions | Administrative queries | Check seconds observed |
|---|---:|---:|---|---:|---:|---:|
| existing | 0 | 0 | 0 / 0 | 0 | 0 | 0.0000 |
| selective | 0 | 0 | 0 / 0 | 0 | 0 | 0.0000 |
| checked | 32 | 32 | 0 / 0 | 0 | 96 | 25.8245 |

The two requested establishment records are intentional. Reproduction writes remain redundant even if they leave no byte-level delta. Before-Write timing is unknown when no matching Write tool event exists. Guarded completion refers to the final successful Stop check in the checked arm; it is separate from the artifact oracle. Duration-source counts and per-model usage are in analysis.json.

- Synthetic cumulative legacy key/value lifecycles; stages within a lifecycle are correlated.
- Historical v1 is an explicitly requested manual snapshot, not validation of a native history feature or new Memory type.
- Literal JSON grading does not establish semantic reliability of surrounding prose.
- Receipt classifications and before-Write timing reuse the recorded scorer; operation identity/output and payload grades are crosschecked here.
- Procedural checks are diagnostic and are excluded from the objective endpoint.
- CLI costs are observed token-usage estimates, not necessarily additional billed charges.
