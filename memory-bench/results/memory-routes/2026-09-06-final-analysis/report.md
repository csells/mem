# Memory-route experiment report

Each run is reported separately. Counts marked T/F/? retain scheduled denominators; missing sessions and unsupported representations are unknown, not failures. The three goal routes share one capture and are not independent trials.

Artifact success checks the actual final JSON. Literal capture/payload checks do not judge surrounding prose. Exact-key and any-key capture are derived from the saved establish memory snapshot using the run's pinned grader; the original case verdict remains in JSON. Native capture stays unknown because that snapshot covers bd only. Other saved scores are aggregated without recomputation.

Before-Write timing is unknown without a matching Write tool event. CLI costs are subscription token-usage estimates, not additional billed dollars; missing costs are reported separately. Durations are per-session elapsed times.

## 2026-09-06-main-02

Source: `/Users/csells/Code/Forks/sjarmak/mem/memory-bench/results/memory-routes/2026-09-06-main-02`. Model: `claude-sonnet-4-6`; CLI: `2.1.263 (Claude Code)`; bd: `bd version 1.2.1 (Homebrew)`.

| Policy | Complete/planned | Halted | Incomplete | Pending | Exact-key capture T/F/? | Any-key capture T/F/? | Observed cost USD | Cost sessions known/planned | Median seconds |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| examples | 8/8 | 0 | 0 | 0 | 0/4/4 | 0/4/4 | 1.5256 | 32/32 | 21.31 |
| protocol | 8/8 | 0 | 0 | 0 | 8/0/0 | 8/0/0 | 1.8270 | 32/32 | 25.85 |

| Policy | Goal | Recorded/planned | Artifact T/F/? | Lookup used T/F/? | Search used T/F/? | Correct payload T/F/? | Correct via lookup T/F/? | Correct via search T/F/? |
|---|---|---:|---|---|---|---|---|---|
| examples | direct | 8/8 | 0/8/0 | 4/4/0 | 4/4/0 | 0/0/8 | 0/4/4 | 0/4/4 |
| examples | search | 8/8 | 0/8/0 | 8/0/0 | 8/0/0 | 0/0/8 | 0/4/4 | 0/3/5 |
| examples | unnecessary | 8/8 | 8/0/0 | 0/8/0 | 0/8/0 | 0/8/0 | 0/8/0 | 0/8/0 |
| protocol | direct | 8/8 | 8/0/0 | 8/0/0 | 0/8/0 | 8/0/0 | 8/0/0 | 0/8/0 |
| protocol | search | 8/8 | 8/0/0 | 8/0/0 | 8/0/0 | 8/0/0 | 8/0/0 | 0/0/8 |
| protocol | unnecessary | 8/8 | 8/0/0 | 8/0/0 | 0/8/0 | 8/0/0 | 8/0/0 | 0/8/0 |

| Policy | Goal | Any read before Write T/F/? | Correct payload before Write T/F/? | Observed cost USD | Median seconds |
|---|---|---|---|---:|---:|
| examples | direct | 4/0/4 | 0/0/8 | 0.3344 | 21.40 |
| examples | search | 4/0/4 | 0/0/8 | 0.4549 | 25.90 |
| examples | unnecessary | 0/8/0 | 0/8/0 | 0.3540 | 18.00 |
| protocol | direct | 8/0/0 | 8/0/0 | 0.3952 | 21.72 |
| protocol | search | 8/0/0 | 8/0/0 | 0.4344 | 22.57 |
| protocol | unnecessary | 0/8/0 | 0/8/0 | 0.4934 | 27.36 |

| Task | Policy | Case state | Exact-key capture | Any-key capture | Direct artifact | Search artifact | Supplied control artifact |
|---|---|---|---|---|---|---|---|
| csv_export-seed-20260906 | examples | complete | fail | fail | fail | fail | pass |
| cache-seed-20260906 | protocol | complete | pass | pass | pass | pass | pass |
| csv_export-seed-20260906 | protocol | complete | pass | pass | pass | pass | pass |
| retry_queue-seed-20260906 | protocol | complete | pass | pass | pass | pass | pass |
| backups-seed-20260906 | examples | complete | fail | fail | fail | fail | pass |
| image_export-seed-20260906 | examples | complete | fail | fail | fail | fail | pass |
| report_format-seed-20260906 | protocol | complete | pass | pass | pass | pass | pass |
| cache-seed-20260906 | examples | complete | ? | ? | fail | fail | pass |
| logging-seed-20260906 | examples | complete | ? | ? | fail | fail | pass |
| report_format-seed-20260906 | examples | complete | ? | ? | fail | fail | pass |
| deployment-seed-20260906 | examples | complete | fail | fail | fail | fail | pass |
| deployment-seed-20260906 | protocol | complete | pass | pass | pass | pass | pass |
| logging-seed-20260906 | protocol | complete | pass | pass | pass | pass | pass |
| image_export-seed-20260906 | protocol | complete | pass | pass | pass | pass | pass |
| retry_queue-seed-20260906 | examples | complete | ? | ? | fail | fail | pass |
| backups-seed-20260906 | protocol | complete | pass | pass | pass | pass | pass |

## 2026-09-06-pilot-01

Source: `/Users/csells/Code/Forks/sjarmak/mem/memory-bench/results/memory-routes/2026-09-06-pilot-01`. Model: `claude-sonnet-4-6`; CLI: `2.1.263 (Claude Code)`; bd: `bd version 1.2.1 (Homebrew)`.

| Policy | Complete/planned | Halted | Incomplete | Pending | Exact-key capture T/F/? | Any-key capture T/F/? | Observed cost USD | Cost sessions known/planned | Median seconds |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| protocol | 1/1 | 0 | 0 | 0 | 1/0/0 | 1/0/0 | 0.3129 | 4/4 | 86.82 |

| Policy | Goal | Recorded/planned | Artifact T/F/? | Lookup used T/F/? | Search used T/F/? | Correct payload T/F/? | Correct via lookup T/F/? | Correct via search T/F/? |
|---|---|---:|---|---|---|---|---|---|
| protocol | direct | 1/1 | 1/0/0 | 1/0/0 | 0/1/0 | 1/0/0 | 1/0/0 | 0/1/0 |
| protocol | search | 1/1 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 0/0/1 |
| protocol | unnecessary | 1/1 | 1/0/0 | 1/0/0 | 0/1/0 | 1/0/0 | 1/0/0 | 0/1/0 |

| Policy | Goal | Any read before Write T/F/? | Correct payload before Write T/F/? | Observed cost USD | Median seconds |
|---|---|---|---|---:|---:|
| protocol | direct | 1/0/0 | 1/0/0 | 0.0601 | 69.32 |
| protocol | search | 1/0/0 | 1/0/0 | 0.0651 | 82.58 |
| protocol | unnecessary | 0/1/0 | 0/1/0 | 0.0743 | 91.07 |

| Task | Policy | Case state | Exact-key capture | Any-key capture | Direct artifact | Search artifact | Supplied control artifact |
|---|---|---|---|---|---|---|---|
| deployment-seed-20260906 | protocol | complete | pass | pass | pass | pass | pass |

## 2026-09-06-main-01

Source: `/Users/csells/Code/Forks/sjarmak/mem/memory-bench/results/memory-routes/2026-09-06-main-01`. Model: `claude-sonnet-4-6`; CLI: `2.1.263 (Claude Code)`; bd: `bd version 1.2.1 (Homebrew)`.

| Policy | Complete/planned | Halted | Incomplete | Pending | Exact-key capture T/F/? | Any-key capture T/F/? | Observed cost USD | Cost sessions known/planned | Median seconds |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| examples | 1/8 | 0 | 0 | 7 | 0/1/7 | 0/1/7 | 0.1876 | 4/32 | 21.78 |
| protocol | 0/8 | 0 | 0 | 8 | 0/0/8 | 0/0/8 | 0.0000 | 0/32 | ? |

| Policy | Goal | Recorded/planned | Artifact T/F/? | Lookup used T/F/? | Search used T/F/? | Correct payload T/F/? | Correct via lookup T/F/? | Correct via search T/F/? |
|---|---|---:|---|---|---|---|---|---|
| examples | direct | 1/8 | 0/1/7 | 0/1/7 | 1/0/7 | 0/0/8 | 0/1/7 | 0/0/8 |
| examples | search | 1/8 | 0/1/7 | 1/0/7 | 1/0/7 | 0/0/8 | 0/1/7 | 0/0/8 |
| examples | unnecessary | 1/8 | 1/0/7 | 0/1/7 | 0/1/7 | 0/1/7 | 0/1/7 | 0/1/7 |
| protocol | direct | 0/8 | 0/0/8 | 0/0/8 | 0/0/8 | 0/0/8 | 0/0/8 | 0/0/8 |
| protocol | search | 0/8 | 0/0/8 | 0/0/8 | 0/0/8 | 0/0/8 | 0/0/8 | 0/0/8 |
| protocol | unnecessary | 0/8 | 0/0/8 | 0/0/8 | 0/0/8 | 0/0/8 | 0/0/8 | 0/0/8 |

| Policy | Goal | Any read before Write T/F/? | Correct payload before Write T/F/? | Observed cost USD | Median seconds |
|---|---|---|---|---:|---:|
| examples | direct | 0/0/8 | 0/0/8 | 0.0393 | 21.88 |
| examples | search | 0/0/8 | 0/0/8 | 0.0611 | 32.95 |
| examples | unnecessary | 0/1/7 | 0/1/7 | 0.0435 | 21.68 |
| protocol | direct | 0/0/8 | 0/0/8 | 0.0000 | ? |
| protocol | search | 0/0/8 | 0/0/8 | 0.0000 | ? |
| protocol | unnecessary | 0/0/8 | 0/0/8 | 0.0000 | ? |

| Task | Policy | Case state | Exact-key capture | Any-key capture | Direct artifact | Search artifact | Supplied control artifact |
|---|---|---|---|---|---|---|---|
| csv_export-seed-20260906 | examples | complete | fail | fail | fail | fail | pass |
| cache-seed-20260906 | protocol | pending | ? | ? | ? | ? | ? |
| csv_export-seed-20260906 | protocol | pending | ? | ? | ? | ? | ? |
| retry_queue-seed-20260906 | protocol | pending | ? | ? | ? | ? | ? |
| backups-seed-20260906 | examples | pending | ? | ? | ? | ? | ? |
| image_export-seed-20260906 | examples | pending | ? | ? | ? | ? | ? |
| report_format-seed-20260906 | protocol | pending | ? | ? | ? | ? | ? |
| cache-seed-20260906 | examples | pending | ? | ? | ? | ? | ? |
| logging-seed-20260906 | examples | pending | ? | ? | ? | ? | ? |
| report_format-seed-20260906 | examples | pending | ? | ? | ? | ? | ? |
| deployment-seed-20260906 | examples | pending | ? | ? | ? | ? | ? |
| deployment-seed-20260906 | protocol | pending | ? | ? | ? | ? | ? |
| logging-seed-20260906 | protocol | pending | ? | ? | ? | ? | ? |
| image_export-seed-20260906 | protocol | pending | ? | ? | ? | ? | ? |
| retry_queue-seed-20260906 | examples | pending | ? | ? | ? | ? | ? |
| backups-seed-20260906 | protocol | pending | ? | ? | ? | ? | ? |
