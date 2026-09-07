"""The one subprocess seam to the TS `mem` CLI.

`corpus.py` (store loading), `memory_systems/ours_system.py` (retrieval-v1), and
`harbor/base_rate_spike.py` (the `mem extract-errors` extractor) all shell out
to `mem ... --json` and unwrap the same success envelope (`{apiVersion, cmd,
ok, data, errors}`). This module owns that seam once, with the failure modes
the call sites should not each re-derive:

- the spawn itself (missing binary named with its fix, spawn OSErrors, timeout,
  non-zero exit) is diagnosed by `spawn.run_checked`, this module's ladder being
  one of the six that used to re-derive it (mem-o9plh);
- exit-0-but-malformed stdout is reported with the command and a stdout excerpt,
  not a bare JSONDecodeError with no context.

Every failure raises `MemCliError` (a RuntimeError) — the pipeline break is
always surfaced, never degraded to "no data".

This module also owns the NDJSON import wire format once: `write_ndjson` is
the one writer, and `import_records`/`import_lessons` own the
`--file`/`--store` argv contract to the TS importers.
"""

import contextlib
import json
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from membench.spawn import redact_credentials, run_checked

# Generous bound: `mem query` over the full ~6.6k-record store completes in
# seconds; anything beyond this is a hung server or a wedged subprocess, not a
# slow query.
DEFAULT_TIMEOUT_S = 120.0


class MemCliError(RuntimeError):
    """A `mem` CLI invocation failed (missing binary, timeout, non-zero exit,
    malformed envelope). Carries the command for context."""


def write_ndjson(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """One JSON object per line — the import format `mem import-records/-lessons`
    reads. Terminates every line rather than joining, so an empty `rows` writes an
    empty file and not a stray blank line (which is not a valid record)."""
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def run_mem_json(
    argv: list[str], *, input: str | None = None, timeout_s: float = DEFAULT_TIMEOUT_S
) -> dict[str, Any]:
    """Run `<argv> --json` and return the success envelope's `data`.

    `argv` is the full command including the binary path; `--json` is appended
    here so every caller goes through the envelope contract. `input`, if given,
    is piped to the process's stdin (e.g. `mem extract-errors` reads its input
    that way)."""
    cmd = " ".join(argv)
    completed = run_checked(
        [*argv, "--json"],
        what=cmd,
        not_found_hint="build the TS CLI first (npm run build at the repo root)",
        timeout_s=timeout_s,
        error=MemCliError,
        input=input,
    )
    try:
        envelope: dict[str, Any] = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        # An exit-0 echo site: `run_checked` never saw this text. Borrows the redaction half
        # only, because the bound here is this call's own (200, tighter than
        # `sanitised_child_output`'s) -- see that docstring for why redaction precedes the cut.
        raise MemCliError(
            f"{cmd} exited 0 but stdout is not a JSON envelope: "
            f"{redact_credentials(completed.stdout)[:200]!r}"
        ) from exc
    if not envelope.get("ok", False):
        raise MemCliError(f"{cmd} error: {envelope.get('errors')}")
    return cast(dict[str, Any], envelope["data"])


def _import_ndjson(
    subcommand: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    store_path: Path,
    mem_bin: str,
    file_path: Path | None = None,
) -> dict[str, Any]:
    """Write `rows` as NDJSON and run `mem <subcommand> --file <rows> --store <store>`.

    `file_path=None` stages the rows in a tempfile that is gone after the call;
    passing a path persists the NDJSON there as a run artifact."""
    with contextlib.ExitStack() as stack:
        staged = file_path
        if staged is None:
            workspace = stack.enter_context(tempfile.TemporaryDirectory(prefix="mem-import-"))
            staged = Path(workspace) / "rows.ndjson"
        write_ndjson(staged, rows)
        return run_mem_json(
            [mem_bin, subcommand, "--file", str(staged), "--store", str(store_path)]
        )


def import_records(
    rows: Sequence[Mapping[str, Any]],
    *,
    store_path: Path,
    mem_bin: str,
    file_path: Path | None = None,
) -> dict[str, Any]:
    """Import work records into `store_path`. Records must land before the lessons
    that cite them — that ordering stays at the call sites (the offline gate resolves
    held signatures between the two imports, so the seam cannot own it)."""
    return _import_ndjson(
        "import-records", rows, store_path=store_path, mem_bin=mem_bin, file_path=file_path
    )


def import_lessons(
    rows: Sequence[Mapping[str, Any]],
    *,
    store_path: Path,
    mem_bin: str,
    file_path: Path | None = None,
) -> dict[str, Any]:
    """Import lessons into `store_path` (after `import_records` — see its docstring)."""
    return _import_ndjson(
        "import-lessons", rows, store_path=store_path, mem_bin=mem_bin, file_path=file_path
    )
