"""Fixture H: the staging-location comparison.

Two candidate staging points for the same resident and the same destination.
The repository answers "is this mission feasible" once per mission; comparing
the two answers is the scientific content, and it is deliberately *not* an
optimisation over staging locations.
"""

from __future__ import annotations

from wildfireguardian_assisted_dispatch.feasibility.exact import exact_feasible_set
from wildfireguardian_assisted_dispatch.fixtures import load
from wildfireguardian_assisted_dispatch.missions.evaluator import evaluate_mission


def _exact(key):
    fixture = load(key)
    return exact_feasible_set(fixture.spec, fixture.ensemble,
                              (fixture.grid[0], fixture.grid[-1]))


def test_the_near_base_has_the_shorter_mission():
    north = evaluate_mission(load("h_north").spec, 0.0,
                             load("h_north").ensemble.scenarios[0])
    south = evaluate_mission(load("h_south").spec, 0.0,
                             load("h_south").ensemble.scenarios[0])
    assert north.mission_duration == 25.0
    assert south.mission_duration == 35.0


def test_the_near_base_has_the_SMALLER_feasible_dispatch_set():
    """Proximity is not the dispatch envelope."""
    north, south = _exact("h_north"), _exact("h_south")
    assert north.last_feasible_instant == 12.0
    assert south.last_feasible_instant == 15.0
    assert north.interval_set.measure < south.interval_set.measure


def test_each_base_is_bound_by_a_different_constraint():
    # North is bound by its own approach corridor (lost at 22), which it must
    # clear by t + 10; south is bound by the egress corridor (lost at 50).
    north = load("h_north")
    scenario = north.ensemble.scenarios[0]
    blocked = evaluate_mission(north.spec, 13.0, scenario)
    assert blocked.hazard_conflict.leg == "ingress"

    south = load("h_south")
    blocked = evaluate_mission(south.spec, 16.0, scenario)
    assert blocked.hazard_conflict.leg == "egress"


def test_neither_mission_is_a_choice_between_bases():
    """Each spec names one base; nothing in the model picks between them."""
    assert load("h_north").spec.base == "base_north"
    assert load("h_south").spec.base == "base_south"
    # The union of the two feasible sets is NOT something the solver computes,
    # and must not be reported as "the" feasible set for the resident.
    north, south = _exact("h_north"), _exact("h_south")
    assert north.interval_set.issubset(south.interval_set)
