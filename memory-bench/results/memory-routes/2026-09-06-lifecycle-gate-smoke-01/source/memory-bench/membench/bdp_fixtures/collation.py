"""The collation family: identifier spellings that separate comparison rules.

The seven graph families spell every Bead id as fixed-width lowercase hex and
every Link id as a zero-padded ordinal, so codepoint order over the canonical
URI, bytewise UTF-8 order, numeric order and case-insensitive order all agree.
That is deliberate there: it makes the reference order a clean total order and
keeps those families about membership and page arithmetic. It also means an
authority that compares numerically, that folds case, that ignores punctuation,
or that percent-decodes and normalizes before comparing passes all seven without
ever being asked the question.

This family asks it. Every identifier here is authored rather than generated,
because the identifiers are the payload. Four groups, each spelling out one axis
on which two comparison rules disagree:

    unpadded-ordinals   `2` after `10`, which numeric comparison reverses
    mixed-case          `Zeta` before `alpha`, which case folding reverses
    punctuation         `alpha-two` before `alpha_one`, which a collator that
                        treats punctuation as ignorable reverses
    normalization       one label percent-encoded from NFC and from NFD, which
                        percent-decoding reorders and normalizing ties

The reference order is ascending by Unicode code point over the canonical URI as
written: no percent-decoding, no Unicode normalization, no case folding, no
numeric parsing. Every identifier in this family is ASCII, so a bytewise UTF-8
comparison and a codepoint comparison cannot disagree; the non-ASCII appears
only inside percent-encoding, which is where a URI is allowed to carry it.

Two kinds of finding come out of this, and they are worth separating.

A comparison rule that ties two distinct ids is not a total order, so it fails
gastownhall/bdp#8's first clause outright, whatever order the authority
documents: two records that compare equal can be served twice or not at all
across a page boundary. Case folding, punctuation-ignoring collation and NFC
normalization all tie ids in this family.

A comparison rule that is a total order but a different one is conformant under
bdp#8 as proposed, which leaves the choice of order to the implementation. It is
detectable only against an authority that documents this family's order.
Numeric-aware comparison and percent-decoding comparison are both of these.

That split is the point of the family. It says which collation mistakes are
protocol violations and which are merely undocumented choices, and bdp#8's
"documents the order it uses" clause is only meaningful once the difference is
written down.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

from membench.bdp_fixtures.mapping import (
    BEAD_TYPE_ID,
    CITES_TYPE_ID,
    JsonObject,
    ScopeUrls,
    bead_properties,
    collection_expectation,
    matching_beads,
    proposal_note,
    record_revision,
    selection_expectation,
)

COLLATION_FAMILY = "collation-edge-identifiers"

# Named apart from `ascending-canonical-uri`, the order the seven graph families
# record. There the two names denote the same sequence, because those ids are
# ASCII and fixed-width. Here they do not: "ascending canonical URI" does not say
# whether the comparison decodes, normalizes, folds or parses first, and this
# family is built out of the ids on which those readings diverge.
COLLATION_ORDER_ID = "ascending-canonical-uri-codepoint"

# Small limits, so a page boundary falls inside a collection of this size. A
# comparison rule that ties two ids can lose or repeat one across a boundary, and
# a single-page collection would never show it.
COLLATION_LIMITS = (3, 10)

# The Selector predicate this family records a selection for. `lifecycle ==
# archived` is the seven families' narrow predicate at roughly 1 Bead in 100,
# which over a collection this size would select nothing.
SELECTOR_PROPERTY = "provenance"
SELECTOR_VALUE = "agent"


class CollationError(RuntimeError):
    """Raised when the authored identifiers stop separating what they claim to."""


@dataclass(frozen=True)
class RivalComparator:
    """One comparison rule an authority might plausibly implement instead.

    Each is a rule someone reaches for on purpose: numeric-aware comparison so
    that `2` precedes `10`, case folding so that listings read alphabetically,
    a collator with punctuation weighted as ignorable, and URI or Unicode
    normalization before comparing. None of them is careless. All of them return
    something other than this family's recorded sequence.
    """

    name: str
    describes: str
    key: Callable[[str], Any]


def _natural_key(value: str) -> tuple[tuple[int, str], ...]:
    """Digit runs compared as integers, everything else as text.

    The shape of a numeric-aware sort, spelled so that a digit run and a text run
    never compare against each other by accident.
    """

    return tuple(
        (int(part), "") if part.isdigit() else (-1, part)
        for part in re.split(r"(\d+)", value)
        if part
    )


def _casefold_key(value: str) -> str:
    return value.casefold()


def _punctuation_ignoring_key(value: str) -> str:
    """Alphanumerics only, case folded.

    A deliberately crude stand-in for a collator run at primary strength with
    punctuation weighted as variable. It is not ICU, and it is not claimed to
    be: it is the coarsest rule that reproduces the failure a variable-weighting
    collator produces on these identifiers.
    """

    return re.sub(r"[^0-9a-z]", "", value.casefold())


def _percent_decoding_key(value: str) -> str:
    return unquote(value)


def _nfc_key(value: str) -> str:
    return unicodedata.normalize("NFC", unquote(value))


RIVALS: tuple[RivalComparator, ...] = (
    RivalComparator(
        "numeric-aware",
        "digit runs compared as integers, so `2` precedes `10`",
        _natural_key,
    ),
    RivalComparator(
        "casefold",
        "case folded before comparing, so `alpha` precedes `Zeta`",
        _casefold_key,
    ),
    RivalComparator(
        "punctuation-ignoring",
        "punctuation dropped and case folded, as a collator at primary strength",
        _punctuation_ignoring_key,
    ),
    RivalComparator(
        "percent-decoding",
        "percent-decoded before comparing, so the encoded octets stop deciding",
        _percent_decoding_key,
    ),
    RivalComparator(
        "nfc-normalizing",
        "percent-decoded and normalized to NFC, so NFC and NFD spellings tie",
        _nfc_key,
    ),
)

RIVALS_BY_NAME: dict[str, RivalComparator] = {rival.name: rival for rival in RIVALS}


@dataclass(frozen=True)
class CollationGroup:
    """One axis, the ids that span it, and the rules those ids separate.

    `defeats` is declared rather than derived. It is checked against what the
    identifiers actually do every time the family is built, so an edit that
    quietly stops separating a rule is a build failure instead of a fixture that
    still looks thorough.
    """

    name: str
    exercises: str
    defeats: tuple[str, ...]
    bead_ids: tuple[str, ...]
    link_ids: tuple[str, ...]


COLLATION_GROUPS: tuple[CollationGroup, ...] = (
    CollationGroup(
        name="unpadded-ordinals",
        exercises="numeric order against codepoint order, with no zero padding to hide it",
        defeats=("numeric-aware",),
        bead_ids=("1", "2", "9", "10", "11", "100", "101", "2000"),
        link_ids=("1", "2", "9", "10", "11"),
    ),
    CollationGroup(
        name="mixed-case",
        exercises="ASCII case order, where every uppercase letter precedes every lowercase one",
        defeats=("casefold", "punctuation-ignoring"),
        bead_ids=("GAMMA", "Gamma", "gamma", "Delta", "delta", "Zeta"),
        link_ids=("EDGE", "Edge", "edge", "Zeta"),
    ),
    CollationGroup(
        name="punctuation",
        exercises="separators inside a common stem, which a variable-weighting collator drops",
        defeats=("punctuation-ignoring",),
        bead_ids=("alpha", "alpha-two", "alpha_one", "alphathree"),
        link_ids=("link-a", "link_b", "linkc"),
    ),
    CollationGroup(
        name="normalization",
        exercises="one label percent-encoded from NFC and from NFD, beside its unaccented form",
        defeats=("percent-decoding", "nfc-normalizing"),
        # `caf%C3%A9` is U+00E9 encoded; `cafe%CC%81` is `e` followed by the
        # encoded combining acute accent. The two decode to the same text under
        # NFC and to different text without it.
        bead_ids=("cafe", "caf%C3%A9", "cafe%CC%81", "r%C3%A9sume", "re%CC%81sume"),
        link_ids=("n%C3%A9e", "ne%CC%81e", "nee"),
    ),
)


def collation_bead_ids() -> tuple[str, ...]:
    """Every authored Bead local id, in the order the groups declare them."""

    return tuple(local_id for group in COLLATION_GROUPS for local_id in group.bead_ids)


def collation_link_ids() -> tuple[str, ...]:
    """Every authored Link local id, in the order the groups declare them."""

    return tuple(local_id for group in COLLATION_GROUPS for local_id in group.link_ids)


def _tie_groups(urls: Sequence[str], rival: RivalComparator) -> list[list[str]]:
    """Sets of distinct URLs this rule cannot tell apart, each sorted."""

    buckets: dict[str, list[str]] = {}
    for url in urls:
        buckets.setdefault(repr(rival.key(url)), []).append(url)
    return sorted(
        (sorted(bucket) for bucket in buckets.values() if len(bucket) > 1),
        key=lambda bucket: bucket[0],
    )


def _defeated_rivals(urls: Sequence[str]) -> tuple[str, ...]:
    """The rules whose order over `urls` differs from the codepoint order.

    A rule that ties two of them counts as defeated too: a tie is a worse answer
    than a different order, not a lesser one, because it is not a total order at
    all.
    """

    reference = sorted(urls)
    defeated: list[str] = []
    for rival in RIVALS:
        if sorted(urls, key=rival.key) != reference or _tie_groups(urls, rival):
            defeated.append(rival.name)
    return tuple(defeated)


def validate_groups(scope: ScopeUrls) -> None:
    """Refuse a group set that no longer separates what it says it separates.

    Every check is a build failure rather than a test, for the same reason
    `build_edges` validates the graph shapes: a family that has quietly stopped
    exercising its axis still emits a tree that looks complete, and the recorded
    claim about it is then false in a file somebody else will trust.
    """

    bead_ids = collation_bead_ids()
    link_ids = collation_link_ids()
    for kind, ids in (("Bead", bead_ids), ("Link", link_ids)):
        duplicates = sorted({local for local in ids if ids.count(local) > 1})
        if duplicates:
            raise CollationError(f"{kind} local ids repeat in this family: {', '.join(duplicates)}")

    for group in COLLATION_GROUPS:
        unknown = sorted(set(group.defeats) - set(RIVALS_BY_NAME))
        if unknown:
            raise CollationError(
                f"{group.name} claims to defeat unknown comparison rules: {', '.join(unknown)}"
            )
        urls = [scope.bead(local_id) for local_id in group.bead_ids]
        actual = _defeated_rivals(urls)
        if actual != tuple(sorted(group.defeats)) and set(actual) != set(group.defeats):
            raise CollationError(
                f"{group.name} declares it defeats {sorted(group.defeats)} but its Bead ids "
                f"defeat {list(actual)}; the declaration and the identifiers disagree"
            )
        if not actual:
            raise CollationError(
                f"{group.name} separates no comparison rule, so it is a group of ids and "
                "nothing more"
            )

    covered = {name for group in COLLATION_GROUPS for name in group.defeats}
    uncovered = sorted(set(RIVALS_BY_NAME) - covered)
    if uncovered:
        raise CollationError(
            f"no group separates {', '.join(uncovered)}, so the family records a comparison "
            "rule it cannot detect"
        )

    # The Link id space is the half `LINK_ID_WIDTH` padded flat in the seven
    # families, so it has to carry the axes too rather than inheriting the claim
    # from the Bead ids.
    link_urls = [scope.link_local(local_id) for local_id in link_ids]
    link_defeated = set(_defeated_rivals(link_urls))
    if link_defeated != set(RIVALS_BY_NAME):
        raise CollationError(
            "the authored Link ids separate only "
            f"{sorted(link_defeated)}, so the Link id space is untested against "
            f"{sorted(set(RIVALS_BY_NAME) - link_defeated)}"
        )


def collation_bead_records(scope: ScopeUrls) -> tuple[JsonObject, ...]:
    """One Bead per authored local id, in ascending canonical URI order.

    Properties come from the same generator the seven families use, so they are a
    function of the Bead's own id and carry nothing else. Here they exist only to
    give the Selector selection something to filter on: this family's payload is
    the identifier, not the record.
    """

    records: list[JsonObject] = []
    for local_id in collation_bead_ids():
        record: JsonObject = {
            "id": scope.bead(local_id),
            "type": BEAD_TYPE_ID,
            "properties": bead_properties(local_id),
        }
        record["revision"] = record_revision(record)
        records.append(record)
    return tuple(sorted(records, key=lambda record: str(record["id"])))


def collation_edges(bead_count: int, link_count: int) -> tuple[tuple[int, int], ...]:
    """Endpoint index pairs for the authored Links, over Beads in reference order.

    The graph shape is not what this family is for, so the rule is the least
    interesting one that still gives the fixture a Link selection worth ordering.
    Half the Links leave the first Bead, which makes `?source=` a multi-page
    selection spanning two of the four identifier groups; the rest fan out from
    the Beads that first Bead points at, so several Beads carry both an inbound
    and an outbound Link. Every Link gets two distinct in-Scope endpoints.
    """

    stride = 5
    if bead_count <= stride:
        raise CollationError(
            f"a stride of {stride} over {bead_count} Beads cannot avoid a self-Link"
        )
    fan = link_count // 2
    if not 1 < fan < bead_count:
        raise CollationError(
            f"{link_count} Links over {bead_count} Beads gives the first Bead a fan-out of "
            f"{fan}, which is not a selection worth recording an order over"
        )
    edges = [(0, index + 1) for index in range(fan)]
    edges += [
        (index - fan + 1, (index - fan + 1 + stride) % bead_count)
        for index in range(fan, link_count)
    ]
    return tuple(edges)


def collation_link_records(
    scope: ScopeUrls, beads: Sequence[Mapping[str, Any]]
) -> tuple[JsonObject, ...]:
    """One Link per authored local id, in ascending canonical URI order.

    Unlike the seven families, ordinals are not assigned here: the Link ids are
    authored, and pairing them with endpoints by position is what keeps the id
    spelling independent of the graph.
    """

    link_ids = collation_link_ids()
    bead_urls = [str(record["id"]) for record in beads]
    records: list[JsonObject] = []
    for local_id, (source_index, target_index) in zip(
        link_ids, collation_edges(len(bead_urls), len(link_ids)), strict=True
    ):
        if source_index == target_index:
            raise CollationError(f"Link {local_id} would be a self-Link at {source_index}")
        record: JsonObject = {
            "id": scope.link_local(local_id),
            "type": CITES_TYPE_ID,
            "source": bead_urls[source_index],
            "target": bead_urls[target_index],
            "properties": {},
        }
        record["revision"] = record_revision(record)
        records.append(record)
    return tuple(sorted(records, key=lambda record: str(record["id"])))


def rival_report(urls: Sequence[str]) -> list[JsonObject]:
    """What each comparison rule does to one collection, recorded rather than argued.

    A rule that ties two ids gets no `sequence`. Recording one would be recording
    an artifact: with a tie, the sequence a sort returns depends on the order the
    items went in, so writing it down would publish this emitter's input order as
    though it were the rule's answer.
    """

    reference = sorted(urls)
    report: list[JsonObject] = []
    for rival in RIVALS:
        ties = _tie_groups(urls, rival)
        entry: JsonObject = {
            "comparison": rival.name,
            "describes": rival.describes,
            "is_a_total_order_over_this_collection": not ties,
            "differs_from_the_reference_order": sorted(urls, key=rival.key) != reference
            or bool(ties),
            "ties": ties,
            "bdp8_reading": (
                "not a total order over these ids, so it fails the first clause whatever "
                "order the authority documents"
                if ties
                else "a total order, but a different one; conformant under the proposal as "
                "written and detectable only against an authority that documents "
                f"{COLLATION_ORDER_ID!r}"
            ),
        }
        if not ties:
            entry["sequence"] = sorted(urls, key=rival.key)
        report.append(entry)
    return report


def collation_expectations(
    beads: Sequence[Mapping[str, Any]],
    links: Sequence[Mapping[str, Any]],
    types: Sequence[Mapping[str, Any]],
    scope: ScopeUrls,
    *,
    limits: Sequence[int] = COLLATION_LIMITS,
) -> JsonObject:
    """What a harness may assert against this family.

    Two things, and they carry very different weight.

    Membership and the page partition are what every conformant authority owes
    whichever order it documents, exactly as in the seven graph families. Here
    they are the check that survives a comparison rule which ties two ids: a rule
    that is not a total order can serve a tied record twice, or drop it, across a
    page boundary, and the membership assertion catches that without knowing
    anything about the order the authority chose.

    The recorded sequence is the other thing, and it binds only against an
    authority documenting this family's order. That is not a weakness of the
    fixture but the substance of it: `collation.comparisons` records what each
    rival comparison rule returns, so a harness can report which mistake an
    authority made rather than only that the sequence was wrong.
    """

    bead_ids = [str(record["id"]) for record in beads]
    link_ids = [str(record["id"]) for record in links]
    type_ids = [str(record["id"]) for record in types]
    for name, ordered in (("beads", bead_ids), ("links", link_ids), ("types", type_ids)):
        if list(ordered) != sorted(ordered):
            raise CollationError(f"{name} records were not handed over in codepoint order")

    matched = matching_beads(beads, SELECTOR_PROPERTY, SELECTOR_VALUE)
    if not 0 < len(matched) < len(bead_ids):
        raise CollationError(
            f"the {SELECTOR_PROPERTY} == {SELECTOR_VALUE!r} selection matches {len(matched)} of "
            f"{len(bead_ids)} Beads, so it is a collection rather than a selection"
        )
    outdegree: dict[str, int] = {}
    for link in links:
        outdegree[str(link["source"])] = outdegree.get(str(link["source"]), 0) + 1
    # Ties break on the canonical URI, so the choice is reproducible rather than
    # incidental, as in the seven graph families.
    source = max(outdegree, key=lambda candidate: (outdegree[candidate], candidate))
    outbound = [str(link["id"]) for link in links if str(link["source"]) == source]
    if len(outbound) < 2:
        raise CollationError(
            "the busiest Bead in this family emits one Link, so the Link selection records an "
            "order over a single record and asserts nothing"
        )

    return {
        "reference_order": COLLATION_ORDER_ID,
        "reference_order_note": (
            "Ascending by Unicode code point over the canonical URI as written: no "
            "percent-decoding, no Unicode normalization, no case folding, no numeric parsing. "
            "Every identifier in this family is ASCII, so a bytewise UTF-8 comparison and a "
            "codepoint comparison agree here; the non-ASCII lives inside percent-encoding."
        ),
        "why_this_family_names_its_own_order": (
            "The seven graph families record 'ascending-canonical-uri'. Their ids are ASCII and "
            "fixed-width, so every reading of that phrase returns the same sequence and the "
            "ambiguity never surfaces. It surfaces here. 'Ascending canonical URI' does not say "
            "whether the comparison decodes, normalizes, folds case or parses digits first, and "
            "this family is built out of the identifiers on which those readings diverge, so it "
            "names the comparison rule in the order id."
        ),
        "bdp8": proposal_note(),
        "serialization_note": (
            "The `items` arrays under dataset/ are the load set and are deliberately NOT in the "
            "reference order, as in the seven graph families."
        ),
        "membership_is_the_order_independent_assertion": (
            "Concatenating every page of one snapshot must yield `selected_set` exactly, each "
            "id once, and that check holds whatever order the authority documents. It is the "
            "assertion a tie threatens: a comparison rule that cannot separate two ids leaves "
            "their relative position to whatever the authority falls back on, and a keyset "
            "continuation built on the comparison alone can then repeat one or skip one. "
            "Whether a given authority actually loses a record depends on how it paginates, so "
            "this tree records which rules tie which ids rather than predicting the outcome; "
            "`collation.comparisons[].ties` names the pairs that would explain a membership "
            "failure here."
        ),
        "scope": scope.scope_url,
        "collections": {
            "beads/": collection_expectation(bead_ids, limits),
            "links/": collection_expectation(link_ids, limits),
            "types/": collection_expectation(type_ids, limits),
        },
        "selections": [
            selection_expectation(
                "Outbound Links of this family's highest-outdegree Bead. A selection rather "
                "than a whole collection, and it spans more than one page, so the comparison "
                "rule has to hold across a continuation over the authored Link ids rather "
                "than only inside a single page.",
                "links/",
                {"source": source},
                outbound,
                limits,
            ),
            selection_expectation(
                f"Beads whose {SELECTOR_PROPERTY} is {SELECTOR_VALUE!r}. About half the family, "
                "so the selected set spans pages and the order has to hold across a "
                "continuation rather than inside one page.",
                "beads/",
                {"selector": f'$[?@.properties.{SELECTOR_PROPERTY} == "{SELECTOR_VALUE}"]'},
                matched,
                limits,
            ),
        ],
        "collation": {
            "groups": [
                {
                    "name": group.name,
                    "exercises": group.exercises,
                    "defeats": list(group.defeats),
                    "bead_ids": list(group.bead_ids),
                    "link_ids": list(group.link_ids),
                    "beads_in_reference_order": sorted(
                        scope.bead(local_id) for local_id in group.bead_ids
                    ),
                }
                for group in COLLATION_GROUPS
            ],
            "comparisons": {
                "beads/": rival_report(bead_ids),
                "links/": rival_report(link_ids),
            },
        },
    }
