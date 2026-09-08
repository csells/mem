"""Render one generated graph family into BDP Bead / Link / Type records.

Pure functions over an edge list from `topologies`. No IO, no randomness, no
reads of any corpus: the same family name must produce byte-identical output on
every machine, which is what makes these usable as conformance fixtures rather
than as a snapshot of one run.

One node becomes one Bead; one generated edge becomes one first-class Link
record with a `cites` Link Type, because BDP Links are not embedded in either
endpoint.

Nothing here reads the frozen ordering corpus. Three earlier revisions of this
package projected it, and each review round found the answer key in whatever
field still looked innocuous: the prose, then the character lengths of the
withheld prose, then `lifecycle` and `provenance`, and finally the adjacency
itself, which no neutralization can reach. `topologies` carries that history and
the measurements behind it.

What survives from that work is the discipline about identifiers. Bead local ids
are digests of a generator-side node name rather than the node index, so the
published id space is not an ordinal enumeration; Link ordinals are assigned
after sorting on the published endpoints, so a Link id is a function of the
published graph and not of the order edges were generated in. Neither is load
bearing for secrecy now. Both are load bearing for the ordering claim: they keep
ids fixed-width, so codepoint order over the canonical URI is a clean total
order, and they keep the reference order independent of construction order.

Serialization order is deliberately NOT the reference order; see
`serialization_order`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

JsonObject = dict[str, Any]

AUTHORITY = "https://fixtures.mem.example"
# Type documents live under the same `/ordering/` prefix the families do, so the
# on-disk tree and the URL space a consumer fetches from line up: the tree root
# stands for `/ordering/`, and one directory never stands for two URL prefixes.
TYPES_BASE = f"{AUTHORITY}/ordering/types"
BEAD_TYPE_ID = f"{TYPES_BASE}/memory"
CITES_TYPE_ID = f"{TYPES_BASE}/cites"

# Exactly the Bead `properties` keys that reach the published tree.
PUBLISHED_PROPERTY_KEYS = ("title", "aliases", "lifecycle", "provenance", "body")

# The order the reference sequences in `ordering.json` are written under. One
# legal order, not a required one: gastownhall/bdp#8 proposes that an authority
# impose a total order, that the order be deterministic for a given selected
# set, that it be stable across the pages of one snapshot, and that the
# authority document the order it uses. It says in terms that the choice of
# order is left to the implementation. See `ordering_expectations`.
FIXTURE_ORDER_ID = "ascending-canonical-uri"

# Bead local ids are fixed-width lowercase hex and Link ordinals are zero-padded
# to a fixed width, so codepoint order over the canonical URI is a total order
# with no prefix or width edges. That is deliberate and it bounds what these
# fixtures test: membership and page partitioning, NOT collation edges
# (numeric-vs-codepoint, case, Unicode normalization, percent-encoding).
BEAD_ID_WIDTH = 12
LINK_ID_WIDTH = 5

# Page limits every family records expectations for. 25 forces continuations in
# every collection at this corpus size; 200 exercises a larger page without
# swallowing the 500-Bead collections whole.
DEFAULT_LIMITS = (25, 200)

# Payload shape. Every Bead gets the same title and body length and one of a
# small fixed pool of filler variants. The lengths sit in the range a real
# operating note occupies, which keeps page payload sizes plausible.
TITLE_LENGTH = 64
BODY_LENGTH = 320
ALIAS_LENGTH = 24
MAX_ALIASES = 2

# `lifecycle` and `provenance` are enumerated properties for a Selector to
# filter on: one narrow predicate matching a handful of Beads, one wide
# predicate matching about half of them. A ~1-in-100 rate keeps the narrow
# predicate narrow without risking an empty collection at 500 Beads.
ARCHIVED_RATE = 100

_FILLER_VARIANTS = (
    "Placeholder prose for a BDP collection-ordering conformance fixture. ",
    "Generated note text. This Bead is a graph node and nothing more. ",
    "Filler body for an ordering fixture Bead, derived from no record. ",
    "Neutral text sized to a plausible operating note and nothing more. ",
    "This payload exists so that a page has bytes in it. It says nothing. ",
    "Fixture filler, generated from the Bead id it is attached to. ",
    "Ordering conformance placeholder. Content intentionally uninformative. ",
    "Stand-in body text for a Memory Bead in a generated graph family. ",
)


class BdpMappingError(RuntimeError):
    """Raised when a generated family cannot be rendered into legal BDP records."""


@dataclass(frozen=True)
class ScopeUrls:
    """Canonical URL spellings for one family's Scope."""

    base: str

    def __post_init__(self) -> None:
        if not self.base.startswith(("http://", "https://")):
            raise BdpMappingError(f"Scope base must be an absolute http(s) URL: {self.base}")
        if self.base.endswith("/"):
            raise BdpMappingError(f"Scope base must not carry a trailing slash: {self.base}")

    @classmethod
    def for_family(cls, family: str) -> ScopeUrls:
        return cls(f"{AUTHORITY}/ordering/{family}")

    def bead(self, local_id: str) -> str:
        return f"{self.base}/beads/{local_id}"

    def link(self, ordinal: int) -> str:
        return self.link_local(f"{ordinal:0{LINK_ID_WIDTH}d}")

    def link_local(self, local_id: str) -> str:
        """A Link URL from an already-spelled local id.

        The seven graph families always reach this through `link`, which
        zero-pads. The collation family spells its own Link ids, because the
        padding is exactly the thing it exists to do without.
        """

        return f"{self.base}/links/{local_id}"

    @property
    def scope_url(self) -> str:
        """The Scope as discovery advertises it, with the spec's trailing slash."""

        return f"{self.base}/"

    @property
    def beads_collection(self) -> str:
        return f"{self.base}/beads/"

    @property
    def links_collection(self) -> str:
        return f"{self.base}/links/"

    @property
    def types_collection(self) -> str:
        return f"{self.base}/types/"


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record_revision(record: Mapping[str, Any]) -> str:
    """A deterministic opaque revision token.

    BDP compares revisions only for equality and applies no semantic validation,
    so any stable nonempty string is legal. Deriving it from the record as built
    so far, which is every field except the revision itself, is what lets the
    whole fixture regenerate byte-identically. It is not a position in the
    content-addressed-token discussion on gastownhall/bdp#6: nothing here claims
    a consumer may recompute or verify it.
    """

    return f"rev-{_digest(_canonical(record))[:16]}"


def bead_local_id(family: str, key: str) -> str:
    """An opaque, fixed-width local id for a Bead.

    The generator's node names are an ordinal enumeration (`n0000`, `n0001`, ...)
    and are not published. Hashing them gives every family a fixed-width id space
    whose codepoint order is unrelated to construction order, so the reference
    order these fixtures record is not the order the graph was built in and an
    authority cannot pass by echoing what it loaded.
    """

    return _digest(f"bdp-fixture-bead:{family}:{key}")[:BEAD_ID_WIDTH]


def _synthetic_text(seed: str, length: int) -> str:
    """Filler of exactly `length` characters, chosen from a small fixed pool.

    It deliberately does NOT embed the Bead id: text interpolating the id would
    be order-isomorphic to it, and an authority documenting "ascending
    `properties.body`" would then reproduce every recorded Bead sequence without
    ordering on the id at all.
    """

    if length <= 0:
        return ""
    variant = _FILLER_VARIANTS[int(_digest(f"variant:{seed}")[:8], 16) % len(_FILLER_VARIANTS)]
    repeats = length // len(variant) + 1
    return (variant * repeats)[:length]


def _alias_count(local_id: str) -> int:
    return int(_digest(f"aliases:{local_id}")[:8], 16) % (MAX_ALIASES + 1)


def _lifecycle(local_id: str) -> str:
    """The narrow Selector predicate: about one Bead in `ARCHIVED_RATE`."""

    return (
        "archived"
        if int(_digest(f"lifecycle:{local_id}")[:8], 16) % ARCHIVED_RATE == 0
        else "active"
    )


def _provenance(local_id: str) -> str:
    """The wide Selector predicate: about half of every family."""

    return "agent" if int(_digest(f"provenance:{local_id}")[:8], 16) % 2 == 0 else "human"


def bead_properties(local_id: str) -> JsonObject:
    """The published `properties` of one Bead, as a function of its own id alone.

    Properties exist here to give a Selector something to filter on and a page
    something to weigh. They carry no meaning, and deriving all of them from the
    Bead id keeps their distributions a property of the emitter rather than of
    anything it read.
    """

    properties: JsonObject = {
        "title": _synthetic_text(f"title:{local_id}", TITLE_LENGTH),
        "aliases": [
            _synthetic_text(f"alias:{index}:{local_id}", ALIAS_LENGTH)
            for index in range(_alias_count(local_id))
        ],
        "lifecycle": _lifecycle(local_id),
        "provenance": _provenance(local_id),
        "body": _synthetic_text(f"body:{local_id}", BODY_LENGTH),
    }
    unexpected = sorted(set(properties) - set(PUBLISHED_PROPERTY_KEYS))
    if unexpected:
        raise BdpMappingError(f"property keys outside the allowlist: {', '.join(unexpected)}")
    return properties


def node_key(index: int) -> str:
    """The generator-side name of one node, before it is hashed into a Bead id."""

    return f"n{index:04d}"


def bead_records(family: str, scope: ScopeUrls, bead_count: int) -> tuple[JsonObject, ...]:
    """One complete Bead record per node, in ascending canonical URI order."""

    by_url: dict[str, str] = {}
    records: list[JsonObject] = []
    for index in range(bead_count):
        key = node_key(index)
        local_id = bead_local_id(family, key)
        url = scope.bead(local_id)
        if url in by_url:
            raise BdpMappingError(
                f"two nodes project onto the same Bead id {url}: {by_url[url]!r} and {key!r}"
            )
        by_url[url] = key
        record: JsonObject = {
            "id": url,
            "type": BEAD_TYPE_ID,
            "properties": bead_properties(local_id),
        }
        record["revision"] = record_revision(record)
        records.append(record)
    return tuple(sorted(records, key=lambda record: str(record["id"])))


def link_records(
    family: str, scope: ScopeUrls, edges: Sequence[tuple[int, int]], bead_count: int
) -> tuple[JsonObject, ...]:
    """One Link per generated edge, in ascending canonical URI order.

    Ordinals are assigned AFTER sorting on the published endpoints, so a Link id
    is a function of the published graph and carries nothing about the order the
    generator emitted edges in.

    Both endpoints must be Beads in this Scope: BDP requires at least one
    in-Scope endpoint, and a dangling endpoint in a fixture would be
    indistinguishable from an authority bug.
    """

    resolved: list[tuple[str, str]] = []
    for source_index, target_index in edges:
        for index in (source_index, target_index):
            if not 0 <= index < bead_count:
                raise BdpMappingError(
                    f"{family} edge endpoint {index} names no Bead in this Scope "
                    f"of {bead_count}"
                )
        resolved.append(
            (
                scope.bead(bead_local_id(family, node_key(source_index))),
                scope.bead(bead_local_id(family, node_key(target_index))),
            )
        )

    # Sorting on the endpoints alone is not a total order between two Links that
    # share a (source, target) tuple, which BDP permits and one family carries on
    # purpose. The enumeration index breaks that tie deterministically.
    ordered_edges = sorted(enumerate(resolved), key=lambda item: (item[1][0], item[1][1], item[0]))

    records: list[JsonObject] = []
    for ordinal, (_, (source, target)) in enumerate(ordered_edges, start=1):
        if len(str(ordinal)) > LINK_ID_WIDTH:
            raise BdpMappingError(
                f"link ordinal {ordinal} exceeds the zero-padded width {LINK_ID_WIDTH}, which "
                "would break the codepoint/ordinal order coincidence these fixtures rely on"
            )
        record: JsonObject = {
            "id": scope.link(ordinal),
            "type": CITES_TYPE_ID,
            "source": source,
            "target": target,
            "properties": {},
        }
        record["revision"] = record_revision(record)
        records.append(record)
    return tuple(sorted(records, key=lambda record: str(record["id"])))


def type_descriptors() -> tuple[JsonObject, ...]:
    """The two Type Descriptor documents, in canonical URI order.

    One document per Type, served at the Type ID URL. This is not the body of
    `GET /types/`, which returns summaries; see `type_summaries`.

    No `propertiesSchema` is published. BDP makes schemas optional, and a schema
    invented here would assert a Memory contract that mem does not actually
    enforce anywhere.
    """

    descriptors: tuple[JsonObject, ...] = (
        {
            "id": BEAD_TYPE_ID,
            "name": "Memory",
            "description": "An operating note in a frozen mem ordering graph family.",
            "describes": "bead",
            "conformsTo": [],
        },
        {
            "id": CITES_TYPE_ID,
            "name": "Cites",
            "description": "A reference from one Memory to another, within one Scope.",
            "describes": "link",
            "conformsTo": [],
            "source": {"conformsTo": [BEAD_TYPE_ID], "external": "none"},
            "target": {"conformsTo": [BEAD_TYPE_ID], "external": "none"},
        },
    )
    return tuple(sorted(descriptors, key=lambda record: str(record["id"])))


def type_summaries() -> tuple[JsonObject, ...]:
    """The `GET /types/` items: exactly `{id, name, describes}` per Type.

    The spec is explicit that the Types collection returns summaries and that the
    full Descriptor is its own document at the Type ID URL. `typeSummary` closes
    `additionalProperties`, so shipping a Descriptor here is not merely verbose,
    it is invalid.
    """

    return tuple(
        {"id": descriptor["id"], "name": descriptor["name"], "describes": descriptor["describes"]}
        for descriptor in type_descriptors()
    )


def descriptor_filename(type_id: str) -> str:
    """The path segment a Type Descriptor document is stored under.

    Mirrors the final segment of the Type ID URL. The tree root stands for
    `/ordering/` and the Type IDs live under `/ordering/types/`, so the on-disk
    path and the URL a consumer fetches line up without a lookup table.
    """

    prefix = f"{TYPES_BASE}/"
    if not type_id.startswith(prefix):
        raise BdpMappingError(f"Type id is not under {prefix}: {type_id}")
    segment = type_id[len(prefix) :]
    if not segment or "/" in segment or "." in segment:
        raise BdpMappingError(f"Type id is not a single plain path segment: {type_id}")
    return f"{segment}.json"


def discovery_document(scope: ScopeUrls, *, limits: Sequence[int] = DEFAULT_LIMITS) -> JsonObject:
    """The Read-profile discovery document a consumer starts from.

    Every collection URL these fixtures record expectations against is reachable
    from here, which is the point: a consumer that hardcodes the paths instead of
    reading discovery is not exercising the protocol.
    """

    if not limits:
        raise BdpMappingError("discovery needs at least one page limit to advertise")
    invalid = sorted({limit for limit in limits if limit < 1})
    if invalid:
        raise BdpMappingError(
            f"advertised page limits must be positive integers, got {invalid}; the schema's "
            "positiveInteger would reject the document"
        )
    return {
        "bdpVersion": "0",
        "profile": "read",
        "scope": scope.scope_url,
        "beads": scope.beads_collection,
        "links": scope.links_collection,
        "types": scope.types_collection,
        "limits": {"page": {"defaultItems": min(limits), "maximumItems": max(limits)}},
    }


def _scramble_key(identifier: str) -> str:
    return _digest(f"bdp-fixture-serialization:{identifier}")


def serialization_order(records: Sequence[Mapping[str, Any]]) -> tuple[JsonObject, ...]:
    """Order a load-set array so it is deliberately NOT the reference order.

    Shipping the records sorted would let an authority that merely echoes the
    order it loaded reproduce every reference sequence without ordering at all.
    Serializing under a digest of the id breaks that coincidence while staying a
    pure function of the input.

    A collection of fewer than two records has only one arrangement, so it comes
    back as-is. `is_canonical_order` is vacuously true of it, and callers must
    not read that as a defect.
    """

    ordered = sorted(
        records, key=lambda record: (_scramble_key(str(record["id"])), str(record["id"]))
    )
    identifiers = [str(record["id"]) for record in ordered]
    if len(identifiers) >= 2 and identifiers == sorted(identifiers):
        # A two-item collection lands in canonical order about half the time. The
        # reversal makes the discrimination property total rather than probable.
        ordered = list(reversed(ordered))
    return tuple(dict(record) for record in ordered)


def is_canonical_order(records: Sequence[Mapping[str, Any]]) -> bool:
    identifiers = [str(record["id"]) for record in records]
    return identifiers == sorted(identifiers)


def _page_count(total: int, limit: int) -> int:
    if limit < 1:
        raise BdpMappingError(f"page limit must be positive: {limit}")
    if total == 0:
        # A conformant authority answers an empty selection with one empty page
        # and `next` null, not with zero pages. Recording 0 here would make the
        # fixture demand a response no authority can send.
        return 1
    return -(-total // limit)


def _page_item_counts(total: int, limit: int) -> list[int]:
    """How many items each page holds, which is the whole page partition.

    Recorded instead of the first id of each page. First ids pin the boundaries
    only under one particular order; item counts are the arithmetic every
    conformant authority owes whichever order it documents, and together with the
    selected set they say exactly what a harness may check.
    """

    count = _page_count(total, limit)
    return [min(limit, total - index * limit) for index in range(count)]


def collection_expectation(selected: Sequence[str], limits: Iterable[int]) -> JsonObject:
    """What a harness may assert about one collection or selection.

    `selected_set` is the membership assertion: concatenating every page of the
    snapshot must yield exactly these ids, each once. It is written in ascending
    canonical URI order so two runs can be diffed, which is a spelling choice and
    not a claim that an authority must return them in that order.
    """

    ordered = sorted(selected)
    expectation: JsonObject = {"total": len(ordered), "selected_set": ordered}
    pages: JsonObject = {}
    for limit in limits:
        count = _page_count(len(ordered), limit)
        pages[str(limit)] = {
            "page_count": count,
            "page_item_counts": _page_item_counts(len(ordered), limit),
            # Whether this limit forces a continuation at all. A selection that
            # fits in one page exercises membership only. Neither limit exercises
            # an opaque cursor: no continuation response is shipped.
            "spans_multiple_pages": count > 1,
        }
    expectation["pages"] = pages
    return expectation


def selection_expectation(
    description: str,
    collection: str,
    parameters: Mapping[str, str],
    matched: Sequence[str],
    limits: Iterable[int],
) -> JsonObject:
    selection: JsonObject = {
        "description": description,
        "collection": collection,
        "parameters": dict(parameters),
    }
    selection.update(collection_expectation(matched, limits))
    return selection


def _highest_outdegree_bead(links: Sequence[Mapping[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for link in links:
        source = str(link["source"])
        counts[source] = counts.get(source, 0) + 1
    if not counts:
        raise BdpMappingError("family has no Links, so it exercises no density case")
    # Ties break on the canonical URI so the choice is reproducible, not incidental.
    return max(counts, key=lambda source: (counts[source], source))


def matching_beads(beads: Sequence[Mapping[str, Any]], key: str, value: str) -> list[str]:
    matched: list[str] = []
    for record in beads:
        properties = record["properties"]
        if not isinstance(properties, Mapping):
            raise BdpMappingError(f"Bead {record['id']} has non-object properties")
        if key not in properties:
            raise BdpMappingError(f"Bead {record['id']} carries no {key!r} property to select on")
        if properties[key] == value:
            matched.append(str(record["id"]))
    return matched


def proposal_note() -> JsonObject:
    """What gastownhall/bdp#8 asks for, and which parts this tree can check.

    The proposal leaves the choice of order to the implementation. An authority
    documenting "descending insertion ordinal" is conformant and returns none of
    the sequences in this file. The reference sequences are therefore one legal
    order rather than a requirement, and a harness asserting them against an
    authority that documents a different order is testing its own preference.
    """

    return {
        "proposal": "https://github.com/gastownhall/bdp/issues/8",
        "clauses": [
            "an authority imposes a total order on the selected set",
            "the order is deterministic for a given selected set",
            "the order is stable across the pages of one snapshot",
            "the authority documents the order it uses",
        ],
        "leaves_choice_of_order_to_the_implementation": True,
        "checkable_against_this_tree": [
            "membership: concatenating every page of a snapshot yields exactly `selected_set`, "
            "each id once, with no omission and no repeat",
            "page partitioning: `page_count` and `page_item_counts` at each recorded limit",
            "the reference sequence, but only against an authority that documents "
            f"{FIXTURE_ORDER_ID!r} as the order it uses",
        ],
        "not_checkable_against_this_tree": [
            "determinism across two reads, which a harness gets by reading twice rather than "
            "from any data here",
            "stability across the pages of one snapshot: no continuation response and no cursor "
            "is shipped, so an authority that re-sorts or restarts on continuation passes "
            "everything here",
            "the documentation duty, which is a property of an authority rather than of a "
            "fixture",
        ],
    }


def ordering_expectations(
    beads: Sequence[Mapping[str, Any]],
    links: Sequence[Mapping[str, Any]],
    types: Sequence[Mapping[str, Any]],
    scope: ScopeUrls,
    *,
    limits: Sequence[int] = DEFAULT_LIMITS,
) -> JsonObject:
    """The selected set and page partition per collection and selection.

    This records what a harness may assert under gastownhall/bdp#8 as proposed:
    membership of the selected set, and the page arithmetic over it, both of
    which every conformant authority owes whichever order it documents. The
    sequences are written in ascending canonical URI order, a spelling that makes
    two runs diffable and that is also the expected sequence for an authority
    documenting that same order. See `proposal_note`.
    """

    bead_ids = [str(record["id"]) for record in beads]
    link_ids = [str(record["id"]) for record in links]
    type_ids = [str(record["id"]) for record in types]
    for name, ordered in (("beads", bead_ids), ("links", link_ids), ("types", type_ids)):
        if list(ordered) != sorted(ordered):
            raise BdpMappingError(f"{name} records were not handed over in canonical URI order")

    hub = _highest_outdegree_bead(links)
    outbound = [str(link["id"]) for link in links if str(link["source"]) == hub]
    inbound = [str(link["id"]) for link in links if str(link["target"]) == hub]
    incident = [
        str(link["id"]) for link in links if hub in (str(link["source"]), str(link["target"]))
    ]

    return {
        "reference_order": FIXTURE_ORDER_ID,
        "reference_order_note": (
            "Ascending canonical URI of the record id. One legal order, not a required one: "
            "gastownhall/bdp#8 leaves the choice of order to the implementation. `selected_set` "
            "is written in this order so that two runs can be diffed."
        ),
        "bdp8": proposal_note(),
        "serialization_note": (
            "The `items` arrays under dataset/ are the load set and are deliberately NOT in the "
            "reference order. An authority that echoes the order it loaded reproduces none of "
            "the reference sequences below."
        ),
        "empty_selection_note": (
            "A selection matching nothing is one page with an empty `items` array and `next` "
            "null, so `page_count` is 1 and `page_item_counts` is [0]."
        ),
        "scope": scope.scope_url,
        "collections": {
            "beads/": collection_expectation(bead_ids, limits),
            "links/": collection_expectation(link_ids, limits),
            "types/": collection_expectation(type_ids, limits),
        },
        "selections": [
            selection_expectation(
                "Outbound Links of this family's highest-outdegree Bead. Whether a page "
                "boundary falls inside that one adjacency varies by family and by limit; "
                "`spans_multiple_pages` says which, per limit.",
                "links/",
                {"source": hub},
                outbound,
                limits,
            ),
            selection_expectation(
                "Inbound Links of the same Bead. Distinct from the outbound set in the five "
                "families whose highest-outdegree Bead is itself cited by something. In the "
                "two forest-shaped families no Bead carries both an inbound and an outbound "
                "Link, so this set is empty and the incident set equals the outbound one: that "
                "is the empty-selection case, and it is also why a pass on those two families "
                "does not discriminate `endpoint` from `source`.",
                "links/",
                {"target": hub},
                inbound,
                limits,
            ),
            selection_expectation(
                "Incident Links of the same Bead, exercising the source-OR-target combination "
                "inside the endpoint predicate.",
                "links/",
                {"endpoint": hub},
                incident,
                limits,
            ),
            selection_expectation(
                "Agent-provenance Beads. About half of every family, so this is the many-page "
                "Selector case: the selected set is decided before pagination and must stay "
                "fixed across every continuation of the snapshot.",
                "beads/",
                {"selector": '$[?@.properties.provenance == "agent"]'},
                matching_beads(beads, "provenance", "agent"),
                limits,
            ),
            selection_expectation(
                "Archived Beads: a handful per family. A selection far smaller than either "
                "page limit, so it must come back as exactly one page with `next` null.",
                "beads/",
                {"selector": '$[?@.properties.lifecycle == "archived"]'},
                matching_beads(beads, "lifecycle", "archived"),
                limits,
            ),
        ],
    }
