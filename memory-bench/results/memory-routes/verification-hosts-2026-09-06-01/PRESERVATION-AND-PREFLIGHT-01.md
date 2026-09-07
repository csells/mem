# Preservation and preflight usage audit

The earlier evidence is preserved. The independent [preservation audit](preservation-01.json) rehashed all **1,283 inputs** to the 96-session analysis: every hash matches. Its first and second generated analyses still differ only in generation time and reporter source hash; all measured fields match.

All **3,324 files** in the original inventory match the previously approved state: 3,322 retain their original hash, and the existing driver change and appended follow-up paragraph retain exactly their previously approved hashes. The original narrative's 21,876 bytes remain an exact prefix. The six dated original runs contain **80 unique sessions and 80 terminal results**. Six older navigation/search pilot sessions also remain preserved in the inventory and are outside these 80. The branch remains `csells/memory-routes-experiments` at `19763909b5a212922730f2273f77b8a09535bd7f`.

The [preflight inventory](preflight-usage-01.json) counts each actual cross-host launch once, including failed attempts. It excludes duplicated aggregate result files and the separately scored `hosts-01` cohort.

| Host | Launched sessions | Completed model terminals | Reported provider cost | Limits |
| --- | ---: | ---: | ---: | --- |
| Claude | 2 | 2 | $0.1214118 | Includes initial instrumentation failure and both sessions' Haiku helper usage. CLI list estimate, not a verified subscription charge. |
| Codex | 4 | 4 | Unknown | All four terminal token records retained; no USD estimate emitted. Includes initial PATH instrumentation failure. |
| OpenCode | 2 | 2 | $0 for emitted steps | Five emitted steps total 10,250 input and 539 output tokens; title-helper usage and local compute cost unknown. Failures are confounded by project-root/input-delivery problems. |
| Gemini | 1 | 0 | Unknown | Existing-auth attempt emitted an init ID, then billing errors and a timeout; no successful model response or terminal usage. |
| Copilot | 0 | 0 | No model launch | Two help/version probes failed because the actual CLI target is missing. |

This is **nine launched preflight sessions, eight completed model terminals**. The known reported cost subtotal is **$0.1214118**, with five session costs unknown; it is not a complete monetary total. No-model loopback instruction checks, tokenizer diagnostics, and the mechanical lifecycle-gate smoke contribute zero model calls. Token definitions differ by host, so their input counters are retained separately.

Across the reported 80-session and 96-session experiments and the new preflights, the preserved original 80 terminals report **$4.6551724**, and the separate 96 lifecycle terminals report **$5.5352622**. Including known preflight costs gives **$10.3118464 before the new scored cross-host cohort**, plus the unknown costs above. This known subtotal excludes the six older navigation/search pilots and their costs. The original 80 already include their dated pilot/control runs; do not add those again. These are reported provider estimates, not invoice measurements.

No prior evidence, frozen source, configuration, credentials, or model state changed during this audit. Safe initial OpenCode smoke outputs and sanitized model rows were copied into the new [preflight evidence directory](preflight-evidence-01/); originals remain in place. No models or tests were launched.
