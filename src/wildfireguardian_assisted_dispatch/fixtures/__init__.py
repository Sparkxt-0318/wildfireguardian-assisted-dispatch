"""Synthetic fixtures A-G, each with a hand calculation attached.

These are the validation instrument for the whole project.  They are small
enough to check with a pencil, and every one of them exists to pin down one
specific piece of semantics:

======  ===========================================================
key     what it pins down
======  ===========================================================
a       the basic deadline arithmetic
b       feasibility governed by the surviving route, not the fast one
b_ens   P_success as a sum over coherent scenarios
c       a corridor used in reverse; the outbound traversal binds
d       pickup duration comes straight off the dispatch envelope
e       a temporary refuge only counts if it holds
f       feasibility is not monotone in dispatch time
g       a segment that cannot be cleared is never entered
g_my    what entry-time-only hazard checking actually costs
======  ===========================================================
"""

from __future__ import annotations

from typing import Callable, Mapping

from . import (
    corridor_conflict,
    mid_edge_closure,
    non_monotonic,
    pickup_sensitivity,
    single_road,
    temporary_refuge,
    two_routes,
)
from .base import Fixture

#: Fixture key -> builder.  Keys are stable; the CLI and the tests both use them.
FIXTURES: Mapping[str, Callable[[], Fixture]] = {
    "a": single_road.build,
    "b": two_routes.build,
    "b_ensemble": two_routes.build_ensemble,
    "c": corridor_conflict.build,
    "d": pickup_sensitivity.build,
    "e": temporary_refuge.build,
    "f": non_monotonic.build,
    "g": mid_edge_closure.build,
    "g_myopic": mid_edge_closure.build_myopic,
}


def load(key: str) -> Fixture:
    """Build the fixture registered under ``key`` (case-insensitive)."""
    try:
        builder = FIXTURES[key.strip().lower()]
    except KeyError as exc:
        raise KeyError(
            f"unknown fixture {key!r}; known fixtures: {', '.join(FIXTURES)}"
        ) from exc
    return builder()


def all_fixtures() -> tuple[Fixture, ...]:
    return tuple(builder() for builder in FIXTURES.values())


__all__ = [
    "Fixture",
    "FIXTURES",
    "load",
    "all_fixtures",
    "single_road",
    "two_routes",
    "corridor_conflict",
    "pickup_sensitivity",
    "temporary_refuge",
    "non_monotonic",
    "mid_edge_closure",
]
