"""Difficulty banding for ftp-oracle anchor bundles (mem-on3f).

Gold-file-count is a weak but nonzero difficulty proxy (mem-f2vi's Option-A
re-run: 2-file codeprobe anchors solved every arm, >=5-file anchors failed
every arm). This buckets a bundle pool into tertiles of gold-file-count so a
cross-rig grid run can report per-band separation instead of one pooled
number.

ZFC: deterministic math over a structural signal (file count), not a semantic
difficulty judgment -- the actual claim ("does a band separate ours from
builtin") is decided from the graded grid's numbers, not from this bucketing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from membench.grading.probe_direct import gold_file_list
from membench.schemas.bundle import TaskBundle

BANDS: tuple[str, str, str] = ("easy", "medium", "hard")


@dataclass(frozen=True)
class DifficultyStats:
    work_id: str
    rig: str
    gold_files: int
    ftp_tests: int
    band: str


def gold_file_count(bundle: TaskBundle) -> int:
    return len(gold_file_list(bundle))


def ftp_test_count(bundle: TaskBundle) -> int:
    oracle = bundle.verification.ftp_oracle
    return len(oracle.ftp_tests) if oracle is not None else 0


def band_pool(bundles: Sequence[TaskBundle]) -> list[DifficultyStats]:
    """Tertile-bucket ``bundles`` by gold-file-count into easy/medium/hard.

    Ordering is ``(gold_file_count, work_id)`` so ties at a boundary (very
    common -- most anchors are 1-2 files) land deterministically regardless of
    glob/dict iteration order, rather than by insertion order. A pool smaller
    than 3 still bands every bundle, just with a degenerate (all-same-band or
    near-even) split -- there is no minimum pool size."""
    ordered = sorted(bundles, key=lambda b: (gold_file_count(b), b.work_id))
    n = len(ordered)
    stats: list[DifficultyStats] = []
    for i, bundle in enumerate(ordered):
        tertile = min(i * len(BANDS) // n, len(BANDS) - 1) if n else 0
        stats.append(
            DifficultyStats(
                work_id=bundle.work_id,
                rig=bundle.rig,
                gold_files=gold_file_count(bundle),
                ftp_tests=ftp_test_count(bundle),
                band=BANDS[tertile],
            )
        )
    return stats
