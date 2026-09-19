"""Coherent hazard scenarios and small scenario ensembles.

A :class:`HazardScenario` is one *coherent* realisation of the fire: a single
consistent story about which roads and places are safe, and when.  A scenario
is deterministic.  Uncertainty is represented by an *ensemble* of scenarios with
weights.

Why not per-edge probabilities
------------------------------
It is tempting to give each edge a survival probability and multiply them along
a route.  That is wrong here and this package refuses to do it.  Wildfire
hazard is massively spatially and temporally correlated: the same wind shift
that closes one corridor closes its neighbours a few minutes later.  Treating
edges as independent underestimates joint failure — exactly the failure mode
that kills a responder mid-mission.  See docs/HAZARD_SEMANTICS.md.

Mission success is therefore evaluated **scenario by scenario**, and

    P_success(t) = sum of the weights of scenarios in which the whole mission
                   succeeds when dispatched at t.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from ..network.graph import Edge, RoadNetwork
from ..units import approx
from .timeline import ALWAYS_OPEN, Timeline


@dataclass(frozen=True)
class HazardScenario:
    """One coherent, deterministic hazard realisation.

    ``edges`` is keyed by **edge id or corridor id**.  An edge-id key overrides
    a corridor key for that direction; a corridor key applies to every direction
    of the road.  Corridor keying is the default because a burning road is
    burning in both directions.
    """

    name: str
    edges: Mapping[str, Timeline] = field(default_factory=dict)
    nodes: Mapping[str, Timeline] = field(default_factory=dict)
    weight: float = 1.0
    description: str = ""

    def __post_init__(self) -> None:
        if self.weight < 0:
            raise ValueError(f"scenario {self.name!r}: weight must be >= 0")
        object.__setattr__(self, "edges", dict(self.edges))
        object.__setattr__(self, "nodes", dict(self.nodes))

    def edge_timeline(self, edge: Edge) -> Timeline:
        if edge.id in self.edges:
            return self.edges[edge.id]
        if edge.corridor in self.edges:
            return self.edges[edge.corridor]
        return ALWAYS_OPEN

    def node_timeline(self, node_id: str) -> Timeline:
        return self.nodes.get(node_id, ALWAYS_OPEN)

    def with_weight(self, weight: float) -> "HazardScenario":
        return HazardScenario(self.name, self.edges, self.nodes, weight,
                              self.description)

    def validate(self, network: RoadNetwork) -> None:
        """Reject hazard keys that match nothing in the network.

        A typo'd corridor id would otherwise silently produce a hazard-free
        network and a cheerfully wrong feasibility result.
        """
        known = set(network.edges) | network.corridors()
        for key in self.edges:
            if key not in known:
                raise KeyError(
                    f"scenario {self.name!r}: hazard key {key!r} matches no edge "
                    f"or corridor in network {network.name!r}"
                )
        for key in self.nodes:
            if key not in network.nodes:
                raise KeyError(
                    f"scenario {self.name!r}: hazard key {key!r} matches no node "
                    f"in network {network.name!r}"
                )

    def describe(self) -> str:  # pragma: no cover - display
        lines = [f"scenario {self.name!r} (weight {self.weight:g})"]
        if self.description:
            lines.append(f"  {self.description}")
        for key, tl in sorted(self.edges.items()):
            lines.append(f"  edge/corridor {key}: {tl.describe()}")
        for key, tl in sorted(self.nodes.items()):
            lines.append(f"  node {key}: {tl.describe()}")
        if not self.edges and not self.nodes:
            lines.append("  no hazards (everything always safe)")
        return "\n".join(lines)


def deterministic(name: str = "deterministic", **kwargs) -> HazardScenario:
    """A single-scenario helper, for the deterministic-first workflow."""
    return HazardScenario(name=name, **kwargs)


@dataclass(frozen=True)
class ScenarioEnsemble:
    """A small, explicit set of weighted coherent scenarios.

    Weights are normalised to sum to 1 so that ``P_success`` is a probability.
    Ensembles in this phase are *small and hand-authored*: they are a sensitivity
    device, not a calibrated forecast.  Nothing here claims the weights are
    empirically grounded (docs/ASSUMPTIONS.md A-006).
    """

    scenarios: tuple[HazardScenario, ...]

    def __post_init__(self) -> None:
        if not self.scenarios:
            raise ValueError("an ensemble needs at least one scenario")
        names = [s.name for s in self.scenarios]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate scenario names in ensemble: {names}")
        total = sum(s.weight for s in self.scenarios)
        if total <= 0:
            raise ValueError("ensemble weights must sum to something positive")
        if not approx(total, 1.0):
            object.__setattr__(
                self, "scenarios",
                tuple(s.with_weight(s.weight / total) for s in self.scenarios),
            )

    @classmethod
    def single(cls, scenario: HazardScenario) -> "ScenarioEnsemble":
        return cls((scenario.with_weight(1.0),))

    @classmethod
    def of(cls, scenarios: Iterable[HazardScenario]) -> "ScenarioEnsemble":
        return cls(tuple(scenarios))

    @property
    def is_deterministic(self) -> bool:
        return len(self.scenarios) == 1

    def weight_of(self, name: str) -> float:
        for s in self.scenarios:
            if s.name == name:
                return s.weight
        raise KeyError(f"no scenario named {name!r}")

    def validate(self, network: RoadNetwork) -> None:
        for s in self.scenarios:
            s.validate(network)

    def __iter__(self):
        return iter(self.scenarios)

    def __len__(self) -> int:
        return len(self.scenarios)

    def describe(self) -> str:  # pragma: no cover - display
        return "\n".join(s.describe() for s in self.scenarios)


__all__ = ["HazardScenario", "ScenarioEnsemble", "deterministic"]
