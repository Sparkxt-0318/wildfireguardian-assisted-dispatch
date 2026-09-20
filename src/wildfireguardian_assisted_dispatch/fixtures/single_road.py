"""Fixture A - single road, one obvious hand-computable deadline.

    base --10-- home --10-- shelter

The only egress corridor is lost at t = 40.  Nothing branches, nothing reopens,
nothing is uncertain: if this fixture disagrees with arithmetic, the kernel is
broken and no other result can be trusted.
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

EGRESS_CLOSURE = 40.0
INGRESS_MINUTES = 10.0
EGRESS_MINUTES = 10.0
PICKUP_MINUTES = 5.0


def network() -> RoadNetwork:
    n = RoadNetwork("A-single-road")
    n.add_node("base", NodeKind.BASE, "responder base")
    n.add_node("home", NodeKind.RESIDENCE, "mobility-limited resident")
    n.add_node("shelter", NodeKind.DESTINATION, "safe destination")
    n.add_road("base", "home", INGRESS_MINUTES)
    n.add_road("home", "shelter", EGRESS_MINUTES)
    return n


def build() -> Fixture:
    net = network()
    spec = MissionSpec(
        network=net, base="base", resident="home",
        destinations=(Destination("shelter"),),
        pickup=PickupModel(PICKUP_MINUTES, "p05"),
        policy=MissionPolicy(horizon=120.0),
        name="A-single-road",
    )
    scenario = HazardScenario(
        name="coherent",
        edges={"home--shelter": Timeline.closes_at(EGRESS_CLOSURE)},
        description="the single egress corridor is lost at t = 40",
    )
    return Fixture(
        key="a",
        title="single road",
        summary="One route in, one route out, one closure. The deadline is a "
                "subtraction.",
        spec=spec,
        ensemble=ScenarioEnsemble.single(scenario),
        grid=dispatch_grid(0, 30, 1),
        hand_calculation=(
            "ingress  : [t, t+10]        base -> home, never hazardous\n"
            "pickup   : [t+10, t+15]     5 min at the address\n"
            "egress   : [t+15, t+25]     home -> shelter, must be clear THROUGHOUT\n"
            "           t + 25 <= 40  =>  t <= 15\n"
            "t_dagger = 40 - 10 - 5 - 10 = 15"
        ),
        expected_windows=((0.0, 15.0),),
        expected_exact_components=((0.0, 15.0),),
        notes=(
            "The deadline is set by the egress EXIT time, not the entry time. "
            "An entry-time-only check would give t <= 25 and send the "
            "responder onto a road that burns under them.",
        ),
    )


__all__ = ["build", "network"]
