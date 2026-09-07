# Memory handoffs across CLI hosts

Observed 44 unique host sessions; 48 scheduled and 72 blocked candidate slots out of 120.

Lifecycle counts are true/false/unknown. Eight stages share one capture; blocked hosts are retained in coverage, not silently dropped.

| Host / native mode | Actual model(s) | Lifecycles T/F/? | Sessions recorded/planned | Estimated cost (known/planned) | Median seconds | Writes / reads | History rewrites |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: |
| claude/isolated | claude-sonnet-4-6 | 2/0/0 | 16/16 | $0.9400 (16/16) | 22.67 | 7 / 24 | 1 |
| claude/normal | claude-sonnet-4-6 | 1/0/0 | 8/8 | $0.6545 (8/8) | 22.80 | 4 / 12 | 1 |
| codex/isolated | gpt-6-astra | 1/0/1 | 12/16 | unknown (0/16) | 25.39 | 6 / 22 | 0 |
| codex/normal | gpt-6-astra | 1/0/0 | 8/8 | unknown (0/8) | 29.71 | 3 / 14 | 0 |
| gemini/isolated | Blocked: Existing API key reaches provider but receives HTTP429 RESOURCE_EXHAUSTED: prepayment credits depleted | — | 0/0 | unknown | — | — | — |
| gemini/normal | Blocked: Existing API key reaches provider but receives HTTP429 RESOURCE_EXHAUSTED: prepayment credits depleted | — | 0/0 | unknown | — | — | — |
| opencode/isolated | Blocked: Current local runtime truncates the matched input: observed 7301-token request reduced to2050tokens, with4096totalcontext. Four-tool input also exceeds this limit; intact matched trial delivery is not validated. Both real preflight tasks failed. | — | 0/0 | unknown | — | — | — |
| opencode/normal | Blocked: Current local runtime truncates the matched input: observed 7301-token request reduced to2050tokens, with4096totalcontext. Four-tool input also exceeds this limit; intact matched trial delivery is not validated. Both real preflight tasks failed. | — | 0/0 | unknown | — | — | — |
| copilot/isolated | Blocked: Installed VS Code shell/shim launcher cannot find the actual GitHub Copilot CLI; help/version prompt to install it | — | 0/0 | unknown | — | — | — |
| copilot/normal | Blocked: Installed VS Code shell/shim launcher cannot find the actual GitHub Copilot CLI; help/version prompt to install it | — | 0/0 | unknown | — | — | — |

## Stage outcomes

| Host / mode / stage | Exact artifact T/F/? | Current capture T/F/? | History capture T/F/? | Full direct payload T/F/? | No writes/changes T/F/? | Requested route T/F/? | Search → recall order T/F/? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| claude/isolated/establish | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 0/2/0 | — | — |
| claude/isolated/direct | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | — |
| claude/isolated/search | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 |
| claude/isolated/revise | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 0/2/0 | — | — |
| claude/isolated/revised_direct | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | — |
| claude/isolated/revised_search | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 |
| claude/isolated/supplied | 2/0/0 | 2/0/0 | 2/0/0 | 0/2/0 | 2/0/0 | — | — |
| claude/isolated/historical | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | — |
| claude/normal/establish | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 0/1/0 | — | — |
| claude/normal/direct | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | — |
| claude/normal/search | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 |
| claude/normal/revise | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 0/1/0 | — | — |
| claude/normal/revised_direct | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | — |
| claude/normal/revised_search | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 |
| claude/normal/supplied | 1/0/0 | 1/0/0 | 1/0/0 | 0/1/0 | 1/0/0 | — | — |
| claude/normal/historical | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | — |
| codex/isolated/establish | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 0/2/0 | — | — |
| codex/isolated/direct | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | — |
| codex/isolated/search | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 |
| codex/isolated/revise | 2/0/0 | 2/0/0 | 2/0/0 | 1/0/1 | 0/2/0 | — | — |
| codex/isolated/revised_direct | 1/0/1 | 1/0/1 | 1/0/1 | 1/0/1 | 1/0/1 | 1/0/1 | — |
| codex/isolated/revised_search | 1/0/1 | 1/0/1 | 1/0/1 | 1/0/1 | 1/0/1 | 1/0/1 | 1/0/1 |
| codex/isolated/supplied | 1/0/1 | 1/0/1 | 1/0/1 | 0/1/1 | 1/0/1 | — | — |
| codex/isolated/historical | 1/0/1 | 1/0/1 | 1/0/1 | 1/0/1 | 1/0/1 | 1/0/1 | — |
| codex/normal/establish | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 0/1/0 | — | — |
| codex/normal/direct | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | — |
| codex/normal/search | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 |
| codex/normal/revise | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 0/1/0 | — | — |
| codex/normal/revised_direct | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | — |
| codex/normal/revised_search | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 |
| codex/normal/supplied | 1/0/0 | 1/0/0 | 1/0/0 | 0/1/0 | 1/0/0 | — | — |
| codex/normal/historical | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | — |

Observed 233 execution markers. Completion guards were absent; no administrative guard queries were added. Native file inventories, read routes, timing unknowns, source hashes, and per-stage model usage remain in analysis.json.

No writes/changes is desired on reproduction stages; establishment and revision require writes. Historical rewrite counts concern complete bodies, independently of correct historical JSON.
Requested route requires a complete correct direct recall on lookup stages. Search stages additionally require a successful observed search delivered before that recall was issued. Missing order or a shared compound tool result remains unknown. This metric does not alter artifact correctness or prove search caused the key selection. The unordered search-plus-full-recall joint is in analysis.json.

- Synthetic legacy KV lifecycles; eight stages share captured state and are correlated.
- Host and model vary together; this is not a controlled comparison of host-only effects.
- Normal retains the installed native-memory default in isolated state, not the operator's personal history.
- An installed native-memory default can be off in both conditions; saved native files alone do not prove their delivery to the model.
- Context windows and effective budgets differ across installed hosts; common prompts do not establish equal retained context or token budgets.
- Literal JSON scores do not certify surrounding prose or source attribution.
- Execution markers add instrumented stderr; they establish attribution, not model attention.
- No completion guards run in this extension; zero guard queries is a design property.
- Reported CLI costs are usage estimates; unknown costs are not zero or additional billed charges.
- The previous experiments are separate and are not pooled here.
