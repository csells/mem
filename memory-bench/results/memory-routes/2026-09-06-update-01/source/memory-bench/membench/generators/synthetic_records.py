"""Deterministic, SDK-free production of the flat world rows.

``world_builder.generate_world_records`` is the only step of the world pipeline that
touches NeMo Data Designer: it returns ``num_records`` flat rows (one per persona) and
everything downstream -- ``records_to_world``, ``materialize_world``, ``write_world``,
the manifest -- is pure. The model authors exactly four fields, and all four are surface
flavor: ``org_name``, ``team_name``, ``persona_name``, ``prd_summary``. Nothing the
benchmark measures reads them; the eval consumes the goal step, the oracle memory and
the opaque values the materializer derives.

So this module fills those four fields from seeded word banks instead, and samples the
category columns off the same ``WorldColumnSpec``. The rows it returns satisfy
``records_to_world``'s contract, which means a world can be frozen with no endpoint, no
SDK and no GPU -- the standing constraint (architecture decision 15) that otherwise
leaves ``fixtures/worlds-tool`` ungeneratable.

What is lost is realism of the prose, and only that. A claim that rests on the surface
reading as human-written (the ``realism/`` verdict track) still needs the NeMo path,
which stays in ``world_builder`` unchanged.
"""

from __future__ import annotations

import random
from typing import Any

from membench.generators.nemo.column_spec import DEFAULT_WORLD_SPEC, WorldColumnSpec
from membench.generators.nemo.world_builder import choose_org

# Word banks for the four LLM-authored fields. Bounded and ordered, so a seeded draw is
# reproducible across processes and Python versions.
_ORG_PREFIXES = (
    "Northwind",
    "Cobalt",
    "Meridian",
    "Halcyon",
    "Ironwood",
    "Lumen",
    "Sablefish",
    "Tessellate",
    "Verdigris",
    "Westmark",
)
_ORG_SUFFIXES = ("Systems", "Labs", "Works", "Dynamics", "Collective", "Industries")

_TEAM_FOCUS = (
    "Platform",
    "Core",
    "Reliability",
    "Enablement",
    "Delivery",
    "Foundations",
)

_FIRST_NAMES = (
    "Ada",
    "Bruno",
    "Camila",
    "Dmitri",
    "Esther",
    "Farid",
    "Greta",
    "Hiroshi",
    "Imani",
    "Joaquin",
    "Kenji",
    "Leila",
    "Mateo",
    "Nadia",
    "Oskar",
    "Priya",
)
_LAST_NAMES = (
    "Almeida",
    "Bergstrom",
    "Castellanos",
    "Doyle",
    "Eriksen",
    "Fontaine",
    "Gruber",
    "Haddad",
    "Ibarra",
    "Jorgensen",
    "Kowalski",
    "Larsen",
    "Moreau",
    "Nakamura",
    "Okonkwo",
    "Petrov",
)


def _org_name(rng: random.Random) -> str:
    return f"{rng.choice(_ORG_PREFIXES)} {rng.choice(_ORG_SUFFIXES)}"


def _prd_summary(*, domain: str, org_size: str, org_name: str) -> str:
    """Two sentences, matching the shape the LLM column asks for. Derived rather than
    drawn: the summary is org-level, so it must be identical across every row."""
    readable = domain.replace("-", " ")
    return (
        f"{org_name} is consolidating its {readable} tooling onto a single "
        f"supported path this quarter. The initiative covers migration of the "
        f"existing {org_size} workloads, a documented rollback, and retirement of "
        f"the superseded configuration."
    )


def _persona_names(rng: random.Random, count: int) -> list[str]:
    """Distinct full names. Drawn from the full first x last product without replacement,
    so two personas never collide -- ``records_to_world`` would otherwise build a world
    whose personas a reader cannot tell apart."""
    pairs = [(first, last) for first in _FIRST_NAMES for last in _LAST_NAMES]
    if count > len(pairs):
        raise ValueError(
            f"cannot draw {count} distinct persona names from {len(pairs)} combinations"
        )
    return [f"{first} {last}" for first, last in rng.sample(pairs, count)]


def _team_name(rng: random.Random, *, domain: str) -> str:
    return f"{domain.replace('-', ' ').title()} {rng.choice(_TEAM_FOCUS)}"


def synthetic_world_records(
    *,
    num_records: int,
    seed: int,
    spec: WorldColumnSpec = DEFAULT_WORLD_SPEC,
) -> list[dict[str, Any]]:
    """Return ``num_records`` flat rows describing ONE organization, deterministically.

    Drop-in for ``generate_world_records`` minus its endpoint arguments: same columns,
    same org-constant invariant, same bounded vocabularies. ``seed`` fixes everything,
    including the org's domain/org_size (via the same ``choose_org`` the NeMo path uses),
    so the same seed reproduces byte-identical rows.

    Raises on a spec carrying a text column this module has no deterministic filler for,
    rather than emitting a placeholder that would reach a frozen fixture.
    """
    if num_records < 1:
        raise ValueError(f"num_records must be >= 1, got {num_records}")

    known_text = {"org_name", "team_name", "persona_name", "prd_summary"}
    unknown = [c.name for c in spec.text_columns if c.name not in known_text]
    if unknown:
        raise ValueError(
            f"no deterministic filler for text column(s) {sorted(unknown)}; "
            f"add one to synthetic_records or generate this spec through NeMo"
        )

    domain, org_size = choose_org(seed)
    # Independent streams per concern, each keyed off the seed, so adding a column or
    # changing num_records cannot silently reshuffle an unrelated field.
    org_rng = random.Random(f"{seed}:org")
    name_rng = random.Random(f"{seed}:personas")

    org_name = _org_name(org_rng)
    prd_summary = _prd_summary(domain=domain, org_size=org_size, org_name=org_name)
    persona_names = _persona_names(name_rng, num_records)

    rows: list[dict[str, Any]] = []
    for index, persona_name in enumerate(persona_names):
        row_rng = random.Random(f"{seed}:row:{index}")
        row: dict[str, Any] = {
            "domain": domain,
            "org_size": org_size,
            "org_name": org_name,
            "prd_summary": prd_summary,
            "team_name": _team_name(row_rng, domain=domain),
            "persona_name": persona_name,
        }
        # Category columns come off the spec itself, so the two producers stay in step if
        # an axis is added. domain/org_size are org-level and already set above.
        for sampler in spec.samplers:
            if sampler.name in row:
                continue
            row[sampler.name] = row_rng.choice(list(sampler.values))
        rows.append(row)
    return rows
