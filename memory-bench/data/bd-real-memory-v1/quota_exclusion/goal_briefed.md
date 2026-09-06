Quota-errored trials currently distort reported task-quality statistics. Exclude them from the reward population in configuration summaries, completed-task summaries, and paired comparisons; retain an explicit quota count and handle an all-quota population.

Existing repository context:

Repository orientation at parent 94d357cf148a742aba88505bbaafc37303f3bb19.
Source: src/codeprobe/analysis/stats.py, lines 281-286.

```python
    # Count of trials whose ``error_category == "quota"`` — broken out
    # separately because quota errors are unrecoverable infrastructure
    # failures, not task-quality failures, and should NOT roll into
    # ``mean_score`` (codeprobe-9xrl). Renderers surface this as a
    # warning so users see how much of the data is contaminated.
    quota_error_count: int = 0
```
