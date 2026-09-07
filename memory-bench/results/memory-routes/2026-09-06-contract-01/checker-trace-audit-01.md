# Public checker trace audit

All 32 sessions produced complete final artifacts and passed their first ordinary
unittest invocation. There were 33 invocations, all successful. No natural
contract-failure → code-edit → passing-rerun sequence occurred.

| Case | Stages | Checker read before code | Read after only | First suite passes | Suite runs | Stages adding tests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| claude-baseline | 8 | 0 | 0 | 8 | 8 | 8 |
| claude-checker | 8 | 6 | 1 | 8 | 8 | 3 |
| codex-checker | 8 | 7 | 0 | 8 | 8 | 8 |
| codex-baseline | 8 | 0 | 0 | 8 | 9 | 8 |

Baseline cases had no checker file or checker-source exposure. The checker remained
byte-identical in both checker lifecycles. No stage changed or removed a prior
workspace file; each added its target component and, in 27/32 stages, component tests.

The checker source was delivered before component creation in 14/16 treatment
stages. Claude read it after creation in `revise` and made no separate source read
in `revised_direct`. All 16 treatment sessions still ran the ordinary suite containing
the canonical checker. Exposure may guide implementation before a failure, but
both baseline lifecycles also succeeded, so this run establishes no incremental effect.

| Case / stage | Checker source timing | First suite test count | Suite runs |
| --- | --- | ---: | ---: |
| [claude-baseline/establish](cases/claude-baseline/establish/tool-calls.json) | absent | 8 | 1 |
| [claude-baseline/direct](cases/claude-baseline/direct/tool-calls.json) | absent | 15 | 1 |
| [claude-baseline/search](cases/claude-baseline/search/tool-calls.json) | absent | 22 | 1 |
| [claude-baseline/revise](cases/claude-baseline/revise/tool-calls.json) | absent | 30 | 1 |
| [claude-baseline/revised_direct](cases/claude-baseline/revised_direct/tool-calls.json) | absent | 38 | 1 |
| [claude-baseline/revised_search](cases/claude-baseline/revised_search/tool-calls.json) | absent | 46 | 1 |
| [claude-baseline/supplied](cases/claude-baseline/supplied/tool-calls.json) | absent | 53 | 1 |
| [claude-baseline/historical](cases/claude-baseline/historical/tool-calls.json) | absent | 60 | 1 |
| [claude-checker/establish](cases/claude-checker/establish/tool-calls.json) | before code | 2 | 1 |
| [claude-checker/direct](cases/claude-checker/direct/tool-calls.json) | before code | 2 | 1 |
| [claude-checker/search](cases/claude-checker/search/tool-calls.json) | before code | 2 | 1 |
| [claude-checker/revise](cases/claude-checker/revise/tool-calls.json) | after code | 2 | 1 |
| [claude-checker/revised_direct](cases/claude-checker/revised_direct/tool-calls.json) | no separate read | 2 | 1 |
| [claude-checker/revised_search](cases/claude-checker/revised_search/tool-calls.json) | before code | 9 | 1 |
| [claude-checker/supplied](cases/claude-checker/supplied/tool-calls.json) | before code | 17 | 1 |
| [claude-checker/historical](cases/claude-checker/historical/tool-calls.json) | before code | 24 | 1 |
| [codex-checker/establish](cases/codex-checker/establish/tool-calls.json) | no separate read | 7 | 1 |
| [codex-checker/direct](cases/codex-checker/direct/tool-calls.json) | before code | 13 | 1 |
| [codex-checker/search](cases/codex-checker/search/tool-calls.json) | before code | 19 | 1 |
| [codex-checker/revise](cases/codex-checker/revise/tool-calls.json) | before code | 26 | 1 |
| [codex-checker/revised_direct](cases/codex-checker/revised_direct/tool-calls.json) | before code | 32 | 1 |
| [codex-checker/revised_search](cases/codex-checker/revised_search/tool-calls.json) | before code | 38 | 1 |
| [codex-checker/supplied](cases/codex-checker/supplied/tool-calls.json) | before code | 44 | 1 |
| [codex-checker/historical](cases/codex-checker/historical/tool-calls.json) | before code | 49 | 1 |
| [codex-baseline/establish](cases/codex-baseline/establish/tool-calls.json) | absent | 6 | 1 |
| [codex-baseline/direct](cases/codex-baseline/direct/tool-calls.json) | absent | 11 | 1 |
| [codex-baseline/search](cases/codex-baseline/search/tool-calls.json) | absent | 16 | 1 |
| [codex-baseline/revise](cases/codex-baseline/revise/tool-calls.json) | absent | 21 | 1 |
| [codex-baseline/revised_direct](cases/codex-baseline/revised_direct/tool-calls.json) | absent | 26 | 1 |
| [codex-baseline/revised_search](cases/codex-baseline/revised_search/tool-calls.json) | absent | 31 | 1 |
| [codex-baseline/supplied](cases/codex-baseline/supplied/tool-calls.json) | absent | 36 | 1 |
| [codex-baseline/historical](cases/codex-baseline/historical/tool-calls.json) | absent | 36 | 2 |

Codex baseline historical ran 36 tests successfully after a shell here-document failed
to create its replay test file. It added that test with the file tool, then passed 41
tests. Its component did not change between runs. This was shell recovery and added
coverage, not repair following a failing checker. Other observed shell errors concerned
memory/task authoring. [Historical trace](cases/codex-baseline/historical/tool-calls.json).

Claude checker retained the correct v1 policy, rationale, approval ID, date and separate
version marker, but omitted `, version v1` from the exact SOURCE phrase. Revision copied
that imperfect original body verbatim to `.v1-snapshot`. This is loss of the exact field
text, not loss of factual source identity. Correct source exports in retained code were
also read, so later correct artifacts do not certify memory-only fidelity.
[Initial record](cases/claude-checker/establish/memory-after.json),
[revision record](cases/claude-checker/revise/memory-after.json).

Claude checker historical obtained the entire original note using
`bd memories "v1-snapshot" --json`, after unsuccessful invented `memories list/show`
paths. It did not call `bd recall`. This was full-body retrieval through a query,
rather than a preview or the prescribed explicit recall route.
[Historical trace](cases/claude-checker/historical/tool-calls.json).

All actual authored follow-ups use retained keys and explain applicability. Some include
policy values or richer instructions; earlier code and tasks remain legitimate alternate
sources. Each lifecycle made three actual memory writes, with no reproduction writes or
historical-body changes. Claude baseline’s “immutable record” phrase expresses a desired
preservation policy; it does not establish an enforced storage guarantee. A second
independent provenance review found no other material unsupported claims.

These are four correlated synthetic lifecycles. No intermediate filesystem snapshots
exist: Claude full Write contents expose initial policies, whereas Codex change events
usually expose paths only. All 16 Claude initial written policies already match their
approvals. No trace demonstrates contract-driven repair. Source exposure does not prove
causal influence, and exact-field checks do not certify all surrounding prose. This is
not a production reliability estimate or validation of a new Memory bead type.

[Structured evidence](checker-trace-audit-01.json) records all 32 rows and hashes of 1322
input files, plus symlink identities. Every input was rechecked unchanged after the audit.
