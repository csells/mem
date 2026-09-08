# Completed policy-handoff cohort

All 264 frozen slots were started and assessed once. No scored session was
retried, replaced, repaired, or given changed conditions.

| Outcome                                        | Main comparison | Separate normal check |
| ---------------------------------------------- | --------------: | --------------------: |
| Assessed sessions                              |         240/240 |                 24/24 |
| Correct accumulated artifacts                  |         185/240 |                 18/24 |
| Passing hidden cases                           |   17,947/19,220 |           1,227/1,360 |
| Strict core handoffs                           |           11/40 |                   3/4 |
| Successful prior-record use                    |          58/120 |                  9/12 |
| Excluding post-test confirmation: strict / use |   10/40; 57/120 |             2/4; 8/12 |
| Duplicate captures in supplied controls        |            0/40 |                   0/4 |

The main strict results are 2/20 generic and 9/20 occasions. Artifact correctness
is 95/120 generic and 90/120 occasions. Better observed memory adoption therefore
does not establish better overall software correctness. The strict core outcome
does not certify every retained sentence or procedural claim.

Read the [full report](../../../../../specs/memory-policy-handoff-results-2026-09-07.md)
for setup, exact CLI/model coverage, semantic definitions, alternate sources,
timing, costs, failures, native-memory limitations, and ranked recommendations.

- [Mechanical summary](mechanical.json) preserves all planned denominators.
- [Semantic summary](semantic.json) links all 44 lifecycle audits, separates main
  and normal modes, and recomputes every strict intersection.
- [Integrity audit](integrity.json) checks frozen inputs, prompts, actual retained
  records, catalogs and receipts across all 264 sessions.
- [Workflow counts](workflow-counts.json) and [command feedback](command-feedback.json)
  are diagnostics, not success scores.

Analysis scripts are in `../analysis-tools/`. They read saved evidence and do not
invoke agents. Their output files are exclusive: use a new output path for a new
analysis rather than overwriting a previous result. All earlier checkpoints and
audit corrections remain preserved.
