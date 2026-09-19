"""Road network construction and its guard rails."""

import pytest

from wildfireguardian_assisted_dispatch.network.graph import (
    NodeKind,
    RoadNetwork,
    corridor_id,
)


def test_two_way_roads_share_a_corridor():
    n = RoadNetwork("t")
    n.add_node("a")
    n.add_node("b")
    forward, backward = n.add_road("a", "b", 4.0)
    assert forward.corridor == backward.corridor == corridor_id("a", "b")
    assert {e.id for e in n.edges.values()} == {"a->b", "b->a"}


def test_oneway_roads_have_one_edge():
    n = RoadNetwork("t")
    n.add_node("a")
    n.add_node("b")
    assert len(n.add_road("a", "b", 4.0, oneway=True)) == 1
    assert n.out_edges("b") == ()


def test_zero_and_negative_travel_times_are_rejected():
    n = RoadNetwork("t")
    n.add_node("a")
    n.add_node("b")
    with pytest.raises(ValueError, match="travel_time must be > 0"):
        n.add_road("a", "b", 0.0)


def test_edges_to_unknown_nodes_are_rejected():
    n = RoadNetwork("t")
    n.add_node("a")
    with pytest.raises(KeyError, match="unknown node"):
        n.add_road("a", "ghost", 4.0)


def test_out_edges_are_deterministically_ordered():
    n = RoadNetwork("t")
    for node in ("a", "z", "m", "b"):
        n.add_node(node)
    for other in ("z", "m", "b"):
        n.add_road("a", other, 1.0)
    assert [e.id for e in n.out_edges("a")] == ["a->b", "a->m", "a->z"]


def test_validate_requires_mission_nodes():
    n = RoadNetwork("t")
    n.add_node("a", NodeKind.BASE)
    with pytest.raises(KeyError, match="missing required node"):
        n.validate(["a", "b"])
