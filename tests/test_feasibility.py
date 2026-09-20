"""Dispatch sweeps, the feasible set, and the ensemble aggregation rule."""

import pytest

from wildfireguardian_assisted_dispatch.feasibility.dispatch import (
    FeasibleDispatchSet,
    dispatch_grid,
    p_success,
    sweep_dispatch_times,
)
from wildfireguardian_assisted_dispatch.fixtures import load


def make_set(flags, threshold=1.0, step=1.0):
    grid = tuple(float(i) for i in range(len(flags)))
    return FeasibleDispatchSet(threshold, grid, tuple(flags), step)


def test_dispatch_grid_is_inclusive():
    assert dispatch_grid(0, 4, 2) == (0.0, 2.0, 4.0)
    with pytest.raises(ValueError):
        dispatch_grid(0, 4, 0)
    with pytest.raises(ValueError):
        dispatch_grid(4, 0, 1)


def test_intervals_gaps_and_monotonicity():
    s = make_set([True, True, False, False, True, False])
    assert s.intervals == ((0.0, 1.0), (4.0, 4.0))
    assert s.gaps == ((1.0, 4.0),)
    assert not s.is_monotone


def test_a_prefix_set_is_a_genuine_deadline():
    s = make_set([True, True, True, False, False])
    assert s.is_monotone and s.is_prefix
    assert s.dispatch_by_deadline() == 2.0


def test_an_empty_set_warns_and_has_no_supremum():
    s = make_set([False, False])
    assert s.is_empty and s.supremum is None
    assert any("no sampled dispatch time" in w for w in s.warnings)


def test_a_set_that_runs_off_the_end_of_the_grid_warns():
    s = make_set([True, True, True])
    assert any("does not bracket" in w for w in s.warnings)


def test_p_success_is_a_weight_sum_not_an_edge_product():
    fixture = load("b_ensemble")
    sweep = fixture.sweep()
    # Hand calculation in the fixture: 1.0 up to t=15, then 0.8 to t=30, then 0.
    assert sweep.outcome_at(15.0).p_success == pytest.approx(1.0)
    assert sweep.outcome_at(16.0).p_success == pytest.approx(0.8)
    assert sweep.outcome_at(31.0).p_success == pytest.approx(0.0)
    # 0.8 is exactly the weight of the two surviving scenarios, 0.5 + 0.3.
    outcome = sweep.outcome_at(20.0)
    assert set(outcome.successes) == {"nominal", "wind_shift"}


def test_thresholds_select_different_sets_from_one_sweep():
    fixture = load("b_ensemble")
    sweep = fixture.sweep()
    assert sweep.feasible_set(1.0).intervals == ((0.0, 15.0),)
    assert sweep.feasible_set(0.8).intervals == ((0.0, 30.0),)
    assert sweep.feasible_set(0.1).intervals == ((0.0, 30.0),)


def test_p_success_helper_agrees_with_the_sweep():
    fixture = load("b_ensemble")
    assert p_success(fixture.spec, 16.0, fixture.ensemble) == pytest.approx(0.8)


def test_sweep_rows_carry_one_record_per_scenario():
    fixture = load("b_ensemble")
    sweep = sweep_dispatch_times(fixture.spec, fixture.ensemble,
                                 dispatch_grid(0, 4, 1))
    rows = sweep.rows()
    assert len(rows) == 5 * 3
    assert {r["scenario"] for r in rows} == {"nominal", "wind_shift", "south_flank"}
    summary = sweep.summary_rows()
    assert len(summary) == 5
    assert summary[0]["p_success"] == pytest.approx(1.0)


def test_outcome_lookup_rejects_off_grid_times():
    fixture = load("a")
    with pytest.raises(KeyError, match="not on the sweep grid"):
        fixture.sweep().outcome_at(0.5)
