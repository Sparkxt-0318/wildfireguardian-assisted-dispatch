"""Property-based invariants.

Fixtures pin down specific answers.  These pin down *relationships* that must
hold across a whole family of worlds, which is a different kind of evidence: a
fixture can be right for the wrong reason, a property that survives a few
hundred random worlds usually cannot.

Scope discipline
----------------
The monotonicity properties below are stated over **closure-only** hazard
worlds (:mod:`worlds`), where a corridor is lost once and never comes back.
They are deliberately *not* asserted over the reopening fixtures: fixture F is
a standing counterexample to "later is worse", and asserting monotonicity
there would be testing a claim the model explicitly denies.  The last group of
tests asserts exactly that non-monotonicity instead.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from wildfireguardian_assisted_dispatch.feasibility.exact import (
    IntervalSet,
    exact_feasible_set,
)
from wildfireguardian_assisted_dispatch.fixtures import FIXTURES, load
from wildfireguardian_assisted_dispatch.hazards.scenario import (
    HazardScenario,
    ScenarioEnsemble,
)
from wildfireguardian_assisted_dispatch.hazards.timeline import Timeline
from wildfireguardian_assisted_dispatch.missions.evaluator import evaluate_mission
from wildfireguardian_assisted_dispatch.missions.spec import Destination, MissionSpec
from wildfireguardian_assisted_dispatch.network.graph import NodeKind, RoadNetwork
from wildfireguardian_assisted_dispatch.network.paths import simple_paths
from wildfireguardian_assisted_dispatch.service.pickup import PickupModel
from wildfireguardian_assisted_dispatch.units import EPS
from wildfireguardian_assisted_dispatch.validation.brute_force import (
    reference_p_success,
    reference_success,
)
from worlds import HORIZON, STUDY_RANGE, World, safe_worlds, worlds

SETTINGS = settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


def feasible_set(world: World) -> IntervalSet:
    return exact_feasible_set(world.spec(), world.ensemble(),
                              STUDY_RANGE).interval_set


# ---------------------------------------------------------------------------
# Monotone-world properties
# ---------------------------------------------------------------------------

@SETTINGS
@given(worlds(), st.floats(min_value=0.0, max_value=30.0))
def test_longer_pickup_never_helps_in_a_monotone_world(world, extra):
    """More time on scene cannot open up new dispatch times."""
    longer = feasible_set(world.with_pickup(world.pickup + extra))
    baseline = feasible_set(world)
    assert longer.issubset(baseline), (
        f"pickup {world.pickup} -> {world.pickup + extra} enlarged the feasible "
        f"set: {baseline} -> {longer}"
    )


@SETTINGS
@given(worlds(), st.floats(min_value=0.0, max_value=15.0))
def test_slower_roads_never_help_in_a_monotone_world(world, delta):
    """Adding travel time to every road cannot open up new dispatch times."""
    slower = feasible_set(world.slower_by(delta))
    baseline = feasible_set(world)
    assert slower.issubset(baseline)


@SETTINGS
@given(worlds(), st.floats(min_value=0.0, max_value=60.0))
def test_earlier_hazard_never_helps_in_a_monotone_world(world, delta):
    """Moving every closure earlier cannot create feasible dispatch times."""
    harsher = feasible_set(world.hazard_earlier_by(delta))
    baseline = feasible_set(world)
    assert harsher.issubset(baseline)


@SETTINGS
@given(worlds())
def test_zero_pickup_is_the_limiting_case(world):
    """p = 0 dominates every positive pickup duration, and is the p -> 0 limit."""
    instant = feasible_set(world.with_pickup(0.0))
    assert feasible_set(world).issubset(instant)
    for p in (0.001, 0.01, 0.1):
        assert feasible_set(world.with_pickup(p)).issubset(instant)


@SETTINGS
@given(worlds())
def test_removing_all_hazard_can_only_enlarge_the_feasible_set(world):
    assert feasible_set(world).issubset(feasible_set(world.without_hazard()))


# ---------------------------------------------------------------------------
# The hazard-free limit agrees with ordinary travel-time arithmetic
# ---------------------------------------------------------------------------

def _fastest_mission_duration(world: World) -> float:
    """Shortest ingress + pickup + shortest egress, computed independently."""
    net = world.network()

    def shortest(a: str, b: str) -> float:
        return min(
            sum(net.edge(e).travel_time for e in path)
            for path in simple_paths(net, a, b)
        )

    return shortest("base", "home") + world.pickup + shortest("home", "shelter")


@SETTINGS
@given(safe_worlds())
def test_an_always_safe_world_is_plain_travel_time_arithmetic(world):
    duration = _fastest_mission_duration(world)
    spec = world.spec()
    scenario = world.scenario()

    result = evaluate_mission(spec, 0.0, scenario)
    assert result.mission_success
    assert result.destination_arrival == pytest.approx(duration, abs=1e-6)

    exact = exact_feasible_set(spec, world.ensemble(), STUDY_RANGE)
    # Feasible from the epoch until the mission would run past the horizon.
    expected_end = min(STUDY_RANGE[1], HORIZON - duration)
    assert len(exact.components) == 1
    assert exact.components[0].lo == pytest.approx(0.0, abs=1e-6)
    assert exact.components[0].hi == pytest.approx(expected_end, abs=1e-6)
    assert exact.is_dispatch_by_deadline


# ---------------------------------------------------------------------------
# Connectivity
# ---------------------------------------------------------------------------

@SETTINGS
@given(worlds())
def test_an_unreachable_destination_is_never_feasible(world):
    """No hazard assumption can make a disconnected mission work."""
    net = world.network()
    net.add_node("island", NodeKind.DESTINATION)   # no roads at all
    spec = MissionSpec(
        network=net, base="base", resident="home",
        destinations=(Destination("island"),),
        pickup=PickupModel(world.pickup), policy=world.spec().policy,
        name="disconnected",
    )
    scenario = world.without_hazard().scenario()
    assert exact_feasible_set(spec, ScenarioEnsemble.single(scenario),
                              STUDY_RANGE).is_empty
    for t in (0.0, 5.0, 50.0):
        assert not evaluate_mission(spec, t, scenario).mission_success
        assert not reference_success(spec, t, scenario).success


def test_an_unreachable_resident_is_never_feasible():
    net = RoadNetwork("severed")
    net.add_node("base", NodeKind.BASE)
    net.add_node("home", NodeKind.RESIDENCE)
    net.add_node("shelter", NodeKind.DESTINATION)
    net.add_road("home", "shelter", 5.0)          # the resident is cut off
    spec = MissionSpec(network=net, base="base", resident="home",
                       destinations=(Destination("shelter"),),
                       pickup=PickupModel(5.0), name="severed")
    scenario = HazardScenario("clear")
    assert exact_feasible_set(spec, ScenarioEnsemble.single(scenario),
                              STUDY_RANGE).is_empty
    assert not evaluate_mission(spec, 0.0, scenario).mission_success


# ---------------------------------------------------------------------------
# Ensemble aggregation
# ---------------------------------------------------------------------------

@SETTINGS
@given(worlds(), st.floats(min_value=0.01, max_value=5.0))
def test_adding_a_failing_scenario_cannot_raise_p_success(world, weight):
    """A positive-weight scenario in which the mission fails can only dilute."""
    spec = world.spec()
    base_scenario = world.scenario("base")
    doomed = HazardScenario(
        "doomed",
        edges={c: Timeline.always_closed() for c in world.closures},
        weight=weight,
        description="every corridor is impassable for all time",
    )
    before = ScenarioEnsemble.single(base_scenario)
    after = ScenarioEnsemble.of((base_scenario.with_weight(1.0), doomed))

    from wildfireguardian_assisted_dispatch.feasibility.dispatch import p_success
    for t in (0.0, 3.0, 11.0, 40.0):
        assert p_success(spec, t, after) <= p_success(spec, t, before) + EPS


@SETTINGS
@given(worlds())
def test_p_success_is_a_normalised_weight_sum(world):
    spec = world.spec()
    ensemble = ScenarioEnsemble.of((
        world.scenario("a").with_weight(2.0),
        world.hazard_earlier_by(10.0).scenario("b").with_weight(1.0),
        world.without_hazard().scenario("c").with_weight(1.0),
    ))
    assert sum(s.weight for s in ensemble) == pytest.approx(1.0)

    from wildfireguardian_assisted_dispatch.feasibility.dispatch import p_success
    for t in (0.0, 7.0, 25.0):
        value = p_success(spec, t, ensemble)
        assert 0.0 - EPS <= value <= 1.0 + EPS
        by_hand = sum(
            s.weight for s in ensemble
            if evaluate_mission(spec, t, s).mission_success
        )
        assert value == pytest.approx(by_hand)
        assert value == pytest.approx(reference_p_success(spec, t, ensemble))


# ---------------------------------------------------------------------------
# Closure convention: the supremum is attained
# ---------------------------------------------------------------------------

@SETTINGS
@given(worlds())
def test_the_last_feasible_instant_is_itself_feasible(world):
    """T_q is closed, so sup T_q must be in T_q - check it by evaluating there."""
    exact = exact_feasible_set(world.spec(), world.ensemble(), STUDY_RANGE)
    if exact.is_empty:
        return
    last = exact.last_feasible_instant
    assert evaluate_mission(world.spec(), last, world.scenario()).mission_success
    # ...and just past it, feasibility is gone (unless the study range clipped it).
    if last < STUDY_RANGE[1] - 1e-6:
        assert not evaluate_mission(world.spec(), last + 1e-3,
                                    world.scenario()).mission_success


@pytest.mark.parametrize("key", sorted(FIXTURES))
def test_every_fixture_attains_its_last_feasible_instant(key):
    fixture = load(key)
    sampled = fixture.feasible_set()
    if sampled.is_empty:
        return
    last = sampled.last_feasible_instant
    from wildfireguardian_assisted_dispatch.feasibility.dispatch import p_success
    assert p_success(fixture.spec, last, fixture.ensemble) >= fixture.threshold - EPS


# ---------------------------------------------------------------------------
# Cross-solver agreement
# ---------------------------------------------------------------------------

@SETTINGS
@given(worlds(), st.floats(min_value=0.0, max_value=120.0))
def test_main_solver_and_reference_oracle_agree(world, t):
    spec, scenario = world.spec(), world.scenario()
    assert (evaluate_mission(spec, t, scenario).mission_success
            == reference_success(spec, t, scenario).success)


@SETTINGS
@given(worlds(), st.floats(min_value=0.0, max_value=120.0))
def test_exact_set_and_main_solver_agree_pointwise(world, t):
    exact = exact_feasible_set(world.spec(), world.ensemble(), STUDY_RANGE)
    success = evaluate_mission(world.spec(), t, world.scenario()).mission_success
    assert exact.contains(t) == success


# ---------------------------------------------------------------------------
# The properties above must NOT be imposed on reopening worlds
# ---------------------------------------------------------------------------

def test_monotonicity_genuinely_fails_on_the_reopening_fixture():
    """The guard rail on the guard rails.

    If "later is never better" held universally, the tests above would be
    stronger than the model. Fixture F shows it does not hold, which is why
    those properties are scoped to closure-only worlds.
    """
    fixture = load("f")
    scenario = fixture.ensemble.scenarios[0]
    assert not evaluate_mission(fixture.spec, 5.0, scenario).mission_success
    assert evaluate_mission(fixture.spec, 12.0, scenario).mission_success


def test_longer_pickup_can_help_when_hazard_reopens():
    """And "longer pickup never helps" fails too, for the same reason.

    Dispatched at t = 6 the responder reaches the address at t = 11. With the
    egress corridor shut on (12, 18):

        p = 2  ->  egress occupies [13, 18]  -- starts inside the closure, fails
        p = 8  ->  egress occupies [19, 24]  -- starts after the reopening, works

    Spending six more minutes on scene is what makes the mission possible. This
    is the counterexample that keeps the pickup-monotonicity property honest
    about its scope.
    """
    fixture = load("f")
    scenario = fixture.ensemble.scenarios[0]
    quick = fixture.spec.with_pickup(PickupModel(2.0))
    slow = fixture.spec.with_pickup(PickupModel(8.0))
    assert not evaluate_mission(quick, 6.0, scenario).mission_success

    longer = evaluate_mission(slow, 6.0, scenario)
    assert longer.mission_success
    assert (longer.pickup_start, longer.pickup_end) == (11.0, 19.0)
    assert longer.destination_arrival == 24.0
