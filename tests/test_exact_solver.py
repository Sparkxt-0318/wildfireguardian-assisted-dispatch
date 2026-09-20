"""The discretization-free feasible-set solver."""

from __future__ import annotations

import pytest

from wildfireguardian_assisted_dispatch.feasibility.exact import (
    ClosedInterval,
    ExactSolverUnavailable,
    IntervalSet,
    exact_feasible_set,
    plan_constraints,
    scenario_feasible_set,
)
from wildfireguardian_assisted_dispatch.fixtures import FIXTURES, load
from wildfireguardian_assisted_dispatch.hazards.scenario import ScenarioEnsemble
from wildfireguardian_assisted_dispatch.hazards.semantics import TraversalAdmission
from wildfireguardian_assisted_dispatch.missions.policy import MissionPolicy
from wildfireguardian_assisted_dispatch.network.paths import (
    PathEnumerationLimit,
    simple_paths,
)


# -- interval arithmetic ----------------------------------------------------

def test_intervals_merge_when_they_touch():
    s = IntervalSet([(0, 1), (1, 2)])
    assert s.parts == (ClosedInterval(0.0, 2.0),)


def test_intervals_do_not_merge_across_a_real_gap():
    s = IntervalSet([(0, 1), (1.5, 2)])
    assert len(s) == 2
    assert s.gaps() == (ClosedInterval(1.0, 1.5),)


def test_intersection_union_and_subset():
    a = IntervalSet([(0, 10)])
    b = IntervalSet([(5, 20)])
    assert a.intersect(b) == IntervalSet([(5, 10)])
    assert a.union(b) == IntervalSet([(0, 20)])
    assert a.intersect(b).issubset(a)
    assert not a.issubset(b)


def test_degenerate_intervals_survive():
    s = IntervalSet([(3, 3)])
    assert not s.is_empty
    assert s.measure == 0.0
    assert s.contains(3.0)
    assert s.parts[0].is_degenerate


def test_measure_and_extremes():
    s = IntervalSet([(0, 2), (5, 6)])
    assert s.measure == 3.0
    assert (s.infimum, s.supremum) == (0.0, 6.0)


# -- path enumeration -------------------------------------------------------

def test_simple_paths_are_deterministic_and_loop_free():
    net = load("b").spec.network
    paths = simple_paths(net, "home", "shelter")
    assert paths == simple_paths(net, "home", "shelter")
    assert len(paths) == 2
    for path in paths:
        heads = [net.edge(e).head for e in path]
        assert len(heads) == len(set(heads))


def test_path_enumeration_refuses_to_truncate():
    net = load("b").spec.network
    with pytest.raises(PathEnumerationLimit, match="refusing to truncate"):
        simple_paths(net, "home", "shelter", max_paths=1)


# -- the solver's stated conditions -----------------------------------------

@pytest.mark.parametrize("policy,expected", [
    (MissionPolicy(admission=TraversalAdmission.ENTRY_ONLY),
     "entry_only"),
    (MissionPolicy(allow_node_revisits=True), "simple paths"),
])
def test_the_solver_refuses_outside_its_stated_conditions(policy, expected):
    fixture = load("a")
    with pytest.raises(ExactSolverUnavailable, match=expected):
        exact_feasible_set(fixture.spec.with_policy(policy), fixture.ensemble,
                           (0.0, 30.0))


def test_the_solver_refuses_too_many_scenarios():
    fixture = load("a")
    scenario = fixture.ensemble.scenarios[0]
    many = ScenarioEnsemble.of(tuple(
        scenario.with_weight(1.0).__class__(name=f"s{i}", edges=scenario.edges,
                                            nodes=scenario.nodes, weight=1.0)
        for i in range(20)
    ))
    with pytest.raises(ExactSolverUnavailable, match="exceeds the cap"):
        exact_feasible_set(fixture.spec, many, (0.0, 30.0), max_scenarios=16)


# -- agreement with the sampled sweep ---------------------------------------

@pytest.mark.parametrize("key", sorted(k for k in FIXTURES if k != "g_myopic"))
def test_every_sampled_feasible_point_is_in_the_exact_set(key):
    fixture = load(key)
    sampled = fixture.feasible_set()
    exact = exact_feasible_set(fixture.spec, fixture.ensemble,
                               (fixture.grid[0], fixture.grid[-1]),
                               threshold=fixture.threshold)
    for t, flag in zip(sampled.grid, sampled.flags):
        assert exact.contains(t) == flag, (
            f"{key}: sampled says {flag} at t={t:g}, exact says "
            f"{exact.contains(t)}"
        )


def test_the_exact_set_names_its_components_and_gaps():
    fixture = load("f")
    exact = exact_feasible_set(fixture.spec, fixture.ensemble, (0.0, 20.0))
    assert [(c.lo, c.hi) for c in exact.components] == [(0.0, 0.0), (11.0, 13.0)]
    assert [(g.lo, g.hi) for g in exact.gaps] == [(0.0, 11.0)]
    assert not exact.is_single_component
    assert not exact.is_dispatch_by_deadline
    assert exact.last_feasible_instant == 13.0


def test_fixture_f_first_component_is_a_single_instant():
    """A measure-zero component the default grid only found by luck.

    T_q = {0} U [11, 13]: the first component is the isolated point t = 0. A
    sweep starting at t = 0.5 would have missed it entirely, which is the same
    defect fixture 'n' exhibits at larger scale.
    """
    exact = exact_feasible_set(load("f").spec, load("f").ensemble, (0.0, 20.0))
    assert exact.components[0].is_degenerate
    assert exact.interval_set.measure == 2.0    # only [11, 13] has width


def test_a_dispatch_by_deadline_is_recognised_when_it_exists():
    fixture = load("a")
    exact = exact_feasible_set(fixture.spec, fixture.ensemble, (0.0, 30.0))
    assert exact.is_single_component
    assert exact.is_dispatch_by_deadline
    assert exact.last_feasible_instant == 15.0


def test_per_plan_constraints_are_exposed_for_inspection():
    fixture = load("b")
    plans = plan_constraints(fixture.spec, fixture.ensemble.scenarios[0])
    assert len(plans) == 2                       # one ingress path, two egress
    by_route = {p.egress_edges: p for p in plans}
    north = by_route[("home->north_j", "north_j->shelter")]
    south = by_route[("home->south_j", "south_j->shelter")]
    assert north.arrival_offset == 20.0
    assert south.arrival_offset == 30.0
    assert north.feasible_t == IntervalSet([(0.0, 15.0)])
    assert south.feasible_t == IntervalSet([(0.0, 30.0)])


def test_scenario_feasible_set_is_the_union_over_plans():
    fixture = load("b")
    scenario = fixture.ensemble.scenarios[0]
    union = scenario_feasible_set(fixture.spec, scenario)
    assert union == IntervalSet([(0.0, 30.0)])


def test_thresholds_select_different_exact_sets():
    fixture = load("b_ensemble")
    strict = exact_feasible_set(fixture.spec, fixture.ensemble, (0.0, 40.0),
                                threshold=1.0)
    lenient = exact_feasible_set(fixture.spec, fixture.ensemble, (0.0, 40.0),
                                 threshold=0.8)
    assert [(c.lo, c.hi) for c in strict.components] == [(0.0, 15.0)]
    assert [(c.lo, c.hi) for c in lenient.components] == [(0.0, 30.0)]
