"""What a grid sweep can and cannot see.

Fixture N is the counterexample: a feasible dispatch window 0.1 minutes wide,
which the default one-minute sweep reports as no window at all.  These tests
pin that defect down, show that boundary refinement cannot rescue it, and show
that the exact solver does.

The point is not that the sweep is broken.  It is that *a sampled empty result
is not evidence of an empty feasible set*, and the software must say so.
"""

from __future__ import annotations

import pytest

from wildfireguardian_assisted_dispatch.feasibility.dispatch import (
    dispatch_grid,
    sweep_dispatch_times,
)
from wildfireguardian_assisted_dispatch.feasibility.exact import exact_feasible_set
from wildfireguardian_assisted_dispatch.feasibility.refine import refine_transitions
from wildfireguardian_assisted_dispatch.fixtures import load
from wildfireguardian_assisted_dispatch.fixtures.narrow_window import TRUE_WINDOW
from wildfireguardian_assisted_dispatch.missions.evaluator import evaluate_mission
from wildfireguardian_assisted_dispatch.validation.brute_force import reference_success


@pytest.fixture
def fixture():
    return load("n")


def test_the_true_window_is_six_seconds_wide():
    assert TRUE_WINDOW == pytest.approx((11.3, 11.4))
    assert TRUE_WINDOW[1] - TRUE_WINDOW[0] == pytest.approx(0.1)


def test_the_default_sweep_finds_nothing(fixture):
    sampled = fixture.feasible_set()
    assert sampled.is_empty
    assert sampled.intervals == ()


def test_but_the_mission_really_is_feasible_there(fixture):
    scenario = fixture.ensemble.scenarios[0]
    for t in (11.3, 11.35, 11.4):
        assert evaluate_mission(fixture.spec, t, scenario).mission_success
        assert reference_success(fixture.spec, t, scenario).success
    for t in (11.29, 11.41):
        assert not evaluate_mission(fixture.spec, t, scenario).mission_success


def test_the_exact_solver_finds_the_window(fixture):
    exact = exact_feasible_set(fixture.spec, fixture.ensemble, (0.0, 20.0))
    assert len(exact.components) == 1
    assert (exact.components[0].lo, exact.components[0].hi) == pytest.approx(
        TRUE_WINDOW)


def test_boundary_refinement_cannot_rescue_a_missed_window(fixture):
    """refine_transitions only refines transitions the grid already saw."""
    sweep = fixture.sweep()
    assert refine_transitions(fixture.spec, fixture.ensemble, sweep) == ()


def test_an_empty_sampled_result_says_it_is_not_evidence_of_emptiness(fixture):
    warnings = fixture.feasible_set().warnings
    assert any("SAMPLED" in w for w in warnings)
    assert any("NOT the same as the feasible set being empty" in w
               for w in warnings)


def test_every_sampled_result_carries_its_resolution():
    """Not just the pathological one - every grid result, always."""
    for key in ("a", "b", "f", "n"):
        fixture = load(key)
        assert any("SAMPLED at" in w for w in fixture.feasible_set().warnings)


@pytest.mark.parametrize("step,found", [
    (1.0, False),
    (0.5, False),
    (0.1, True),
    (0.05, True),
])
def test_the_window_appears_once_the_grid_is_finer_than_the_feature(step, found):
    fixture = load("n")
    grid = dispatch_grid(0.0, 20.0, step)
    sweep = sweep_dispatch_times(fixture.spec, fixture.ensemble, grid)
    assert (not sweep.feasible_set().is_empty) == found


def test_the_resolved_fixture_agrees_with_the_exact_answer():
    fixture = load("n_resolved")
    sampled = fixture.feasible_set()
    exact = exact_feasible_set(fixture.spec, fixture.ensemble,
                               (fixture.grid[0], fixture.grid[-1]))
    assert sampled.intervals == ((11.3, 11.4),)
    assert (exact.components[0].lo, exact.components[0].hi) == pytest.approx(
        TRUE_WINDOW)
    # The sampled endpoints happen to coincide with the true ones here only
    # because the grid was chosen to divide them.
    assert not sampled.is_prefix


def test_reported_precision_never_exceeds_the_grid_step():
    """A sampled window is reported at grid points, never at invented precision."""
    fixture = load("a")
    sweep = sweep_dispatch_times(fixture.spec, fixture.ensemble,
                                 dispatch_grid(0, 30, 2))
    sampled = sweep.feasible_set()
    assert sampled.resolution == 2.0
    # The true boundary is 15; a 2-minute grid can only say 14.
    assert sampled.last_feasible_instant == 14.0
    exact = exact_feasible_set(fixture.spec, fixture.ensemble, (0.0, 30.0))
    assert exact.last_feasible_instant == 15.0
