"""The mission specification.

    Responder Base  ->  Resident  ->  Safe Destination

A :class:`MissionSpec` is dispatch-time-independent: it says who, where, how
long the pickup takes and under which rules.  The dispatch time is an *argument*
to evaluation, because the whole research question is how the answer varies
with it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ..network.graph import NodeKind, RoadNetwork
from ..network.travel import DEFAULT_TRAVEL_MODEL, TravelModel
from ..service.pickup import DEFAULT_PICKUP, PickupModel
from ..units import INFINITY, geq, leq
from .policy import DEFAULT_POLICY, MissionPolicy


@dataclass(frozen=True)
class Destination:
    """A place the mission may legitimately end at.

    ``min_safe_dwell`` is what separates a *shelter* from a *temporary refuge*.
    Arriving at a refuge one minute before it is overrun is not a completed
    mission; it is a mission that ends in the same place the resident started,
    only later.  The destination node must therefore be safe throughout
    ``[arrival, arrival + min_safe_dwell]``.

    ``available_from`` / ``available_until`` model administrative availability
    (a shelter that opens at 09:00, a staging area that is struck at 14:00) and
    are independent of the node's hazard timeline; both constraints apply.
    """

    node: str
    kind: NodeKind = NodeKind.DESTINATION
    min_safe_dwell: float = 0.0
    available_from: float = 0.0
    available_until: float = INFINITY
    label: str = ""
    priority: int = 0

    def __post_init__(self) -> None:
        if self.min_safe_dwell < 0:
            raise ValueError("min_safe_dwell must be >= 0")
        if self.available_until < self.available_from:
            raise ValueError(
                f"destination {self.node!r}: available_until precedes available_from"
            )

    def accepts_arrival(self, t: float) -> bool:
        return geq(t, self.available_from) and leq(t, self.available_until)

    def describe(self) -> str:  # pragma: no cover - display
        bits = [f"destination {self.node}"]
        if self.min_safe_dwell:
            bits.append(f"min safe dwell {self.min_safe_dwell:g} min")
        if self.available_from or self.available_until != INFINITY:
            until = ("inf" if self.available_until == INFINITY
                     else f"{self.available_until:g}")
            bits.append(f"available [{self.available_from:g}, {until}]")
        return ", ".join(bits)


@dataclass(frozen=True)
class MissionSpec:
    """Everything about the mission except when it is dispatched."""

    network: RoadNetwork
    base: str
    resident: str
    destinations: tuple[Destination, ...]
    pickup: PickupModel = DEFAULT_PICKUP
    policy: MissionPolicy = DEFAULT_POLICY
    travel: TravelModel = DEFAULT_TRAVEL_MODEL
    name: str = "mission"

    def __post_init__(self) -> None:
        if not self.destinations:
            raise ValueError("a mission needs at least one destination")
        object.__setattr__(self, "destinations", tuple(self.destinations))
        self.network.validate(
            [self.base, self.resident, *(d.node for d in self.destinations)]
        )
        if self.base == self.resident:
            raise ValueError("base and resident must be distinct nodes")
        for d in self.destinations:
            if d.node == self.resident:
                raise ValueError(
                    f"destination {d.node!r} is the resident's own node: the "
                    "mission would be trivially complete without evacuating"
                )

    @property
    def destination_nodes(self) -> tuple[str, ...]:
        return tuple(d.node for d in self.destinations)

    def destination(self, node: str) -> Destination:
        for d in self.destinations:
            if d.node == node:
                return d
        raise KeyError(f"{node!r} is not a destination of mission {self.name!r}")

    def with_pickup(self, pickup: PickupModel | float) -> "MissionSpec":
        """Copy with a different pickup duration (used by the D sensitivity sweep)."""
        model = pickup if isinstance(pickup, PickupModel) else PickupModel(float(pickup))
        return MissionSpec(
            network=self.network, base=self.base, resident=self.resident,
            destinations=self.destinations, pickup=model, policy=self.policy,
            travel=self.travel, name=self.name,
        )

    def with_policy(self, policy: MissionPolicy) -> "MissionSpec":
        return MissionSpec(
            network=self.network, base=self.base, resident=self.resident,
            destinations=self.destinations, pickup=self.pickup, policy=policy,
            travel=self.travel, name=self.name,
        )

    def describe(self) -> str:  # pragma: no cover - display
        lines = [
            f"mission {self.name!r} on network {self.network.name!r}",
            f"  base      : {self.base}",
            f"  resident  : {self.resident}",
            f"  {self.pickup.describe()}",
            f"  policy    : {self.policy.describe()}",
        ]
        lines += [f"  {d.describe()}" for d in self.destinations]
        return "\n".join(lines)


def destinations_from(nodes: Iterable[str] | Sequence[Destination]) -> tuple[Destination, ...]:
    """Convenience: accept plain node ids or full Destination objects."""
    out: list[Destination] = []
    for n in nodes:
        out.append(n if isinstance(n, Destination) else Destination(node=str(n)))
    return tuple(out)


__all__ = ["Destination", "MissionSpec", "destinations_from"]
