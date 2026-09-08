# Model qualification: all ten interfaces viable

All 20 planned sessions started once and produced successful exact-model host receipts; no session timed out. Sixteen passed every diagnostic. Astra, Sol, Terra, Luna, Sonnet 5, Opus 5, Fable 5.1, and GLM passed both sessions. Haiku and Qwen failed both diagnostic-compliance checks; their evidence is preserved and they remain viable interfaces for the main experiment.

Haiku omitted required diagnostic markers (and capture-stage search/prime), while real code, capture, and recall succeeded. Qwen capture performed real code/save/search/recall but omitted markers, prime, and closure. Its fresh reuse session repeated the actual assigned issue ID and emitted a Bash call as text without executing it. This is observed behavior, not evidence of an authentication failure or undelivered launch prompt.

The run took 403.81 seconds. User configuration hashes were unchanged. Claude receipts report $1.88067045 in list-basis usage cost; Codex and GLM have no dollar receipt, and local Qwen reports zero model cost. Applying each Claude profile's observed two-session mean to the planned 102 Claude sessions gives $23.46872940; the explicit diagnostics are smaller than main tasks, so this is not a cap or a verified billed charge.

No retries or scored sessions were launched. Per-profile costs, actual IDs, helper model keys, hashes, and limits are in qualification-admission.json.
