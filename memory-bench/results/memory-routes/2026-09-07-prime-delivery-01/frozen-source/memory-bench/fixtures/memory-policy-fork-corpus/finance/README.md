# Meridian Credits finance family

Two unblinded, independently reviewable worlds: account-first and subscription-first. Each is a self-contained ordinary coding exercise with tasks.json, starter, delayed public_tests, hidden graders, and a same-author separately implemented reference. The logical family is finance; world assignment should match within each compared profile/arm.

The current agreement reverses cap scope at stage3. Scalar output cannot establish cap scope; aggregate totals cannot establish line-allocation priority. Stage2 needs original cap scope; stage4 needs current allocation priority; stage5 needs original allocation priority. Source approval issues and any actual agent documentation remain legitimate sources. No memory names, keys, lookup/save instructions or handoff requests appear in product tasks or the starter.

All public command examples specify their release and remain applicable. A current-default change does not invalidate earlier explicit-release examples. Stage6 requests only support/MC-406.json under completely supplied current rules; no new endpoint or permanent policy is introduced.

Validation: 680/680 cumulative hidden cases; 60 cumulative public-case comparisons,12 actual checker invocations,2 starter smoke invocations;22/22 defect variants rejected. Evidence and source hashes are in validation-summary.json and validation-1788805781864040000/report.json. No candidate model has run. Independent task/oracle review is required before freeze.

Hidden stage6 includes an artifact-only case with artifact_json_path and expected, mutually exclusive with stdin. The runner should read that fixed relative path from the saved candidate workspace, reject escaped/symlink targets, and strictly compare parsed JSON types and structure. Other cases retain name/stdin/expected/argv.
