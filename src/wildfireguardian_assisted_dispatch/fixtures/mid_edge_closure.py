"""Fixture G - mid-edge closure, and what each admission policy does with it.

    base --4-- home --10-------------- shelter     (fast corridor, lost at t = 20)
                  \\--6-- mid --8--/                (slow corridor, lost at t = 40)

Pickup is 2 minutes.  Dispatch at t = 6 and the fast corridor is *safe at the
instant the responder would turn onto it* (t = 12 <= 20) and unsafe eight
minutes before they would come off it (t = 22 > 20).

That single fact separates the two admission policies:

``FULL_INTERVAL`` (default)
    The fast corridor is never entered.  The mission takes the slow road and
    arrives at t = 26.  Success.

``ENTRY_ONLY`` (the red-team policy)
    The fast corridor looks fine at the entry instant, and it promises an
    arrival at t = 22 rather than t = 26, so a myopic planner takes it.  The
    full-interval audit then reports what actually happens: the responder and
    the resident are caught on the segment at t = 20, four minutes short of the
    far end, with no modelled way back.

This is the fixture that makes the chosen semantics explicit rather than
implicit.  The failure is reported as ``CAUGHT_MID_EDGE`` with the segment, the
entry time, the instant safety was lost, and the exit time that never happened.
"""

from __future__ import annotations

from ..feasibility.dispatch import dispatch_grid
from ..hazards.scenario import HazardScenario, ScenarioEnsemble
from ..hazards.semantics import TraversalAdmission
from ..hazards.timeline import Timeline
from ..missions.policy import MissionPolicy
from ..missions.spec import Destination, MissionSpec
from ..network.graph import NodeKind, RoadNetwork
from ..service.pickup import PickupModel
from .base import Fixture

FAST_CLOSURE = 20.0
SLOW_CLOSURE = 40.0
PICKUP_MINUTES = 2.0


def network() -> RoadNetwork:
    n = RoadNetwork("G-mid-edge-closure")
    n.add_node("base", NodeKind.BASE)
    n.add_node("home", NodeKind.RESIDENCE)
    n.add_node("mid", NodeKind.JUNCTION, "midway junction on the long way round")
    n.add_node("shelter", NodeKind.DESTINATION)
    n.add_road("base", "home", 4.0)
    n.add_road("home", "shelter", 10.0, corridor="fast")
    n.add_road("home", "mid", 6.0, corridor="slow_a")
    n.add_road("mid", "shelter", 8.0, corridor="slow_b")
    return n


SCENARIO = HazardScenario(
    name="coherent",
    edges={
        "fast": Timeline.closes_at(FAST_CLOSURE),
        "slow_b": Timeline.closes_at(SLOW_CLOSURE),
    },
    description="the direct corridor is lost at t = 20; the long way round "
                "holds until t = 40",
)


def _spec(admission: TraversalAdmission, name: str) -> MissionSpec:
    return MissionSpec(
        network=network(), base="base", resident="home",
        destinations=(Destination("shelter"),),
        pickup=PickupModel(PICKUP_MINUTES, "p02"),
        policy=MissionPolicy(admission=admission, horizon=120.0),
        name=name,
    )


def build() -> Fixture:
    """Fixture G under the default full-interval admission policy."""
    return Fixture(
        key="g",
        title="mid-edge closure, full-interval admission",
        summary="A segment that cannot be cleared is never entered; the "
                "mission takes the long way round.",
        spec=_spec(TraversalAdmission.FULL_INTERVAL, "G-mid-edge-full-interval"),
        ensemble=ScenarioEnsemble.single(SCENARIO),
        grid=dispatch_grid(0, 25, 1),
        hand_calculation=(
            "arrive home t+4, pickup ends t+6\n"
            "fast: [t+6, t+16] must be clear THROUGHOUT;  t + 16 <= 20 => t <=  4\n"
            "slow: [t+6, t+12] then [t+12, t+20];         t + 20 <= 40 => t <= 20\n"
            "feasible iff either survives  =>  t <= 20\n"
            "route: fast while t <= 4 (arrival t+16), slow after (arrival t+20)"
        ),
        expected_windows=((0.0, 20.0),),
        notes=(
            "At t = 6 the fast corridor is safe at the entry instant t = 12 "
            "and unsafe at the exit instant t = 22. This policy declines it.",
        ),
    )


def build_myopic() -> Fixture:
    """Fixture G under entry-time-only admission - the policy being indicted."""
    return Fixture(
        key="g_myopic",
        title="mid-edge closure, entry-time-only admission",
        summary="The same network, planned by checking only the entry instant. "
                "The responder gets caught mid-segment.",
        spec=_spec(TraversalAdmission.ENTRY_ONLY, "G-mid-edge-entry-only"),
        ensemble=ScenarioEnsemble.single(SCENARIO),
        grid=dispatch_grid(0, 25, 1),
        hand_calculation=(
            "the myopic planner admits the fast corridor whenever it is safe at\n"
            "the entry instant:  t + 6 <= 20  =>  t <= 14, and prefers it\n"
            "because it promises arrival at t+16 instead of t+20.\n"
            "  t <=  4        fast is genuinely clear             -> SUCCESS\n"
            "  5 <= t <= 14   fast is entered and lost mid-way    -> CAUGHT_MID_EDGE\n"
            " 15 <= t <= 20   fast is already unsafe at entry,\n"
            "                 so the slow road is taken instead   -> SUCCESS\n"
            "  t >= 21        the slow road is entered and lost\n"
            "                 mid-way as well                     -> CAUGHT_MID_EDGE\n"
            "T = [0, 4] U [15, 20]"
        ),
        expected_windows=((0.0, 4.0), (15.0, 20.0)),
        expected_monotone=False,
        notes=(
            "The hole in this feasible set is manufactured entirely by the "
            "wrong hazard semantics. Under full-interval admission the same "
            "network gives the single interval [0, 20].",
            "Between t = 5 and t = 14 this policy does not merely lose the "
            "mission: it reports success right up to the audit, having driven "
            "the resident onto a road that closes under them.",
        ),
    )


__all__ = ["build", "build_myopic", "network", "SCENARIO"]
