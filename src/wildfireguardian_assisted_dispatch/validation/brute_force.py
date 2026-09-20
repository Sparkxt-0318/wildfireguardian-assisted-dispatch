"""An independent, deliberately slow reference evaluator.

Purpose
-------
The main solver's 153 tests can only tell us that the main solver is
self-consistent. This module exists so that the fixtures can be checked against
a *second* implementation that shares as little mission logic as practical with
the first.

What is shared, and what is not
-------------------------------
Shared (unavoidable — these are the problem statement, not the solution):
:class:`RoadNetwork`, :class:`Timeline`, :class:`HazardScenario`,
:class:`MissionSpec`.

**Not** shared: path finding, state search, time bookkeeping, hazard
assessment, plan selection, failure classification. This module enumerates
simple paths with a naive recursive DFS, adds up travel times by hand, and
decides safety by scanning a timeline's raw window tuples with explicit
comparisons. It never calls ``explore``, ``assess_edge_traversal``,
``assess_node_occupancy``, ``admits``, or ``evaluate_mission``.

It is exponential in the network size and is only ever run on the tiny
synthetic fixtures, which is exactly what a reference oracle is for.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..hazards.scenario import HazardScenario
from ..hazards.semantics import TraversalAdmission
from ..hazards.timeline import Timeline
from ..missions.spec import MissionSpec
from ..network.graph import RoadNetwork
from ..units import EPS


class BruteForceLimit(RuntimeError):
    """The reference enumeration exceeded its own guard rails."""


# ---------------------------------------------------------------------------
# Independent primitives.  These deliberately re-derive what the main package
# already knows how to do, using nothing but raw window tuples and arithmetic.
# ---------------------------------------------------------------------------

def _open_at(timeline: Timeline, t: float) -> bool:
    """Is the element safe at the instant ``t``?  (closed-window convention)"""
    for window in timeline.windows:
        if window.start - EPS <= t <= window.end + EPS:
            return True
    return False


def _open_throughout(timeline: Timeline, a: float, b: float) -> bool:
    """Is the element safe at every instant of the closed interval [a, b]?"""
    for window in timeline.windows:
        if window.start - EPS <= a and b <= window.end + EPS:
            return True
    return False


def _simple_paths(network: RoadNetwork, source: str, target: str,
                  max_paths: int) -> list[tuple[str, ...]]:
    """Every simple path source -> target, as tuples of edge ids (naive DFS)."""
    found: list[tuple[str, ...]] = []

    def walk(node: str, visited: tuple[str, ...], edges: tuple[str, ...]) -> None:
        if len(found) > max_paths:
            raise BruteForceLimit(
                f"more than {max_paths} simple paths from {source!r} to "
                f"{target!r}; the reference oracle is only meant for tiny graphs"
            )
        if node == target:
            found.append(edges)
            return
        for edge in network.out_edges(node):
            if edge.head in visited:
                continue
            walk(edge.head, visited + (edge.head,), edges + (edge.id,))

    walk(source, (source,), ())
    return found


@dataclass(frozen=True)
class ReferencePlan:
    """One fully-specified candidate mission, timed out by hand."""

    ingress_edges: tuple[str, ...]
    egress_edges: tuple[str, ...]
    destination: str
    resident_arrival: float
    pickup_start: float
    pickup_end: float
    destination_arrival: float
    entry_admissible: bool
    fully_safe: bool
    first_unsafe_edge: str | None
    first_unsafe_instant: float | None

    @property
    def sort_key(self) -> tuple:
        return (self.destination_arrival, self.destination,
                self.ingress_edges, self.egress_edges)


@dataclass(frozen=True)
class ReferenceOutcome:
    """What the reference oracle concluded at one dispatch time."""

    dispatch_time: float
    scenario: str
    success: bool
    chosen: ReferencePlan | None
    plans_considered: int
    safe_plans: int

    @property
    def destination_arrival(self) -> float | None:
        if self.chosen is None or not self.success:
            return None
        return self.chosen.destination_arrival


def enumerate_plans(spec: MissionSpec, dispatch_time: float,
                    scenario: HazardScenario, *,
                    max_paths: int = 2000) -> list[ReferencePlan]:
    """Every simple-path plan, timed and classified, with no search at all."""
    plans: list[ReferencePlan] = []
    horizon = spec.policy.horizon

    ingress_paths = _simple_paths(spec.network, spec.base, spec.resident, max_paths)
    for ingress in ingress_paths:
        # -- time the ingress leg by hand ----------------------------------
        clock = dispatch_time
        ingress_safe = _open_at(scenario.node_timeline(spec.base), dispatch_time)
        ingress_entry_ok = ingress_safe
        first_bad_edge: str | None = None
        first_bad_time: float | None = None
        over_horizon = False
        for edge_id in ingress:
            edge = spec.network.edge(edge_id)
            entry, exit_ = clock, clock + edge.travel_time
            if exit_ > horizon + EPS:
                over_horizon = True
            timeline = scenario.edge_timeline(edge)
            if not _open_at(timeline, entry):
                ingress_entry_ok = False
            if ingress_safe and not _open_throughout(timeline, entry, exit_):
                ingress_safe = False
                first_bad_edge = edge_id
                first_bad_time = _loss_instant(timeline, entry)
            if not _open_at(scenario.node_timeline(edge.head), exit_):
                ingress_safe = False
                ingress_entry_ok = False
            clock = exit_
        arrival = clock

        pickup_start = arrival
        pickup_end = arrival + spec.pickup.duration
        service_ok = _open_throughout(scenario.node_timeline(spec.resident),
                                      pickup_start, pickup_end)
        if pickup_end > horizon + EPS:
            over_horizon = True

        for destination in spec.destinations:
            for egress in _simple_paths(spec.network, spec.resident,
                                        destination.node, max_paths):
                clock = pickup_end
                egress_safe = True
                egress_entry_ok = True
                bad_edge, bad_time = first_bad_edge, first_bad_time
                leg_over_horizon = over_horizon
                for edge_id in egress:
                    edge = spec.network.edge(edge_id)
                    entry, exit_ = clock, clock + edge.travel_time
                    if exit_ > horizon + EPS:
                        leg_over_horizon = True
                    timeline = scenario.edge_timeline(edge)
                    if not _open_at(timeline, entry):
                        egress_entry_ok = False
                    if egress_safe and not _open_throughout(timeline, entry, exit_):
                        egress_safe = False
                        if bad_edge is None:
                            bad_edge = edge_id
                            bad_time = _loss_instant(timeline, entry)
                    if not _open_at(scenario.node_timeline(edge.head), exit_):
                        egress_safe = False
                        egress_entry_ok = False
                    clock = exit_
                landing = clock

                accepted = (destination.available_from - EPS <= landing
                            <= destination.available_until + EPS)
                dwell_ok = _open_throughout(
                    scenario.node_timeline(destination.node), landing,
                    landing + destination.min_safe_dwell)

                plans.append(ReferencePlan(
                    ingress_edges=ingress,
                    egress_edges=egress,
                    destination=destination.node,
                    resident_arrival=arrival,
                    pickup_start=pickup_start,
                    pickup_end=pickup_end,
                    destination_arrival=landing,
                    entry_admissible=(ingress_entry_ok and egress_entry_ok
                                      and service_ok and accepted and dwell_ok
                                      and not leg_over_horizon),
                    fully_safe=(ingress_safe and egress_safe and service_ok
                                and accepted and dwell_ok
                                and not leg_over_horizon),
                    first_unsafe_edge=bad_edge,
                    first_unsafe_instant=bad_time,
                ))
    return plans


def _loss_instant(timeline: Timeline, entry: float) -> float | None:
    """Last safe instant of the window containing ``entry``, scanned by hand."""
    for window in timeline.windows:
        if window.start - EPS <= entry <= window.end + EPS:
            return window.end
    return entry


def reference_success(spec: MissionSpec, dispatch_time: float,
                      scenario: HazardScenario, *,
                      max_paths: int = 2000) -> ReferenceOutcome:
    """Decide mission feasibility by exhaustive plan enumeration.

    Under ``FULL_INTERVAL`` admission the rule is simply *does a fully safe plan
    exist*.  Under ``ENTRY_ONLY`` the rule is the myopic one: take the
    entry-admissible plan with the earliest arrival, then audit it honestly —
    which is stated here in four lines rather than reproduced from the main
    evaluator.
    """
    plans = enumerate_plans(spec, dispatch_time, scenario, max_paths=max_paths)
    safe = [p for p in plans if p.fully_safe]

    if spec.policy.admission is TraversalAdmission.FULL_INTERVAL:
        chosen = min(safe, key=lambda p: p.sort_key) if safe else None
        return ReferenceOutcome(dispatch_time, scenario.name, bool(safe), chosen,
                                len(plans), len(safe))

    admitted = [p for p in plans if p.entry_admissible]
    chosen = min(admitted, key=lambda p: p.sort_key) if admitted else None
    success = chosen is not None and chosen.fully_safe
    return ReferenceOutcome(dispatch_time, scenario.name, success, chosen,
                            len(plans), len(safe))


def reference_p_success(spec: MissionSpec, dispatch_time: float,
                        ensemble) -> float:
    """``P_success`` by reference evaluation: a weighted count, nothing else."""
    total = 0.0
    for scenario in ensemble:
        if reference_success(spec, dispatch_time, scenario).success:
            total += scenario.weight
    return total


def reference_feasible_flags(spec: MissionSpec, ensemble,
                             grid: Sequence[float],
                             threshold: float = 1.0) -> tuple[bool, ...]:
    """Feasibility flags over a dispatch grid, computed by brute force."""
    return tuple(
        reference_p_success(spec, float(t), ensemble) >= threshold - EPS
        for t in grid
    )


__all__ = [
    "BruteForceLimit",
    "ReferencePlan",
    "ReferenceOutcome",
    "enumerate_plans",
    "reference_success",
    "reference_p_success",
    "reference_feasible_flags",
]
