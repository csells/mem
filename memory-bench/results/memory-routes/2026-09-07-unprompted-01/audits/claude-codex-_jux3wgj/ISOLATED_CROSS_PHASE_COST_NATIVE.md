The table covers all 48 observed Claude/Codex isolated sessions across checkpoint and continuation. Costs are reported host costs, not a price estimate. Normal-mode runs are still unobserved.

| Host | Phase | Arm | Sessions | Reported USD | Primary / auxiliary USD | Actual native setting | Archived native evidence |
| --- | --- | --- | ---: | ---: | --- | --- | --- |
| Claude | checkpoint | baseline | 6 | 1.0336683 | 1.0279173 / 0.0057510 | autoMemoryEnabled=false | no files |
| Claude | checkpoint | memory | 6 | 1.0415406 | 1.0357716 / 0.0057690 | autoMemoryEnabled=false | no files |
| Claude | continuation | baseline | 6 | 1.6569413 | 1.6511673 / 0.0057740 | autoMemoryEnabled=false | no files |
| Claude | continuation | memory | 6 | 1.6828160 | 1.6770600 / 0.0057560 | autoMemoryEnabled=false | no files |
| Codex | checkpoint | baseline | 6 | unavailable | not reported | generation/use explicitly disabled | 6 SQLite snapshots; generated records 0; jobs 0 |
| Codex | checkpoint | memory | 6 | unavailable | not reported | generation/use explicitly disabled | 6 SQLite snapshots; generated records 0; jobs 0 |
| Codex | continuation | baseline | 6 | unavailable | not reported | generation/use explicitly disabled | 6 SQLite snapshots; generated records 0; jobs 0 |
| Codex | continuation | memory | 6 | unavailable | not reported | generation/use explicitly disabled | 6 SQLite snapshots; generated records 0; jobs 0 |

Claude total: $5.4149662, comprising primary claude-sonnet-4-6 $5.3919162 and auxiliary claude-haiku-4-5-20251001 $0.0230500. Codex identifies gpt-6-astra and reports tokens, but no dollar cost; unavailable does not mean free or zero. No cost-effectiveness inference follows from these small unreplicated groups.

All 24 Claude native directories contain no files. Each of the 24 Codex native snapshots contains a memories_1.sqlite runtime database: stage1_outputs has zero rows and jobs has zero rows. The migration table has initialization data, which is not business-memory capture. No WAL is present. These archived databases were inspected read-only and their hashes verified unchanged. Disabled generation and absent useful records mean these isolated sessions do not measure an enabled native-memory system’s effectiveness.

Both baseline and added Beads-memory arms have the same isolated native settings. Successful Beads captures in continuation are a separate route and must not be counted as native writes. Prior phase reports retain their original evidence and scores.

For the forthcoming normal phase, inspect actual launch settings and native-after files separately for each host. The frozen design enables Claude automatic memory but leaves Codex at its default-off native feature state. That is a design expectation, not yet an observation of a normal session. Native file creation, copied availability, useful capture, actual read, and proven automatic context delivery need separate evidence; their absence or lack of visibility must be stated.

Full per-session settings, native file hashes/table counts, and result/launch source hashes are in isolated-cross-phase-cost-native.json. Existing reports and frozen artifacts were not changed.
