"""The model-free specification of what NeMo Data Designer generates.

This module holds NO ``data_designer`` import — it is the declarative "what":
category samplers (the diversity axes) and LLM-text columns (the surface prose),
as plain frozen dataclasses. ``world_builder.build_config_builder`` turns this
spec into a live ``DataDesignerConfigBuilder``; keeping the spec separate makes
the generation axes reviewable and unit-testable without the SDK or a model.

One NeMo run produces one row per persona (``num_records`` = persona count); the
org-level fields repeat across rows and are de-duplicated by ``records_to_world``.
The jinja prompts reference sampler columns by name (``{{ domain }}`` etc.), which
is how NeMo couples the prose to the sampled axes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# A NeMo "model_alias" — resolved by `data-designer config models` to a local NIM
# or the OAuth Claude CLI (mem's no-paid-API stance: the memory stack stays free;
# generation is offline and one-time). Overridable per build.
DEFAULT_MODEL_ALIAS = "local-nim"


@dataclass(frozen=True)
class CategorySampler:
    """A category-sampler column: NeMo samples ``name`` uniformly from ``values``.
    The bounded value set is also the contract ``records_to_world`` validates the
    output against, so drift surfaces instead of passing silently."""

    name: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class LLMTextColumn:
    """An LLM-text column: NeMo fills ``name`` by prompting ``model_alias`` with
    ``prompt`` (a jinja template referencing earlier columns)."""

    name: str
    prompt: str
    model_alias: str = DEFAULT_MODEL_ALIAS


@dataclass(frozen=True)
class WorldColumnSpec:
    """The full column set for one world-generation run."""

    samplers: tuple[CategorySampler, ...] = field(default_factory=tuple)
    text_columns: tuple[LLMTextColumn, ...] = field(default_factory=tuple)

    def column_names(self) -> tuple[str, ...]:
        return tuple(s.name for s in self.samplers) + tuple(c.name for c in self.text_columns)


# The default diversity axes. Bounded value sets keep generation reproducible-in-
# shape and let `records_to_world` reject out-of-vocabulary output.
DOMAINS = (
    "cuda-engineering",
    "chip-design",
    "customer-support",
    "legal",
    "medical",
    "research-platform",
    "data-infrastructure",
)
ORG_SIZES = ("startup", "scaleup", "enterprise")
PERSONA_ROLES = (
    "staff-engineer",
    "engineering-manager",
    "site-reliability-engineer",
    "product-manager",
    "support-lead",
    "legal-counsel",
    "researcher",
    "qa-engineer",
)
CHANNEL_KINDS = ("chat", "email", "issue-tracker", "docs", "meeting")
REPO_LANGUAGES = ("python", "cuda-cpp", "go", "typescript", "rust")


# NOTE: ``domain`` and ``org_size`` are ORG-level — one value per world, not per
# row — so they are NOT in this per-row sampler set. ``world_builder`` chooses them
# once (seeded) and injects them as single-value (constant) samplers at build time,
# which keeps every persona row in one coherent organization. The text columns
# below reference them via jinja, so they must exist as columns at generation time.
DEFAULT_WORLD_SPEC = WorldColumnSpec(
    samplers=(
        CategorySampler("persona_role", PERSONA_ROLES),
        CategorySampler("channel_kind", CHANNEL_KINDS),
        CategorySampler("repo_language", REPO_LANGUAGES),
    ),
    text_columns=(
        LLMTextColumn(
            "org_name",
            "Invent one realistic company name for a {{ org_size }} "
            "{{ domain }} organization. Return only the name, no punctuation.",
        ),
        LLMTextColumn(
            "team_name",
            "Name one team that would own {{ domain }} work at a {{ org_size }} "
            "company. Return only the team name.",
        ),
        LLMTextColumn(
            "persona_name",
            "Invent one full name for a {{ persona_role }}. Return only the name.",
        ),
        LLMTextColumn(
            "prd_summary",
            "Write a two-sentence PRD summary for a current initiative at a "
            "{{ org_size }} {{ domain }} company. Be concrete and domain-specific.",
        ),
    ),
)
