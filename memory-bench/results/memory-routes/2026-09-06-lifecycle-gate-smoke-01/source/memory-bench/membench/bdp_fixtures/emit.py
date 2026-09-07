"""Write the BDP fixture tree and its determinism manifest.

Everything published here is generated: the seven graph shapes come from
`topologies`, and every Bead property comes from that Bead's own opaque id. The
emitter reads no corpus, so the only input is the family name, and a re-emit is
the determinism check: a clean `git diff` afterwards is the evidence, a dirty
one is a defect.

Tree shape, which mirrors the URL space a consumer would fetch from. The tree
root stands for `/ordering/`:

    manifest.json
    types/<segment>.json          one Type Descriptor document per Type ID URL
    <family>/discovery.json       the Read discovery document
    <family>/dataset/beads.json   the load set, deliberately not in reference order
    <family>/dataset/links.json
    <family>/dataset/types.json   the `GET /types/` inventory of summaries
    <family>/ordering.json        the selected sets and page partitions

Eight families are written under that layout: the seven graph shapes, plus the
collation family, whose payload is the identifier spelling rather than the graph
shape. It is recorded under `collation_family` in the manifest rather than
alongside the seven, because every density figure in the manifest and the README
quantifies over the seven and a 23-Bead family has no density to compare.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from membench.bdp_fixtures.collation import (
    COLLATION_FAMILY,
    COLLATION_GROUPS,
    COLLATION_LIMITS,
    COLLATION_ORDER_ID,
    RIVALS,
    collation_bead_records,
    collation_expectations,
    collation_link_records,
    validate_groups,
)
from membench.bdp_fixtures.mapping import (
    BEAD_TYPE_ID,
    CITES_TYPE_ID,
    DEFAULT_LIMITS,
    FIXTURE_ORDER_ID,
    BdpMappingError,
    JsonObject,
    ScopeUrls,
    bead_records,
    descriptor_filename,
    discovery_document,
    is_canonical_order,
    link_records,
    ordering_expectations,
    proposal_note,
    serialization_order,
    type_descriptors,
    type_summaries,
)
from membench.bdp_fixtures.topologies import (
    BEADS_PER_FAMILY,
    TOPOLOGIES,
    TOPOLOGIES_BY_NAME,
    TOPOLOGY_SEED,
    build_edges,
)

MANIFEST_SCHEMA_VERSION = 5
DEFAULT_OUT = Path("fixtures/bdp/ordering-families")

# The vendored bundle these fixtures were validated against, pinned by commit so
# the claim names one revision rather than whatever upstream HEAD happens to be.
SCHEMA_BUNDLE_COMMIT = "f8307699979c29af67a30effb9c3d2702f919813"
SCHEMA_BUNDLE_URL = (
    "https://raw.githubusercontent.com/gastownhall/bdp/"
    f"{SCHEMA_BUNDLE_COMMIT}/schemas/bdp-v0.schema.json"
)
SCHEMA_BUNDLE_SHA256 = "d91e5936e2901abe55a8d9223b02458c2865be8d068b6310a5b71150277895dd"

DATASET_FILENAMES = ("beads.json", "links.json", "types.json")
DESCRIPTOR_FILENAMES = frozenset(
    descriptor_filename(str(descriptor["id"])) for descriptor in type_descriptors()
)


def _is_emitter_owned(relative: Path) -> bool:
    """Whether the emitter could have written this exact relative path.

    Pruning must be decided on the whole path, never on the basename. `manifest.
    json`, `types.json` and `links.json` are generic names, and matching them at
    any depth turned `--out fixtures` into a command that deleted the frozen
    ordering suite's own non-regenerable `manifest.json`, which lives under a
    sibling directory this emitter has no business touching.
    """

    parts = relative.parts
    if parts == ("manifest.json",):
        return True
    if len(parts) == 2 and parts[0] == "types":
        return parts[1] in DESCRIPTOR_FILENAMES
    if len(parts) == 2:
        return parts[1] in ("discovery.json", "ordering.json")
    if len(parts) == 3:
        return parts[1] == "dataset" and parts[2] in DATASET_FILENAMES
    return False


def _is_emitter_owned_directory(relative: Path) -> bool:
    parts = relative.parts
    if parts == ("types",):
        return True
    if len(parts) == 1:
        return True
    return len(parts) == 2 and parts[1] == "dataset"


def _write(path: Path, payload: Mapping[str, Any] | Sequence[Any]) -> tuple[str, int]:
    encoded = (json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n").encode(
        "utf-8"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest(), len(encoded)


def _duplicate_endpoint_tuples(links: Sequence[Mapping[str, Any]]) -> int:
    """How many Links repeat a (type, source, target) another Link already has.

    BDP v0 permits this explicitly and defines no tuple-uniqueness constraint, so
    the count is recorded rather than rejected: a consumer that silently collapses
    such Links is non-conformant, and it can only be caught by a fixture that has
    some. Zero is a legitimate answer and is recorded as such.
    """

    seen: set[tuple[str, str, str]] = set()
    duplicates = 0
    for link in links:
        key = (str(link["type"]), str(link["source"]), str(link["target"]))
        if key in seen:
            duplicates += 1
        seen.add(key)
    return duplicates


def _prune(out_root: Path, written: set[Path]) -> list[str]:
    """Delete files this emitter could have written at that exact path but did not.

    Without it, dropping or renaming a family leaves its documents on disk, the
    manifest no longer mentions them, and a re-emit still shows a clean `git
    diff`. Ownership is decided by the whole relative path (`_is_emitter_owned`),
    so an `--out` pointing at a populated directory cannot lose a file that
    merely shares a basename with one of ours.
    """

    removed: list[str] = []
    for path in sorted(out_root.rglob("*.json")):
        relative = path.relative_to(out_root)
        if _is_emitter_owned(relative) and path not in written:
            path.unlink()
            removed.append(str(relative))
    for directory in sorted(out_root.rglob("*"), reverse=True):
        if not directory.is_dir():
            continue
        if not _is_emitter_owned_directory(directory.relative_to(out_root)):
            continue
        if not any(directory.iterdir()):
            directory.rmdir()
    return removed


def emit_shared_types(out_root: Path) -> JsonObject:
    """Write one Type Descriptor document per Type, at its Type ID path.

    The Type IDs are authority-wide rather than per-family, so the documents live
    once at the root of the tree instead of being copied into all seven families.
    """

    files: JsonObject = {}
    for descriptor in type_descriptors():
        name = descriptor_filename(str(descriptor["id"]))
        digest, size = _write(out_root / "types" / name, descriptor)
        files[f"types/{name}"] = {
            "sha256": digest,
            "bytes": size,
            "serves": str(descriptor["id"]),
        }
    return files


def emit_family(family: str, out_root: Path) -> JsonObject:
    """Emit one family's discovery, load set and ordering expectations."""

    if family not in TOPOLOGIES_BY_NAME:
        raise BdpMappingError(f"unknown graph family: {family}")
    scope = ScopeUrls.for_family(family)
    edges = build_edges(family, BEADS_PER_FAMILY)
    beads = bead_records(family, scope, BEADS_PER_FAMILY)
    links = link_records(family, scope, edges, BEADS_PER_FAMILY)
    summaries = type_summaries()
    ordering = ordering_expectations(beads, links, summaries, scope, limits=DEFAULT_LIMITS)

    outdegree: dict[str, int] = {}
    indegree: dict[str, int] = {}
    for link in links:
        outdegree[str(link["source"])] = outdegree.get(str(link["source"]), 0) + 1
        indegree[str(link["target"])] = indegree.get(str(link["target"]), 0) + 1

    shipped = {
        "beads.json": serialization_order(beads),
        "links.json": serialization_order(links),
        "types.json": serialization_order(summaries),
    }
    for name, records in shipped.items():
        # A collection of fewer than two records has one arrangement, so the
        # property is vacuous rather than violated. Raising there would refuse a
        # legitimate family and blame the wrong thing.
        if len(records) >= 2 and is_canonical_order(records):
            raise BdpMappingError(
                f"{family}/dataset/{name} serialized in reference order, so an authority that "
                "echoes the order it loaded would pass this family without ordering at all"
            )

    directory = out_root / family
    files: JsonObject = {}
    digest, size = _write(directory / "discovery.json", discovery_document(scope))
    files["discovery.json"] = {"sha256": digest, "bytes": size}
    for name, records in shipped.items():
        digest, size = _write(directory / "dataset" / name, {"items": list(records), "next": None})
        files[f"dataset/{name}"] = {"sha256": digest, "bytes": size}
    digest, size = _write(directory / "ordering.json", ordering)
    files["ordering.json"] = {"sha256": digest, "bytes": size}

    return {
        "scope": scope.scope_url,
        # What this shape is for, so a consumer that drops a family knows which
        # conformance property it just stopped testing.
        "exercises": TOPOLOGIES_BY_NAME[family].exercises,
        "bead_count": len(beads),
        "link_count": len(links),
        "type_count": len(summaries),
        "max_outdegree": max(outdegree.values(), default=0),
        "max_indegree": max(indegree.values(), default=0),
        "duplicate_endpoint_tuple_links": _duplicate_endpoint_tuples(links),
        # Whether the hub's inbound, outbound and incident selections are three
        # pairwise-distinct sets. False in the forest-shaped families, where no
        # Bead carries both an inbound and an outbound Link, so `endpoint` cannot
        # be discriminated from `source` there. Recorded rather than asserted in
        # prose, because the README makes a claim about it.
        "hub_predicates_are_pairwise_distinct": _hub_predicates_distinct(links),
        # Recorded so the discrimination property is visible in the manifest
        # rather than only in prose: every shipped array is in an order a
        # conformant authority must reorder.
        "serialized_in_reference_order": {
            name: is_canonical_order(records) for name, records in shipped.items()
        },
        "selections": [
            {
                "collection": selection["collection"],
                "parameters": selection["parameters"],
                "total": selection["total"],
            }
            for selection in ordering["selections"]
        ],
        "files": files,
    }


def emit_collation_family(out_root: Path) -> JsonObject:
    """Emit the collation family, which is about identifier spellings, not shape.

    It sits beside the seven graph families and shares their Scope prefix and
    their two Types, so a consumer fetches it the same way. Everything else about
    it differs: the ids are authored rather than digested, they are neither
    fixed-width nor all-lowercase, and the order it records is named for the
    comparison rule rather than for the field compared.
    """

    scope = ScopeUrls.for_family(COLLATION_FAMILY)
    validate_groups(scope)
    beads = collation_bead_records(scope)
    links = collation_link_records(scope, beads)
    summaries = type_summaries()
    ordering = collation_expectations(beads, links, summaries, scope, limits=COLLATION_LIMITS)

    shipped = {
        "beads.json": serialization_order(beads),
        "links.json": serialization_order(links),
        "types.json": serialization_order(summaries),
    }
    for name, records in shipped.items():
        if len(records) >= 2 and is_canonical_order(records):
            raise BdpMappingError(
                f"{COLLATION_FAMILY}/dataset/{name} serialized in reference order, so an "
                "authority that echoes the order it loaded would pass without ordering at all"
            )

    directory = out_root / COLLATION_FAMILY
    files: JsonObject = {}
    digest, size = _write(
        directory / "discovery.json", discovery_document(scope, limits=COLLATION_LIMITS)
    )
    files["discovery.json"] = {"sha256": digest, "bytes": size}
    for name, records in shipped.items():
        digest, size = _write(directory / "dataset" / name, {"items": list(records), "next": None})
        files[f"dataset/{name}"] = {"sha256": digest, "bytes": size}
    digest, size = _write(directory / "ordering.json", ordering)
    files["ordering.json"] = {"sha256": digest, "bytes": size}

    comparisons = ordering["collation"]["comparisons"]
    return {
        "scope": scope.scope_url,
        "exercises": (
            "collation edges: numeric against codepoint, ASCII case, punctuation a "
            "variable-weighting collator drops, and NFC against NFD inside percent-encoding"
        ),
        "reference_order": COLLATION_ORDER_ID,
        "page_limits": list(COLLATION_LIMITS),
        "bead_count": len(beads),
        "link_count": len(links),
        "type_count": len(summaries),
        "groups": {group.name: list(group.defeats) for group in COLLATION_GROUPS},
        # Which of the comparison rules this family separates from the recorded
        # order, per id space. The Link ids have to carry the axes themselves:
        # in the seven graph families they are zero-padded ordinals, which is the
        # padding this family exists to do without.
        "comparison_rules_separated": {
            collection: sorted(
                entry["comparison"] for entry in report if entry["differs_from_the_reference_order"]
            )
            for collection, report in comparisons.items()
        },
        # A rule that ties two distinct ids is not a total order, so it fails
        # gastownhall/bdp#8's first clause whatever order the authority documents.
        # Recorded apart from the rules that merely return a different order.
        "comparison_rules_that_are_not_a_total_order": {
            collection: sorted(
                entry["comparison"]
                for entry in report
                if not entry["is_a_total_order_over_this_collection"]
            )
            for collection, report in comparisons.items()
        },
        "comparison_rules_considered": [rival.name for rival in RIVALS],
        "serialized_in_reference_order": {
            name: is_canonical_order(records) for name, records in shipped.items()
        },
        "selections": [
            {
                "collection": selection["collection"],
                "parameters": selection["parameters"],
                "total": selection["total"],
            }
            for selection in ordering["selections"]
        ],
        "files": files,
    }


def _hub_predicates_distinct(links: Sequence[Mapping[str, Any]]) -> bool:
    counts: dict[str, int] = {}
    for link in links:
        counts[str(link["source"])] = counts.get(str(link["source"]), 0) + 1
    if not counts:
        return False
    hub = max(counts, key=lambda source: (counts[source], source))
    outbound = {str(link["id"]) for link in links if str(link["source"]) == hub}
    inbound = {str(link["id"]) for link in links if str(link["target"]) == hub}
    incident = outbound | inbound
    return len({frozenset(outbound), frozenset(inbound), frozenset(incident)}) == 3


def emit_all(*, out_root: Path) -> JsonObject:
    """Emit every family plus the determinism manifest over the tree."""

    out_root.mkdir(parents=True, exist_ok=True)
    shared_types = emit_shared_types(out_root)
    families: JsonObject = {}
    for family in sorted(TOPOLOGIES_BY_NAME):
        families[family] = emit_family(family, out_root)
    collation = emit_collation_family(out_root)

    manifest: JsonObject = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "bead": "mem-vn4ek",
        "status": "generated-graph-shapes",
        "authored_not_measured": (
            "Every graph shape is authored to exercise a consumer policy. None of these "
            "structures is a measured field frequency, and nothing here supports a claim about "
            "how often they occur in a real store."
        ),
        "generated_not_projected": (
            "These graphs are generated from this package's own seed. Earlier revisions "
            "projected the frozen ordering corpus behind memory-bench, and that corpus cannot "
            "be published in this form: it is authored around one distinguished node per "
            "family, so degree is the benchmark's answer key. Sweeping degree predicates over "
            "the projected Links, `deg==4` returned exactly three Beads in the branching "
            "family and all three were gold, and no one of 200 random same-sized decoy sets "
            "per family reached that precision in six of the seven families, against a 1.8% "
            "base rate. Neutralizing identifiers, free text and property values does not reach "
            "that channel, and neither does any rewiring that preserves the degree sequence."
        ),
        "identifiers_are_opaque": (
            "Bead ids are digests of a generator-side node name, and Link ordinals are assigned "
            "after sorting on the published endpoints. Neither the Bead id space nor the Link "
            "id space is the order the graph was built in, so the reference order these "
            "fixtures record cannot be reproduced by echoing the load order."
        ),
        "properties_are_synthetic": (
            "Every Bead property is generated from that Bead's own opaque id. Properties exist "
            "to give a Selector something to filter on and a page something to weigh; they "
            "carry no meaning and no distribution worth reading."
        ),
        "generator": {
            "seed": TOPOLOGY_SEED,
            "beads_per_family": BEADS_PER_FAMILY,
            "exercises": {
                topology.name: topology.exercises
                for topology in sorted(TOPOLOGIES, key=lambda t: t.name)
            },
        },
        "bdp": {
            "profile": "read",
            "schema_bundle": SCHEMA_BUNDLE_URL,
            "schema_bundle_commit": SCHEMA_BUNDLE_COMMIT,
            "schema_bundle_sha256": SCHEMA_BUNDLE_SHA256,
            "bead_type": BEAD_TYPE_ID,
            "link_type": CITES_TYPE_ID,
            "reference_order": FIXTURE_ORDER_ID,
            "page_limits": list(DEFAULT_LIMITS),
            "bdp8": proposal_note(),
        },
        "shared_types": shared_types,
        "family_count": len(families),
        "families": families,
        # Kept out of `families`. The seven are graph shapes at one fixed id
        # spelling, and every density claim in the README and the manifest
        # quantifies over them; the collation family is the same protocol at a
        # deliberately awkward id spelling and has no density to compare. Folding
        # it in would put a 23-Bead family in a table about hubs and fan-in.
        "collation_family_note": (
            "A separate family, under the same Scope prefix and the same two Types, whose "
            "payload is the identifier spelling rather than the graph shape. It records its own "
            f"order id ({COLLATION_ORDER_ID}) because 'ascending canonical URI' does not say "
            "which comparison rule, and on these ids the readings diverge."
        ),
        "collation_family": {COLLATION_FAMILY: collation},
    }

    written = {out_root / "manifest.json"}
    written |= {out_root / name for name in shared_types}
    for family, entry in families.items():
        written |= {out_root / family / name for name in entry["files"]}
    written |= {out_root / COLLATION_FAMILY / name for name in collation["files"]}
    # Pruning is deliberately not recorded in the manifest. A "files removed on
    # this run" key would differ between the run that pruned and the identical
    # run after it, which is exactly the drift the determinism gate exists to
    # catch, and it would report it as a failure of the emitter. The caller gets
    # the list instead, and `__main__` prints it.
    removed = _prune(out_root, written)

    # The manifest is written last and returned exactly as written: a caller that
    # re-serializes the return value must get the bytes on disk, or the
    # determinism check is comparing against something no reader ever sees.
    _write(out_root / "manifest.json", manifest)
    return {"manifest": manifest, "pruned": removed}
