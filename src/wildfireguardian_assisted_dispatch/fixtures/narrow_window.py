"""Fixture N - a feasible window narrower than the default sweep step.

    base --5-- home --5-- shelter,  pickup 2 min

The egress corridor is safe only on ``[18.3, 23.4]``.  The egress leg occupies
``[t+7, t+12]``, so

    t + 7 >= 18.3  and  t + 12 <= 23.4   =>   11.3 <= t <= 11.4

The feasible dispatch set is a single component **0.1 minutes wide** — six
seconds.  A sweep on the default one-minute grid samples t = 11 and t = 12 and
finds *neither*, so it reports the mission infeasible at every sampled dispatch
time.  ``refine_transitions`` cannot rescue it: there is no observed transition
to refine.

This fixture is the counterexample that motivates the exact interval solver
(``validation/exact_intervals.py``) and the temporal-resolution discipline in
``docs/TEMPORAL_RESOLUTION.md``.  It is deliberately kept in the fixture set as
a standing reminder that *a grid sweep reporting an empty feasible set is not
evidence that the set is empty*.
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

WINDOW_OPEN = 18.3
WINDOW_CLOSE = 23.4
PICKUP_MINUTES = 2.0

#: The exact feasible set, derived by hand in the module docstring.
TRUE_WINDOW = (WINDOW_OPEN - 7.0, WINDOW_CLOSE - 12.0)   # (11.3, 11.4)


def network() -> RoadNetwork:
    n = RoadNetwork("N-narrow-window")
    n.add_node("base", NodeKind.BASE)
    n.add_node("home", NodeKind.RESIDENCE)
    n.add_node("shelter", NodeKind.DESTINATION)
    n.add_road("base", "home", 5.0)
    n.add_road("home", "shelter", 5.0, corridor="egress")
    return n


SCENARIO = HazardScenario(
    name="narrow",
    edges={"egress": Timeline.from_windows([[WINDOW_OPEN, WINDOW_CLOSE]])},
    description="the egress corridor is passable only between t = 18.3 and "
                "t = 23.4",
)


def _spec() -> MissionSpec:
    return MissionSpec(
        network=network(), base="base", resident="home",
        destinations=(Destination("shelter"),),
        pickup=PickupModel(PICKUP_MINUTES, "p02"),
        policy=MissionPolicy(horizon=120.0),
        name="N-narrow-window",
    )


def build() -> Fixture:
    return Fixture(
        key="n",
        title="feasible window narrower than the sweep step",
        summary="A six-second feasible window that a one-minute grid sweep "
                "reports as no window at all.",
        spec=_spec(),
        ensemble=ScenarioEnsemble.single(SCENARIO),
        grid=dispatch_grid(0, 20, 1),
        hand_calculation=(
            "egress corridor safe only on [18.3, 23.4]\n"
            "arrive home t+5, pickup ends t+7, egress occupies [t+7, t+12]\n"
            "  t + 7  >= 18.3  =>  t >= 11.3\n"
            "  t + 12 <= 23.4  =>  t <= 11.4\n"
            "TRUE feasible set   : [11.3, 11.4]   (0.1 min = 6 s wide)\n"
            "SAMPLED on a 1-min grid: empty - neither t=11 nor t=12 is feasible"
        ),
        expected_windows=(),                       # what the grid sweep reports
        expected_exact_components=(TRUE_WINDOW,),  # what is actually true
        notes=(
            "The grid result and the exact result disagree here BY DESIGN. The "
            "grid is not wrong about its samples; it is silent about everything "
            "between them, and silence is not emptiness.",
            "A sweep that reports an empty feasible set must never be quoted as "
            "'the mission is infeasible' without the exact solver or a stated "
            "temporal resolution.",
        ),
    )


def build_resolved() -> Fixture:
    """The same study on a grid fine enough to see the window."""
    fixture = build()
    return Fixture(
        key="n_resolved",
        title="the same narrow window, sampled at 0.05 min",
        summary="Resolution chosen below the feature size; the grid now agrees "
                "with the exact solver.",
        spec=fixture.spec,
        ensemble=fixture.ensemble,
        grid=dispatch_grid(11.0, 12.0, 0.05),
        hand_calculation=(
            "same arithmetic as fixture n, sampled at 0.05 min over [11, 12]:\n"
            "grid points 11.30, 11.35, 11.40 are feasible; 11.25 and 11.45 are not\n"
            "sampled windows: [11.3, 11.4]"
        ),
        expected_windows=((11.3, 11.4),),
        expected_exact_components=(TRUE_WINDOW,),
        # The studied range starts at t = 11, which is infeasible, so the
        # sampled feasibility indicator rises before it falls. That is what
        # `is_monotone` reports, and it is why monotonicity of the indicator is
        # NOT the predicate that licenses a dispatch-by deadline; see
        # ExactFeasibleSet.is_dispatch_by_deadline.
        expected_monotone=False,
        notes=(
            "Sampling finer than the narrowest feature you care about is the "
            "only way a grid can be trusted - and you generally do not know "
            "the feature size in advance, which is why the exact solver exists.",
        ),
    )


__all__ = ["build", "build_resolved", "network", "SCENARIO", "TRUE_WINDOW"]
