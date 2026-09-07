# HarborPass sequential CLI exercise

This package contains six cumulative product issues for a small Python standard-library renewal-notice CLI.

- `tasks.json`: shared public contract and six ordered issue descriptions. Supply the shared contract with issue 1 and preserve the issue history.
- `starter/`: runnable starting project, public documentation, two smoke tests, and the public-example runner. Copy only this directory into the coding agent's working project initially.
- `public_tests/stage_N.json`: public examples accompanying issue N. Deliver the applicable examples with each issue. A later explicit policy revision changes the expected live behavior of earlier examples.
- `graders/stage-N.json`: hidden, cumulative black-box cases for stage N. Each case is `{ "name": STRING, "stdin": OBJECT, "expected": OBJECT, "argv": [] }`. Run `python3 main.py`, send the stdin object as JSON, require exit status zero, parse exactly one stdout JSON value, and compare exact JSON types, keys, values, and array order. JSON key order and outer whitespace do not matter.
- `graders/grade.py`: optional standalone black-box grader with the same cases.
- `reference/main.py`: separately implemented business reference; `--stage N` selects cumulative release behavior, defaulting to stage 6.
- `reference/SPEC.md`: the business specification used for reference implementation.
- `graders/mutants/`: intentionally wrong copies used solely to establish grader sensitivity.

Keep graders, reference code, mutation files, and authoring reports outside the evaluated agent's context. Prior coding-agent source, prior issues, and ordinary project history remain available as later issues run. No deletion or reset of prior information is required.

Run a candidate stage from this package directory:

```sh
python3 graders/grade.py --stage 4 --project /path/to/candidate
```

Validate every cumulative reference release, every public example, serialized grader consistency, and all four defect mutations:

```sh
python3 graders/validate.py
```

Run the executable starter's smoke tests:

```sh
python3 -m unittest discover -s starter/tests -v
```

The exercise has no dependencies, network activity, Git setup, or real customer data. Python 3.9+ is sufficient.

This revision preserves the initial authored exercise at `/tmp/harbor-renewal-exercise.pTuzHK`. The support preview repeats the fully supplied release 1.0 notice policy and remains frozen when live policy changes.
