"""The full-traversal-interval operator A_e([t_in, t_out], m)."""

import pytest

from wildfireguardian_assisted_dispatch.hazards.scenario import (
    HazardScenario,
    ScenarioEnsemble,
)
from wildfireguardian_assisted_dispatch.hazards.semantics import (
    TraversalAdmission,
    Verdict,
    admits,
    assess_edge_traversal,
    assess_node_occupancy,
)
from wildfireguardian_assisted_dispatch.hazards.timeline import Timeline
from wildfireguardian_assisted_dispatch.network.graph import RoadNetwork
from wildfireguardian_assisted_dispatch.units import INFINITY


@pytest.fixture
def net():
    n = RoadNetwork("t")
    n.add_node("a")
    n.add_node("b")
    n.add_road("a", "b", 5.0)
    return n


@pytest.fixture
def closing(net):
    return HazardScenario("m", edges={"a--b": Timeline.closes_at(7)})


def test_entry_safe_but_not_safe_throughout_is_a_mid_edge_catch(net, closing):
    a = assess_edge_traversal(net.edge("a->b"), 4, 9, closing)
    assert a.safe_at_entry
    assert not a.safe_throughout
    assert a.safety_lost_at == 7
    assert a.verdict is Verdict.CAUGHT_MID_EDGE
    assert "loses safety at 7" in a.explain()


def test_entry_time_only_admission_accepts_what_full_interval_refuses(net, closing):
    a = assess_edge_traversal(net.edge("a->b"), 4, 9, closing)
    assert admits(a, TraversalAdmission.ENTRY_ONLY)
    assert not admits(a, TraversalAdmission.FULL_INTERVAL)


def test_blocked_at_entry_reports_the_reopening(net):
    scenario = HazardScenario(
        "m", edges={"a--b": Timeline.from_windows([[0, 5], [20, 40]])})
    a = assess_edge_traversal(net.edge("a->b"), 10, 15, scenario)
    assert a.verdict is Verdict.BLOCKED_AT_ENTRY
    assert a.next_opening == 20
    assert a.margin is None


def test_margin_is_the_spare_time_after_clearing(net, closing):
    assert assess_edge_traversal(net.edge("a->b"), 0, 5, closing).margin == 2
    a = assess_edge_traversal(net.edge("a->b"), 0, 5,
                              HazardScenario("clear"))
    assert a.margin == INFINITY


def test_corridor_hazards_apply_to_both_directions(net):
    scenario = HazardScenario("m", edges={"a--b": Timeline.closes_at(7)})
    forward = assess_edge_traversal(net.edge("a->b"), 4, 9, scenario)
    backward = assess_edge_traversal(net.edge("b->a"), 4, 9, scenario)
    assert forward.safe_throughout == backward.safe_throughout is False


def test_edge_id_key_overrides_the_corridor_key(net):
    scenario = HazardScenario("m", edges={
        "a--b": Timeline.closes_at(7),
        "b->a": Timeline.always_open(),
    })
    assert not assess_edge_traversal(net.edge("a->b"), 4, 9, scenario).safe_throughout
    assert assess_edge_traversal(net.edge("b->a"), 4, 9, scenario).safe_throughout


def test_node_occupancy_over_a_service_window(net):
    scenario = HazardScenario("m", nodes={"b": Timeline.closes_at(12)})
    assert assess_node_occupancy("b", 5, 12, scenario).safe_throughout
    assert not assess_node_occupancy("b", 5, 13, scenario).safe_throughout


def test_unknown_hazard_keys_are_rejected(net):
    with pytest.raises(KeyError, match="matches no edge or corridor"):
        HazardScenario("typo", edges={"a--z": Timeline.closes_at(1)}).validate(net)
    with pytest.raises(KeyError, match="matches no node"):
        HazardScenario("typo", nodes={"z": Timeline.closes_at(1)}).validate(net)


def test_ensemble_normalises_weights():
    e = ScenarioEnsemble.of([
        HazardScenario("a", weight=2.0), HazardScenario("b", weight=2.0),
    ])
    assert [s.weight for s in e] == [0.5, 0.5]
    assert not e.is_deterministic
    assert ScenarioEnsemble.single(HazardScenario("only")).is_deterministic


def test_ensemble_rejects_duplicate_names():
    with pytest.raises(ValueError, match="duplicate scenario names"):
        ScenarioEnsemble.of([HazardScenario("a"), HazardScenario("a")])
