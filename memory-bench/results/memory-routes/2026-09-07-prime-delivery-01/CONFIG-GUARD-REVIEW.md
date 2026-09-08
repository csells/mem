# Effective settings after a live Codex config change

The first operational continuation stopped at 28 assessed sessions when the
original whole-file profile guard detected a change to
`/Users/csells/.codex/config.toml`. Its failed continuation summary remains in
`recovery-01/phase1/summary.json`. Every started session has an assessment; no
additional slot was claimed or lost at this stop. The original two censored
lifecycles remain the only prelaunch claims.

The frozen Codex profile hash is
`fdf06fc3bdbd3a7996cb9d76a2fc1ccdf4056a23d50da6161005dae0a467408e`;
the observed changed hash is
`77da355d76bd24897476305420becd97593927945ca5e97f1389ae5568fa9b8b`.
The other three live profile hashes remain unchanged. The config writer and
exact textual change are not established, and the original full file was not
archived. No user config is restored, rewritten or replaced.

The [read-only source and launch review](audits/codex-config-effective-condition-review-1788825263695324000.json)
establishes why this byte change does not alter the tested Codex conditions:

- The frozen base adapter parses only `model_reasoning_effort` and
  `service_tier`, requiring both values to be strings.
- The frozen model-profile layer removes both inherited command-line overrides,
  inserts the profile's fixed `high` reasoning effort, and leaves the default
  service tier. Its public launch settings reflect those fixed values.
- The CLI runs with `--ignore-user-config`, explicit model/native-memory/tool
  settings and its isolated scratch configuration. Other source TOML fields do
  not enter the prepared invocation.
- All six assessed Codex launches began before the observed file modification
  and have the same normalized effective invocation. The other hosts' relevant
  configuration files did not change.

The guard refinement therefore validates effective experimental settings while
retaining the raw file mismatch as an observed deviation. It must continue to
check every original frozen source, executable, fixture and other host profile;
require the same expected Codex source home; reject an invalid TOML file or
non-string consumed settings; and bind the reviewed adapter transformation that
fixes the actual invocation. Tests exercise the complete prepare path with safe
synthetic config/auth inputs and no inference, not merely a guessed equivalence
of selected strings. Any changed effective condition still stops the run.

This is a second documented operational deviation from the original guard, not
a rewrite of its manifest or a new set of agent-facing conditions. All previous
results, failures, claims and recovery inputs remain immutable. A separately
reviewed `recovery-02` plan may run only the 176 untouched eligible slots:
40 remaining in phase 1 and 136 in phase 2. It retains durable file logging,
the original order, four workers, model pins, native settings, deadlines,
actual records and independent graders. An exact phase-1 summary review is still
required before phase 2. No prior trial is rerun or repurchased.

The maximum remains 204 assessed sessions out of 216 planned. Report both
operational interruptions, twelve censored slots, the one posthoc assessment,
and the complete-cell sensitivities declared in `OPERATIONAL-RECOVERY.md`.
Preserving a valid effective configuration does not establish memory adoption,
faithful capture or correct subsequent work; those outcomes still require the
independent artifact and semantic audits.
