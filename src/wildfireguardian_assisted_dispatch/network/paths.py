"""Simple-path enumeration.

Used by the exact interval solver, which needs the finite set of combinatorial
plans rather than a search over timed states.

Note for auditors: :mod:`...validation.brute_force` deliberately carries its
*own* private copy of this algorithm.  The duplication is intentional — a
reference oracle that shares its path enumeration with the solver it is meant
to check is not an independent check of path enumeration.
"""

from __future__ import annotations

from .graph import RoadNetwork


class PathEnumerationLimit(RuntimeError):
    """The number of simple paths exceeded the stated cap.

    Raised rather than truncated: a partial plan set would silently shrink the
    computed feasible set, which is the same class of silent failure as a
    truncated state search.
    """


def simple_paths(network: RoadNetwork, source: str, target: str, *,
                 max_paths: int = 5000) -> list[tuple[str, ...]]:
    """Every simple path ``source -> target``, as tuples of edge ids.

    Deterministic: edges are expanded in sorted id order, so the returned list
    is stable across runs.
    """
    if source not in network.nodes:
        raise KeyError(f"unknown node {source!r}")
    if target not in network.nodes:
        raise KeyError(f"unknown node {target!r}")

    found: list[tuple[str, ...]] = []
    stack: list[tuple[str, frozenset[str], tuple[str, ...]]] = [
        (source, frozenset((source,)), ())
    ]
    while stack:
        node, visited, edges = stack.pop()
        if node == target:
            found.append(edges)
            if len(found) > max_paths:
                raise PathEnumerationLimit(
                    f"more than {max_paths} simple paths from {source!r} to "
                    f"{target!r}; refusing to truncate the plan set"
                )
            continue
        for edge in reversed(network.out_edges(node)):
            if edge.head in visited:
                continue
            stack.append((edge.head, visited | {edge.head}, edges + (edge.id,)))
    return found


__all__ = ["simple_paths", "PathEnumerationLimit"]
