"""Fixture B - two routes, one closes earlier.

    base --5-- home --5-- north_j --5--  shelter      (fast, fragile)
                    \\--10-- south_j --10-- /          (slow, durable)

The fast route dies at t = 35, the slow one at t = 60.  The interesting content
is the *switch*: up to a point the planner takes the fast road, after that it
must take the slow one, and the feasible set extends well past the moment the
fast road is lost.  A dispatcher who only knows about the fast route would
declare the mission infeasible 15 minutes too early.

:func:`build_ensemble` is the same network under three coherent scenarios, and
exists to show ``P_success`` doing its job on numbers that can be checked by
hand.
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

NORTH_CLOSURE = 35.0
SOUTH_CLOSURE = 60.0
PICKUP_MINUTES = 5.0


def network() -> RoadNetwork:
    n = RoadNetwork("B-two-routes")
    n.add_node("base", NodeKind.BASE)
    n.add_node("home", NodeKind.RESIDENCE)
    n.add_node("north_j", NodeKind.JUNCTION, "ridge junction")
    n.add_node("south_j", NodeKind.JUNCTION, "valley junction")
    n.add_node("shelter", NodeKind.DESTINATION)
    n.add_road("base", "home", 5.0)
    n.add_road("home", "north_j", 5.0)
    n.add_road("north_j", "shelter", 5.0)
    n.add_road("home", "south_j", 10.0)
    n.add_road("south_j", "shelter", 10.0)
    return n


def _spec(net: RoadNetwork) -> MissionSpec:
    return MissionSpec(
        network=net, base="base", resident="home",
        destinations=(Destination("shelter"),),
        pickup=PickupModel(PICKUP_MINUTES, "p05"),
        policy=MissionPolicy(horizon=150.0),
        name="B-two-routes",
    )


NOMINAL = HazardScenario(
    name="nominal",
    edges={
        "north_j--shelter": Timeline.closes_at(NORTH_CLOSURE),
        "shelter--south_j": Timeline.closes_at(SOUTH_CLOSURE),
    },
    description="fast ridge road lost at 35, slow valley road at 60",
)

WIND_SHIFT = HazardScenario(
    name="wind_shift",
    edges={
        "north_j--shelter": Timeline.closes_at(20.0),
        "shelter--south_j": Timeline.closes_at(SOUTH_CLOSURE),
    },
    weight=0.3,
    description="the ridge road goes 15 minutes earlier than nominal",
)

SOUTH_FLANK = HazardScenario(
    name="south_flank",
    edges={
        "north_j--shelter": Timeline.closes_at(NORTH_CLOSURE),
        "shelter--south_j": Timeline.closes_at(28.0),
    },
    weight=0.2,
    description="the fire runs down the valley and takes the slow road first",
)


def build() -> Fixture:
    net = network()
    return Fixture(
        key="b",
        title="two routes, one closes earlier",
        summary="The feasible set is governed by the surviving route, not the "
                "obvious one.",
        spec=_spec(net),
        ensemble=ScenarioEnsemble.single(NOMINAL),
        grid=dispatch_grid(0, 40, 1),
        hand_calculation=(
            "arrive home t+5, pickup ends t+10\n"
            "north: [t+10, t+15] then [t+15, t+20];  t + 20 <= 35  =>  t <= 15\n"
            "south: [t+10, t+20] then [t+20, t+30];  t + 30 <= 60  =>  t <= 30\n"
            "feasible iff EITHER route survives  =>  t <= 30\n"
            "chosen route: north while t <= 15 (earlier arrival), south after"
        ),
        expected_windows=((0.0, 30.0),),
        expected_exact_components=((0.0, 30.0),),
        notes=(
            "For t <= 15 the mission arrives at t+20 via the ridge; from t = 16 "
            "it arrives at t+30 via the valley. Feasibility survives the loss "
            "of the fast route; the arrival time jumps by 10 minutes.",
        ),
    )


def build_ensemble() -> Fixture:
    """Fixture B under a three-scenario coherent ensemble."""
    net = network()
    ensemble = ScenarioEnsemble.of((
        NOMINAL.with_weight(0.5), WIND_SHIFT, SOUTH_FLANK,
    ))
    spec = _spec(net)
    return Fixture(
        key="b_ensemble",
        title="two routes under a three-scenario ensemble",
        summary="P_success is a sum of coherent scenario weights, never a "
                "product of edge probabilities.",
        spec=MissionSpec(
            network=spec.network, base=spec.base, resident=spec.resident,
            destinations=spec.destinations, pickup=spec.pickup,
            policy=spec.policy, travel=spec.travel,
            name="B-two-routes-ensemble",
        ),
        ensemble=ensemble,
        grid=dispatch_grid(0, 40, 1),
        threshold=1.0,
        hand_calculation=(
            "nominal     (w=0.5): north t<=15, south t<=30  -> succeeds t <= 30\n"
            "wind_shift  (w=0.3): north t<= 0, south t<=30  -> succeeds t <= 30\n"
            "south_flank (w=0.2): north t<=15, south never  -> succeeds t <= 15\n"
            "P_success(t) = 1.0 for t <= 15\n"
            "             = 0.8 for 16 <= t <= 30\n"
            "             = 0.0 for t >= 31\n"
            "T at q=1.0 is [0, 15];  at q=0.8 it is [0, 30]"
        ),
        expected_windows=((0.0, 15.0),),
        expected_exact_components=((0.0, 15.0),),
        expected_p_success={0.0: 1.0, 15.0: 1.0, 16.0: 0.8, 30.0: 0.8, 31.0: 0.0},
        notes=(
            "Under an independent-edge product model the same inputs would "
            "give a smooth, higher survival number with no threshold at t = 15. "
            "That number would be fiction.",
        ),
    )


__all__ = ["build", "build_ensemble", "network"]
