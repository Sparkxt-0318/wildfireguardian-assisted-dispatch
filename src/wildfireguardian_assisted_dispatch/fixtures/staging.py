"""Fixture H - staging-location comparison.

    base_north --10-- home --10-- shelter
    base_south --20--/

The same resident, the same egress corridor, two candidate responder staging
points.  The northern base is twice as close.  Its approach corridor is also
the one the fire takes first:

    north approach lost at t = 22
    egress corridor lost at t = 50
    south approach never lost

The lesson is that **proximity is not the dispatch envelope**.  Staging at the
near base buys a shorter mission and a *smaller* feasible dispatch set, because
the binding constraint moves from the egress leg onto the approach.

This is a comparison of two independently-specified missions, not an
optimisation over staging locations: the repository answers "is this mission
feasible", once per mission.
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

NORTH_APPROACH_CLOSURE = 22.0
EGRESS_CLOSURE = 50.0
PICKUP_MINUTES = 5.0


def network() -> RoadNetwork:
    n = RoadNetwork("H-staging")
    n.add_node("base_north", NodeKind.BASE, "near staging point")
    n.add_node("base_south", NodeKind.BASE, "far staging point")
    n.add_node("home", NodeKind.RESIDENCE)
    n.add_node("shelter", NodeKind.DESTINATION)
    n.add_road("base_north", "home", 10.0, corridor="north_approach")
    n.add_road("base_south", "home", 20.0, corridor="south_approach")
    n.add_road("home", "shelter", 10.0, corridor="egress")
    return n


SCENARIO = HazardScenario(
    name="coherent",
    edges={
        "north_approach": Timeline.closes_at(NORTH_APPROACH_CLOSURE),
        "egress": Timeline.closes_at(EGRESS_CLOSURE),
    },
    description="the northern approach is lost at t = 22; the egress corridor "
                "holds until t = 50",
)


def _spec(base: str, name: str) -> MissionSpec:
    return MissionSpec(
        network=network(), base=base, resident="home",
        destinations=(Destination("shelter"),),
        pickup=PickupModel(PICKUP_MINUTES, "p05"),
        policy=MissionPolicy(horizon=150.0),
        name=name,
    )


def build_north() -> Fixture:
    return Fixture(
        key="h_north",
        title="staging comparison: near base",
        summary="The near staging point is bound by its own approach corridor, "
                "not by the egress.",
        spec=_spec("base_north", "H-staging-north"),
        ensemble=ScenarioEnsemble.single(SCENARIO),
        grid=dispatch_grid(0, 30, 1),
        hand_calculation=(
            "ingress: [t, t+10] on the north approach, clear THROUGHOUT\n"
            "         t + 10 <= 22  =>  t <= 12      <-- binding\n"
            "pickup : [t+10, t+15]\n"
            "egress : [t+15, t+25];  t + 25 <= 50  =>  t <= 25\n"
            "T = [0, 12];  mission duration 25 min"
        ),
        expected_windows=((0.0, 12.0),),
        expected_exact_components=((0.0, 12.0),),
        notes=(
            "Ten minutes closer to the resident, and three dispatch minutes "
            "worse off than the far base.",
        ),
    )


def build_south() -> Fixture:
    return Fixture(
        key="h_south",
        title="staging comparison: far base",
        summary="The far staging point is bound by the egress corridor, and "
                "keeps a larger feasible dispatch set.",
        spec=_spec("base_south", "H-staging-south"),
        ensemble=ScenarioEnsemble.single(SCENARIO),
        grid=dispatch_grid(0, 30, 1),
        hand_calculation=(
            "ingress: [t, t+20] on the south approach, never hazardous\n"
            "pickup : [t+20, t+25]\n"
            "egress : [t+25, t+35];  t + 35 <= 50  =>  t <= 15   <-- binding\n"
            "T = [0, 15];  mission duration 35 min"
        ),
        expected_windows=((0.0, 15.0),),
        expected_exact_components=((0.0, 15.0),),
        notes=(
            "A longer mission (35 min vs 25 min) with a wider dispatch window "
            "(t <= 15 vs t <= 12). Mission duration and dispatch envelope are "
            "different quantities and can order oppositely.",
        ),
    )


__all__ = ["build_north", "build_south", "network", "SCENARIO"]
