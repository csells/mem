# Memory-route experiment report

Each run is reported separately. Counts marked T/F/? retain scheduled denominators; missing sessions and unsupported representations are unknown, not failures. The three goal routes share one capture and are not independent trials.

Artifact success checks the actual final JSON. Literal capture/payload checks do not judge surrounding prose. Exact-key and any-key capture are derived from the saved establish memory snapshot using the run's pinned grader; the original case verdict remains in JSON. Native capture stays unknown because that snapshot covers bd only. Other saved scores are aggregated without recomputation.

Before-Write timing is unknown without a matching Write tool event. CLI costs are subscription token-usage estimates, not additional billed dollars; missing costs are reported separately. Durations are per-session elapsed times.

## 2026-09-06-main-02

Source: `/Users/csells/Code/Forks/sjarmak/mem/memory-bench/results/memory-routes/2026-09-06-main-02`. Model: `claude-sonnet-4-6`; CLI: `2.1.263 (Claude Code)`; bd: `bd version 1.2.1 (Homebrew)`.

| Policy | Complete/planned | Halted | Incomplete | Pending | Exact-key capture T/F/? | Any-key capture T/F/? | Observed cost USD | Cost sessions known/planned | Median seconds |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| examples | 7/8 | 0 | 0 | 1 | 0/4/4 | 0/4/4 | 1.3328 | 28/32 | 21.38 |
| protocol | 6/8 | 0 | 1 | 1 | 7/0/1 | 7/0/1 | 1.5327 | 27/32 | 25.35 |

| Policy | Goal | Recorded/planned | Artifact T/F/? | Lookup used T/F/? | Search used T/F/? | Correct payload T/F/? | Correct via lookup T/F/? | Correct via search T/F/? |
|---|---|---:|---|---|---|---|---|---|
| examples | direct | 7/8 | 0/7/1 | 3/4/1 | 4/3/1 | 0/0/8 | 0/4/4 | 0/3/5 |
| examples | search | 7/8 | 0/7/1 | 7/0/1 | 7/0/1 | 0/0/8 | 0/4/4 | 0/3/5 |
| examples | unnecessary | 7/8 | 7/0/1 | 0/7/1 | 0/7/1 | 0/7/1 | 0/7/1 | 0/7/1 |
| protocol | direct | 7/8 | 7/0/1 | 7/0/1 | 0/7/1 | 7/0/1 | 7/0/1 | 0/7/1 |
| protocol | search | 7/8 | 7/0/1 | 7/0/1 | 7/0/1 | 7/0/1 | 7/0/1 | 0/0/8 |
| protocol | unnecessary | 6/8 | 6/0/2 | 6/0/2 | 0/6/2 | 6/0/2 | 6/0/2 | 0/6/2 |

| Policy | Goal | Any read before Write T/F/? | Correct payload before Write T/F/? | Observed cost USD | Median seconds |
|---|---|---|---|---:|---:|
| examples | direct | 3/0/5 | 0/0/8 | 0.2878 | 20.26 |
| examples | search | 3/0/5 | 0/0/8 | 0.4054 | 25.95 |
| examples | unnecessary | 0/7/1 | 0/7/1 | 0.3097 | 17.78 |
| protocol | direct | 7/0/1 | 7/0/1 | 0.3450 | 21.08 |
| protocol | search | 7/0/1 | 7/0/1 | 0.3783 | 22.65 |
| protocol | unnecessary | 0/6/2 | 0/6/2 | 0.3686 | 27.96 |

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
| logging-seed-20260906 | protocol | incomplete | pass | pass | pass | pass | ? |
| image_export-seed-20260906 | protocol | complete | pass | pass | pass | pass | pass |
| retry_queue-seed-20260906 | examples | pending | ? | ? | ? | ? | ? |
| backups-seed-20260906 | protocol | pending | ? | ? | ? | ? | ? |
