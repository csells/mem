# Four coding-agent CLIs: versions and harness qualification

Scope confirmed by the user: Claude Code, Codex, OpenCode, and zcode all work.
Gemini and Copilot are excluded from this experiment. A previous profile's
failure is not a verdict that its CLI is unusable.

## Updates completed

| CLI           | Before    | Current   | Verification                                                             |
| ------------- | --------- | --------- | ------------------------------------------------------------------------ |
| Claude Code   | 2.1.263   | 2.1.263   | `claude update` reports up to date on latest.                            |
| Codex         | 0.153.4   | 0.153.4   | Installed version equals npm's `latest` dist-tag. Alpha is not selected. |
| OpenCode      | 1.18.20   | 1.18.20   | `brew update`, then targeted `brew upgrade opencode`: already installed. |
| zcode-app-cli | 3.10.2-18 | 3.11.2-21 | Updated through npm's latest release; bundled runtime remains 0.16.5.    |

All update commands completed successfully. Hashes of the four existing
configuration files match before and after. No authentication, model selection,
native-memory settings, or existing model-server configuration was changed.
The zcode package and Claude executable were copied aside before updating;
Homebrew cleanup was disabled. Logs, before/after metadata, and rollback material
are retained at
`/var/folders/6k/xzgngnms6jg4_z2l40y0_9vh0000gn/T/memory-cli-updates-20260907-73uo3zw8/`.

The earlier inventory recorded OpenCode 1.18.15. It was already 1.18.20 when this
update pass began. Previous experiment fingerprints and outputs remain unchanged.

## Candidate headless profiles

| CLI         | Executable                        | Candidate primary model           | Interface                                                                                               |
| ----------- | --------------------------------- | --------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Claude Code | `/Users/csells/.local/bin/claude` | `claude-sonnet-4-6`               | `-p`, streaming JSON, project setting sources, noninteractive permissions.                              |
| Codex       | `/opt/homebrew/bin/codex`         | `gpt-6-astra`                     | `exec --json`, project rules enabled, existing ChatGPT login in private scratch config.                 |
| OpenCode    | `/opt/homebrew/bin/opencode`      | `ollama/qwen3-coder:30b-a3b-q8_0` | `run --format json --model … --pure --auto`; exact prompt bytes supplied through stdin.                 |
| zcode       | `/opt/homebrew/bin/zcode`         | `zai/glm-5.3`                     | `--prompt … --output-format stream-json --mode yolo --cwd …`; model pinned in supported project config. |

zcode is its own runtime, not an alias for another tested CLI. Its public launcher
reports both the npm package and bundled runtime versions. The installed runtime
supports streaming JSON even though its short help only advertises `--json`.
Model request events, session identity, tool result events, and terminal results
must be checked together; a zero shell exit alone does not certify completion.

Claude and Codex retain their previously tested model anchors and existing
authentication. zcode retains its configured Z.AI main model and existing API key;
the key is passed transiently rather than written into the project config.
OpenCode's configured provider and fallback identify the local Qwen model; no
remote provider or new credential is substituted. These are different model/host
profiles, so comparisons cannot attribute differences solely to the CLI.

## Isolation and instruction delivery

The new [host boundary](../memory-bench/membench/runner/memory_unprompted_hosts.py)
reuses the tested Claude/Codex launch and observation code. OpenCode and zcode
have separate preparation paths. Every launch runs inside the existing external
filesystem sandbox with writable scratch paths and a dedicated real Beads store.
User state and previous experiment evidence are outside its writable scope.

OpenCode keeps project discovery enabled. Disabling project configuration also
disables AGENTS discovery and would invalidate this experiment. Its explicit
project skill root remains enabled while personal skills and plugins are excluded.
The current preflight confirms the expected effective provider and skill paths.

zcode natively reads AGENTS.md and accepts the canonical project skill directory
through `skills.roots`. An isolated `skills list --json` discovers the Beads skill.
Its diagnostic about being unable to scan personal `~/.agents/skills` reflects
the deliberate sandbox boundary. Project skill discovery succeeds independently.
The public project override contains no credentials; storage and session database
paths are routed to scratch with supported environment overrides.

OpenCode has no separately configured automatic memory extractor in this profile;
the repository and any agent-created notes remain available. Its isolated and
normal-native conditions may therefore be equivalent. zcode's headless entry
explicitly disables automatic extraction; normal headless behavior must not be
reported as the desktop application's full native-memory behavior. Its memory
feature/use switches and actual retained files are recorded separately.

## Qualification status and evidence

The [paired integration driver](../memory-bench/scripts/memory_unprompted_smoke.py)
exercises file/shell work, issue operations, capture, search, full lookup, a known
missing-key error, and reuse from a fresh session. Unique markers placed only in
AGENTS, the skill, and its memory reference check instruction delivery. Actual
records carry forward without repair. These explicit integration tasks never
enter the ordinary-task adoption corpus.

Before inference, 62 focused adapter/receipt/isolation tests passed. New modules
passed strict mypy, Ruff, and Black. Isolated zcode skill discovery and OpenCode
effective-config checks passed without model calls:
[preflight evidence](../memory-bench/results/memory-routes/2026-09-07-four-cli-preflight-01/).

The real checks are recorded under
[four-CLI smoke evidence](../memory-bench/results/memory-routes/2026-09-07-four-cli-smoke-01/).
All eight sessions completed with their requested primary models. All four hosts
demonstrated instruction/skill delivery, real capture/search/full lookup, and
unchanged retained information in a fresh consumer session. Corrected strict
checks passed 6/8 sessions: Claude, Codex, and zcode passed both; OpenCode failed
marker checks and skipped search/prime in reuse. The
[qualification report](memory-four-hosts-qualification-2026-09-07.md) separates
those model adherence failures from working tool integration. Initial grades
remain preserved alongside read-only corrections; no session was repurchased.

The local OpenCode check uses a task-owned Ollama endpoint with an explicit
32768-token context and the installed model's bytes read-only. Its process and
logs are separate from the user's existing server. The running allocation is
checked from `/api/ps`; model architecture capacity or client metadata alone
does not establish the effective context. This is a qualified test profile,
not a change to the user's normal OpenCode or Ollama configuration.

See the [experiment description](../docs/adoption-harness/MEMORY-UNPROMPTED.md)
and [full plan](plans/0005-unprompted-memory-adoption.md) for the actual goals,
ordinary-task review, proposed 96-session comparison, and limits of the claims.
