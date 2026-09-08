"""Frozen types for the lexical-miss recall experiment (mem-lbuvd).

This experiment measures candidate-generation recall, which the ordering
experiment cannot: `beads_ordering.runner.validate_rank_truth` requires the
literal candidate set to EQUAL the labelled set, so the primary Memory is
recalled with probability 1 by construction there.

A `MissKind` names *why* the literal matcher fails, so recall can be reported per
capability rather than as one undifferentiated average.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from membench.beads_ordering.models import MemoryFixture

# The secondary budget, here rather than in the runner so `TaskRecall` can
# derive its own flags without importing the module that constructs it.
RECALL_AT_10 = 10


class MissKind(StrEnum):
    SYNONYM = "synonym"
    ABBREVIATION = "abbreviation"
    RENAMED_CONCEPT = "renamed-concept"
    MORPHOLOGICAL = "morphological"


class TaskClass(StrEnum):
    LEXICAL_MISS = "lexical-miss"
    LEXICAL_HIT_CONTROL = "lexical-hit-control"


class Generator(StrEnum):
    LITERAL = "literal"
    FTS = "fts"
    EMBEDDING = "embedding"


class LexicalMissTask(BaseModel):
    """One task whose gold Memory does NOT literally contain the query.

    Two construction invariants define the class and are enforced mechanically at
    freeze time by `corpus.validate_miss_construction`, never by a model:

    - `query` is absent from the primary and every acceptable entry point;
    - `query` is present in at least one distractor, so the literal matcher
      returns a non-empty *wrong* candidate set rather than nothing. Without that
      second condition recall would be 0 for a degenerate reason.
    """

    model_config = ConfigDict(frozen=True)

    task_id: str
    miss_kind: MissKind
    query: str
    surface_form: str
    primary_relevant: str
    acceptable_entry_points: tuple[str, ...] = ()
    distractors: tuple[str, ...]
    literal_matching_distractors: tuple[str, ...]


class FrozenMissCorpus(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    seed: int
    memories: tuple[MemoryFixture, ...]
    tasks: tuple[LexicalMissTask, ...]


class TaskRecall(BaseModel):
    """Recall of one task under one generator, at every preregistered budget.

    `matched_k` is the size of the LITERAL candidate set for this same task.
    Recall without a size control is gameable: a generator returning the whole
    corpus scores 1.0. Holding the budget at what the shipped matcher already
    costs is what makes the arms comparable.
    """

    model_config = ConfigDict(frozen=True)

    task_id: str
    task_class: TaskClass
    miss_kind: MissKind | None
    generator: Generator
    corpus_size: int = Field(ge=1)
    matched_k: int = Field(ge=0)
    candidate_set_size: int = Field(ge=0)
    # Ranks are 1-based positions. `ge=1` makes rank 0 unrepresentable rather than
    # merely unlikely: a `_rank_of` that returned 0 for "not found" would otherwise
    # satisfy every `rank <= budget` comparison below and invert recall silently.
    primary_rank: int | None = Field(default=None, ge=1)
    useful_rank: int | None = Field(default=None, ge=1)
    # How many labelled Memories other than the primary exist for this task. When
    # this is >= matched_k the budget can be consumed entirely by non-primary
    # labels, so recall at matched-k is bounded below the ceiling by construction.
    n_labelled_non_primary: int = Field(ge=0)
    primary_at_matched_k: bool
    primary_at_10: bool
    primary_unbounded: bool
    useful_at_matched_k: bool

    @model_validator(mode="after")
    def _budget_flags_follow_from_the_ranks(self) -> TaskRecall:
        """Recompute the four booleans instead of trusting the caller.

        These flags are what every reported statistic averages. Deriving them here
        means a measurement path that computed one of them wrongly fails loudly at
        construction rather than shifting a headline by a silent amount.
        """

        expected = {
            "primary_at_matched_k": self.primary_rank is not None
            and self.primary_rank <= self.matched_k,
            "primary_at_10": self.primary_rank is not None and self.primary_rank <= RECALL_AT_10,
            "primary_unbounded": self.primary_rank is not None,
            "useful_at_matched_k": self.useful_rank is not None
            and self.useful_rank <= self.matched_k,
        }
        wrong = sorted(name for name, value in expected.items() if getattr(self, name) != value)
        if wrong:
            raise ValueError(
                f"{self.task_id}/{self.generator.value}: budget flags disagree with the "
                f"ranks ({', '.join(wrong)})"
            )
        return self
