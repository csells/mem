# Workflow feedback at the second infrastructure interruption

This is a diagnostic checkpoint of the 28 assessed sessions. The planned cohort
has 216 slots; it is not the phase-1 comparison or the final experiment report.
The family auditors separately adjudicate memory fidelity and correct use.

Three rejected command forms received useful correction feedback:

| Session | Rejected request | Subsequent actual command |
| --- | --- | --- |
| OpenCode/Qwen, finance, thin-prime, stage 1 | `bd update ... --status completed` | `bd close ...` succeeded |
| zcode/GLM, Courier, rich-prime, stage 1 | `bd close ... --note ...` | `bd close --help`, then `--reason ...`, succeeded |
| zcode/GLM, Courier, rich-prime, stage 2 | `bd ls` | Error suggested `list`; `bd list` succeeded |

Their `.workflow.json` records retain receipt indices, exact stderr and links to
the original argv. These are evidence for improving command discovery, help and
possibly aliases. They do not establish that adding every attempted form is the
right API change. No explicit `--feedback` channel was installed in this cohort.

Five Haiku sessions invoked native `Skill` with `beads` and `prime --no-memories`
arguments. None of those five actually executed `bd prime`. The skill tool
reported that it launched the skill; the CLI prime output was therefore not
delivered through that requested route. Native skill calls and actual CLI
executions need separate counts.

Three Qwen sessions produced pseudo-tool markup as ordinary assistant text and
then stopped. Their normalized traces, raw parent events, ancestry receipts and
isolated host databases contain no actual tool calls. They are finance
rich-prime stage 1, thin-prime stage 2 and startup-briefing stage 2. This is a
host/model invocation failure distinct from choosing not to capture a memory.

Qwen's Courier startup-briefing stage 1 also demonstrates a different measurement
hazard: the parent delegated to an Explore child, whose 16 tools are absent from
the parent normalized tool list. The isolated read-only database export records
the child and its actual `ollama/qwen3-coder:30b-a3b-q8_0` assistant messages.
Parent and child session token receipts are retained separately. Local cost
receipts are zero; hardware and energy costs remain unpriced.

Actual command receipts distinguish help from mutation. At this checkpoint,
there are five successful saves and 16 successful help calls. The frozen coarse
observer sometimes counts `remember --help` as a write; workflow counts exclude
that diagnostic inflation. Two full help outputs missing from normalized Codex
calls were recovered from raw tool-call output envelopes. Missing normalized
output alone is not evidence that the model lacked the information.

Host-reported known cost totals $0.738568, with ten sessions lacking dollar
receipts. These figures are incomplete cost evidence. The second interruption
was a change to the ignored user Codex TOML file, which is documented separately
in the reviewed effective-condition analysis. This audit does not describe all
global configuration files as unchanged.
