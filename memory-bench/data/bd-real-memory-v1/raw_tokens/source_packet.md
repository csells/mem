Repository orientation at parent 3a8d18988ea5cdcb6bd3f1032ab22c9bdce4cb2b.
Source: src/codeprobe/core/executor.py, lines 807-828.

```python
    # Scoring details — emit the unified ScoreResult contract: ``reward``
    # mirrors ``score`` (codeprobe / EB / CSB read either name) and
    # ``diagnostics`` carries run-level cost / time alongside the IR
    # breakdown the scorer already populated. Existing top-level fields
    # (score, status, scorer_family, sub_scores, …) stay so older
    # consumers keep working.
    scoring = {
        "score": completed.automated_score,
        "reward": completed.automated_score,
        "status": completed.status,
        **completed.scoring_details,
    }
    diagnostics: dict = {}
    existing_diag = completed.scoring_details.get("diagnostics")
    if isinstance(existing_diag, dict):
        diagnostics.update(existing_diag)
    diagnostics["task_time_seconds"] = float(completed.duration_seconds)
    if completed.cost_usd is not None:
        diagnostics["token_cost_usd"] = float(completed.cost_usd)
    scoring["diagnostics"] = diagnostics
    (task_dir / "scoring.json").write_text(
        _json.dumps(scoring, indent=2) + "\n", encoding="utf-8"
```
