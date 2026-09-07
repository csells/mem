"""Real corpus loader — feed the P1.5 store into the replay path under the guard.

Loads the work-audit graph (the SQLite+FTS5 sidecar) through the existing TS
store-reader primitive (`mem query --json`, which is `queryRecords`) and projects
each WorkRecord onto the LOO-relevant `WorkRef` (`validity.work_ref_from_record`).
No new substrate, no re-parsing of the store schema in Python: the same reader the
retrieval path uses produces the corpus the harness-owned LOO guard then bounds.

The query work is loaded the same way (`mem query <work_id> --json` →
`validity.query_from_record`), so the boundary the guard enforces is the record's
own `started` — never a value the harness picks.
"""

from collections.abc import Callable
from typing import Any

from membench.mem_cli import run_mem_json
from membench.schemas.work_record import WorkRecord
from membench.validity import (
    QueryWork,
    WorkRef,
    query_from_record,
    work_ref_from_record,
)

# A runner takes the `mem` argv (without `--json`) and returns the success
# envelope's `data`. Injectable so the loader is testable without a built CLI.
CorpusRunner = Callable[[list[str]], dict[str, Any]]


def _default_runner(mem_bin: str) -> CorpusRunner:
    """Shell to the `mem` CLI through the shared seam (`mem_cli.run_mem_json`:
    timeout, missing-binary and malformed-envelope context, fail-loud)."""

    def run(args: list[str]) -> dict[str, Any]:
        return run_mem_json([mem_bin, *args])

    return run


def _resolve(runner: CorpusRunner | None, mem_bin: str | None) -> CorpusRunner:
    if runner is not None:
        return runner
    if mem_bin is None:
        raise ValueError("corpus loader needs either an injected `runner` or a `mem_bin` path.")
    return _default_runner(mem_bin)


def load_corpus(
    store_path: str,
    *,
    mem_bin: str | None = None,
    runner: CorpusRunner | None = None,
) -> list[WorkRef]:
    """Load the whole store as a `WorkRef` corpus (the LOO guard bounds it per
    query). Order is the reader's deterministic `ORDER BY work_id`.

    Each record is validated against the `WorkRecord` contract before projection,
    so a malformed record fails loudly here rather than downstream."""
    data = _resolve(runner, mem_bin)(["query", "--store", store_path])
    records = data["records"]
    for record in records:
        WorkRecord.model_validate(record)
    return [work_ref_from_record(record) for record in records]


def load_query_work(
    store_path: str,
    work_id: str,
    *,
    mem_bin: str | None = None,
    runner: CorpusRunner | None = None,
) -> QueryWork:
    """Load one record and build its replay query context. Raises if the work_id
    is absent — a replay against a non-existent query work is a caller error, not
    an empty run."""
    data = _resolve(runner, mem_bin)(["query", work_id, "--store", store_path])
    records = data["records"]
    if not records:
        raise ValueError(f"no record for work_id {work_id!r} in {store_path}")
    record = records[0]
    WorkRecord.model_validate(record)
    return query_from_record(record)
