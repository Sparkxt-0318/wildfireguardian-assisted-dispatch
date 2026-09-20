"""Every fixture must reproduce its own hand calculation."""

import pytest

from wildfireguardian_assisted_dispatch.fixtures import FIXTURES, load
from wildfireguardian_assisted_dispatch.validation.handcalc import check_fixture


@pytest.mark.parametrize("key", sorted(FIXTURES))
def test_fixture_matches_its_hand_calculation(key):
    check = check_fixture(load(key))
    assert check.ok, check.describe()


@pytest.mark.parametrize("key", sorted(FIXTURES))
def test_every_fixture_documents_its_arithmetic(key):
    fixture = load(key)
    assert fixture.hand_calculation.strip(), (
        f"fixture {key} has no hand calculation; expected windows copied from a "
        "previous run would validate nothing"
    )
    # A fixture must state an expected answer somewhere. Fixture 'n' states an
    # empty SAMPLED answer on purpose, so the exact components carry it there.
    assert fixture.expected_windows or fixture.expected_exact_components


def test_fixture_a_deadline_is_a_subtraction():
    # 40 (closure) - 10 (ingress) - 5 (pickup) - 10 (egress) = 15
    assert load("a").feasible_set().dispatch_by_deadline() == 15.0


def test_fixture_b_survives_the_loss_of_the_fast_route():
    feasible = load("b").feasible_set()
    assert feasible.dispatch_by_deadline() == 30.0
    assert feasible.is_prefix


def test_fixture_c_is_bound_by_the_outbound_traversal():
    fixture = load("c")
    assert fixture.feasible_set().dispatch_by_deadline() == 14.0
    # The naive inbound-only answer would have been 45 - 10 - 8 = 27.
    assert fixture.feasible_set().supremum < 27.0


def test_fixture_e_switches_destination_when_the_refuge_stops_holding():
    from wildfireguardian_assisted_dispatch.missions.evaluator import evaluate_mission

    fixture = load("e")
    scenario = fixture.ensemble.scenarios[0]
    assert evaluate_mission(fixture.spec, 14.0, scenario).destination_node == "refuge"
    assert evaluate_mission(fixture.spec, 15.0, scenario).destination_node == "shelter"


def test_fixture_e_refuge_arrival_alone_is_not_success():
    from wildfireguardian_assisted_dispatch.missions.evaluator import evaluate_mission

    fixture = load("e")
    scenario = fixture.ensemble.scenarios[0]
    result = evaluate_mission(fixture.spec, 20.0, scenario)
    # The responder could physically reach the refuge at t=36, well before it is
    # overrun at t=60 - but not with 30 minutes of margin, so it is not a
    # destination and the mission goes to the durable shelter instead.
    assert result.destination_node == "shelter"
    assert result.destination_arrival == 51.0
