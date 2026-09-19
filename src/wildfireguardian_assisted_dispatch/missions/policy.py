"""Mission policies: what the planner is and is not allowed to do.

Every rule that changes the answer lives here, named, defaulted, and logged
into the mission record.  A result produced under a different policy is a
different result and says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..hazards.semantics import TraversalAdmission
from ..units import HOUR


class WaitingPolicy(str, Enum):
    """Whether the responder may hold position to let a hazard pass.

    ``PROHIBITED`` is the phase-1 policy and the only implemented one.  The
    mission clock advances *only* by edge traversal and by pickup service; there
    is no idle time anywhere, which is what makes every reported timestamp a sum
    of quantities the reader can check by hand.

    ``EXPLICIT_AT_ALLOWED_NODES`` is reserved.  If waiting is ever supported it
    must be (a) explicit — a decision the planner makes, never a side effect of
    a scheduling rule, (b) located at a node from a declared allow-list, and
    (c) visible in the mission log as its own leg with its own hazard
    assessment.  Anything less re-introduces implicit waiting through the back
    door.  See docs/DECISIONS.md D-004.
    """

    PROHIBITED = "prohibited"
    EXPLICIT_AT_ALLOWED_NODES = "explicit_at_allowed_nodes"


class WaitingNotImplementedError(NotImplementedError):
    """Raised when a config asks for a waiting policy phase 1 does not implement."""


@dataclass(frozen=True)
class MissionPolicy:
    """The rule set a mission evaluation runs under."""

    admission: TraversalAdmission = TraversalAdmission.FULL_INTERVAL
    waiting: WaitingPolicy = WaitingPolicy.PROHIBITED
    #: Absolute clock time after which the mission is abandoned, in minutes from
    #: the scenario epoch.  Bounds the time-expanded search, which would
    #: otherwise circulate forever in a cyclic network.
    horizon: float = 8 * HOUR
    #: Safety valve for the state search; exceeding it raises rather than
    #: silently truncating and reporting a false infeasibility.
    max_states: int = 200_000
    #: May a leg visit the same node twice?
    #:
    #: Default ``False``, and this is a *waiting* decision, not a graph
    #: convenience.  With revisits allowed, a responder can drive base -> home
    #: -> base -> home purely to burn ten minutes until a corridor reopens.
    #: That is waiting, performed with the engine running, and letting the
    #: search discover it silently would smuggle waiting back into a model
    #: that claims to forbid it.  So each leg is a simple path unless the
    #: caller explicitly opts in, and when it does, the resulting plans must be
    #: read as hold-by-circulation.  See docs/DECISIONS.md D-005.
    allow_node_revisits: bool = False
    #: How many distinct resident-arrival times the evaluator will branch on.
    #: Arrival times are *not* dominated by earliness (a later arrival can be
    #: the only feasible one), so the evaluator must try more than the first.
    max_resident_arrivals: int = 64

    def __post_init__(self) -> None:
        object.__setattr__(self, "admission", TraversalAdmission(self.admission))
        object.__setattr__(self, "waiting", WaitingPolicy(self.waiting))
        if self.waiting is not WaitingPolicy.PROHIBITED:
            raise WaitingNotImplementedError(
                f"waiting policy {self.waiting.value!r} is declared but not "
                "implemented in phase 1; only 'prohibited' is available. "
                "See docs/DECISIONS.md D-004."
            )
        if self.horizon <= 0:
            raise ValueError("horizon must be positive")

    def describe(self) -> str:  # pragma: no cover - display
        return (f"admission={self.admission.value}, waiting={self.waiting.value}, "
                f"revisits={'allowed' if self.allow_node_revisits else 'prohibited'}, "
                f"horizon={self.horizon:g} min")


DEFAULT_POLICY = MissionPolicy()

#: The deliberately-wrong policy used by red-team fixtures to show what
#: entry-time-only hazard checking costs.
MYOPIC_POLICY = MissionPolicy(admission=TraversalAdmission.ENTRY_ONLY)

__all__ = [
    "WaitingPolicy",
    "WaitingNotImplementedError",
    "MissionPolicy",
    "DEFAULT_POLICY",
    "MYOPIC_POLICY",
]
