r"""Edge and node hazard semantics: the full-traversal-interval operator.

The central object is

.. math::  A_e([t_{in}, t_{out}], m)

the availability of edge :math:`e` for a traversal that *enters* at
:math:`t_{in}` and *leaves* at :math:`t_{out}` under hazard scenario :math:`m`.

It is evaluated over the **whole closed interval**, never only at the entry
instant.  Two distinct questions come out of one assessment:

``safe_at_entry``
    Would a myopic planner, checking only the entry instant, accept this
    traversal?

``safe_throughout``
    Is every instant of the occupancy interval safe?

What happens when a road becomes unsafe halfway across
------------------------------------------------------
There is no reversing and no escape hatch.  A vehicle that is on the segment
when the segment's safety is lost is **caught**: the mission ends there, at
``safety_lost_at``, with the responder (and, on the egress leg, the resident)
on a burning road.  This project refuses to model a mid-edge U-turn, because a
U-turn would need a half-edge travel time, an unmodelled turnaround, and a
claim about driver behaviour under smoke that no synthetic fixture can support
(docs/DECISIONS.md D-003).

Two admission policies make that consequence visible instead of hiding it:

:attr:`TraversalAdmission.FULL_INTERVAL` (default)
    The planner may only enter an edge it can provably clear.  Catches are
    impossible by construction; the mission fails earlier and honestly, with a
    ``NO_SAFE_ROUTE_*`` reason.

:attr:`TraversalAdmission.ENTRY_ONLY`
    The planner admits any edge that is safe at the entry instant — the
    classical "check the hazard layer when you turn onto the road" mistake.
    Plans are still *audited* over the full interval afterwards, so the result
    is a mission that fails with ``CAUGHT_MID_EDGE``.  This policy exists to
    quantify the error, not to be used.

Whatever the admission policy, the audit is always full-interval.  Nothing in
this package ever reports success for a plan that spends an instant on an
unsafe element.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..network.graph import Edge
from ..units import INFINITY, geq, gt
from .scenario import HazardScenario
from .timeline import Timeline


class TraversalAdmission(str, Enum):
    """Which traversals the *planner* is allowed to commit to."""

    FULL_INTERVAL = "full_interval"
    ENTRY_ONLY = "entry_only"


class Verdict(str, Enum):
    ALLOWED = "allowed"
    BLOCKED_AT_ENTRY = "blocked_at_entry"
    CAUGHT_MID_EDGE = "caught_mid_edge"
    BLOCKED_AT_EXIT_NODE = "blocked_at_exit_node"


@dataclass(frozen=True)
class ElementAssessment:
    r"""The value of :math:`A_e([t_{in}, t_{out}], m)` for one element."""

    element_id: str
    element_type: str  # "edge" | "node"
    entry_time: float
    exit_time: float
    safe_at_entry: bool
    safe_throughout: bool
    safety_lost_at: float | None
    next_opening: float | None
    timeline_description: str

    @property
    def verdict(self) -> Verdict:
        if not self.safe_at_entry:
            return Verdict.BLOCKED_AT_ENTRY
        if not self.safe_throughout:
            return Verdict.CAUGHT_MID_EDGE
        return Verdict.ALLOWED

    @property
    def margin(self) -> float | None:
        """Spare time between clearing the element and losing it, in minutes.

        ``None`` when the element is not safe throughout.  ``inf`` when the
        element never closes.  This is the number a dispatcher actually wants:
        "you cleared that bridge with 3 minutes to spare".
        """
        if not self.safe_throughout or self.safety_lost_at is None:
            return None if not self.safe_throughout else INFINITY
        return self.safety_lost_at - self.exit_time

    def explain(self) -> str:
        span = f"[{self.entry_time:g}, {self.exit_time:g}]"
        if self.verdict is Verdict.ALLOWED:
            m = self.margin
            tail = "never closes" if m == INFINITY else f"{m:g} min of margin"
            return (f"{self.element_type} {self.element_id} is safe throughout "
                    f"{span} ({tail})")
        if self.verdict is Verdict.BLOCKED_AT_ENTRY:
            reopen = ("never reopens" if self.next_opening is None
                      else f"reopens at {self.next_opening:g}")
            return (f"{self.element_type} {self.element_id} is already unsafe at "
                    f"entry time {self.entry_time:g} ({reopen}; "
                    f"{self.timeline_description})")
        return (f"{self.element_type} {self.element_id} is safe at entry "
                f"{self.entry_time:g} but loses safety at "
                f"{self.safety_lost_at:g}, before the traversal would end at "
                f"{self.exit_time:g} ({self.timeline_description})")


def assess_timeline(timeline: Timeline, element_id: str, element_type: str,
                    entry_time: float, exit_time: float) -> ElementAssessment:
    """Evaluate one timeline over the closed occupancy interval."""
    if gt(entry_time, exit_time):
        raise ValueError(
            f"{element_type} {element_id}: occupancy interval "
            f"[{entry_time}, {exit_time}] is reversed"
        )
    horizon = timeline.safety_horizon(entry_time)
    safe_at_entry = horizon is not None
    safe_throughout = safe_at_entry and geq(horizon, exit_time)
    if safe_at_entry:
        lost_at = None if horizon == INFINITY else horizon
        next_open = None
    else:
        lost_at = entry_time
        next_open = timeline.next_opening(entry_time)
    return ElementAssessment(
        element_id=element_id,
        element_type=element_type,
        entry_time=entry_time,
        exit_time=exit_time,
        safe_at_entry=safe_at_entry,
        safe_throughout=safe_throughout,
        safety_lost_at=lost_at,
        next_opening=next_open,
        timeline_description=timeline.describe(),
    )


def assess_edge_traversal(edge: Edge, entry_time: float, exit_time: float,
                          scenario: HazardScenario) -> ElementAssessment:
    r"""Compute :math:`A_e([t_{in}, t_{out}], m)` for a road segment."""
    return assess_timeline(
        scenario.edge_timeline(edge), edge.id, "edge", entry_time, exit_time
    )


def assess_node_occupancy(node_id: str, entry_time: float, exit_time: float,
                          scenario: HazardScenario) -> ElementAssessment:
    """Assess occupying a node over ``[entry_time, exit_time]``.

    Passing *through* a junction is instantaneous (``entry == exit``); standing
    at the resident's address for the pickup is not, and that is precisely where
    a node closure bites.
    """
    return assess_timeline(
        scenario.node_timeline(node_id), node_id, "node", entry_time, exit_time
    )


def admits(assessment: ElementAssessment, admission: TraversalAdmission) -> bool:
    """Would the planner commit to this traversal under ``admission``?"""
    if admission is TraversalAdmission.FULL_INTERVAL:
        return assessment.safe_throughout
    if admission is TraversalAdmission.ENTRY_ONLY:
        return assessment.safe_at_entry
    raise ValueError(f"unknown admission policy {admission!r}")  # pragma: no cover


__all__ = [
    "TraversalAdmission",
    "Verdict",
    "ElementAssessment",
    "assess_timeline",
    "assess_edge_traversal",
    "assess_node_occupancy",
    "admits",
]
