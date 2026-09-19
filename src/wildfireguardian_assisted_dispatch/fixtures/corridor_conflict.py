"""Fixture C - inbound vs outbound conflict on one corridor.

    base --10-- junction --8-- home        (home is on a dead-end spur)
                    |
                    6
                    |
                 shelter

The resident lives up a spur.  The responder drives in along the spur and must
drive back out along **the same corridor, in reverse**, with the pickup sitting
between the two traversals.  The spur is lost at t = 45.

This is the fixture that punishes one-directional thinking.  The inbound
traversal is comfortably clear; the constraint is entirely on the outbound one,
and the gap between the two answers is exactly the round trip plus the pickup.
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

SPUR_CLOSURE = 45.0
APPROACH_MINUTES = 10.0
SPUR_MINUTES = 8.0
EXIT_MINUTES = 6.0
PICKUP_MINUTES = 5.0


def network() -> RoadNetwork:
    n = RoadNetwork("C-corridor-conflict")
    n.add_node("base", NodeKind.BASE)
    n.add_node("junction", NodeKind.JUNCTION, "spur head")
    n.add_node("home", NodeKind.RESIDENCE, "dead-end spur address")
    n.add_node("shelter", NodeKind.DESTINATION)
    n.add_road("base", "junction", APPROACH_MINUTES)
    n.add_road("junction", "home", SPUR_MINUTES, corridor="spur")
    n.add_road("junction", "shelter", EXIT_MINUTES)
    return n


def build() -> Fixture:
    net = network()
    spec = MissionSpec(
        network=net, base="base", resident="home",
        destinations=(Destination("shelter"),),
        pickup=PickupModel(PICKUP_MINUTES, "p05"),
        policy=MissionPolicy(horizon=150.0),
        name="C-corridor-conflict",
    )
    scenario = HazardScenario(
        name="coherent",
        edges={"spur": Timeline.closes_at(SPUR_CLOSURE)},
        description="the dead-end spur is lost at t = 45, in both directions",
    )
    return Fixture(
        key="c",
        title="inbound vs outbound conflict",
        summary="The same corridor is used in reverse on the way out; the "
                "outbound traversal sets the deadline.",
        spec=spec,
        ensemble=ScenarioEnsemble.single(scenario),
        grid=dispatch_grid(0, 30, 1),
        hand_calculation=(
            "approach  : [t,      t+10]   base -> junction\n"
            "spur in   : [t+10,   t+18]   junction -> home      (corridor 'spur')\n"
            "pickup    : [t+18,   t+23]\n"
            "spur out  : [t+23,   t+31]   home -> junction      (corridor 'spur')\n"
            "exit      : [t+31,   t+37]   junction -> shelter\n"
            "binding constraint is the OUTBOUND spur:  t + 31 <= 45  =>  t <= 14\n"
            "t_dagger = 45 - (10 + 8 + 5 + 8) = 14"
        ),
        expected_windows=((0.0, 14.0),),
        notes=(
            "Checking only the inbound traversal gives t + 18 <= 45, i.e. "
            "t <= 27: thirteen minutes of pure fiction, and every one of them "
            "strands the responder and the resident on the spur.",
            "Both directions share the corridor id 'spur', which is why the "
            "reverse traversal consults the same timeline.",
        ),
    )


__all__ = ["build", "network"]
