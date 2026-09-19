"""Fixture F - non-monotonic feasibility.

    base --5-- home --5-- shelter,  pickup 2 min

The single egress corridor has a **reopening** hazard: it is safe up to t = 12,
unsafe on (12, 18) while a flare front crosses it, safe again from t = 18, and
finally lost at t = 25.

    Timeline: [0, 12] U [18, 25]

The consequence is the whole reason this project reports a set rather than a
deadline::

    feasible dispatch times = {0} U [11, 13]

Dispatching at t = 5 fails.  Dispatching at t = 12 — seven minutes *later* —
succeeds, because the egress leg then lands in the reopened window.  There is
no waiting in either plan; the later dispatch simply meets the corridor at a
different phase of its timeline.

Anyone who summarises this as "leave before t† = 13" has told the dispatcher
that t = 5 is fine.  It is not.
"""

from __future__ import annotations

from ..feasibility.dispatch import dispatch_grid
from ..hazards.scenario import HazardScenario, ScenarioEnsemble
from ..hazards.timeline import Timeline
from ..missions.policy import MissionPolicy
from ..missions.spec import Destination, MissionSpec
from ..network.graph import NodeKind, RoadNetwork
from ..service.pickup import PickupModel
from .base import Fixture

FLARE_START = 12.0
FLARE_END = 18.0
FINAL_CLOSURE = 25.0
PICKUP_MINUTES = 2.0


def network() -> RoadNetwork:
    n = RoadNetwork("F-non-monotonic")
    n.add_node("base", NodeKind.BASE)
    n.add_node("home", NodeKind.RESIDENCE)
    n.add_node("shelter", NodeKind.DESTINATION)
    n.add_road("base", "home", 5.0)
    n.add_road("home", "shelter", 5.0)
    return n


def build() -> Fixture:
    net = network()
    spec = MissionSpec(
        network=net, base="base", resident="home",
        destinations=(Destination("shelter"),),
        pickup=PickupModel(PICKUP_MINUTES, "p02"),
        policy=MissionPolicy(horizon=120.0),
        name="F-non-monotonic",
    )
    scenario = HazardScenario(
        name="reopening",
        edges={
            "home--shelter": Timeline.from_windows(
                [[0.0, FLARE_START], [FLARE_END, FINAL_CLOSURE]]
            ),
        },
        description="a flare front crosses the egress corridor between t = 12 "
                    "and t = 18; the corridor is finally lost at t = 25",
    )
    return Fixture(
        key="f",
        title="non-monotonic feasibility",
        summary="Later can be better. The feasible dispatch set has a hole in "
                "it, so no single deadline describes it.",
        spec=spec,
        ensemble=ScenarioEnsemble.single(scenario),
        grid=dispatch_grid(0, 20, 1),
        hand_calculation=(
            "egress corridor safe on [0, 12] U [18, 25]\n"
            "arrive home t+5, pickup ends t+7, egress occupies [t+7, t+12]\n"
            "  fits in [0, 12] :  t + 12 <= 12            =>  t <= 0\n"
            "  fits in [18, 25]:  t + 7 >= 18 and t + 12 <= 25\n"
            "                     =>  11 <= t <= 13\n"
            "T = {0} U [11, 13]     sup T = 13, but T is NOT an interval"
        ),
        expected_windows=((0.0, 0.0), (11.0, 13.0)),
        expected_monotone=False,
        notes=(
            "latest_dispatch() raises NonMonotonicFeasibilityError here, by "
            "design. sup T = 13 is a true statement about the supremum and a "
            "false statement about the set.",
            "No waiting is involved in either feasible window. The responder "
            "drives continuously in both; only the phase of the corridor's "
            "timeline differs.",
        ),
    )


__all__ = ["build", "network"]
