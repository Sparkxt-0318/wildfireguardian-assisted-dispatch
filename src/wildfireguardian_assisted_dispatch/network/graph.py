"""Synthetic directed road networks.

The graph is deliberately tiny and explicit.  Every fixture in this project is
meant to be re-derivable with pen and paper, so the data model avoids anything
that would make a traversal hard to audit: no geometry, no turn restrictions,
no capacities, no speed profiles.

Directionality
--------------
Edges are directed.  A two-way road is two directed edges that share a
``corridor`` identifier.  The corridor is the unit that hazards act on by
default, which is what makes fixture C (inbound vs. outbound conflict) work:
when the responder drives out along a corridor and back in along the same
corridor, both traversals consult the same hazard timeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Iterator, Mapping


class NodeKind(str, Enum):
    """What a node represents.  Purely descriptive: the mission spec decides
    which node is the base / resident / destination."""

    JUNCTION = "junction"
    BASE = "base"
    RESIDENCE = "residence"
    DESTINATION = "destination"
    REFUGE = "refuge"


@dataclass(frozen=True)
class Node:
    id: str
    kind: NodeKind = NodeKind.JUNCTION
    label: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Node.id must be a non-empty string")


@dataclass(frozen=True)
class Edge:
    """A directed road segment with a constant free-flow traversal time.

    ``travel_time`` is in minutes (see :mod:`..units`).  It must be strictly
    positive: zero-length edges would let the search loop forever without time
    advancing, and would also make "no implicit waiting" unverifiable.
    """

    id: str
    tail: str
    head: str
    travel_time: float
    corridor: str = ""
    label: str = ""

    def __post_init__(self) -> None:
        if self.travel_time <= 0:
            raise ValueError(
                f"edge {self.id!r}: travel_time must be > 0, got {self.travel_time!r}"
            )
        if self.tail == self.head:
            raise ValueError(f"edge {self.id!r}: self-loops are not allowed")
        if not self.corridor:
            object.__setattr__(self, "corridor", corridor_id(self.tail, self.head))


def corridor_id(u: str, v: str) -> str:
    """Undirected identity of the road joining ``u`` and ``v``."""
    a, b = sorted((u, v))
    return f"{a}--{b}"


def edge_id(u: str, v: str) -> str:
    """Directed identity of the edge from ``u`` to ``v``."""
    return f"{u}->{v}"


class RoadNetwork:
    """A directed multigraph of synthetic roads.

    Construction is imperative and validating; a malformed network raises at
    build time rather than producing a silently unreachable mission.
    """

    def __init__(self, name: str = "unnamed") -> None:
        self.name = name
        self._nodes: dict[str, Node] = {}
        self._edges: dict[str, Edge] = {}
        self._out: dict[str, list[str]] = {}
        self._in: dict[str, list[str]] = {}

    # -- construction -------------------------------------------------------
    def add_node(self, node_id: str, kind: NodeKind | str = NodeKind.JUNCTION,
                 label: str = "") -> Node:
        if node_id in self._nodes:
            raise ValueError(f"duplicate node id {node_id!r}")
        node = Node(id=node_id, kind=NodeKind(kind), label=label)
        self._nodes[node_id] = node
        self._out[node_id] = []
        self._in[node_id] = []
        return node

    def ensure_node(self, node_id: str, kind: NodeKind | str = NodeKind.JUNCTION) -> Node:
        if node_id not in self._nodes:
            return self.add_node(node_id, kind)
        return self._nodes[node_id]

    def add_edge(self, tail: str, head: str, travel_time: float, *,
                 corridor: str | None = None, label: str = "",
                 id: str | None = None) -> Edge:
        for n in (tail, head):
            if n not in self._nodes:
                raise KeyError(f"unknown node {n!r}; add it before its edges")
        eid = id or edge_id(tail, head)
        if eid in self._edges:
            raise ValueError(f"duplicate edge id {eid!r}")
        edge = Edge(
            id=eid,
            tail=tail,
            head=head,
            travel_time=float(travel_time),
            corridor=corridor or corridor_id(tail, head),
            label=label,
        )
        self._edges[eid] = edge
        self._out[tail].append(eid)
        self._in[head].append(eid)
        return edge

    def add_road(self, u: str, v: str, travel_time: float, *,
                 oneway: bool = False, corridor: str | None = None,
                 label: str = "") -> tuple[Edge, ...]:
        """Add a road.  Two-way by default; both directions share a corridor."""
        cid = corridor or corridor_id(u, v)
        forward = self.add_edge(u, v, travel_time, corridor=cid, label=label)
        if oneway:
            return (forward,)
        backward = self.add_edge(v, u, travel_time, corridor=cid, label=label)
        return (forward, backward)

    # -- access -------------------------------------------------------------
    @property
    def nodes(self) -> Mapping[str, Node]:
        return self._nodes

    @property
    def edges(self) -> Mapping[str, Edge]:
        return self._edges

    def node(self, node_id: str) -> Node:
        try:
            return self._nodes[node_id]
        except KeyError as exc:  # pragma: no cover - defensive
            raise KeyError(f"unknown node {node_id!r}") from exc

    def edge(self, eid: str) -> Edge:
        try:
            return self._edges[eid]
        except KeyError as exc:  # pragma: no cover - defensive
            raise KeyError(f"unknown edge {eid!r}") from exc

    def out_edges(self, node_id: str) -> tuple[Edge, ...]:
        """Outgoing edges, in a deterministic (id-sorted) order.

        Determinism matters: two runs of the same scenario must produce byte
        identical mission logs, otherwise validation fixtures are worthless.
        """
        return tuple(self._edges[e] for e in sorted(self._out.get(node_id, ())))

    def in_edges(self, node_id: str) -> tuple[Edge, ...]:
        return tuple(self._edges[e] for e in sorted(self._in.get(node_id, ())))

    def corridors(self) -> set[str]:
        return {e.corridor for e in self._edges.values()}

    def edges_of_corridor(self, corridor: str) -> tuple[Edge, ...]:
        return tuple(e for e in self._edges.values() if e.corridor == corridor)

    def __iter__(self) -> Iterator[Node]:
        return iter(self._nodes.values())

    def __len__(self) -> int:
        return len(self._nodes)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (f"RoadNetwork(name={self.name!r}, nodes={len(self._nodes)}, "
                f"edges={len(self._edges)})")

    # -- validation ---------------------------------------------------------
    def validate(self, required_nodes: Iterable[str] = ()) -> None:
        for n in required_nodes:
            if n not in self._nodes:
                raise KeyError(f"network {self.name!r} is missing required node {n!r}")
        for edge in self._edges.values():
            if edge.tail not in self._nodes or edge.head not in self._nodes:
                raise ValueError(f"edge {edge.id!r} references an unknown node")


__all__ = ["Node", "NodeKind", "Edge", "RoadNetwork", "corridor_id", "edge_id"]
