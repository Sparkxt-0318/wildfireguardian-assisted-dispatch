"""Fixture D: on-scene time comes straight off the dispatch envelope."""

import pytest

from wildfireguardian_assisted_dispatch.feasibility.sensitivity import (
    sweep_pickup_durations,
)
from wildfireguardian_assisted_dispatch.fixtures import load
from wildfireguardian_assisted_dispatch.fixtures.pickup_sensitivity import (
    last_feasible_instant_for,
)
from wildfireguardian_assisted_dispatch.service.pickup import (
    PICKUP_PROFILE_MINUTES,
    PICKUP_SENSITIVITY_MINUTES,
    PickupModel,
)


@pytest.mark.parametrize("minutes,expected", [(2, 28), (5, 25), (10, 20), (15, 15)])
def test_each_scenario_duration_shifts_the_deadline_one_for_one(minutes, expected):
    fixture = load("d")
    spec = fixture.spec.with_pickup(PickupModel(float(minutes)))
    from wildfireguardian_assisted_dispatch.feasibility.dispatch import (
        sweep_dispatch_times,
    )
    feasible = sweep_dispatch_times(spec, fixture.ensemble,
                                    fixture.grid).feasible_set()
    assert feasible.dispatch_by_deadline() == float(expected)
    assert last_feasible_instant_for(minutes) == expected


def test_the_sensitivity_sweep_is_monotone_in_pickup_duration():
    fixture = load("d")
    sensitivity = sweep_pickup_durations(fixture.spec, fixture.ensemble,
                                         fixture.grid,
                                         PICKUP_SENSITIVITY_MINUTES)
    latest = [c.latest_feasible for c in sensitivity.cases]
    assert latest == [28.0, 25.0, 20.0, 15.0]
    assert sensitivity.is_monotone_in_pickup


def test_sensitivity_rows_are_flat_and_complete():
    fixture = load("d")
    rows = sweep_pickup_durations(fixture.spec, fixture.ensemble, fixture.grid,
                                  [2.0, 15.0]).rows()
    assert [r["pickup_duration"] for r in rows] == [2.0, 15.0]
    assert rows[0]["latest_feasible"] == 28.0


def test_profiles_are_the_four_scenario_durations():
    assert sorted(PICKUP_PROFILE_MINUTES.values()) == [2.0, 5.0, 10.0, 15.0]
    assert PickupModel.of("p10").duration == 10.0
    assert "not a validated medical" in PickupModel.of("p10").note.lower()
    with pytest.raises(KeyError, match="unknown pickup profile"):
        PickupModel.of("critical")


def test_pickup_starts_the_instant_the_responder_arrives():
    # No implicit waiting: service begins at the arrival instant, never later.
    assert PickupModel(5.0).window(12.0) == (12.0, 17.0)
