"""Fixture E - temporary refuge as an alternative destination.

    base --6-- home --5--  refuge    (near, but overrun at t = 60)
                    --20-- shelter   (far, but holds)

The refuge is the obvious choice: it is fifteen minutes closer.  It is also a
place that burns at t = 60, so arriving there at t = 59 is not a completed
mission — it is the same emergency, relocated.

That is what ``min_safe_dwell`` encodes: a destination only ends the mission if
it stays safe for a declared period after arrival.  Set it to zero and the
model will happily "succeed" by parking the resident in front of the fire.
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

REFUGE_OVERRUN = 60.0
REFUGE_DWELL = 30.0
SHELTER_CORRIDOR_CLOSURE = 70.0
PICKUP_MINUTES = 5.0


def network() -> RoadNetwork:
    n = RoadNetwork("E-temporary-refuge")
    n.add_node("base", NodeKind.BASE)
    n.add_node("home", NodeKind.RESIDENCE)
    n.add_node("refuge", NodeKind.REFUGE, "school gymnasium, not a hardened shelter")
    n.add_node("shelter", NodeKind.DESTINATION, "regional evacuation centre")
    n.add_road("base", "home", 6.0)
    n.add_road("home", "refuge", 5.0)
    n.add_road("home", "shelter", 20.0)
    return n


def build() -> Fixture:
    net = network()
    spec = MissionSpec(
        network=net, base="base", resident="home",
        destinations=(
            Destination("refuge", kind=NodeKind.REFUGE,
                        min_safe_dwell=REFUGE_DWELL,
                        label="temporary refuge"),
            Destination("shelter", min_safe_dwell=0.0,
                        label="durable destination"),
        ),
        pickup=PickupModel(PICKUP_MINUTES, "p05"),
        policy=MissionPolicy(horizon=180.0),
        name="E-temporary-refuge",
    )
    scenario = HazardScenario(
        name="coherent",
        edges={"home--shelter": Timeline.closes_at(SHELTER_CORRIDOR_CLOSURE)},
        nodes={"refuge": Timeline.closes_at(REFUGE_OVERRUN)},
        description="the refuge is overrun at t = 60; the long corridor holds "
                    "until t = 70",
    )
    return Fixture(
        key="e",
        title="temporary refuge",
        summary="A near refuge that does not hold is not a destination.",
        spec=spec,
        ensemble=ScenarioEnsemble.single(scenario),
        grid=dispatch_grid(0, 50, 1),
        hand_calculation=(
            "arrive home t+6, pickup ends t+11\n"
            "refuge : arrival t+16, must stay safe for 30 min\n"
            "         t + 16 + 30 <= 60   =>   t <= 14\n"
            "shelter: arrival t+31, corridor clear throughout\n"
            "         t + 31 <= 70        =>   t <= 39\n"
            "mission feasible iff EITHER destination qualifies  =>  t <= 39\n"
            "chosen destination: refuge while t <= 14 (earliest arrival), "
            "shelter after"
        ),
        expected_windows=((0.0, 39.0),),
        expected_exact_components=((0.0, 39.0),),
        notes=(
            "At t = 15 the refuge stops qualifying and the mission gets 15 "
            "minutes longer overnight: arrival jumps from t+16 to t+31. "
            "Feasibility does not break, but the margin does.",
            "With min_safe_dwell = 0 the refuge would qualify until t = 44 and "
            "the model would report success for missions that end with the "
            "resident inside the fire perimeter.",
        ),
    )


__all__ = ["build", "network"]
