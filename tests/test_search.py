"""Time-expanded search: completeness, no waiting, and the revisit policy."""

import pytest

from wildfireguardian_assisted_dispatch.hazards.scenario import HazardScenario
from wildfireguardian_assisted_dispatch.hazards.semantics import TraversalAdmission
from wildfireguardian_assisted_dispatch.hazards.timeline import Timeline
from wildfireguardian_assisted_dispatch.network.graph import RoadNetwork
from wildfireguardian_assisted_dispatch.network.travel import DEFAULT_TRAVEL_MODEL
from wildfireguardian_assisted_dispatch.search.time_expanded import (
    SearchBudgetExceeded,
    distinct_arrival_times,
    explore,
)


def chain() -> RoadNetwork:
    n = RoadNetwork("chain")
    for node in ("a", "b", "c"):
        n.add_node(node)
    n.add_road("a", "b", 5.0)
    n.add_road("b", "c", 5.0)
    return n


def run(net, scenario, origin="a", start=0.0, **kwargs):
    kwargs.setdefault("horizon", 120.0)
    return explore(net, DEFAULT_TRAVEL_MODEL, scenario, origin, start, **kwargs)


def test_arrival_times_are_exact_sums_of_travel_times():
    result = run(chain(), HazardScenario("clear"))
    assert [a.time for a in result.at("c")] == [10.0]
    assert result.at("b")[0].time == 5.0


def test_simple_paths_only_by_default():
    # a->b->a would be waiting performed with the engine running.
    result = run(chain(), HazardScenario("clear"))
    for node, arrivals in result.arrivals.items():
        for arrival in arrivals:
            visited = [t.head for t in arrival.traversals]
            assert len(visited) == len(set(visited))
    assert [a.time for a in result.at("a")] == [0.0]


def test_revisits_can_be_enabled_explicitly():
    result = run(chain(), HazardScenario("clear"), allow_node_revisits=True,
                 horizon=25.0)
    assert [a.time for a in result.at("a")] == [0.0, 10.0, 20.0]


def test_later_arrivals_are_kept_because_earliest_does_not_dominate():
    """A reopening corridor makes a later arrival the only useful one."""
    n = RoadNetwork("reopen")
    for node in ("a", "b", "c", "d"):
        n.add_node(node)
    n.add_road("a", "b", 5.0)          # fast approach
    n.add_road("a", "c", 20.0)         # slow approach
    n.add_road("b", "d", 5.0)
    n.add_road("c", "d", 5.0)
    scenario = HazardScenario("m", edges={
        "b--d": Timeline.always_closed(),
        "c--d": Timeline.opens_at(20.0),
    })
    result = run(n, scenario)
    assert [a.time for a in result.at("d")] == [25.0]


def test_horizon_bounds_the_search():
    result = run(chain(), HazardScenario("clear"), horizon=6.0)
    assert result.reached("b") and not result.reached("c")
    assert result.horizon_hit


def test_budget_exhaustion_raises_instead_of_reporting_infeasible():
    with pytest.raises(SearchBudgetExceeded, match="unreliable"):
        run(chain(), HazardScenario("clear"), max_states=1,
            allow_node_revisits=True, horizon=1000.0)


def test_unsafe_origin_short_circuits():
    scenario = HazardScenario("m", nodes={"a": Timeline.always_closed()})
    result = run(chain(), scenario)
    assert result.origin_blocked is not None
    assert not result.reached("b")


def test_entry_only_admission_expands_doomed_edges():
    scenario = HazardScenario("m", edges={"b--c": Timeline.closes_at(7.0)})
    strict = run(chain(), scenario)
    myopic = run(chain(), scenario, admission=TraversalAdmission.ENTRY_ONLY)
    assert not strict.reached("c")
    assert myopic.reached("c")
    assert not myopic.at("c")[0].is_safe


def test_blocking_conflicts_put_the_near_miss_first():
    scenario = HazardScenario("m", edges={"b--c": Timeline.closes_at(7.0)})
    conflicts = run(chain(), scenario).blocking_conflicts()
    assert conflicts[0].element_id == "b->c"
    assert conflicts[0].safe_at_entry


def test_distinct_arrival_times_keeps_one_chain_per_instant():
    n = RoadNetwork("diamond")
    for node in ("a", "x", "y", "z"):
        n.add_node(node)
    n.add_road("a", "x", 5.0)
    n.add_road("a", "y", 5.0)
    n.add_road("x", "z", 5.0)
    n.add_road("y", "z", 5.0)
    arrivals = run(n, HazardScenario("clear")).at("z")
    assert len(arrivals) == 2
    assert len(distinct_arrival_times(arrivals)) == 1
