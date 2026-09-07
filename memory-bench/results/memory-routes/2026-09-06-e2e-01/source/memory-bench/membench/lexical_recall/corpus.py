"""Author and freeze the lexical-miss corpus (mem-lbuvd).

The ordering corpus injects the literal query string into exactly the labelled
Memories, which is what makes its equality gate hold and its recall 1.0 by
construction. This corpus inverts that: the query goes into the DISTRACTORS only,
and the gold Memory carries a different surface form for the same thing.

Two invariants define the task class, and both are checked mechanically against
the materialized text rather than trusted from the pair table:

- the query is absent from the primary and every acceptable entry point;
- the query is present in at least one distractor, so the literal matcher returns
  a non-empty *wrong* candidate set. Without this the arm would score 0 because it
  found nothing, which is a different and uninteresting failure.
"""

from __future__ import annotations

import hashlib
import random

from membench.beads_ordering.models import FrozenCorpus, MemoryFixture
from membench.lexical_recall.models import FrozenMissCorpus, LexicalMissTask, MissKind
from membench.lexical_recall.scenarios import (
    FILLER_PREDICATES,
    FILLER_SUBJECTS,
    PAIRS_BY_KIND,
)

FROZEN_SEED = 5877
BACKGROUND_COUNT = 500


class MissCorpusError(RuntimeError):
    pass


def _background(seed: int) -> tuple[MemoryFixture, ...]:
    rng = random.Random(seed)
    notes: list[MemoryFixture] = []
    for index in range(1, BACKGROUND_COUNT + 1):
        subject = rng.choice(FILLER_SUBJECTS)
        predicate = rng.choice(FILLER_PREDICATES)
        notes.append(
            MemoryFixture(
                id=f"bg-{index:04d}",
                key=f"bg-{index:04d}",
                title=f"Operational note {index}",
                body=f"Operational note {index}. {subject.capitalize()} {predicate}.",
            )
        )
    return tuple(notes)


def _rename_sentence(kind: MissKind, surface_form: str) -> str:
    if kind is MissKind.RENAMED_CONCEPT:
        # The rename note cannot name the retired term: writing it here would put
        # the query string back into the gold Memory and dissolve the miss. A real
        # rename note that has finished propagating looks exactly like this.
        return (
            f" The concept was renamed; {surface_form} is the current term "
            "and the retired name is no longer used."
        )
    return ""


def _task_memories(
    *, index: int, kind: MissKind, query: str, surface_form: str, distractor_count: int
) -> tuple[MemoryFixture, MemoryFixture, tuple[MemoryFixture, ...]]:
    slug = f"lm-{index:02d}"
    primary = MemoryFixture(
        id=f"{slug}-primary",
        key=f"{slug}-primary",
        title=f"Corrected guidance for {surface_form}",
        lifecycle="active",
        navigation_rank=100,
        body=(
            f"Operational note {slug}. The accepted guidance covers {surface_form} "
            f"and supersedes the earlier rollout."
            f"{_rename_sentence(kind, surface_form)}"
        ),
    )
    entry = MemoryFixture(
        id=f"{slug}-entry",
        key=f"{slug}-entry",
        title=f"{surface_form} navigation map",
        aliases=(surface_form,),
        lifecycle="active",
        navigation_rank=200,
        references=(primary.id,),
        body=f"Start here for {surface_form}. Follow the reference for the accepted guidance.",
    )
    distractors = tuple(
        MemoryFixture(
            id=f"{slug}-d{position}",
            key=f"{slug}-d{position}",
            title=f"Retired {query} thread",
            lifecycle="archived",
            body=(
                f"Historical {query} discussion from the retired rollout. "
                f"Superseded and kept for the audit trail."
            ),
        )
        for position in range(1, distractor_count + 1)
    )
    return primary, entry, distractors


def build_frozen_corpus(seed: int = FROZEN_SEED) -> FrozenMissCorpus:
    if seed != FROZEN_SEED:
        raise MissCorpusError(f"the lexical-miss corpus is frozen at seed {FROZEN_SEED}")
    memories: list[MemoryFixture] = list(_background(seed))
    tasks: list[LexicalMissTask] = []
    index = 0
    for kind, pairs in PAIRS_BY_KIND.items():
        for query, surface_form in pairs:
            # 2, 3 or 4 literal-matching distractors, so matched-k varies across
            # tasks instead of collapsing to one constant budget.
            distractor_count = 2 + (index % 3)
            primary, entry, distractors = _task_memories(
                index=index,
                kind=kind,
                query=query,
                surface_form=surface_form,
                distractor_count=distractor_count,
            )
            memories.extend([primary, entry, *distractors])
            distractor_ids = tuple(memory.id for memory in distractors)
            tasks.append(
                LexicalMissTask(
                    task_id=f"lexmiss-{kind.value}-{index:02d}",
                    miss_kind=kind,
                    query=query,
                    surface_form=surface_form,
                    primary_relevant=primary.id,
                    acceptable_entry_points=(entry.id,),
                    distractors=distractor_ids,
                    literal_matching_distractors=distractor_ids,
                )
            )
            index += 1
    corpus = FrozenMissCorpus(seed=seed, memories=tuple(memories), tasks=tuple(tasks))
    validate_miss_construction(corpus)
    return corpus


def literal_matches(corpus: FrozenMissCorpus, query: str) -> set[str]:
    """Beads' matcher, reimplemented: case-insensitive substring over key or the
    complete stored value. Used to check construction at freeze time; the measured
    literal arm always shells the real binary."""

    needle = query.lower()
    # `corpus_size` is passed so freeze-time validation reads the SAME string the
    # arms index at run time (`document_text`, `seed_beads_workspace`). Identical
    # today only because this corpus never populates `structural_ranks_by_corpus`.
    size = len(corpus.memories)
    return {
        memory.id
        for memory in corpus.memories
        if needle in memory.key.lower() or needle in memory.stored_value(size).lower()
    }


def validate_miss_construction(corpus: FrozenMissCorpus) -> None:
    """Enforce the two class invariants plus the no-incidental-match rule."""

    for task in corpus.tasks:
        matches = literal_matches(corpus, task.query)
        if task.primary_relevant in matches:
            raise MissCorpusError(
                f"{task.task_id}: the query literally matches the primary Memory, "
                "so this is not a lexical miss"
            )
        recalled_entries = matches & set(task.acceptable_entry_points)
        if recalled_entries:
            raise MissCorpusError(
                f"{task.task_id}: the query literally matches an acceptable entry point"
            )
        matching_distractors = matches & set(task.literal_matching_distractors)
        if not matching_distractors:
            raise MissCorpusError(
                f"{task.task_id}: no distractor matches literally, so the literal arm "
                "would return an empty candidate set and recall would be 0 for a "
                "degenerate reason"
            )
        labelled = {task.primary_relevant, *task.acceptable_entry_points, *task.distractors}
        stray = matches - labelled
        if stray:
            raise MissCorpusError(
                f"{task.task_id}: {len(stray)} unlabelled Memories match the query literally"
            )


def as_seedable_corpus(corpus: FrozenMissCorpus) -> FrozenCorpus:
    """Adapt to the type `beads_ordering.runner.seed_beads_workspace` takes.

    Reusing that function rather than copying it is deliberate: the workspace this
    experiment measures must be materialized by exactly the same path the ordering
    experiment used, or the literal arm is not the same instrument. It reads only
    `memories`, so the task tuple is empty.
    """

    return FrozenCorpus(seed=corpus.seed, memories=corpus.memories, tasks=())


def corpus_digest(corpus: FrozenMissCorpus) -> str:
    """Pin the generated corpus.

    Nothing is stored on disk, so the fixture identity IS this digest. It is taken
    over exactly the `key\\0stored_value` pairs `seed_beads_workspace` imports, so
    a workspace that reports a different digest is a different corpus.
    """

    size = len(corpus.memories)
    payload = "\n".join(f"{memory.key}\0{memory.stored_value(size)}" for memory in corpus.memories)
    return hashlib.sha256(payload.encode()).hexdigest()
