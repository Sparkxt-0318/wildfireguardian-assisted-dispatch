"""Mission evaluation: the record, the failure reasons, the selection rule."""

import pytest

from wildfireguardian_assisted_dispatch.fixtures import load
from wildfireguardian_assisted_dispatch.hazards.scenario import HazardScenario
from wildfireguardian_assisted_dispatch.hazards.timeline import Timeline
from wildfireguardian_assisted_dispatch.missions.evaluator import evaluate_mission
from wildfireguardian_assisted_dispatch.missions.policy import (
    MissionPolicy,
    WaitingNotImplementedError,
    WaitingPolicy,
)
from wildfireguardian_assisted_dispatch.missions.result import FailureReason
from wildfireguardian_assisted_dispatch.missions.spec import Destination, MissionSpec
from wildfireguardian_assisted_dispatch.network.graph import NodeKind, RoadNetwork
from wildfireguardian_assisted_dispatch.service.pickup import PickupModel


def simple_spec(**policy_kwargs) -> MissionSpec:
    n = RoadNetwork("simple")
    n.add_node("base", NodeKind.BASE)
    n.add_node("home", NodeKind.RESIDENCE)
    n.add_node("shelter", NodeKind.DESTINATION)
    n.add_road("base", "home", 10.0)
    n.add_road("home", "shelter", 10.0)
    return MissionSpec(
        network=n, base="base", resident="home",
        destinations=(Destination("shelter"),),
        pickup=PickupModel(5.0, "p05"),
        policy=MissionPolicy(horizon=120.0, **policy_kwargs),
        name="simple",
    )


def test_successful_record_is_complete_and_chains_in_time():
    result = evaluate_mission(simple_spec(), 0.0, HazardScenario("clear"))
    assert result.mission_success
    assert result.failure_reason is FailureReason.NONE
    assert result.resident_arrival_time == 10.0
    assert (result.pickup_start, result.pickup_end) == (10.0, 15.0)
    assert result.destination_arrival == 25.0
    assert result.mission_duration == 25.0
    assert result.ingress_route.edge_sequence == ("base->home",)
    assert result.egress_route.edge_sequence == ("home->shelter",)


def test_pickup_sits_between_the_two_legs_with_no_idle_time():
    result = evaluate_mission(simple_spec(), 0.0, HazardScenario("clear"))
    kinds = [e.kind for e in result.log]
    assert kinds == ["dispatch", "travel", "arrival", "service", "travel",
                     "arrival"]
    for previous, entry in zip(result.log, result.log[1:]):
        assert previous.end_time == entry.start_time


def test_egress_closure_is_reported_as_no_safe_route_egress():
    scenario = HazardScenario("m", edges={"home--shelter": Timeline.closes_at(20)})
    result = evaluate_mission(simple_spec(), 0.0, scenario)
    assert not result.mission_success
    assert result.failure_reason is FailureReason.NO_SAFE_ROUTE_EGRESS
    assert result.hazard_conflict.leg == "egress"
    assert result.destination_arrival is None


def test_ingress_closure_is_reported_separately():
    scenario = HazardScenario("m", edges={"base--home": Timeline.closes_at(5)})
    result = evaluate_mission(simple_spec(), 0.0, scenario)
    assert result.failure_reason is FailureReason.NO_SAFE_ROUTE_INGRESS


def test_service_window_closure_is_its_own_failure():
    # Reaching the address at t=10 is fine; standing there until t=15 is not.
    scenario = HazardScenario("m", nodes={"home": Timeline.closes_at(12)})
    result = evaluate_mission(simple_spec(), 0.0, scenario)
    assert result.failure_reason is FailureReason.SERVICE_WINDOW_UNSAFE
    assert result.resident_arrival_time == 10.0
    assert "pickup would occupy" in result.hazard_conflict.detail


def test_resident_node_lost_before_arrival():
    scenario = HazardScenario("m", nodes={"home": Timeline.closes_at(5)})
    result = evaluate_mission(simple_spec(), 0.0, scenario)
    assert result.failure_reason is FailureReason.RESIDENT_NODE_UNSAFE_ON_ARRIVAL


def test_base_unsafe_at_dispatch():
    scenario = HazardScenario("m", nodes={"base": Timeline.closes_at(5)})
    result = evaluate_mission(simple_spec(), 6.0, scenario)
    assert result.failure_reason is FailureReason.BASE_UNSAFE_AT_DISPATCH


def test_destination_availability_window_is_enforced():
    n = RoadNetwork("windowed")
    n.add_node("base", NodeKind.BASE)
    n.add_node("home", NodeKind.RESIDENCE)
    n.add_node("shelter", NodeKind.DESTINATION)
    n.add_road("base", "home", 10.0)
    n.add_road("home", "shelter", 10.0)
    spec = MissionSpec(
        network=n, base="base", resident="home",
        destinations=(Destination("shelter", available_until=20.0),),
        pickup=PickupModel(5.0), policy=MissionPolicy(horizon=120.0),
        name="windowed",
    )
    result = evaluate_mission(spec, 0.0, HazardScenario("clear"))
    assert result.failure_reason is FailureReason.DESTINATION_UNAVAILABLE


def test_waiting_policies_other_than_prohibited_are_refused():
    with pytest.raises(WaitingNotImplementedError, match="not implemented"):
        MissionPolicy(waiting=WaitingPolicy.EXPLICIT_AT_ALLOWED_NODES)


def test_selection_takes_the_earliest_destination_arrival():
    fixture = load("b")
    scenario = fixture.ensemble.scenarios[0]
    early = evaluate_mission(fixture.spec, 0.0, scenario)
    late = evaluate_mission(fixture.spec, 20.0, scenario)
    assert early.egress_route.node_sequence == ("home", "north_j", "shelter")
    assert late.egress_route.node_sequence == ("home", "south_j", "shelter")


def test_mission_spec_rejects_a_destination_at_the_resident_node():
    n = RoadNetwork("degenerate")
    n.add_node("base", NodeKind.BASE)
    n.add_node("home", NodeKind.RESIDENCE)
    n.add_road("base", "home", 5.0)
    with pytest.raises(ValueError, match="resident's own node"):
        MissionSpec(network=n, base="base", resident="home",
                    destinations=(Destination("home"),))


def test_results_serialise_to_flat_rows():
    row = evaluate_mission(simple_spec(), 0.0, HazardScenario("clear")).to_row()
    assert row["mission_success"] is True
    assert row["ingress_path"] == "base -> home"
    assert row["destination_arrival"] == 25.0
    assert set(row) >= {
        "dispatch_time", "resident_arrival_time", "pickup_start", "pickup_end",
        "destination_arrival", "mission_success", "failure_reason",
    }
