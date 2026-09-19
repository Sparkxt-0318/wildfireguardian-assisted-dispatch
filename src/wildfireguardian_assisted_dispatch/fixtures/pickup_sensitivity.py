"""Fixture D - pickup duration sensitivity.

    base --8-- home --12-- shelter,  egress corridor lost at t = 50

Nothing here is subtle, and that is the point: the feasible set must move
one-for-one with on-scene time.  Every minute of pickup is a minute off the
dispatch envelope, and the fixture pins that to the four scenario durations
(2, 5, 10, 15 minutes) the research plan uses.
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

EGRESS_CLOSURE = 50.0
INGRESS_MINUTES = 8.0
EGRESS_MINUTES = 12.0


def network() -> RoadNetwork:
    n = RoadNetwork("D-pickup-sensitivity")
    n.add_node("base", NodeKind.BASE)
    n.add_node("home", NodeKind.RESIDENCE)
    n.add_node("shelter", NodeKind.DESTINATION)
    n.add_road("base", "home", INGRESS_MINUTES)
    n.add_road("home", "shelter", EGRESS_MINUTES)
    return n


SCENARIO = HazardScenario(
    name="coherent",
    edges={"home--shelter": Timeline.closes_at(EGRESS_CLOSURE)},
    description="the egress corridor is lost at t = 50",
)


def latest_dispatch_for(pickup_minutes: float) -> float:
    """The hand formula: ``50 - 8 - p - 12``."""
    return EGRESS_CLOSURE - INGRESS_MINUTES - pickup_minutes - EGRESS_MINUTES


def build(pickup_minutes: float = 5.0) -> Fixture:
    net = network()
    spec = MissionSpec(
        network=net, base="base", resident="home",
        destinations=(Destination("shelter"),),
        pickup=PickupModel(pickup_minutes, f"sweep-{pickup_minutes:g}min"),
        policy=MissionPolicy(horizon=150.0),
        name="D-pickup-sensitivity",
    )
    latest = latest_dispatch_for(pickup_minutes)
    return Fixture(
        key="d",
        title="pickup sensitivity",
        summary="On-scene time comes straight off the dispatch envelope, "
                "minute for minute.",
        spec=spec,
        ensemble=ScenarioEnsemble.single(SCENARIO),
        grid=dispatch_grid(0, 40, 1),
        hand_calculation=(
            "t + 8 + p + 12 <= 50   =>   t <= 30 - p\n"
            "p =  2 min  ->  t <= 28\n"
            "p =  5 min  ->  t <= 25\n"
            "p = 10 min  ->  t <= 20\n"
            "p = 15 min  ->  t <= 15\n"
            f"this instance uses p = {pickup_minutes:g} min  ->  t <= {latest:g}"
        ),
        expected_windows=((0.0, latest),) if latest >= 0 else (),
        notes=(
            "The four durations are scenario parameters. They are not "
            "validated medical or triage categories and must never be "
            "reported as such.",
        ),
    )


__all__ = ["build", "network", "latest_dispatch_for", "SCENARIO"]
