"""§1-§2 - the synthetic enterprise world and project schemas.

A NeMo-Data-Designer run produces, offline, the *cast and setting* of an
enterprise: the org, its teams, personas, channels, knowledge bases and repos
(``EnterpriseWorld``), plus the long-lived ``Project`` context (a PRD summary
and a set of ``TaskBrief``s) shared across tasks. These schemas hold ONLY the
NeMo-generated surface — the diversity layer.

They deliberately do NOT hold memory facts or the memory-dependency structure:
that ground truth is authored in pure Python by the materialiser (Phase 2,
``generators.enterprise_workflow``), which references this world's entities when
it writes the fact graph. NeMo supplies the who/where/what-domain; Python writes
the script. Keeping the boundary here is the ZFC line — no oracle lives in
model output.

Same house style as ``schemas.sequence``: plain ``BaseModel`` with list defaults,
plus ``model_validator`` referential-integrity checks so a malformed world fails
at construction, not deep in materialisation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

WORLD_SCHEMA_VERSION = "world.v1"


class Team(BaseModel):
    """An org unit. ``charter`` is one line of NeMo-generated surface describing it."""

    team_id: str
    name: str
    charter: str = ""


class Persona(BaseModel):
    """A person in the org. ``team_id`` (when set) must name a team in the world —
    enforced by ``EnterpriseWorld`` so materialised facts can attribute to a real
    cast member."""

    persona_id: str
    name: str
    role: str = ""
    team_id: str | None = None


class Channel(BaseModel):
    """A communication surface a fact can be attributed to (§1 communication
    channels). ``kind`` is a coarse, stringly-but-bounded category — the column
    spec samples it from a fixed set, so unknown kinds indicate a spec drift."""

    channel_id: str
    name: str
    kind: str = "chat"  # chat | email | issue-tracker | docs | meeting


class KnowledgeBase(BaseModel):
    """A documentation/knowledge surface (§1 knowledge bases)."""

    kb_id: str
    name: str
    topic: str = ""


class Repository(BaseModel):
    """A code repository in the world (§1 repositories)."""

    repo_id: str
    name: str
    language: str = ""


def _duplicate(ids: list[str]) -> str | None:
    """First id that appears more than once, or None. Order-preserving so the error
    names the first collision a reader would hit."""
    seen: set[str] = set()
    for i in ids:
        if i in seen:
            return i
        seen.add(i)
    return None


class EnterpriseWorld(BaseModel):
    """A synthetic organization (§1). Entity ids are unique within their kind and
    every ``Persona.team_id`` resolves to a team in this world; a world that
    violates either is a generation bug and raises at construction.

    ``seed`` and ``generator_version`` are provenance: a world is reproducible from
    its seed + the NeMo config, and the version pins which generator produced it.
    """

    world_id: str
    domain: str
    org_name: str
    teams: list[Team] = Field(default_factory=list)
    personas: list[Persona] = Field(default_factory=list)
    channels: list[Channel] = Field(default_factory=list)
    knowledge_bases: list[KnowledgeBase] = Field(default_factory=list)
    repositories: list[Repository] = Field(default_factory=list)
    seed: int
    generator_version: str = WORLD_SCHEMA_VERSION

    @model_validator(mode="after")
    def _check_integrity(self) -> EnterpriseWorld:
        for kind, ids in (
            ("team", [t.team_id for t in self.teams]),
            ("persona", [p.persona_id for p in self.personas]),
            ("channel", [c.channel_id for c in self.channels]),
            ("knowledge_base", [k.kb_id for k in self.knowledge_bases]),
            ("repository", [r.repo_id for r in self.repositories]),
        ):
            dup = _duplicate(ids)
            if dup is not None:
                raise ValueError(f"duplicate {kind} id {dup!r} in world {self.world_id!r}")

        team_ids = {t.team_id for t in self.teams}
        for p in self.personas:
            if p.team_id is not None and p.team_id not in team_ids:
                raise ValueError(
                    f"persona {p.persona_id!r} references unknown team {p.team_id!r} "
                    f"in world {self.world_id!r}"
                )
        return self


class TaskBrief(BaseModel):
    """A project-level task plan (the blueprint surface, §6.Metadata). The
    materialiser turns one brief into a memory-dependent ``BenchmarkSequence``;
    here it carries only NeMo-generated title/goal/narrative, no oracle."""

    brief_id: str
    title: str
    domain: str = ""
    goal: str = ""
    narrative: str = ""


class Project(BaseModel):
    """Long-lived context shared across tasks (§2), bound to one world. Holds the
    NeMo-generated PRD summary and the task briefs the materialiser expands into
    sequences; ``world_id`` back-references the owning ``EnterpriseWorld``."""

    project_id: str
    world_id: str
    name: str
    goal: str = ""
    prd_summary: str = ""
    task_briefs: list[TaskBrief] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_brief_ids(self) -> Project:
        dup = _duplicate([b.brief_id for b in self.task_briefs])
        if dup is not None:
            raise ValueError(f"duplicate task_brief id {dup!r} in project {self.project_id!r}")
        return self
