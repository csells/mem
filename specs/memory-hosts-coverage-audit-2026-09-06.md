# Independent host coverage audit

The saved evidence supports running the matched memory procedure on **Claude Code
2.1.263 / Sonnet 4.6** and **Codex 0.153.4 / gpt-6-astra**. It does not yet support
a memory-reliability claim for the other three candidates.

This audit inspected the frozen manifest at **2026-09-07 01:20:34 UTC**. All 276
archived source hashes matched. The schedule contains **six lifecycles / 48 planned
sessions**, with **72 blocked candidate slots** retained from the 120-session bound.
At that inspection time, no scored session results had been saved. The counts below
validate coverage and preflight; completed outcomes must come from the subsequent
independent report, not this audit.
[Frozen manifest](../memory-bench/results/memory-routes/2026-09-06-hosts-01/manifest.json).

| Candidate | What the actual evidence establishes | Smallest next step |
| --- | --- | --- |
| Claude Code / Sonnet 4.6 | Corrected common smoke completed with actual model identity, exact artifact, one accepted memory write, two observed reads, search and direct lookup, and no unknown receipt evidence. | Complete and independently regrade the frozen cohort. |
| Codex / gpt-6-astra | Same common boundary checks passed. The earlier shell PATH failure is preserved and is an instrumentation failure, not a memory verdict. | Complete and independently regrade the frozen cohort; keep unreported USD cost unknown. |
| Gemini CLI 0.55.1 | Existing Keychain API key reached the provider, which explicitly reported depleted prepayment credits. Initialization named only `auto`; no concrete successful model, terminal result, tool call, or artifact was established. | Restore availability on the existing billing route, then run one bounded common smoke with an explicit model and actual model evidence. No alternate account/model route was tested. |
| OpenCode 1.18.15 / local Qwen | CLI, model identity and terminal transport work. Its common task failed, and matched server warnings prove prompt truncation from 7,301 and 7,121 tokens to 2,050. | Under a separately authorized isolated configuration, provide enough context for the full request and response, verify no truncation, then repeat a bounded common smoke before scheduling memory trials. Preserve the existing profile and both failed preflights. |
| Copilot launcher | The VS Code shim could not find the actual CLI; help/version emitted an installation prompt despite exit 0. No actual CLI version, auth route, or model was verified. | Make the actual CLI available, verify existing authentication, then pin its model and run one common smoke. The launcher alone is insufficient. |

Claude and Codex smoke claims are supported by their separate saved results:
[Claude](../memory-bench/results/memory-routes/2026-09-06-host-common-smoke-02/result.json),
[Codex](../memory-bench/results/memory-routes/2026-09-06-host-common-smoke-codex-02/result.json).
Gemini/Copilot logs were copied to permanent evidence after checking the Gemini
key and common credential patterns; those seven copies contained no detected
credential values. Original logs were preserved and no auth/settings files were
copied. [Copy manifest](../memory-bench/results/memory-routes/2026-09-06-host-coverage-01/blocked-host-evidence-01/manifest.json).

## OpenCode is a context blocker, not a memory verdict

The independent no-model receiver proved that restricting permissions exposes
exactly `bash`, `edit`, `read`, and `write`, reducing tool-schema JSON from 21,203
to 10,189 bytes. That still leaves **2,121 tokens of system and user text before
tools**, exceeding the observed 2,050-token input budget. Tool JSON contributes
another 2,375 tokens. These component counts exclude the exact chat template;
they are not a claim that a new four-tool inference was run. The tokenizer's model
weights matched the installed Qwen model, and its runtime reported 4,096 context.
[Diagnosis and original warnings](../memory-bench/results/memory-routes/2026-09-06-host-context-diagnostic-01/diagnosis.json),
[token counts](../memory-bench/results/memory-routes/2026-09-06-host-context-diagnostic-01/tokenization.json),
[model proof](../memory-bench/results/memory-routes/2026-09-06-host-context-diagnostic-01/tokenizer-model-proof.json).

Do not replace this finding with “OpenCode cannot use memory,” or claim that
truncation alone explains every incorrect action. Some task content was evidently
retained; the complete supplied context was not. The configured OpenAI-compatible
endpoint has no supported per-request context-size setting; changing a declared
client limit is insufficient. [Ollama's context-setting contract](https://docs.ollama.com/api/openai-compatibility#setting-the-context-size).

## Boundaries for the final conclusion

- **Coverage is two measured host/model configurations, not five.** Blocked slots
  are unavailable measurements, not failed memory sessions. Preflight smokes are
  separate from the 48 scored-session schedule.
- **Six lifecycles are the relevant replication units.** Eight linked stages share
  their original capture. Per host, the schedule is cache and image export with
  native memory isolated, plus cache only with installed native defaults retained.
- **“Normal” does not mean native memory enabled everywhere.** Claude's normal
  condition enables its default automatic-memory feature in fresh state; Codex's
  installed memories feature defaults off. Neither imports personal history.
  OpenCode's project/global instruction delivery was verified without inference,
  which establishes assembly rather than attention or semantic capture.
  [Actual native-delivery controls](../memory-bench/results/memory-routes/2026-09-06-host-coverage-01/native-discovery-01/SUMMARY.json).
- **Correct artifacts, requested retrieval routes, and faithful records are
  distinct outcomes.** Search must precede complete lookup to establish that
  delivery order; their presence in one shell call alone is weaker evidence.
  Historical body immutability is stronger than reproducing historical values.
- **This tests a complete procedure on legacy keyed Beads memory.** It does not
  validate the proposed new Memory type, unrestricted prose truth, long-term
  production reliability, or a causal advantage of one host. Host, model, native
  defaults and capacity differ; the new procedure must not be pooled with the
  earlier 96-session experiment as one homogeneous sample.

The practical recommendation remains small: capture a durable agreement under a
stable key, preserve the initial historical reference once, recall the complete
body before applying it, update only the current reference for a permanent change,
and avoid writes during ordinary reproduction. Treat the final cohort results as
evidence for the observed scope of that procedure, with failures and unknowns
reported separately. Fixing storage semantics cannot recover instructions that the
host never delivered intact.
