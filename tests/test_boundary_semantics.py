"""Exact-equality boundary cases.

The convention (docs/TIME_SEMANTICS.md, D-002) is that hazard windows are
**closed**: ``closes_at(T)`` means the element is safe at exactly ``T`` and
unsafe for every instant after.  That single choice decides every case below,
and each case is checked against the main evaluator *and* the independent
brute-force oracle, so a convention implemented inconsistently in the two
places cannot pass.

None of these expectations were chosen because they made a test pass.  They
are all derived from the one stated convention, and the consequences - some of
them uncomfortable, such as a mission "succeeding" with exactly zero margin -
are recorded rather than smoothed away.
"""

from __future__ import annotations

import pytest

from wildfireguardian_assisted_dispatch.feasibility.exact import exact_feasible_set
from wildfireguardian_assisted_dispatch.hazards.scenario import (
    HazardScenario,
    ScenarioEnsemble,
)
from wildfireguardian_assisted_dispatch.hazards.semantics import (
    TraversalAdmission,
    Verdict,
    assess_edge_traversal,
)
from wildfireguardian_assisted_dispatch.hazards.timeline import Timeline
from wildfireguardian_assisted_dispatch.missions.evaluator import evaluate_mission
from wildfireguardian_assisted_dispatch.missions.policy import MissionPolicy
from wildfireguardian_assisted_dispatch.missions.result import FailureReason
from wildfireguardian_assisted_dispatch.missions.spec import Destination, MissionSpec
from wildfireguardian_assisted_dispatch.network.graph import NodeKind, RoadNetwork
from wildfireguardian_assisted_dispatch.service.pickup import PickupModel
from wildfireguardian_assisted_dispatch.validation.brute_force import reference_success

# base --10-- home --10-- shelter;  dispatch at t = 0 gives
#   ingress [0, 10], pickup [10, 10+p], egress [10+p, 20+p]
INGRESS = 10.0
EGRESS = 10.0


def chain(pickup: float = 5.0, *, dwell: float = 0.0,
          available_from: float = 0.0,
          available_until: float = float("inf"),
          admission: TraversalAdmission = TraversalAdmission.FULL_INTERVAL,
          extra_route: bool = False) -> MissionSpec:
    n = RoadNetwork("boundary")
    n.add_node("base", NodeKind.BASE)
    n.add_node("home", NodeKind.RESIDENCE)
    n.add_node("shelter", NodeKind.DESTINATION)
    n.add_road("base", "home", INGRESS, corridor="in")
    n.add_road("home", "shelter", EGRESS, corridor="out")
    if extra_route:
        n.add_node("long", NodeKind.JUNCTION)
        n.add_road("home", "long", 12.0, corridor="long_a")
        n.add_road("long", "shelter", 12.0, corridor="long_b")
    return MissionSpec(
        network=n, base="base", resident="home",
        destinations=(Destination("shelter", min_safe_dwell=dwell,
                                  available_from=available_from,
                                  available_until=available_until),),
        pickup=PickupModel(pickup, "boundary"),
        policy=MissionPolicy(admission=admission, horizon=200.0),
        name="boundary",
    )


def both_solvers(spec: MissionSpec, scenario: HazardScenario,
                 t: float = 0.0) -> tuple[bool, bool]:
    """(main solver, independent reference oracle)."""
    return (evaluate_mission(spec, t, scenario).mission_success,
            reference_success(spec, t, scenario).success)


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------

def test_edge_safety_lost_exactly_at_the_exit_instant_is_safe():
    """Clearing a segment at the very instant it closes counts as clearing it."""
    spec = chain()
    # egress occupies [15, 25]; the corridor's last safe instant is 25.
    scenario = HazardScenario("m", edges={"out": Timeline.closes_at(25.0)})
    result = evaluate_mission(spec, 0.0, scenario)
    assert result.mission_success
    assert result.egress_route.traversals[-1].margin == 0.0
    assert both_solvers(spec, scenario) == (True, True)


def test_one_epsilon_earlier_closure_is_not_safe():
    """...and the neighbouring case fails, so the convention is doing work."""
    spec = chain()
    scenario = HazardScenario("m", edges={"out": Timeline.closes_at(24.999)})
    assert both_solvers(spec, scenario) == (False, False)


def test_edge_safety_lost_exactly_at_the_entry_instant():
    """Safe at entry, unsafe one instant later: a catch, not a clean block."""
    spec = chain()
    scenario = HazardScenario("m", edges={"out": Timeline.closes_at(15.0)})
    edge = spec.network.edge("home->shelter")

    assessment = assess_edge_traversal(edge, 15.0, 25.0, scenario)
    assert assessment.safe_at_entry          # closed windows include the end
    assert not assessment.safe_throughout
    assert assessment.safety_lost_at == 15.0
    assert assessment.verdict is Verdict.CAUGHT_MID_EDGE

    # Under the default policy the segment is simply never entered.
    result = evaluate_mission(spec, 0.0, scenario)
    assert not result.mission_success
    assert result.failure_reason is FailureReason.NO_SAFE_ROUTE_EGRESS
    assert both_solvers(spec, scenario) == (False, False)


def test_a_myopic_planner_is_caught_at_the_entry_instant_itself():
    """The degenerate catch: zero progress made before safety is lost."""
    spec = chain(admission=TraversalAdmission.ENTRY_ONLY)
    scenario = HazardScenario("m", edges={"out": Timeline.closes_at(15.0)})
    result = evaluate_mission(spec, 0.0, scenario)
    assert result.failure_reason is FailureReason.CAUGHT_MID_EDGE
    aborted = [e for e in result.log if e.kind == "travel_aborted"]
    assert (aborted[0].start_time, aborted[0].end_time) == (15.0, 15.0)
    assert both_solvers(spec, scenario) == (False, False)


def test_a_corridor_reopening_exactly_at_the_entry_instant_is_usable():
    spec = chain()
    scenario = HazardScenario("m", edges={"out": Timeline.opens_at(15.0)})
    assert both_solvers(spec, scenario) == (True, True)


def test_a_corridor_reopening_one_epsilon_late_is_not():
    spec = chain()
    scenario = HazardScenario("m", edges={"out": Timeline.opens_at(15.001)})
    assert both_solvers(spec, scenario) == (False, False)


def test_a_window_exactly_as_long_as_the_traversal_is_usable():
    spec = chain()
    scenario = HazardScenario(
        "m", edges={"out": Timeline.from_windows([[15.0, 25.0]])})
    assert both_solvers(spec, scenario) == (True, True)


def test_a_window_one_epsilon_too_short_is_not():
    spec = chain()
    scenario = HazardScenario(
        "m", edges={"out": Timeline.from_windows([[15.0, 24.999]])})
    assert both_solvers(spec, scenario) == (False, False)


def test_a_degenerate_window_cannot_carry_a_positive_duration_traversal():
    spec = chain()
    scenario = HazardScenario(
        "m", edges={"out": Timeline.from_windows([[15.0, 15.0]])})
    assert both_solvers(spec, scenario) == (False, False)


# ---------------------------------------------------------------------------
# The service window
# ---------------------------------------------------------------------------

def test_pickup_completing_exactly_as_the_address_is_lost_is_safe():
    """The pickup ends at t = 15; the address's last safe instant is 15."""
    spec = chain()
    scenario = HazardScenario("m", nodes={"home": Timeline.closes_at(15.0)})
    assert both_solvers(spec, scenario) == (True, True)


def test_pickup_one_epsilon_too_long_loses_the_service_window():
    spec = chain(pickup=5.001)
    scenario = HazardScenario("m", nodes={"home": Timeline.closes_at(15.0)})
    result = evaluate_mission(spec, 0.0, scenario)
    assert result.failure_reason is FailureReason.SERVICE_WINDOW_UNSAFE
    assert both_solvers(spec, scenario) == (False, False)


def test_zero_pickup_at_an_address_lost_exactly_on_arrival():
    """p = 0 makes the service a single instant, which the convention allows."""
    spec = chain(pickup=0.0)
    scenario = HazardScenario("m", nodes={"home": Timeline.closes_at(10.0)})
    assert both_solvers(spec, scenario) == (True, True)


# ---------------------------------------------------------------------------
# Destinations
# ---------------------------------------------------------------------------

def test_a_refuge_lost_exactly_on_arrival_qualifies_when_no_dwell_is_required():
    """Uncomfortable, and true: with min_safe_dwell = 0 this is a success.

    It is exactly why fixture E exists and why D-009 makes the dwell explicit.
    """
    spec = chain(dwell=0.0)
    scenario = HazardScenario("m", nodes={"shelter": Timeline.closes_at(25.0)})
    assert both_solvers(spec, scenario) == (True, True)


def test_the_same_refuge_fails_the_moment_any_dwell_is_required():
    spec = chain(dwell=0.001)
    scenario = HazardScenario("m", nodes={"shelter": Timeline.closes_at(25.0)})
    result = evaluate_mission(spec, 0.0, scenario)
    assert result.failure_reason is FailureReason.REFUGE_DWELL_UNSAFE
    assert both_solvers(spec, scenario) == (False, False)


def test_dwell_satisfied_to_the_exact_instant():
    spec = chain(dwell=10.0)
    scenario = HazardScenario("m", nodes={"shelter": Timeline.closes_at(35.0)})
    assert both_solvers(spec, scenario) == (True, True)
    spec = chain(dwell=10.001)
    assert both_solvers(spec, scenario) == (False, False)


def test_availability_window_endpoints_are_inclusive():
    scenario = HazardScenario("clear")
    assert both_solvers(chain(available_until=25.0), scenario) == (True, True)
    assert both_solvers(chain(available_until=24.999), scenario) == (False, False)
    assert both_solvers(chain(available_from=25.0), scenario) == (True, True)
    assert both_solvers(chain(available_from=25.001), scenario) == (False, False)


# ---------------------------------------------------------------------------
# Dispatching exactly on the feasible-set boundary
# ---------------------------------------------------------------------------

def test_dispatch_exactly_at_the_last_feasible_instant_succeeds():
    spec = chain()
    scenario = HazardScenario("m", edges={"out": Timeline.closes_at(40.0)})
    ensemble = ScenarioEnsemble.single(scenario)
    exact = exact_feasible_set(spec, ensemble, (0.0, 60.0))
    last = exact.last_feasible_instant
    assert last == pytest.approx(15.0)      # 40 - 10 - 5 - 10
    assert evaluate_mission(spec, last, scenario).mission_success
    assert not evaluate_mission(spec, last + 1e-6, scenario).mission_success
    assert reference_success(spec, last, scenario).success
    assert not reference_success(spec, last + 1e-6, scenario).success


def test_the_feasible_set_is_closed_at_both_ends_of_every_component():
    """Both endpoints of every component are themselves feasible."""
    spec = chain()
    scenario = HazardScenario(
        "m", edges={"out": Timeline.from_windows([[0.0, 20.0], [30.0, 50.0]])})
    exact = exact_feasible_set(spec, ScenarioEnsemble.single(scenario), (0.0, 60.0))
    assert len(exact.components) >= 1
    for component in exact.components:
        assert evaluate_mission(spec, component.lo, scenario).mission_success
        assert evaluate_mission(spec, component.hi, scenario).mission_success


def test_a_gap_really_is_infeasible_in_its_interior():
    spec = chain()
    scenario = HazardScenario(
        "m", edges={"out": Timeline.from_windows([[0.0, 20.0], [30.0, 50.0]])})
    exact = exact_feasible_set(spec, ScenarioEnsemble.single(scenario), (0.0, 60.0))
    for gap in exact.gaps:
        midpoint = 0.5 * (gap.lo + gap.hi)
        assert not evaluate_mission(spec, midpoint, scenario).mission_success
