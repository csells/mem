# bd memory experiment

Scheduled pairs: 96. Manifest: `c69fa64acddb6c6c`.

| Condition | Variant | Complete / scheduled | Handoff yes / no / unknown | Goal yes / no / unknown |
|---|---|---:|---:|---:|
| generic | necessary | 16 / 16 | 0 / 16 / 0 | 16 / 0 / 0 |
| generic | unnecessary | 16 / 16 | 0 / 16 / 0 | 16 / 0 / 0 |
| explicit | necessary | 16 / 16 | 8 / 8 / 0 | 14 / 2 / 0 |
| explicit | unnecessary | 16 / 16 | 2 / 14 / 0 | 14 / 2 / 0 |
| redirect | necessary | 16 / 16 | 12 / 4 / 0 | 12 / 4 / 0 |
| redirect | unnecessary | 16 / 16 | 1 / 15 / 0 | 15 / 1 / 0 |

Unknown outcomes are retained in the JSON scheduled-denominator bounds.

| Treatment minus baseline | Variant | Endpoint | Difference | Cluster bootstrap 95% | Task clusters |
|---|---|---|---:|---|---:|
| explicit minus generic | necessary | handoff | 0.5 | [0.1875, 0.8125] | 8 |
| explicit minus generic | necessary | goal_action_success | -0.125 | [-0.25, 0.0] | 8 |
| explicit minus generic | unnecessary | handoff | 0.125 | [0.0, 0.3125] | 8 |
| explicit minus generic | unnecessary | goal_action_success | -0.125 | [-0.375, 0.0] | 8 |
| redirect minus generic | necessary | handoff | 0.75 | [0.375, 1.0] | 8 |
| redirect minus generic | necessary | goal_action_success | -0.25 | [-0.625, 0.0] | 8 |
| redirect minus generic | unnecessary | handoff | 0.0625 | [0.0, 0.1875] | 8 |
| redirect minus generic | unnecessary | goal_action_success | -0.0625 | [-0.1875, 0.0] | 8 |
| redirect minus explicit | necessary | handoff | 0.25 | [-0.0625, 0.625] | 8 |
| redirect minus explicit | necessary | goal_action_success | -0.125 | [-0.4375, 0.125] | 8 |
| redirect minus explicit | unnecessary | handoff | -0.0625 | [-0.3125, 0.125] | 8 |
| redirect minus explicit | unnecessary | goal_action_success | 0.0625 | [0.0, 0.1875] | 8 |

| Condition | Variant | bd reads / writes | Unnecessary goal reads | Native reads / writes | CLI estimated USD | Cost-unknown legs |
|---|---|---:|---:|---:|---:|---:|
| generic | necessary | 0.0 / 0.0 | None | 33.0 / 32.0 | 2.0247745 | 0 |
| generic | unnecessary | 0.0 / 0.0 | 0.0 | 21.0 / 32.0 | 1.8967907 | 0 |
| explicit | necessary | 105.0 / 26.0 | None | 37.0 / 12.0 | 2.5635444 | 0 |
| explicit | unnecessary | 29.0 / 40.0 | 16.0 | 22.0 / 4.0 | 2.238101 | 0 |
| redirect | necessary | 162.0 / 41.0 | None | 44.0 / 0.0 | 2.5773369 | 0 |
| redirect | unnecessary | 32.0 / 55.0 | 11.0 | 19.0 / 0.0 | 2.1709423 | 0 |

Endpoints use saved leg evidence; no post hoc transcript rescoring.
Unknown outcomes remain in scheduled bounds; observed rates omit them explicitly.
Bootstrap resamples work IDs retaining matched repeats, twins and conditions.
Bootstrap intervals are descriptive for small task counts, not confirmatory claims.
CLI final-result cost estimates are not billing receipts; missing costs are unknown.
Duration is CLI-reported session duration, not independent wall-clock measurement.
Counters include partial legs as observed lower bounds when transcripts are incomplete.
Hook reaches are differenced within pairs because their saved counts are cumulative.
