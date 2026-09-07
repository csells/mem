"""S3 — the retention disposition-stream ``BenchmarkSequence`` generator (Tier 0).

A retention sequence is N write steps, each establishing ONE record carrying its
``record_class`` (the arm's classify input) and the schedule's ground-truth
``disposition`` oracle. The oracle is the retention policy applied to the class —
``RETENTION_POLICY`` is the single source of truth shared with the arm, so the
generator's ground truth and the arm's behaviour can never silently drift apart.

The whole structure is authored here deterministically: given a seed the sequence is
byte-reproducible. There is no model and no network in this path — the
wrongful_destruction gate this stream feeds voids precisely BECAUSE its disposition
oracle is deterministic rather than judged. A local model may later fill richer
record surface offline into a frozen ``generator_version``-tagged fixture, but the
class, the disposition, and the ids are always ours; CI never calls a model.
"""

from __future__ import annotations

import random

from membench.memory_systems.retention_scheduled_system import RETENTION_POLICY
from membench.schemas.sequence import BenchmarkSequence, SequenceStep

GENERATOR_VERSION = "retention-schedule.v1"

# Deterministic class order (dict insertion order) so a seeded draw is reproducible.
_CLASSES: tuple[str, ...] = tuple(RETENTION_POLICY)


def _draw_classes(rng: random.Random, n_records: int, cover_all: bool) -> list[str]:
    """The per-record class assignment. ``cover_all`` guarantees every policy class
    appears at least once (so a scored run touches every disposition, not one
    corner), then fills the remainder by a seeded draw and shuffles deterministically."""
    if not cover_all:
        return [rng.choice(_CLASSES) for _ in range(n_records)]
    if n_records < len(_CLASSES):
        raise ValueError(
            f"cover_all needs n_records >= {len(_CLASSES)} (one per class), got {n_records}"
        )
    classes = list(_CLASSES) + [rng.choice(_CLASSES) for _ in range(n_records - len(_CLASSES))]
    rng.shuffle(classes)
    return classes


def generate_retention_sequence(
    *,
    seed: int,
    n_records: int = 6,
    cover_all: bool = False,
) -> BenchmarkSequence:
    """Emit a deterministic retention ``BenchmarkSequence`` for ``seed``.

    Same seed (and args) ⇒ byte-identical sequence. Each step establishes one record
    whose ``record_class`` drives the arm and whose ``disposition`` is the schedule's
    ground-truth oracle (the policy applied to the class)."""
    if n_records < 1:
        raise ValueError(f"need >= 1 record, got {n_records}")
    rng = random.Random(seed)
    classes = _draw_classes(rng, n_records, cover_all)

    steps: list[SequenceStep] = []
    for i, cls in enumerate(classes):
        rid = f"rec-{i}"
        steps.append(
            SequenceStep(
                step_id=f"s{i}-write-{rid}",
                user_request=f"Store record {i} (retention class {cls}).",
                expected_memory_writes={rid: f"record {rid}: retention class {cls}"},
                record_class=cls,
                disposition=RETENTION_POLICY[cls],
            )
        )

    return BenchmarkSequence(
        sequence_id=f"retention-seed{seed}-n{n_records}",
        title="Retention schedule disposition stream",
        domain="retention-schedule",
        goal="apply the retention schedule without wrongful destruction",
        steps=steps,
    )
