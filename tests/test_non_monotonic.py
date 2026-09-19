"""Fixture F: feasibility is not monotone in dispatch time."""

import pytest

from wildfireguardian_assisted_dispatch.feasibility.dispatch import (
    NonMonotonicFeasibilityError,
)
from wildfireguardian_assisted_dispatch.feasibility.refine import refine_transitions
from wildfireguardian_assisted_dispatch.fixtures import load
from wildfireguardian_assisted_dispatch.missions.evaluator import evaluate_mission


@pytest.fixture
def fixture():
    return load("f")


def test_the_feasible_set_has_a_hole(fixture):
    feasible = fixture.feasible_set()
    assert feasible.intervals == ((0.0, 0.0), (11.0, 13.0))
    assert feasible.gaps == ((0.0, 11.0),)
    assert not feasible.is_monotone


def test_a_later_dispatch_succeeds_where_an_earlier_one_fails(fixture):
    scenario = fixture.ensemble.scenarios[0]
    assert not evaluate_mission(fixture.spec, 5.0, scenario).mission_success
    assert evaluate_mission(fixture.spec, 12.0, scenario).mission_success


def test_latest_dispatch_refuses_to_summarise_a_set_with_a_hole(fixture):
    feasible = fixture.feasible_set()
    with pytest.raises(NonMonotonicFeasibilityError, match="not monotone"):
        feasible.latest_dispatch()
    # The supremum is still available, and still true as a statement about the
    # supremum - it is just not a latest-dispatch recommendation.
    assert feasible.supremum == 13.0
    assert feasible.latest_dispatch(allow_non_monotonic=True) == 13.0


def test_the_non_monotonicity_is_surfaced_as_a_warning(fixture):
    warnings = fixture.feasible_set().warnings
    assert any("NOT monotone" in w for w in warnings)


def test_no_waiting_is_used_in_either_feasible_window(fixture):
    scenario = fixture.ensemble.scenarios[0]
    for t in (0.0, 12.0):
        result = evaluate_mission(fixture.spec, t, scenario)
        assert result.mission_success
        assert not any(e.kind == "wait" for e in result.log)
        # The whole mission is exactly 5 + 2 + 5 minutes of travel and service.
        assert result.mission_duration == 12.0


def test_boundaries_refine_below_grid_resolution(fixture):
    sweep = fixture.sweep()
    transitions = refine_transitions(fixture.spec, fixture.ensemble, sweep,
                                     tolerance=0.001)
    kinds = [t.kind for t in transitions]
    assert kinds == ["loss", "gain", "loss"]
    # Exact answers: feasibility is lost just after t=0, regained at t=11,
    # and lost again just after t=13.
    assert transitions[0].boundary == pytest.approx(0.0, abs=0.01)
    assert transitions[1].boundary == pytest.approx(11.0, abs=0.01)
    assert transitions[2].boundary == pytest.approx(13.0, abs=0.01)
