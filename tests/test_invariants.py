"""The model's own claims, checked independently of the evaluator."""

import dataclasses

import pytest

from wildfireguardian_assisted_dispatch.fixtures import FIXTURES, load
from wildfireguardian_assisted_dispatch.hazards.scenario import HazardScenario
from wildfireguardian_assisted_dispatch.missions.evaluator import evaluate_mission
from wildfireguardian_assisted_dispatch.missions.result import LogEntry
from wildfireguardian_assisted_dispatch.validation.invariants import (
    InvariantViolation,
    validate_many,
    validate_mission_result,
)


@pytest.mark.parametrize("key", sorted(FIXTURES))
def test_no_implicit_waiting_anywhere_in_any_fixture(key):
    fixture = load(key)
    for scenario in fixture.ensemble:
        results = [evaluate_mission(fixture.spec, t, scenario)
                   for t in fixture.grid]
        validate_many(results, fixture.spec, scenario).raise_if_failed()


@pytest.mark.parametrize("key", sorted(FIXTURES))
def test_every_mission_clock_minute_is_travel_or_declared_service(key):
    fixture = load(key)
    scenario = fixture.ensemble.scenarios[0]
    for t in fixture.grid:
        result = evaluate_mission(fixture.spec, t, scenario)
        for entry in result.log:
            assert entry.kind in {
                "dispatch", "travel", "travel_aborted", "arrival", "service",
                "dwell", "abort",
            }, f"undeclared log kind {entry.kind!r}"


def test_a_fabricated_gap_in_the_log_is_caught():
    fixture = load("a")
    scenario = fixture.ensemble.scenarios[0]
    result = evaluate_mission(fixture.spec, 0.0, scenario)
    # Insert five minutes of idling that the evaluator never produced.
    tampered = dataclasses.replace(result, log=result.log[:3] + tuple(
        dataclasses.replace(e, start_time=e.start_time + 5.0,
                            end_time=e.end_time + 5.0)
        for e in result.log[3:]
    ))
    report = validate_mission_result(tampered, fixture.spec, scenario)
    assert not report.ok
    assert any("gap or overlap" in v for v in report.violations)
    with pytest.raises(InvariantViolation):
        report.raise_if_failed()


def test_a_stretched_service_entry_is_caught():
    fixture = load("a")
    scenario = fixture.ensemble.scenarios[0]
    result = evaluate_mission(fixture.spec, 0.0, scenario)
    log = list(result.log)
    index = next(i for i, e in enumerate(log) if e.kind == "service")
    log[index] = dataclasses.replace(log[index], end_time=log[index].end_time + 3)
    report = validate_mission_result(
        dataclasses.replace(result, log=tuple(log)), fixture.spec, scenario)
    assert any("pickup model" in v for v in report.violations)


def test_an_explicit_wait_entry_is_rejected_under_the_no_waiting_policy():
    fixture = load("a")
    scenario = fixture.ensemble.scenarios[0]
    result = evaluate_mission(fixture.spec, 0.0, scenario)
    wait = LogEntry(kind="wait", start_time=result.dispatch_time,
                    end_time=result.dispatch_time, element="base",
                    detail="hold for the flare to pass")
    report = validate_mission_result(
        dataclasses.replace(result, log=(wait,) + result.log),
        fixture.spec, scenario)
    assert any("prohibits waiting" in v for v in report.violations)


def test_a_success_claimed_over_an_unsafe_scenario_is_caught():
    """Re-audit a genuine success against a harsher scenario."""
    fixture = load("a")
    result = evaluate_mission(fixture.spec, 0.0, fixture.ensemble.scenarios[0])
    assert result.mission_success

    from wildfireguardian_assisted_dispatch.hazards.timeline import Timeline
    harsher = HazardScenario("harsher",
                             edges={"home--shelter": Timeline.closes_at(16)})
    report = validate_mission_result(result, fixture.spec, harsher)
    assert not report.ok
    assert any("safe_throughout" in v for v in report.violations)


def test_a_clean_result_passes_every_check():
    fixture = load("a")
    report = validate_mission_result(
        evaluate_mission(fixture.spec, 0.0, fixture.ensemble.scenarios[0]),
        fixture.spec, fixture.ensemble.scenarios[0])
    assert report.ok
    assert len(report.checks_run) > 10
    assert report.describe().startswith("invariant report: OK")
