"""The seven graph shapes the BDP conformance fixtures are built on.

These graphs are generated here, from this module's own seed. They are NOT a
projection of the frozen ordering corpus, and that is a deliberate reversal of
the first three revisions of this package.

Why the reversal. The frozen families were authored around a distinguished node
per family (a stale hub, a member of a reference cycle, a newly authored note
nobody links to), which is exactly what makes them hard cases for a retrieval
benchmark. It also makes degree the benchmark's label. Sweeping degree
predicates over the published Links and controlling against 200 random
same-sized decoy sets per family, `deg==4` returned exactly three Beads in the
branching family and all three were benchmark gold; `deg==2` returned 4 of 5 in
the DAG family and 3 of 5 in the chain family. No decoy set reached those
precisions in six of the seven families, against a 1.8% base rate. Neutralizing
identifiers, free text and property values does not touch that channel, and
nothing that preserves the degree sequence can: rewiring under a fixed degree
sequence preserves it exactly, and deleting the distinguished nodes destroys the
shape, because the distinguished node usually IS the shape.

So the corpus's adjacency is not published. What these fixtures owe BDP is a set
of graph shapes that break ordering and pagination assumptions, together with
recorded expectations over them, and that never required our adjacency. Building
the shapes here instead of inheriting them also lets each one be chosen for the
conformance property it exercises, including two properties the projected tree
could not reach at all: no projected family had a single selection larger than
the biggest advertised page limit, and none had two Links sharing a
`(type, source, target)` tuple, which BDP v0 permits and a consumer must not
collapse.

Family names are stable labels for graph shapes and are kept from the projected
revision so that the offer on gastownhall/beads#6051 and the discussion on
gastownhall/bdp#8 keep referring to the same seven scopes. No family contains
domain content; the "incident runbook" in a name is a label, not a payload.

Determinism is by construction: every choice comes from a digest of a string, so
the output is byte-identical on any interpreter, with no dependence on the
`random` module's stability across releases.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass

# Bumped when a shape changes, so a tree emitted under an older layout is not
# mistaken for a re-emit of this one.
TOPOLOGY_SEED = "bdp-fixture-topology/v1"

BEADS_PER_FAMILY = 500

Edges = tuple[tuple[int, int], ...]


class TopologyError(RuntimeError):
    """Raised when a generated shape violates its own declared contract."""


def _pick(seed: str, bound: int) -> int:
    """A deterministic index in `[0, bound)` drawn from a digest of `seed`."""

    if bound <= 0:
        raise TopologyError(f"cannot draw an index from an empty range (bound={bound})")
    return int(hashlib.sha256(f"{TOPOLOGY_SEED}:{seed}".encode()).hexdigest()[:16], 16) % bound


def _dedupe(edges: Sequence[tuple[int, int]]) -> Edges:
    """Drop repeated endpoint pairs, preserving first-seen order.

    Used by every shape except the one whose whole point is to repeat them.
    """

    seen: set[tuple[int, int]] = set()
    kept: list[tuple[int, int]] = []
    for edge in edges:
        if edge in seen:
            continue
        seen.add(edge)
        kept.append(edge)
    return tuple(kept)


def _hub_and_spoke(count: int) -> Edges:
    """One dominant hub, plus a handful of Beads citing it.

    Exercises the selection that is larger than any advertised page limit: the
    hub's outbound set is 380 Links, so `?source=<hub>` must paginate at both 25
    and 200, and the selected set has to stay fixed across every continuation.
    The hub is also cited, so its inbound, outbound and incident sets are three
    different sets and `endpoint` cannot be answered by reading `source`.
    """

    hub = 0
    edges = [(hub, spoke) for spoke in range(1, 381)]
    edges += [(citer, hub) for citer in range(381, 387)]
    # A quiet remainder, so the family is not only its hub.
    edges += [(node, node + 1) for node in range(400, 460, 2)]
    return _dedupe(edges)


def _sparse_authority(count: int) -> Edges:
    """A few heavily cited authorities in an otherwise sparse graph.

    Exercises high indegree against low outdegree: `?target=<authority>` spans
    pages while `?source=<authority>` fits in one, so a consumer that conflates
    the two predicates fails here and nowhere else.
    """

    edges: list[tuple[int, int]] = []
    citer = 16
    for authority, fan_in in ((0, 60), (1, 40), (2, 25)):
        for _ in range(fan_in):
            edges.append((citer, authority))
            citer += 1
    # The most-citing Bead is also the most-cited one, so the hub the manifest
    # reports has both an inbound and an outbound set.
    edges += [(0, target) for target in range(3, 16)]
    # A sparse tail, each Bead citing one of the already-linked Beads. Keeps the
    # graph from being three stars and a field of isolated nodes.
    for node in range(citer, 470):
        edges.append((node, _pick(f"sparse-tail:{node}", citer)))
    return _dedupe(edges)


def _layered_dag(count: int) -> Edges:
    """Ten layers of fifty, each Bead citing one to three in the next layer.

    Exercises an acyclic graph with a flat degree distribution: no Bead stands
    out, so every selection is small and a consumer cannot pass by special-casing
    a hub.
    """

    edges: list[tuple[int, int]] = []
    layer_size = 50
    for layer in range(9):
        for index in range(layer_size):
            source = layer * layer_size + index
            for step in range(1 + _pick(f"dag-fan:{source}", 3)):
                offset = _pick(f"dag-edge:{source}:{step}", layer_size)
                edges.append((source, (layer + 1) * layer_size + offset))
    return _dedupe(edges)


def _supersedes_chains(count: int) -> Edges:
    """Forty chains of twelve, each Bead superseding its predecessor.

    Exercises deep paths at low degree, and the root of every chain cites its own
    tip, so each chain closes into a cycle. A consumer that walks Links to build
    a reachable set must terminate. One index Bead cites every chain root, which
    gives the family a hub whose inbound and outbound sets are both non-empty
    without disturbing the chains themselves.
    """

    edges: list[tuple[int, int]] = []
    chain_length = 12
    chains = 40
    for chain in range(chains):
        root = chain * chain_length
        for step in range(chain_length - 1):
            edges.append((root + step + 1, root + step))
        edges.append((root, root + chain_length - 1))
    index = chains * chain_length
    edges += [(index, chain * chain_length) for chain in range(chains)]
    edges += [(index + 1 + offset, index) for offset in range(4)]
    return _dedupe(edges)


def _disjoint_clusters(count: int) -> Edges:
    """Twenty-five separate stars, and two hundred Beads in no Link at all.

    Exercises the empty selection and the disconnected graph. Every cluster
    centre only emits, so the hub's inbound set is empty, its incident set equals
    its outbound set, and this is the one family where `endpoint` is NOT
    discriminated from `source`. That is the point of the family rather than an
    accident of it: an authority must return an empty page with `next` null, not
    a 404, for a Bead that is a legal endpoint with no Links.
    """

    edges: list[tuple[int, int]] = []
    cluster_size = 12
    for cluster in range(25):
        centre = cluster * cluster_size
        for member in range(1, cluster_size):
            edges.append((centre, centre + member))
    return _dedupe(edges)


def _branching_with_repeated_links(count: int) -> Edges:
    """A release tree, with some adjacencies recorded by more than one Link.

    Exercises the rule that Links are first-class: BDP v0 permits several Links
    to share a `(type, source, target)` tuple and defines no uniqueness
    constraint over it, so a consumer that keys Links by their endpoints silently
    loses records here. No projected family had a single repeated tuple, so this
    shape is the only place that rule is tested.

    Deliberately NOT passed through `_dedupe`.
    """

    edges: list[tuple[int, int]] = []
    root = 0
    branches = tuple(range(1, 17))
    edges += [(root, branch) for branch in branches]
    leaf = len(branches) + 1
    first_leaf_of_second_branch = leaf + 28
    for branch in branches:
        for _ in range(28):
            edges.append((branch, leaf))
            leaf += 1
    # The repeats. Same ordered pair, and so the same (type, source, target),
    # recorded as separate Link records with distinct ids.
    edges += [(root, branches[0]), (root, branches[0])]
    edges += [(branches[1], first_leaf_of_second_branch)] * 3
    return tuple(edges)


def _cross_team_network(count: int) -> Edges:
    """A dense middle where many Beads both cite and are cited.

    Exercises `endpoint` as a genuine union: incident sets here are large and
    differ from both the inbound and the outbound set for most Beads, so the
    predicate cannot be answered by either one alone.
    """

    edges: list[tuple[int, int]] = []
    core = 150
    for node in range(core):
        for step in range(2 + _pick(f"net-fan:{node}", 5)):
            target = _pick(f"net-edge:{node}:{step}", core)
            if target != node:
                edges.append((node, target))
    for node in range(core, 430):
        edges.append((node, _pick(f"net-tail:{node}", core)))
    return _dedupe(edges)


@dataclass(frozen=True)
class Topology:
    """One family: a name, the property it exists to exercise, and its builder."""

    name: str
    exercises: str
    build: Callable[[int], Edges]
    allows_repeated_endpoint_tuples: bool = False


TOPOLOGIES: tuple[Topology, ...] = (
    Topology(
        "platform-documentation-hub-spoke",
        "a selection larger than the largest advertised page limit",
        _hub_and_spoke,
    ),
    Topology(
        "incident-runbook-sparse-authority",
        "high indegree against low outdegree, separating ?target= from ?source=",
        _sparse_authority,
    ),
    Topology(
        "data-schema-dependency-dag",
        "a flat degree distribution with no hub to special-case",
        _layered_dag,
    ),
    Topology(
        "migration-correction-temporal-chain",
        "deep paths and short cycles at low degree",
        _supersedes_chains,
    ),
    Topology(
        "distributed-system-clustered-components",
        "the empty selection, and Beads that are in no Link at all",
        _disjoint_clusters,
    ),
    Topology(
        "release-engineering-branching-playbooks",
        "several Links sharing one (type, source, target) tuple",
        _branching_with_repeated_links,
        allows_repeated_endpoint_tuples=True,
    ),
    Topology(
        "security-policy-cross-team-network",
        "incident sets that differ from both the inbound and the outbound set",
        _cross_team_network,
    ),
)

TOPOLOGIES_BY_NAME: dict[str, Topology] = {topology.name: topology for topology in TOPOLOGIES}


def build_edges(family: str, bead_count: int = BEADS_PER_FAMILY) -> Edges:
    """The edge list for one family, validated against the shape's own contract.

    Every check here is a build failure rather than a test, because a shape that
    silently stops exercising its property still emits a tree that looks fine.
    """

    if family not in TOPOLOGIES_BY_NAME:
        raise TopologyError(f"unknown topology: {family}")
    topology = TOPOLOGIES_BY_NAME[family]
    edges = topology.build(bead_count)
    if not edges:
        raise TopologyError(f"{family} generated no edges")
    for source, target in edges:
        if not 0 <= source < bead_count or not 0 <= target < bead_count:
            raise TopologyError(
                f"{family} generated an edge ({source}, {target}) outside "
                f"[0, {bead_count}); the shape and the Bead count disagree"
            )
        if source == target:
            raise TopologyError(f"{family} generated a self-Link at node {source}")
    repeated = len(edges) - len(set(edges))
    if repeated and not topology.allows_repeated_endpoint_tuples:
        raise TopologyError(
            f"{family} repeats {repeated} endpoint pairs but does not declare "
            "allows_repeated_endpoint_tuples; a repeat here is a generator bug, and it would "
            "be published as a conformance case nobody chose"
        )
    if topology.allows_repeated_endpoint_tuples and not repeated:
        raise TopologyError(
            f"{family} declares repeated endpoint tuples but generated none, so the only "
            "family covering that BDP rule would not cover it"
        )
    return edges
