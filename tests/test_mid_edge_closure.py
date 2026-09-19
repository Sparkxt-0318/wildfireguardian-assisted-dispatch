"""Fixture G: what happens when a road becomes unsafe halfway across."""

import pytest

from wildfireguardian_assisted_dispatch.fixtures import load
from wildfireguardian_assisted_dispatch.missions.evaluator import evaluate_mission
from wildfireguardian_assisted_dispatch.missions.result import FailureReason


@pytest.fixture
def strict():
    return load("g")


@pytest.fixture
def myopic():
    return load("g_myopic")


def test_full_interval_admission_never_enters_a_segment_it_cannot_clear(strict):
    result = evaluate_mission(strict.spec, 6.0, strict.ensemble.scenarios[0])
    assert result.mission_success
    assert result.egress_route.node_sequence == ("home", "mid", "shelter")
    assert result.destination_arrival == 26.0
    assert result.egress_route.is_safe


def test_entry_time_only_admission_gets_caught_mid_segment(myopic):
    result = evaluate_mission(myopic.spec, 6.0, myopic.ensemble.scenarios[0])
    assert not result.mission_success
    assert result.failure_reason is FailureReason.CAUGHT_MID_EDGE
    conflict = result.hazard_conflict
    assert conflict.element_id == "home->shelter"
    assert conflict.entry_time == 12.0
    assert conflict.safety_lost_at == 20.0
    assert conflict.exit_time == 22.0
    assert "responder and resident caught" in conflict.detail


def test_the_aborted_traversal_is_truncated_in_the_log(myopic):
    result = evaluate_mission(myopic.spec, 6.0, myopic.ensemble.scenarios[0])
    aborted = [e for e in result.log if e.kind == "travel_aborted"]
    assert len(aborted) == 1
    assert (aborted[0].start_time, aborted[0].end_time) == (12.0, 20.0)
    assert result.log[-1].kind == "abort"
    assert result.log[-1].start_time == 20.0


def test_a_caught_mission_reports_no_destination_arrival(myopic):
    result = evaluate_mission(myopic.spec, 6.0, myopic.ensemble.scenarios[0])
    assert result.destination_arrival is None
    assert any("would have reached shelter at t=22" in n for n in result.notes)


def test_the_two_policies_disagree_only_where_the_semantics_bite(strict, myopic):
    scenario = strict.ensemble.scenarios[0]
    disagreements = []
    for t in range(0, 26):
        a = evaluate_mission(strict.spec, float(t), scenario).mission_success
        b = evaluate_mission(myopic.spec, float(t), scenario).mission_success
        if a != b:
            disagreements.append(t)
    # Entry-time-only checking loses ten dispatch minutes that full-interval
    # checking keeps - and loses them by driving into the fire, not by
    # declining the mission.
    assert disagreements == list(range(5, 15))


def test_entry_only_feasibility_is_non_monotone_purely_from_bad_semantics(myopic):
    assert myopic.feasible_set().intervals == ((0.0, 4.0), (15.0, 20.0))
    assert not myopic.feasible_set().is_monotone
    assert load("g").feasible_set().is_monotone
