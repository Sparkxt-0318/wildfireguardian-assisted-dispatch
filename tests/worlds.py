"""Random synthetic worlds for property-based testing.

The generators here produce **monotone hazard worlds**: every timeline is
closure-only, ``[0, T]``, so hazard can only ever get worse with time.  That
restriction is deliberate and load-bearing.  Several of the properties under
test (longer pickup cannot help, slower roads cannot help, earlier closures
cannot help) are simply *false* in a world with reopening corridors — fixture
F is the counterexample — so imposing them on a general world would be testing
a claim the model does not make.

Everything generated here is tiny: four or five nodes, a handful of roads.
The exact interval solver runs on each world, so the tests are checking a
closed-form answer rather than a sampled one.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from hypothesis import strategies as st

from wildfireguardian_assisted_dispatch.hazards.scenario import (
    HazardScenario,
    ScenarioEnsemble,
)
from wildfireguardian_assisted_dispatch.hazards.timeline import Timeline
from wildfireguardian_assisted_dispatch.missions.policy import MissionPolicy
from wildfireguardian_assisted_dispatch.missions.spec import Destination, MissionSpec
from wildfireguardian_assisted_dispatch.network.graph import NodeKind, RoadNetwork
from wildfireguardian_assisted_dispatch.service.pickup import PickupModel

HORIZON = 400.0
STUDY_RANGE = (0.0, 120.0)

#: Corridor ids of the generated topology.  Two routes in, two routes out.
CORRIDORS = ("c_base_mid", "c_base_home", "c_mid_home", "c_home_shelter",
             "c_mid_shelter")


@dataclass(frozen=True)
class World:
    """A generated mission plus a single coherent, closure-only scenario."""

    travel: dict[str, float]
    closures: dict[str, float]
    pickup: float

    def network(self) -> RoadNetwork:
        n = RoadNetwork("generated")
        n.add_node("base", NodeKind.BASE)
        n.add_node("mid", NodeKind.JUNCTION)
        n.add_node("home", NodeKind.RESIDENCE)
        n.add_node("shelter", NodeKind.DESTINATION)
        n.add_road("base", "mid", self.travel["c_base_mid"], corridor="c_base_mid")
        n.add_road("base", "home", self.travel["c_base_home"], corridor="c_base_home")
        n.add_road("mid", "home", self.travel["c_mid_home"], corridor="c_mid_home")
        n.add_road("home", "shelter", self.travel["c_home_shelter"],
                   corridor="c_home_shelter")
        n.add_road("mid", "shelter", self.travel["c_mid_shelter"],
                   corridor="c_mid_shelter")
        return n

    def spec(self) -> MissionSpec:
        return MissionSpec(
            network=self.network(), base="base", resident="home",
            destinations=(Destination("shelter"),),
            pickup=PickupModel(self.pickup, "generated"),
            policy=MissionPolicy(horizon=HORIZON),
            name="generated",
        )

    def scenario(self, name: str = "monotone") -> HazardScenario:
        return HazardScenario(
            name=name,
            edges={c: Timeline.closes_at(self.closures[c]) for c in CORRIDORS},
            description="closure-only hazard: every corridor is lost once and "
                        "never reopens",
        )

    def ensemble(self) -> ScenarioEnsemble:
        return ScenarioEnsemble.single(self.scenario())

    # -- monotone perturbations --------------------------------------------
    def with_pickup(self, pickup: float) -> "World":
        return replace(self, pickup=pickup)

    def slower_by(self, delta: float) -> "World":
        """Every road takes ``delta`` minutes longer."""
        return replace(self, travel={k: v + delta for k, v in self.travel.items()})

    def hazard_earlier_by(self, delta: float) -> "World":
        """Every finite closure happens ``delta`` minutes sooner (floored at 0)."""
        return replace(self, closures={k: max(0.0, v - delta)
                                       for k, v in self.closures.items()})

    def without_hazard(self) -> "World":
        return replace(self, closures={k: float("inf") for k in self.closures})


_travel = st.floats(min_value=1.0, max_value=25.0, allow_nan=False,
                    allow_infinity=False).map(lambda x: round(x, 2))
_closure = st.one_of(
    st.floats(min_value=0.0, max_value=200.0, allow_nan=False,
              allow_infinity=False).map(lambda x: round(x, 2)),
    st.just(float("inf")),
)


@st.composite
def worlds(draw, pickup=st.floats(min_value=0.0, max_value=20.0,
                                  allow_nan=False, allow_infinity=False)) -> World:
    return World(
        travel={c: draw(_travel) for c in CORRIDORS},
        closures={c: draw(_closure) for c in CORRIDORS},
        pickup=round(draw(pickup), 2),
    )


@st.composite
def safe_worlds(draw) -> World:
    """A world with no hazards at all."""
    return draw(worlds()).without_hazard()


__all__ = ["World", "worlds", "safe_worlds", "CORRIDORS", "HORIZON", "STUDY_RANGE"]
