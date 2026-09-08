# Prime-delivery experiment: final verification

The [final report](../../../../specs/memory-prime-delivery-results-2026-09-07.md)
separates measured outcomes, operational failures, practitioner observations and
proposed improvements. Execution and all 196 assessed-session semantic audits are
finished. No claimed trial was rerun, no retained agreement was repaired by the
investigator, and no frozen condition was changed to improve an outcome.

## Final evidence

- [Mechanical counts](final-mechanical.json): 196/216 sessions assessed,
  120 correct artifacts, 13,134/15,554 assessed hidden checks, and
  $10.5592762 reported scored usage with 94 unknown-dollar receipts.
- [Semantic outcomes](final-semantic-corrected.json): all 36 planned lifecycles and 108
  planned prior-use legs retained; 1 strict handoff, 9/34 complete initial
  captures and 33 successful preparatory uses, including 23 with complete
  faithful required entries. Thirty-one lifecycles have all six assessments.
- [Conditional denominators](final-behavior-denominators-corrected.json): 88 prior-use legs
  with generation, 38 applicable entries and 33 successful uses; 26 controls with
  generation, 13 with a prior record, zero duplicate captures, 25 correct support
  attachments and 13 correct accumulated products. These supplement the planned
  denominators rather than replace them.
- [Terminal phase summary](../2026-09-07-prime-delivery-01/recovery-02/phase2/summary.json):
  `stopped_with_new_fault`, with Astra and GLM blocked and no shared-input fault.
  Twenty slots remain unassessed: twelve original prelaunch/dependent slots,
  two later authentication slots, and six after the GLM deadline/terminal-receipt
  fault. Twenty assessed Astra turns had no generation after provider denial.
- [Authoritative operational dispositions](../2026-09-07-prime-delivery-01/audits/workflow-2alw5dw6/final-dispositions-1788832158835590000.json)
  identify every slot separately. The original observer's earlier censor labels
  remain preserved and are not the authority for later failures.
- [Workflow review](../2026-09-07-prime-delivery-01/audits/workflow-2alw5dw6/final-workflow-review-1788832361529065000.md)
  binds actual generation, prime/reference exposure, native-memory observations,
  primary/helper models, costs, Qwen's observer false negative and GLM's timeout.
- [Finance final export](../2026-09-07-prime-delivery-01/audits/finance-cp3z5hwq/normalized-final-1788832220883503000.json)
  covers 96 assessed sessions and twelve censored slots; the
  [Courier final export](../2026-09-07-prime-delivery-01/audits/courier-begfwz8d/FINAL-lifecycles-corrected-1788832644234050000.json)
  covers 100 assessed sessions and eight censored slots. Both bind original
  evidence and preserve partial-entry and source/provenance qualifications.

The corrected semantic exports preserve an explicit review correction: Luna's
Courier rich-prime stage 4 had an applicable partial record available despite a
failed search. The conditional available-entry denominator is 38, not the earlier
37; successful-use, complete-entry and core counts are unchanged. Original
exports and stage audits remain intact. Availability is distinct from delivery.

## Integrity and preservation

[Final integrity](final-integrity.json) verifies all 450 frozen source files,
seven executables, 196 task/launch/package checks, actual-key catalogs and exact
memory carry-forward. Three of four raw global profile hashes still match. The
sole mismatch is the previously reviewed Codex configuration change; the frozen
adapter's effective settings remained unchanged. It is reported, not erased.

[Final preservation](final-preservation-corrected.json) verifies all 264 earlier
policy-handoff results, 68 protected first-phase results and twelve admission
inputs. An earlier audit incorrectly treated slot IDs as filesystem paths; its
false missing-path report is retained in `final-preservation.json`, with the
correction and its hash explicitly linked. No original evidence changed.
An [independent terminal review](../2026-09-07-prime-delivery-01/audits/courier-begfwz8d/independent-terminal-mechanical-preservation-review-1788832292120384000.json)
repeated the counts and preservation checks successfully.

The supervisor and read-only watcher exited before final exports. The
[owned watch-registry closure](../2026-09-07-prime-delivery-01/audits/workflow-2alw5dw6/watch-terminal-closure-1788832397798952000.json)
preserves the original start, PID and 216-slot denominator and records execution
finished with 196 assessments and twenty censored slots. It does not claim
216/216 completion or infer memory success from process exit.

## Applicable verification

The [pre-run checks](targeted-checks-01.json) and [log](targeted-checks-01.log)
record 76 passing targeted/shared tests and passing Ruff, Black and strict mypy
for the new delivery package, runtime, orchestrator and qualifications. The
[twelve real delivery qualifications](../2026-09-07-prime-delivery-qualification-01/result.json)
passed explicit diagnostics across all six pinned profiles before scoring.
Those explicit diagnostics are not voluntary-adoption observations.

Additional bounded checks cover the read-only recovery and reporting paths:

- [Five completed-turn assessment guards](recovery-tests-01.json), with no new inference.
- [Twenty-three continuation guards](../2026-09-07-prime-delivery-01/recovery-02/verification-1788825610545656000.json),
  including existing-claim refusal and the effective configuration condition.
- [Seven aggregate-denominator guards](final-analysis-guard-tests-1788830404940332000.json).
- [Fifteen operational-disposition guards](../2026-09-07-prime-delivery-01/audits/workflow-2alw5dw6/final-dispositions-verification-1788829365266191000.json).
- [Five delivery-exposure guards](../2026-09-07-prime-delivery-01/audits/workflow-2alw5dw6/delivery-exposure-verification-1788829794105234000.json).

No broader unchanged test suite was rerun for this report. The preceding
[repository verification state](../2026-09-07-policy-handoff-verification-01/SUMMARY.md),
including its platform limitations, remains preserved. This summary claims the
specific checks above; it does not claim a newly green full-repository test run.

This small, partly censored synthetic comparison does not establish production
reliability, an isolated host effect, a winning prompt surface, native-memory
reliability, relevant-header selection at prime, or conformance of the proposed
new Memory bead type.
