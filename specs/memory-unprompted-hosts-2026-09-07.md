# Installed coding-agent readiness for the unprompted-memory redesign

This is a read-only inventory, not a new experiment or inference preflight.
Claude Code and Codex report existing logins. Gemini retains selected API-key
material, but provider availability is unverified now. OpenCode retains a local
Qwen route, but runtime context is unverified now. The Copilot executable supplied
by VS Code is still a launcher without a discoverable underlying CLI.

Inspection completed: 2026-09-07T15:07:42.137283+00:00. Each subprocess had a separate 30-second
timeout and closed stdin. No inference prompt, install, login/logout, credential
refresh, configuration edit, server change, model load, experiment rerun, or old
evidence modification was performed. Authentication output was filtered to status
metadata; credential values and account identities were not printed. Ollama checks
were metadata-only GET requests, not generation requests.

## Current installed inventory

| Candidate                | Current executable                                                                                         | Version result                                                                                              | Current authentication/readiness evidence                                                                                                                                          |
| ------------------------ | ---------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Claude Code              | `/Users/csells/.local/bin/claude`                                                                          | `2.1.263 (Claude Code)`                                                                                     | `claude auth status` exits 0: logged in, `claude.ai`, `firstParty`, Max subscription. This is login metadata, not a fresh model-availability check.                                |
| Codex                    | `/opt/homebrew/bin/codex`                                                                                  | `codex-cli 0.153.4`                                                                                         | `codex login status` exits 0 and reports ChatGPT login. `codex features list` reports `memories stable false` and external memory import false.                                    |
| Gemini CLI               | `/opt/homebrew/bin/gemini`                                                                                 | `0.55.1`                                                                                                    | User settings select `gemini-api-key`; the corresponding Keychain service item exists. No provider request was made.                                                               |
| OpenCode                 | `/opt/homebrew/bin/opencode`                                                                               | `1.18.15`                                                                                                   | `opencode providers list` exits 0 and reports zero stored provider credentials. Existing configuration uses the local Ollama endpoint, which does not require a remote credential. |
| Copilot VS Code launcher | `/Users/csells/Library/Application Support/Code/User/globalStorage/github.copilot-chat/copilotCli/copilot` | No CLI version. Both version/help exit 0 after reporting the CLI cannot be found and offering installation. | No actual Copilot CLI, authentication status, entitlement, or inference availability established. Closed stdin did not accept the installation prompt.                             |

Resolved launcher targets:

- Claude: `/Users/csells/.local/share/claude/versions/2.1.263`.
- Codex: `/opt/homebrew/lib/node_modules/@openai/codex/bin/codex.js`.
- Gemini: `/opt/homebrew/lib/node_modules/@google/gemini-cli/bundle/gemini.js`.
- OpenCode: `/opt/homebrew/Cellar/opencode/1.18.15/libexec/lib/node_modules/opencode-ai/bin/opencode.exe`.
- Copilot: the supplied shell wrapper itself, invoking `copilotCLIShim.js` through
  VS Code's Electron helper.

These versions match the preceding experiment. That fact is not a complete
package fingerprint or a substitute for freezing the next experiment's actual
executables, models, instructions, and adapters.

## Supported headless interfaces

These options are advertised by the installed help, rather than inferred from
another agent's syntax. The forms below describe interfaces; no prompt-bearing
command was run during this inventory.

| CLI      | Headless entry and model selection                        | Useful observed options                                                                                                                                                                                                                                                              |
| -------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Claude   | `claude -p <prompt> --model <model>`                      | `--output-format json` or `stream-json`, `--verbose`, `--no-session-persistence`, `--max-budget-usd`, `--setting-sources`, `--settings`, `--tools`, `--allowedTools`, `--permission-mode`, `--permission-prompts none`, `--mcp-config`, `--strict-mcp-config`.                       |
| Codex    | `codex exec <prompt> --model <model>`; stdin is supported | `--json`, `--cd`, `--sandbox`, `--ephemeral`, `--ignore-user-config`, `--ignore-rules`, `--config`, `--output-schema`, `--output-last-message`. Root `--ask-for-approval never` is available. `--ignore-user-config` does not bypass authentication in `CODEX_HOME`.                 |
| Gemini   | `gemini --prompt <prompt> --model <model>`                | `--output-format json` or `stream-json`, `--approval-mode`, `--policy`, `--admin-policy`, `--skip-trust`, `--sandbox`, `--extensions`, `--allowed-mcp-server-names`, `--include-directories`, and `--acp`. `--allowed-tools` is explicitly deprecated in favor of the policy engine. |
| OpenCode | `opencode run <message> --model <provider/model>`         | `--format json`, `--agent`, `--variant`, `--dir`, `--file`, `--attach`, `--pure`, and `--auto`. `--command` is a named command mode, not another spelling of the message. `serve` and `acp` are also advertised; neither was started.                                                |
| Copilot  | Unverified                                                | The shim cannot supply the actual CLI's help. Do not invent a headless adapter from another CLI's flags or treat the shim's zero exit status as admission.                                                                                                                           |

For an ordinary-workflow experiment, isolate settings deliberately without
accidentally suppressing the intended instructions and skills. Claude help says
`--bare` skips automatic memory and CLAUDE.md discovery, while `--safe-mode`
disables customizations including skills and project instructions; neither is a
neutral choice for testing their normal adoption. Authentication and native-memory
choices remain separate from instruction delivery.

## Gemini: retained API-key route, unverified alternatives

The safe metadata check was:

```sh
security find-generic-password -s gemini-cli-api-key
```

It returned 0. Both stdout and stderr were discarded; neither `-w` nor `-g` was
used. The installed implementation identifies this service and the
`default-api-key` entry in
`/opt/homebrew/lib/node_modules/@google/gemini-cli/bundle/chunk-32XQ54AJ.js`
(around line 310535). Presence does not prove a usable key, remaining credit, or
successful inference.

Only selected, nonsensitive settings fields were read:
`~/.gemini/settings.json` selects `security.auth.selectedType = gemini-api-key`.
No model override is present in that user settings file. None of
`GEMINI_API_KEY`, `GOOGLE_API_KEY`, `GOOGLE_GENAI_USE_VERTEXAI`,
`GOOGLE_CLOUD_PROJECT`, or `GOOGLE_CLOUD_LOCATION` is populated in this inspecting
process. This does not exclude project-specific environment loading in a future
session, and absence of these variables does not imply absence of the Keychain
key.

The installed implementation supports Google login, Gemini API key, Vertex AI,
and an AI API Gateway route. Its ordinary auth validation accepts the API key
from the environment or retained storage. Vertex validation requires project and
location, or a Google API key for its express route. This was verified from
installed source around `chunk-3PF5QBBI.js:60830` and
`gemini-63IMHOLI.js:15898`, not by attempting those routes.

There is no auth-status subcommand in the installed top-level help.
`~/.gemini/google_accounts.json` exists, but `oauth_creds.json` does not. No account
contents were printed. A separate safe `gcloud auth list --format=json` summary
reports two stored accounts and one active account; the conventional
`~/.config/gcloud/application_default_credentials.json` is absent. Gcloud login
is not evidence of a ready Gemini OAuth session or Vertex entitlement/ADC.
No alternative route has been validated, selected, or configured.

The historical failed provider request reported depleted prepaid credits.
**That remains historical evidence, not a refreshed billing status.** The
smallest next step is to establish availability on the already selected route,
or deliberately authorize and qualify another existing route, before buying any
memory trials. Login material alone does not clear the blocker.

## OpenCode: model present, runtime context still needs qualification

`~/.config/opencode/opencode.json` currently defines provider `ollama`, using
`@ai-sdk/openai-compatible` and `http://localhost:11434/v1`. Its model is
`qwen3-coder:30b-a3b-q8_0`. It declares no model `limit` or per-model options and no
top-level default model. No secret option values were printed.

Two read-only metadata requests succeeded:

- `GET http://localhost:11434/api/ps`: zero loaded models. There is no current
  loaded-model context size to report.
- `GET http://localhost:11434/api/tags`: the configured Qwen model is installed.
  Its architecture metadata reports a 262144-token context capacity. This is not
  the running server's allocated context and does not overturn the earlier
  observed 4096-token runtime or truncation to a 2050-token input budget.

`opencode run --help` has no direct context-size flag. The existing harness uses
`OPENCODE_CONFIG` and `OPENCODE_CONFIG_DIR` for scratch configuration; those are
reusable integration points already exercised by previous non-model delivery
checks. A declared client context limit alone does not enlarge an Ollama runtime.
The [prior context diagnostic](../memory-bench/results/memory-routes/2026-09-06-host-context-diagnostic-01/diagnosis.json)
and [tokenizer proof](../memory-bench/results/memory-routes/2026-09-06-host-context-diagnostic-01/tokenizer-model-proof.json)
remain unchanged.

The next remedy is a separately isolated, explicitly sized local server/model
profile, paired with matching client limits and enough room for instructions,
tools, task, and output. Verify actual context and absence of truncation before
admission. No server was started, restarted, reconfigured, or asked to load a
model here. Switching OpenCode to another provider/model would be a distinct
profile needing its own authentication and admission evidence.

## Copilot: launcher resolved, actual CLI not found

The shim strips its own directory from PATH and runs `copilot --version` to find
the real CLI. Its embedded minimum version is `0.0.394`; that is a compatibility
threshold, not an installed version. Its installation paths mention the
`@github/copilot` npm package and Homebrew's `copilot-cli`, but no installation
was performed.

The actual CLI did not resolve after excluding the shim from PATH. A bounded
file inventory found no matching CLI or `@github/copilot` installation under:

- Homebrew global Node packages and binary directories, plus `/usr/local/bin`.
- `~/.local/bin`, `~/.local/share`, `~/bin`, and `~/.npm/_npx`.
- `~/.vscode/extensions`, the supplied VS Code Copilot shim directory, and
  `~/.copilot`.

`~/.nvm` and `~/.volta` were absent. The search found a Copilot skill template's
`package.json`, which is not the CLI. This is a bounded search and PATH result,
not a claim that no executable could exist anywhere on the machine. The VS Code
extension or an unrelated GitHub login is not proof of usable Copilot CLI auth.
The next remedy is to make the actual executable discoverable or explicitly
install it, then inspect its own version/help/auth metadata and qualify its exact
model before scheduling trials. That work was not performed in this inventory.

## Current facts versus historical model availability

The completed [contract experiment](memory-contract-experiments-2026-09-06.md)
establishes successful inference on Claude/Sonnet 4.6 and Codex/GPT-6 Astra under
its frozen profiles. Today's local status checks support continued login
presence; they do not claim a new successful provider request. Prior Gemini,
OpenCode, and Copilot blockers are retained in the
[host coverage audit](memory-hosts-coverage-audit-2026-09-06.md) and its linked logs.
No earlier blocked slot or failed trial has been relabeled, repaired, or rerun.

The next redesigned schedule should preserve all five candidates in its coverage
matrix. Admit each actual CLI/model/profile only with the necessary real smoke
when authorized and technically ready; keep unavailable profiles explicit, with
concrete blockers. Pin native-memory behavior and instruction discovery separately
from authentication, model capacity, and successful inference.

## Commands used for this inventory

All prompt-bearing agent entry points were avoided. These were help, status,
file-metadata, selected configuration-field, and local service metadata reads:

```text
claude --version
claude --help
claude auth --help
claude auth status
codex --version
codex --help
codex login --help
codex login status
codex exec --help
codex features --help
codex features list
gemini --version
gemini --help
opencode --version
opencode --help
opencode run --help
opencode providers --help
opencode providers list
opencode debug --help
<VS Code Copilot shim> --version
<VS Code Copilot shim> --help
security find-generic-password -s gemini-cli-api-key  [all output suppressed]
gcloud auth list --format=json  [account identities suppressed]
GET localhost:11434/api/ps
GET localhost:11434/api/tags
```

`rg --files` and bounded source searches inspected launcher/package locations and
installed auth implementations. No credentials file was opened for its values.
Status output was summarized through a whitelist of fields; the report records
no secret material. This report is the only intentional workspace change; CLI
status commands may maintain their own incidental diagnostic logs.
