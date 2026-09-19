"""Time-expanded state search over a hazard-constrained road network.

Why not Dijkstra
----------------
Earliest arrival is **not** a dominant label here.  A hazard timeline may
*reopen* a corridor: arriving at a junction at t = 9 can strand you, while
arriving at t = 19 lets you take a road that reopened at t = 18.  Under the
no-waiting rule the planner cannot convert an early arrival into a late one, so
an earlier label does not dominate a later one and the usual "settle each node
once" argument collapses.

So the search is a complete enumeration over *time-expanded states* ``(node,
arrival time)``.  Every state is expanded at most once; travel times are
strictly positive, so the clock advances on every expansion and the horizon
makes the reachable state set finite even in a cyclic network.  Small synthetic
fixtures are the whole point of this phase, and completeness is worth much more
here than asymptotics.

The search never inserts idle time.  A state's time is the exact sum of the
start time and the traversal durations behind it, which is what makes the
no-implicit-waiting invariant checkable after the fact.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Sequence

from ..hazards.scenario import HazardScenario
from ..hazards.semantics import (
    ElementAssessment,
    TraversalAdmission,
    admits,
    assess_edge_traversal,
    assess_node_occupancy,
)
from ..missions.result import Traversal
from ..network.graph import RoadNetwork
from ..network.travel import TravelModel
from ..units import gt, quantize


class SearchBudgetExceeded(RuntimeError):
    """The state search hit ``max_states``.

    Raised rather than swallowed: a truncated search would report a mission as
    infeasible when it merely ran out of budget, which is the single most
    dangerous silent failure this package could have.
    """


@dataclass(frozen=True)
class Arrival:
    """A reachable ``(node, time)`` state and the chain that produced it."""

    node: str
    time: float
    traversals: tuple[Traversal, ...]

    @property
    def sort_key(self) -> tuple[float, int, tuple[str, ...]]:
        return (self.time, len(self.traversals),
                tuple(t.edge_id for t in self.traversals))

    @property
    def is_safe(self) -> bool:
        """True iff every traversal behind this state is safe over its whole
        occupancy interval (can be False only under ENTRY_ONLY admission)."""
        return all(t.safe_throughout for t in self.traversals)


@dataclass
class Exploration:
    """Everything reachable from one origin at one start time."""

    origin: str
    start_time: float
    arrivals: dict[str, list[Arrival]] = field(default_factory=dict)
    blocked: list[ElementAssessment] = field(default_factory=list)
    states_expanded: int = 0
    horizon_hit: bool = False
    origin_blocked: ElementAssessment | None = None

    def at(self, node: str) -> list[Arrival]:
        """Arrivals at ``node``, ascending by time then by path."""
        return self.arrivals.get(node, [])

    def earliest(self, node: str) -> Arrival | None:
        options = self.at(node)
        return options[0] if options else None

    def reached(self, node: str) -> bool:
        return bool(self.arrivals.get(node))

    def blocking_conflicts(self) -> list[ElementAssessment]:
        """Blocked assessments, most informative first.

        A near miss outranks a hopeless one: an element that was safe when the
        responder arrived and then ran out of time ("you were ninety seconds
        late") explains a routing failure far better than an element that had
        already burned an hour earlier.  Within each class, the *earliest*
        conflict wins, so the quoted reason is the first thing that went wrong
        rather than whatever the search happened to try last while circling the
        network.
        """
        return sorted(
            self.blocked,
            key=lambda a: (0 if a.safe_at_entry else 1, a.entry_time, a.element_id),
        )


def explore(
    network: RoadNetwork,
    travel: TravelModel,
    scenario: HazardScenario,
    origin: str,
    start_time: float,
    *,
    admission: TraversalAdmission = TraversalAdmission.FULL_INTERVAL,
    horizon: float,
    max_states: int = 200_000,
    allow_node_revisits: bool = False,
) -> Exploration:
    """Enumerate every ``(node, time)`` state reachable from ``origin``.

    The enumeration is complete by design: there is no goal-directed early
    exit, because a later arrival at the goal can be the only feasible one and
    stopping at the first would quietly turn a feasible mission into an
    infeasible one.

    ``allow_node_revisits=False`` (the default) restricts each leg to a simple
    path.  That is a modelling decision about waiting, not an optimisation: see
    :attr:`..missions.policy.MissionPolicy.allow_node_revisits`.
    """
    result = Exploration(origin=origin, start_time=start_time)

    origin_ok = assess_node_occupancy(origin, start_time, start_time, scenario)
    if not origin_ok.safe_throughout:
        result.origin_blocked = origin_ok
        result.blocked.append(origin_ok)
        return result

    start = Arrival(node=origin, time=start_time, traversals=())
    result.arrivals[origin] = [start]

    def visited_nodes(arrival: Arrival) -> frozenset[str]:
        return frozenset((origin,) + tuple(t.head for t in arrival.traversals))

    def dedup_key(node: str, time: float, arrival: Arrival):
        # With revisits prohibited, two chains reaching the same node at the
        # same instant are NOT interchangeable: they may have burned different
        # nodes and so admit different continuations.  The visited set is part
        # of the state.
        if allow_node_revisits:
            return (node, quantize(time))
        return (node, quantize(time), visited_nodes(arrival))

    counter = 0  # tie-breaker keeping heap order total and deterministic
    queue: list[tuple[float, int, int, Arrival]] = [(start_time, 0, counter, start)]
    visited: set = {dedup_key(origin, start_time, start)}

    while queue:
        _, _, _, state = heapq.heappop(queue)
        result.states_expanded += 1
        if result.states_expanded > max_states:
            raise SearchBudgetExceeded(
                f"state search from {origin!r} at t={start_time:g} exceeded "
                f"max_states={max_states}; the result would be an unreliable "
                "'infeasible'. Shrink the horizon or raise the budget."
            )

        state_nodes = None if allow_node_revisits else visited_nodes(state)
        for edge in network.out_edges(state.node):
            if state_nodes is not None and edge.head in state_nodes:
                continue
            duration = travel.duration(edge, state.time)
            exit_time = state.time + duration
            if gt(exit_time, horizon):
                result.horizon_hit = True
                continue

            edge_assessment = assess_edge_traversal(edge, state.time, exit_time, scenario)
            if not admits(edge_assessment, admission):
                result.blocked.append(edge_assessment)
                continue

            # Passing through a junction is instantaneous, but it still has to
            # be a place that exists at that instant.
            head_assessment = assess_node_occupancy(edge.head, exit_time, exit_time,
                                                    scenario)
            if not head_assessment.safe_throughout:
                result.blocked.append(head_assessment)
                continue

            traversal = Traversal(
                edge_id=edge.id,
                tail=edge.tail,
                head=edge.head,
                entry_time=state.time,
                exit_time=exit_time,
                safe_throughout=edge_assessment.safe_throughout,
                safety_lost_at=edge_assessment.safety_lost_at,
                margin=edge_assessment.margin,
            )
            nxt = Arrival(node=edge.head, time=exit_time,
                          traversals=state.traversals + (traversal,))
            key = dedup_key(edge.head, exit_time, nxt)
            if key in visited:
                continue
            visited.add(key)
            result.arrivals.setdefault(edge.head, []).append(nxt)
            counter += 1
            heapq.heappush(queue, (exit_time, len(nxt.traversals), counter, nxt))

    for node in result.arrivals:
        result.arrivals[node].sort(key=lambda a: a.sort_key)
    return result


def distinct_arrival_times(arrivals: Sequence[Arrival]) -> list[Arrival]:
    """One representative arrival per distinct time, ascending.

    Two chains that reach the same node at the same instant are
    interchangeable for everything downstream, so the mission evaluator only
    needs one of them — but it needs *all distinct times*, because later is not
    worse in general.
    """
    seen: set[float] = set()
    out: list[Arrival] = []
    for arrival in sorted(arrivals, key=lambda a: a.sort_key):
        q = quantize(arrival.time)
        if q in seen:
            continue
        seen.add(q)
        out.append(arrival)
    return out


__all__ = [
    "Arrival",
    "Exploration",
    "SearchBudgetExceeded",
    "explore",
    "distinct_arrival_times",
]
