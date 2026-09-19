"""Turning reachable states into mission legs.

Thin by design: all the hazard logic lives in :mod:`..hazards.semantics` and all
the enumeration in :mod:`.time_expanded`.  This module only shapes results.
"""

from __future__ import annotations

from typing import Sequence

from ..hazards.scenario import HazardScenario
from ..missions.result import Route
from ..network.graph import RoadNetwork
from ..network.travel import TravelModel
from ..hazards.semantics import TraversalAdmission
from .time_expanded import Arrival, Exploration, distinct_arrival_times, explore


def route_from_arrival(origin: str, start_time: float, arrival: Arrival) -> Route:
    """Materialise the chain behind ``arrival`` as a :class:`Route`."""
    return Route(
        origin=origin,
        terminus=arrival.node,
        start_time=start_time,
        end_time=arrival.time,
        traversals=arrival.traversals,
    )


def leg_options(
    network: RoadNetwork,
    travel: TravelModel,
    scenario: HazardScenario,
    origin: str,
    start_time: float,
    *,
    admission: TraversalAdmission,
    horizon: float,
    max_states: int,
) -> Exploration:
    """Run one leg's state search."""
    return explore(
        network, travel, scenario, origin, start_time,
        admission=admission, horizon=horizon, max_states=max_states,
    )


def arrivals_at(exploration: Exploration, node: str) -> list[Arrival]:
    """Distinct arrival times at ``node``, ascending.

    All of them, not just the earliest: with reopening corridors an earlier
    arrival does not dominate a later one.
    """
    return distinct_arrival_times(exploration.at(node))


def best_arrival(arrivals: Sequence[Arrival]) -> Arrival | None:
    return min(arrivals, key=lambda a: a.sort_key) if arrivals else None


__all__ = ["route_from_arrival", "leg_options", "arrivals_at", "best_arrival"]
