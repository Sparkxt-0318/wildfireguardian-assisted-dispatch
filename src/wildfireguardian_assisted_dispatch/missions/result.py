"""Mission records: what actually happened, minute by minute.

The evaluator never returns a bare boolean.  A mission that fails must say
where, when, and against which hazard, because the failure reason is the
research output — "infeasible" on its own is not a finding.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Sequence

from ..hazards.semantics import ElementAssessment
from ..units import INFINITY


class FailureReason(str, Enum):
    """Why a mission could not be completed.

    Ordered roughly by how far the mission got; :func:`progress_rank` turns
    that into the priority used when several candidate plans fail differently.
    """

    NONE = "none"
    BASE_UNSAFE_AT_DISPATCH = "base_unsafe_at_dispatch"
    NO_SAFE_ROUTE_INGRESS = "no_safe_route_ingress"
    RESIDENT_NODE_UNSAFE_ON_ARRIVAL = "resident_node_unsafe_on_arrival"
    SERVICE_WINDOW_UNSAFE = "service_window_unsafe"
    NO_SAFE_ROUTE_EGRESS = "no_safe_route_egress"
    DESTINATION_UNAVAILABLE = "destination_unavailable"
    REFUGE_DWELL_UNSAFE = "refuge_dwell_unsafe"
    CAUGHT_MID_EDGE = "caught_mid_edge"
    HORIZON_EXCEEDED = "horizon_exceeded"


#: Failure reasons ordered by how much they tell the reader, which for this
#: model is "how far into the mission the plan got".  HORIZON_EXCEEDED sits at
#: the bottom on purpose: it is a budget artefact, not a hazard finding, and a
#: branch that looped around the network until the clock ran out must never
#: outrank a branch that hit an actual closure.
_PROGRESS_ORDER: tuple[FailureReason, ...] = (
    FailureReason.HORIZON_EXCEEDED,
    FailureReason.BASE_UNSAFE_AT_DISPATCH,
    FailureReason.NO_SAFE_ROUTE_INGRESS,
    FailureReason.RESIDENT_NODE_UNSAFE_ON_ARRIVAL,
    FailureReason.SERVICE_WINDOW_UNSAFE,
    FailureReason.NO_SAFE_ROUTE_EGRESS,
    FailureReason.REFUGE_DWELL_UNSAFE,
    FailureReason.DESTINATION_UNAVAILABLE,
    FailureReason.CAUGHT_MID_EDGE,
    FailureReason.NONE,
)


def progress_rank(reason: FailureReason) -> int:
    """How far into the mission this failure occurred; higher is further."""
    return _PROGRESS_ORDER.index(reason)


@dataclass(frozen=True)
class HazardConflict:
    """The specific hazard that blocked or caught the mission."""

    element_id: str
    element_type: str
    leg: str                  # "ingress" | "service" | "egress" | "dispatch"
    entry_time: float
    exit_time: float
    safety_lost_at: float | None
    next_opening: float | None
    timeline: str
    detail: str

    @classmethod
    def from_assessment(cls, assessment: ElementAssessment, leg: str,
                        detail: str = "") -> "HazardConflict":
        return cls(
            element_id=assessment.element_id,
            element_type=assessment.element_type,
            leg=leg,
            entry_time=assessment.entry_time,
            exit_time=assessment.exit_time,
            safety_lost_at=assessment.safety_lost_at,
            next_opening=assessment.next_opening,
            timeline=assessment.timeline_description,
            detail=detail or assessment.explain(),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __str__(self) -> str:  # pragma: no cover - display
        return f"[{self.leg}] {self.detail}"


@dataclass(frozen=True)
class Traversal:
    """One edge occupied over one closed time interval."""

    edge_id: str
    tail: str
    head: str
    entry_time: float
    exit_time: float
    safe_throughout: bool
    safety_lost_at: float | None
    margin: float | None

    @property
    def duration(self) -> float:
        return self.exit_time - self.entry_time

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __str__(self) -> str:  # pragma: no cover - display
        flag = "" if self.safe_throughout else "  <-- CAUGHT"
        return (f"{self.entry_time:7.2f} -> {self.exit_time:7.2f}  "
                f"{self.edge_id}{flag}")


@dataclass(frozen=True)
class Route:
    """An ordered chain of traversals from ``origin`` to ``terminus``."""

    origin: str
    terminus: str
    start_time: float
    end_time: float
    traversals: tuple[Traversal, ...] = ()

    @property
    def node_sequence(self) -> tuple[str, ...]:
        if not self.traversals:
            return (self.origin,)
        return (self.traversals[0].tail,) + tuple(t.head for t in self.traversals)

    @property
    def edge_sequence(self) -> tuple[str, ...]:
        return tuple(t.edge_id for t in self.traversals)

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def min_margin(self) -> float:
        """Tightest clearance against any hazard on this route, in minutes."""
        margins = [t.margin for t in self.traversals if t.margin is not None]
        return min(margins) if margins else INFINITY

    @property
    def is_safe(self) -> bool:
        return all(t.safe_throughout for t in self.traversals)

    def to_dict(self) -> dict[str, Any]:
        return {
            "origin": self.origin,
            "terminus": self.terminus,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "nodes": list(self.node_sequence),
            "edges": list(self.edge_sequence),
            "traversals": [t.to_dict() for t in self.traversals],
            "min_margin": self.min_margin,
        }

    def path_string(self) -> str:
        return " -> ".join(self.node_sequence)

    def __str__(self) -> str:  # pragma: no cover - display
        return (f"{self.path_string()}  ({self.start_time:g} -> "
                f"{self.end_time:g}, {self.duration:g} min)")


EMPTY_ROUTE = Route(origin="", terminus="", start_time=0.0, end_time=0.0)


@dataclass(frozen=True)
class LogEntry:
    """One line of the mission log.

    Every minute of the mission clock is accounted for by exactly one entry.
    :func:`..validation.invariants.check_no_implicit_waiting` relies on that:
    if consecutive entries do not abut, time went somewhere undeclared.
    """

    kind: str        # "dispatch" | "travel" | "service" | "arrival" | "abort"
    start_time: float
    end_time: float
    element: str
    detail: str

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __str__(self) -> str:  # pragma: no cover - display
        return (f"{self.start_time:7.2f} - {self.end_time:7.2f}  "
                f"{self.kind:<8} {self.element:<14} {self.detail}")


@dataclass(frozen=True)
class MissionResult:
    """The full record of one (dispatch time, scenario) evaluation."""

    dispatch_time: float
    scenario: str
    mission_success: bool
    failure_reason: FailureReason = FailureReason.NONE
    hazard_conflict: HazardConflict | None = None

    ingress_route: Route | None = None
    resident_arrival_time: float | None = None
    pickup_start: float | None = None
    pickup_end: float | None = None
    egress_route: Route | None = None
    destination_node: str | None = None
    destination_arrival: float | None = None

    log: tuple[LogEntry, ...] = ()
    policy: str = ""
    mission_name: str = ""
    pickup_duration: float | None = None
    notes: tuple[str, ...] = ()

    @property
    def mission_duration(self) -> float | None:
        if self.destination_arrival is None:
            return None
        return self.destination_arrival - self.dispatch_time

    @property
    def min_margin(self) -> float:
        margins = [r.min_margin for r in (self.ingress_route, self.egress_route)
                   if r is not None]
        return min(margins) if margins else INFINITY

    def to_dict(self) -> dict[str, Any]:
        return {
            "dispatch_time": self.dispatch_time,
            "scenario": self.scenario,
            "mission_name": self.mission_name,
            "policy": self.policy,
            "pickup_duration": self.pickup_duration,
            "ingress_route": self.ingress_route.to_dict() if self.ingress_route else None,
            "resident_arrival_time": self.resident_arrival_time,
            "pickup_start": self.pickup_start,
            "pickup_end": self.pickup_end,
            "egress_route": self.egress_route.to_dict() if self.egress_route else None,
            "destination_node": self.destination_node,
            "destination_arrival": self.destination_arrival,
            "mission_success": self.mission_success,
            "failure_reason": self.failure_reason.value,
            "hazard_conflict": self.hazard_conflict.to_dict() if self.hazard_conflict else None,
            "mission_duration": self.mission_duration,
            "min_margin": None if self.min_margin == INFINITY else self.min_margin,
            "log": [e.to_dict() for e in self.log],
            "notes": list(self.notes),
        }

    def to_row(self) -> dict[str, Any]:
        """A flat record for tabular (parquet/CSV) output."""
        margin = self.min_margin
        return {
            "dispatch_time": self.dispatch_time,
            "scenario": self.scenario,
            "mission_name": self.mission_name,
            "policy": self.policy,
            "pickup_duration": self.pickup_duration,
            "mission_success": self.mission_success,
            "failure_reason": self.failure_reason.value,
            "resident_arrival_time": self.resident_arrival_time,
            "pickup_start": self.pickup_start,
            "pickup_end": self.pickup_end,
            "destination_node": self.destination_node,
            "destination_arrival": self.destination_arrival,
            "mission_duration": self.mission_duration,
            "ingress_path": self.ingress_route.path_string() if self.ingress_route else None,
            "egress_path": self.egress_route.path_string() if self.egress_route else None,
            "min_margin": None if margin == INFINITY else margin,
            "hazard_conflict_element": (
                self.hazard_conflict.element_id if self.hazard_conflict else None),
            "hazard_conflict_leg": (
                self.hazard_conflict.leg if self.hazard_conflict else None),
            "hazard_conflict_detail": (
                self.hazard_conflict.detail if self.hazard_conflict else None),
        }

    def render(self) -> str:
        """Human-readable mission log."""
        head = "SUCCESS" if self.mission_success else f"FAILED ({self.failure_reason.value})"
        lines = [
            f"mission {self.mission_name or '?'} | scenario {self.scenario} | "
            f"dispatch t={self.dispatch_time:g} | {head}",
            f"  policy: {self.policy}",
        ]
        for entry in self.log:
            lines.append("  " + str(entry))
        if self.hazard_conflict is not None:
            lines.append(f"  hazard conflict: {self.hazard_conflict}")
        if self.mission_success:
            margin = self.min_margin
            m = "inf" if margin == INFINITY else f"{margin:g}"
            lines.append(
                f"  arrival at {self.destination_node} t={self.destination_arrival:g}"
                f" (mission duration {self.mission_duration:g} min, "
                f"tightest hazard margin {m} min)"
            )
        for note in self.notes:
            lines.append(f"  note: {note}")
        return "\n".join(lines)


def worst_failure(results: Sequence[MissionResult]) -> MissionResult | None:
    """Pick the most informative failure: the one that got furthest."""
    if not results:
        return None
    return max(results, key=lambda r: (progress_rank(r.failure_reason),
                                       -(r.dispatch_time)))


__all__ = [
    "FailureReason",
    "progress_rank",
    "HazardConflict",
    "Traversal",
    "Route",
    "EMPTY_ROUTE",
    "LogEntry",
    "MissionResult",
    "worst_failure",
]
