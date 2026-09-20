"""The independent brute-force oracle, and what it is for.

These tests are not about the oracle being clever - it is deliberately stupid.
They are about the main solver and a second implementation, written from the
model description rather than from the solver, reaching the same answers.
"""

from __future__ import annotations

import pytest

from wildfireguardian_assisted_dispatch.feasibility.dispatch import p_success
from wildfireguardian_assisted_dispatch.fixtures import FIXTURES, load
from wildfireguardian_assisted_dispatch.missions.evaluator import evaluate_mission
from wildfireguardian_assisted_dispatch.validation.brute_force import (
    BruteForceLimit,
    enumerate_plans,
    reference_feasible_flags,
    reference_p_success,
    reference_success,
)


@pytest.mark.parametrize("key", sorted(FIXTURES))
def test_the_oracle_reproduces_every_fixture_pointwise(key):
    fixture = load(key)
    sampled = fixture.feasible_set()
    oracle = reference_feasible_flags(fixture.spec, fixture.ensemble,
                                      fixture.grid, fixture.threshold)
    assert oracle == sampled.flags, (
        f"{key}: the main solver and the reference oracle disagree at "
        f"{[t for t, a, b in zip(fixture.grid, sampled.flags, oracle) if a != b]}"
    )


@pytest.mark.parametrize("key", sorted(FIXTURES))
def test_the_oracle_reproduces_p_success_not_just_feasibility(key):
    fixture = load(key)
    for t in fixture.grid[::4]:
        assert reference_p_success(fixture.spec, t, fixture.ensemble) == pytest.approx(
            p_success(fixture.spec, t, fixture.ensemble))


@pytest.mark.parametrize("key", ["a", "b", "c", "e", "g", "h_north"])
def test_the_oracle_reproduces_the_chosen_route_and_arrival(key):
    """Agreement on the answer *and* on the plan that produced it."""
    fixture = load(key)
    scenario = fixture.ensemble.scenarios[0]
    for t in fixture.grid[::3]:
        result = evaluate_mission(fixture.spec, t, scenario)
        outcome = reference_success(fixture.spec, t, scenario)
        assert result.mission_success == outcome.success
        if not result.mission_success:
            continue
        assert result.destination_arrival == pytest.approx(
            outcome.destination_arrival)
        assert result.destination_node == outcome.chosen.destination
        assert result.ingress_route.edge_sequence == outcome.chosen.ingress_edges
        assert result.egress_route.edge_sequence == outcome.chosen.egress_edges


def test_the_oracle_agrees_about_the_myopic_catch():
    """The entry-only case, where the exact solver cannot help."""
    fixture = load("g_myopic")
    scenario = fixture.ensemble.scenarios[0]
    for t in range(0, 26):
        result = evaluate_mission(fixture.spec, float(t), scenario)
        outcome = reference_success(fixture.spec, float(t), scenario)
        assert result.mission_success == outcome.success, f"t={t}"
    caught = reference_success(fixture.spec, 6.0, scenario)
    assert not caught.success
    assert caught.chosen.entry_admissible          # the myopic planner took it
    assert not caught.chosen.fully_safe            # and it was never safe
    assert caught.chosen.first_unsafe_edge == "home->shelter"
    assert caught.chosen.first_unsafe_instant == 20.0


def test_the_oracle_enumerates_every_plan_including_the_bad_ones():
    fixture = load("b")
    plans = enumerate_plans(fixture.spec, 0.0, fixture.ensemble.scenarios[0])
    assert len(plans) == 2
    assert {p.destination_arrival for p in plans} == {20.0, 30.0}
    assert all(p.fully_safe for p in plans)


def test_the_oracle_refuses_to_truncate_its_enumeration():
    fixture = load("b")
    with pytest.raises(BruteForceLimit, match="only meant for tiny graphs"):
        enumerate_plans(fixture.spec, 0.0, fixture.ensemble.scenarios[0],
                        max_paths=0)
