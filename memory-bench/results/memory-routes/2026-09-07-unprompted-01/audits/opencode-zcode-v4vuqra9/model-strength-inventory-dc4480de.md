The completed cohort did not test the requested primary-model strength range. It used Astra, Sonnet 4.6, Qwen3 Coder 30B, and GLM-5.3, with 30 sessions each. Haiku 4.5 appears as auxiliary usage in all Claude sessions, not as a primary coding condition.

| Requested family | Explicit prospective model ID | Completed primary coverage |
|---|---|---|
| Sol | `gpt-5.6-sol` | None |
| Terra | `gpt-5.6-terra` | None |
| Luna | `gpt-5.6-luna` | None |
| Haiku | `claude-haiku-4-5-20251001` | None |
| Sonnet | `claude-sonnet-5` | 30 with older `claude-sonnet-4-6`; no Sonnet 5 |
| Opus | `claude-opus-5` | None |
| Fable | `claude-fable-5-1` | None |

Sol/Terra/Luna are listed in the current Codex model cache. [Official OpenAI Sol documentation](https://developers.openai.com/api/docs/models/gpt-5.6-sol) confirms the explicit family naming. Claude’s [current model overview](https://platform.claude.com/docs/en/models/overview) supplies its four listed IDs. Fable is not an unknown alias: installed Claude help offers it, user settings select `claude-fable-5-1[1m]`, and [official Fable 5.1 documentation](https://platform.claude.com/docs/en/models/fable-5-1/overview) confirms the model.

OpenCode’s cached OpenAI/Anthropic catalogs contain all these families, but the configured local provider is Ollama Qwen. zcode’s configured provider exposes GLM models; its GLM-5-Turbo helper was configured but absent from all 550 recorded model responses. Catalogs and config strings do not establish account access or execution qualification. No inference, paid smoke, installation, authentication change, or global configuration change was performed.

Suggested reframe: estimate a memory-assisted capability and cost frontier, rather than ranking four confounded host/model bundles. First vary model tier within one host while holding task variants, memory intervention, tools, helper policy, reasoning policy and native mode fixed. Then cross selected exact models across hosts to estimate host effects separately. Include the previous Sonnet4.6/Astra anchors.

Use paired independently authored lifecycle variants, counterbalanced order and repeats for each model×intervention cell. Record capture fidelity, prior full-body retrieval, actual application, stale-history errors and artifact quality separately. Report both fixed-resource comparisons and observed cost/latency frontiers: one420-second cutoff alone confounds slower strong models with failure. Keep explicit tool-protocol failures as outcomes but distinguish model behavior from adapter evidence faults.

Make later business tasks naturally need long-lived or cross-project decisions while preserving code/issues/history; do not force memory by deleting alternatives. Hold supplied-control tasks unchanged, and report useful newly scoped captures separately from duplicate writes. A larger model count without these controls would not answer whether memory enables a cheaper model to complete the same work.


Detailed evidence and source hashes: `model-strength-inventory-dc4480de.json` (SHA256 `9ff2faa7dc26b95b51d0b02cb679b1641ae8a67c5c0adb9756c6dc329086fe33`). CLI help transcripts remain in `/var/folders/6k/xzgngnms6jg4_z2l40y0_9vh0000gn/T/readonly-model-inventory-rayfpy_v`.
