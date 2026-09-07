"""Landing-commit ANCHOR bundles (mem-bxhh.3.2) -- the real fail-to-pass eval objects.

The trace-replayed `assemble_bundle` path turns a bead's transcript into a bundle
whose gold diff is a *reconstruction* (the agent's edits replayed against an
approximate base). This module builds the other kind: a bundle anchored on a real
rig LANDING COMMIT, whose gold diff is ground truth (``git diff parent..landing``)
and whose verification carries a curated fail-to-pass oracle (`harbor.ftp_curate`).
These are the discriminating eval anchor the flat N=9 dashboard pool lacked
(docs/mem-rig-eval-infra-feasibility.md): a memory arm either reproduces the
landing change well enough to turn the red->green tests green, or it does not.

Shape differences from a replayed bundle, all honest about the different provenance:

- ``output`` is a `ReplayResult` with NO ``calls`` -- nothing was replayed. Its
  ``file_diffs`` is the real two-ref diff and ``replay_success_rate`` is 1.0: the
  gold diff is exact by construction, not a fidelity estimate. (The empty-calls
  ==> 0.0 convention in `replay` marks a transcript that produced no diff as
  non-admittable; it does not apply here, where the diff comes from git, not a
  replay -- so the rate is the authoritative 1.0.)
- ``trace_ref`` points at the git commit (``git:<rig>@<sha>``), not a ``.jsonl``:
  the mined source is the commit, there is no transcript.
- ``loo_excluded_work_ids`` is just the anchor's own id. A landing commit is not a
  bead with convoy/issue siblings, so self-exclusion is the whole boundary.

ZFC: pure mechanism -- git IO (injectable `Runner`), structural field reads, set
ops. No model calls, no semantic heuristics. ``behavioral`` vs ``feature_presence``
was decided upstream by `ftp_curate` (a structural fact), not judged here.
"""

from __future__ import annotations

import subprocess
import typing
from collections.abc import Mapping, Sequence
from pathlib import Path

from membench.bundle.replay import ReplayResult
from membench.schemas.bundle import (
    BundleEnv,
    BundleVerification,
    FtpOracle,
    FtpType,
    TaskBundle,
)
from membench.spawn import Runner

# Anchor bundles carry a ground-truth git diff, not a replayed one: no mutation
# calls were applied, and the diff is exact. 1.0 says "authoritative", distinct
# from the replay path's empty-calls==>0.0 ("no diff, non-admittable") convention.
_ANCHOR_REPLAY_SUCCESS_RATE = 1.0

# Allowed FtpType values -- guards a hand-written oracle payload at the boundary.
# Derived from the schema Literal so it can never drift from `FtpType`.
_FTP_TYPES: frozenset[str] = frozenset(typing.get_args(FtpType))


def _git_out(clone: Path, args: Sequence[str], runner: Runner) -> str:
    completed = runner(
        ["git", "-C", str(clone), *args], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {clone} failed: {completed.stderr.strip()}")
    return completed.stdout


def landing_gold_diff(
    clone: Path, parent: str, landing: str, *, runner: Runner = subprocess.run
) -> dict[str, str]:
    """The per-file gold diff of ``landing`` against ``parent`` (``parent..landing``).

    File names come from ``--name-only -z`` (NUL-delimited -- robust to spaces),
    then one ``git diff parent..landing -- <path>`` per file keeps the split
    unambiguous (mirrors `replay.gold_diff`, two refs instead of a working tree)."""
    rng = f"{parent}..{landing}"
    names = _git_out(clone, ["diff", "--no-color", "--name-only", "-z", rng], runner)
    return {
        name: _git_out(clone, ["diff", "--no-color", rng, "--", name], runner)
        for name in names.split("\0")
        if name
    }


def commit_subject_body(
    clone: Path, sha: str, *, runner: Runner = subprocess.run
) -> tuple[str, str]:
    """``(subject, body)`` of ``sha`` -- the anchor bundle's issue leg. ``%s`` is the
    one-line subject, ``%b`` the rest of the message (empty for a single-line one)."""
    subject = _git_out(clone, ["show", "-s", "--format=%s", sha], runner).strip()
    body = _git_out(clone, ["show", "-s", "--format=%b", sha], runner).strip()
    return subject, body


def ftp_oracle_from_payload(entry: Mapping[str, object]) -> FtpOracle:
    """Map one `ftp_curate.rig_report` ``commits[]`` entry onto an `FtpOracle`.

    The harbor dataclass and the schema model share field names; this is the one
    place that crosses the harbor->schema boundary (the schema stays an import
    leaf). The ``type`` value is checked against the closed vocabulary so a typo in
    a hand-edited oracle fails loudly rather than slipping past the Literal."""
    ftp_type = entry.get("type")
    if ftp_type not in _FTP_TYPES:
        raise ValueError(f"ftp oracle has unknown type {ftp_type!r} (expected one of {_FTP_TYPES})")
    try:
        commit, parent = str(entry["commit"]), str(entry["parent"])
    except KeyError as exc:
        raise ValueError(
            f"ftp oracle entry missing required field {exc}; got keys {sorted(entry)}"
        ) from exc
    return FtpOracle(
        commit=commit,
        parent=parent,
        ftp_tests=tuple(_str_seq(entry, "ftp_tests")),
        behavioral=tuple(_str_seq(entry, "behavioral")),
        feature_presence=tuple(_str_seq(entry, "feature_presence")),
        type=ftp_type,  # type: ignore[arg-type]  # membership-checked against FtpType above
    )


def _str_seq(entry: Mapping[str, object], key: str) -> list[str]:
    value = entry.get(key, [])
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise ValueError(f"ftp oracle field {key!r} must be a list of nodeids, got {value!r}")
    return [str(v) for v in value]


def anchor_bundle(
    *,
    rig: str,
    repo: str,
    base_image: str,
    ftp: FtpOracle,
    gold_file_diffs: Mapping[str, str],
    issue_title: str,
    issue_body: str = "",
    work_id: str | None = None,
) -> TaskBundle:
    """Build the `TaskBundle` for one landing-commit anchor.

    ``ftp.commit``/``ftp.parent`` are the anchors: the bundle checks out ``repo`` at
    ``ftp.parent`` (the base) and the graded arm must reproduce the change that
    turns ``ftp``'s tests green. ``gold_file_diffs`` is the ground-truth
    ``parent..commit`` diff -- a non-empty diff is required (a landing commit with
    no diff is not a task). ``work_id`` defaults to ``<rig>-<sha12>``."""
    if not gold_file_diffs:
        raise ValueError(f"anchor {rig}@{ftp.commit[:12]} has an empty gold diff -- not a task")
    if not issue_title.strip():
        raise ValueError(f"anchor {rig}@{ftp.commit[:12]} has an empty issue title -- no task leg")
    wid = work_id or f"{rig}-{ftp.commit[:12]}"
    output = ReplayResult(
        calls=(),
        file_diffs=tuple(sorted(gold_file_diffs.items())),
        replay_success_rate=_ANCHOR_REPLAY_SUCCESS_RATE,
    )
    return TaskBundle(
        work_id=wid,
        rig=rig,
        issue_title=issue_title,
        issue_body=issue_body,
        trace_ref=f"git:{rig}@{ftp.commit}",
        output=output,
        env=BundleEnv(repo=repo, base_commit=ftp.parent, base_image=base_image),
        loo_excluded_work_ids=(wid,),
        verification=BundleVerification(ftp_oracle=ftp),
    )


def materialize_rig_anchors(
    rig: str,
    clone: Path,
    oracle_commits: Sequence[Mapping[str, object]],
    out_dir: Path,
    *,
    repo: str,
    base_image: str,
    runner: Runner = subprocess.run,
) -> list[Path]:
    """Materialize one anchor bundle per ``oracle_commits`` entry (a
    `ftp_curate.rig_report` ``commits[]`` list) into ``out_dir``.

    For each entry: pull the commit's subject/body and the ``parent..commit`` gold
    diff from ``clone``, build the `TaskBundle`, and write ``<work_id>.json``.
    Returns the written paths in input order. The diff and subject come from git
    (``clone`` must contain the commit); the parent + ftp set come from the oracle
    payload, which `ftp_curate` already computed -- no re-derivation."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for entry in oracle_commits:
        ftp = ftp_oracle_from_payload(entry)
        # The oracle records the landing SHA as it was passed to curate-ftp, which
        # may be an abbreviation (the feasibility-doc / bead form, e.g. "6f0c65").
        # Expand it to the full SHA so the work_id, trace_ref, and ftp.commit are
        # unambiguous in a durable artifact (the parent is already a full SHA from
        # rev-list). Resolved against the clone, where the commit must exist anyway.
        rev = f"{ftp.commit}^{{commit}}"
        full = _git_out(clone, ["rev-parse", "--verify", rev], runner).strip()
        if full != ftp.commit:
            ftp = ftp.model_copy(update={"commit": full})
        subject, body = commit_subject_body(clone, ftp.commit, runner=runner)
        gold = landing_gold_diff(clone, ftp.parent, ftp.commit, runner=runner)
        bundle = anchor_bundle(
            rig=rig,
            repo=repo,
            base_image=base_image,
            ftp=ftp,
            gold_file_diffs=gold,
            issue_title=subject,
            issue_body=body,
        )
        path = out_dir / f"{bundle.work_id}.json"
        path.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
        written.append(path)
    return written
