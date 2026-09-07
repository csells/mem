# Additional installed memory-experiment hosts

Inspected September 6, 2026 (local time). This inventory distinguishes an installed
launcher, an authenticated route, and a host capable of producing model/tool events.
Only one short model smoke per Gemini and OpenCode was authorized and attempted.
No login, model installation, model substitution, credential refresh, server change,
or user configuration edit was performed.

| Host | Installed version | Existing route | Observed availability |
| --- | --- | --- | --- |
| Gemini CLI | 0.55.1 | Existing API key in macOS Keychain | Billing blocked: provider returned HTTP 429, prepayment credits depleted |
| OpenCode | 1.18.15 | Existing local Ollama, `ollama/qwen3-coder:30b-a3b-q8_0` | Model and tool events observed; the initial file-write task failed |
| GitHub Copilot CLI | Actual CLI version unverified | VS Code shim exists; no actual CLI found by shim | Installation blocked: launcher prompts to install the actual CLI |

Blocked hosts remain part of coverage accounting; neither blocked host supports a
claim about memory task performance. OpenCode remains eligible despite its failed
smoke, subject to the explicit context and project-root limitations below.

## Preserved local evidence

Read-only executable/help probes:
`/private/tmp/memory-hosts-inventory._fmy8myj/`. Files include `probes.json`,
`gemini-{version,help}.log`, `opencode-{version,help,run-help}.log`, and
`copilot-{version,help}.log`.

Authorized smoke evidence:
`/private/var/folders/6k/xzgngnms6jg4_z2l40y0_9vh0000gn/T/memory-host-smokes.4tn0pq9f/`.
Each host has `summary.json`, `stdout.jsonl`, `stderr.log`, `profile.sb`, and its
fresh `work/` and `config/` directories. These files are preserved. Credentials
were passed only in a transient process environment and were not serialized.

The help probes denied network and allowed writes only in their scratch directory.
The model smokes used the experiment's external macOS Seatbelt profile, allowing
network while denying content reads from user directories and the source repo,
and allowing writes only in each host's scratch directory. All original user
configuration and state remained outside the write allowance.

## Gemini CLI

`/opt/homebrew/bin/gemini` resolves to the installed Google npm package's
`bundle/gemini.js`. Both executable `--version` and package metadata report 0.55.1.
Installed help confirms `-p`, `--model`, `--output-format stream-json`,
`--approval-mode`, `--skip-trust`, and per-session identity options. Headless JSONL
has initialization, messages, tool-use/results, errors, and a terminal result;
usage belongs in actual result records rather than inferred zeroes.
[Official headless reference](https://geminicli.com/docs/cli/headless/).

The user settings select `gemini-api-key`; no explicit model name is configured.
Relevant inherited API-key variables and OAuth credential file were absent. That
did **not** establish absence of credentials: the installed source loads an API
key from Keychain service `gemini-cli-api-key`, account `default-api-key`. That
entry exists. Its credential payload was parsed in memory, and only metadata and
presence were reported. The smoke used that same key through `GEMINI_API_KEY`.
[Official authentication options](https://geminicli.com/docs/get-started/authentication/).

The one smoke initialized session `144a144c-5bd0-42c1-92b9-099fcf19f63f`, reporting
model `auto`. This is an alias, not proof of a specific executed model. The service
repeatedly returned HTTP 429 `RESOURCE_EXHAUSTED`, explicitly stating depleted
prepayment credits. The smoke was terminated after 120 seconds of internal retry;
the CLI's signal handler exited 0, but there was no terminal result, tool execution,
or `smoke.txt`. The billing failure is the concrete blocker. Usage and cost are
unknown, not assumed zero. A successful run requires the existing route to become
funded or a separately authorized auth-route change.

`GEMINI_CLI_HOME` isolates the CLI's `.gemini` directory without changing `HOME`.
For a future run, retain only selected auth metadata and use a fresh settings file;
copying all user settings would import hooks, MCP servers, and instructions.
`model.maxSessionTurns` provides a turn bound. The external sandbox remains the
filesystem boundary even when headless tools are automatically approved.
[Configuration reference](https://geminicli.com/docs/reference/configuration/).

Ordinary native context loads global, workspace/ancestor, and just-in-time
`GEMINI.md` files. Native instruction files must be isolated and retained separately
from transcripts. [Context hierarchy](https://geminicli.com/docs/cli/gemini-md/).
The separate experimental Auto Memory feature is off by default. It considers
sessions idle for at least three hours with at least ten user messages and writes
review candidates, requiring approval to apply them. These short fresh-session
trials would not exercise that mechanism.
[Auto Memory behavior](https://geminicli.com/docs/cli/auto-memory/).

## OpenCode

`/opt/homebrew/bin/opencode` resolves to the Homebrew 1.18.15 binary. Installed
`run --help` confirms `--model provider/model`, `--format json`, `--dir`, `--pure`,
and `--auto`. The JSONL stream contains completed tool states and per-step token
and provider-cost records. It does not identify the model in those events, so the
adapter crossmatches stream message IDs to actual assistant rows in the scratch
OpenCode database. [Official CLI reference](https://opencode.ai/docs/cli/).

The existing config contains only the Ollama provider, using the OpenAI-compatible
adapter and `http://localhost:11434/v1`; its configured model is
`qwen3-coder:30b-a3b-q8_0`. No remote auth store or provider key was found. Read-only
Ollama metadata confirmed an active endpoint and that exact installed model. There
was no pull, create, model replacement, or server restart.

The smoke completed session `ses_f86a6a7c6ffeNrN7xy6hr2KzTC` after 69.552 seconds,
exit 0. It emitted three model steps, a denied write to `/smoke.txt`, an unavailable
tool call, and then a final response asking for task details. The requested local
file was absent. The three emitted steps reported 6,150 input and 291 output tokens
in total, provider cost 0. OpenCode also invokes a title helper; its usage was not
emitted in this stream. Local compute cost is unmeasured. Exit 0 and a final stop
therefore prove transport completion, not successful task execution.

Two limitations prevent attributing this failure to memory or even cleanly to
model ability:

- The first smoke directory was not a valid Git repository. OpenCode recorded
  the correct cwd but project root `/`, which plausibly cued the root-level write.
  The common driver will initialize a valid empty Git repository for **all** hosts
  in subsequent fresh workspaces; the first smoke is retained unchanged.
- Ollama's actual loaded context was 4,096 tokens, although static model metadata
  advertises a 262,144-token maximum. Each emitted prompt counted 2,050 tokens.
  Input truncation is a material confound for the common instructions; the counts
  alone do not prove which content was lost. The existing configuration remains
  unchanged and cannot be described as an equal-capacity model comparison.

Ollama documents no context-size request parameter on this OpenAI-compatible
endpoint. Raising OpenCode's declared model limit would not raise the server's
actual context. Supported alternatives involve a new model definition or a server
configuration change; neither was performed.
[OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility#setting-the-context-size).
Larger contexts require more memory and can cause CPU offloading.
[Context and memory costs](https://docs.ollama.com/context-length).

OpenCode merges configuration sources; an explicit config file alone does not
erase global configuration. The adapter isolates XDG config/data/cache/state,
disables Claude compatibility, excludes external plugins and skills, and disables
updates/sharing. Project config discovery is disabled only in the isolated mode:
the same flag also disables project `AGENTS.md` discovery in this installed
version. Normal mode retains discovery inside its fresh Git workspace. The
installed binary attempted background
plugin dependency setup even with `--pure`; the smoke sandbox denied its writes
to the user's npm cache. The adapter additionally selects a scratch npm cache and
offline mode. [Configuration precedence](https://opencode.ai/docs/config/).

The verified ordinary native mechanism is `AGENTS.md` discovery, including a
global file and project file; Claude files are supported as fallbacks. No separate
automatic memory extractor was established. The normal condition exposes two
initially empty scratch instruction files through the ordinary locations and
retains their contents; empty scaffolds do not count as semantic captures. The
isolated condition exposes neither. User instructions and old sessions are not
imported. [Native instruction rules](https://opencode.ai/docs/rules/).

Actual instruction delivery was also checked without model inference: the installed
binary sent requests to a local receiver that returned a deliberate HTTP 400, while
the sandbox blocked other destinations. The corrected normal request included both
distinct global and project instruction markers; the isolated request included
neither. The test also established that global instruction lookup uses
`OPENCODE_CONFIG_DIR` when set, so the adapter places its global link there. These
two corrections precede the common OpenCode model smoke. Preserved requests,
controls, installed-source excerpts, and hashes are in
`memory-bench/results/memory-routes/2026-09-06-host-coverage-01/native-discovery-01/`.
This proves instruction assembly, not model attention, capture, or task success.

Implementation: `memory-bench/membench/runner/memory_host_other.py` implements
`prepare(host, local, env, prompt, model, mode, budget)`,
`observe(host, stream, local)`, and `export_evidence(local, destination)`.
The exclusive evidence export contains only selected actual assistant identity
rows, avoiding authentication tables and conversation text. It can be regraded
without access to user state or the original scratch database. Budget in dollars
is not an OpenCode CLI-enforced bound; the parent enforces wall-clock termination.

## GitHub Copilot CLI

The given VS Code path is an executable shell wrapper, not the CLI itself. Its
shim looks for a separate `copilot` command after excluding its own directory from
`PATH`. Both help and version probes printed an installation prompt followed by
`Cannot find GitHub Copilot CLI`. They exited 0 with stdin closed. The shim's
minimum supported version constant is **not** an installed version. Installation
was not accepted. [Official installation reference](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli).

Current official docs describe headless `-p`, `--model`, JSONL output, custom
instruction controls, `COPILOT_HOME`, tool permissions, and existing GitHub token
authentication. Those capabilities could support an adapter after a genuine CLI
is available, but were not executable-verified here. The existing tiny Copilot
config and absent relevant token variables do not prove authentication. There was
no Copilot model call, no verified model pin, and no measured usage.
[Programmatic reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference),
[Command reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference).
