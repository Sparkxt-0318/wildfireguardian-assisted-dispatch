"""Pickup / on-scene service model.

The responder does not teleport the resident into the vehicle.  Between arrival
at the address and departure towards the destination there is a service
interval of positive duration, during which **the responder and the resident
are both standing at the resident's node** and are exposed to whatever happens
to that node.

Scenario parameters
-------------------
The shipped profiles are the four scenario values the research plan calls for::

    2 min, 5 min, 10 min, 15 min

**These are scenario parameters, not validated medical or triage categories.**
They are not derived from any EMS dataset, they are not calibrated against any
real assisted-evacuation record, and they must not be reported as if they were.
Their only job is to make pickup-duration sensitivity visible (fixture D).
See docs/ASSUMPTIONS.md A-004.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..units import lt


@dataclass(frozen=True)
class PickupModel:
    """A deterministic on-scene service duration, in minutes."""

    duration: float
    profile: str = "custom"
    note: str = ""

    def __post_init__(self) -> None:
        if lt(self.duration, 0.0):
            raise ValueError(f"pickup duration must be >= 0, got {self.duration}")

    def window(self, arrival_time: float) -> tuple[float, float]:
        """``(pickup_start, pickup_end)`` for an arrival at ``arrival_time``.

        There is no implicit waiting: service starts the instant the responder
        arrives.  A delayed start would be a *wait* and would have to be
        declared explicitly (docs/DECISIONS.md D-004).
        """
        return (arrival_time, arrival_time + self.duration)

    @classmethod
    def of(cls, profile: str) -> "PickupModel":
        try:
            duration = PICKUP_PROFILE_MINUTES[profile]
        except KeyError as exc:
            raise KeyError(
                f"unknown pickup profile {profile!r}; "
                f"known profiles: {sorted(PICKUP_PROFILE_MINUTES)}"
            ) from exc
        return cls(duration=duration, profile=profile,
                   note=PROFILE_DISCLAIMER)

    def describe(self) -> str:  # pragma: no cover - display
        return f"pickup {self.profile} = {self.duration:g} min"


PROFILE_DISCLAIMER = (
    "Scenario parameter only. Not a validated medical or triage category."
)

#: Named scenario durations, in minutes.  Names are deliberately neutral and
#: describe *time on scene*, never a clinical condition.
PICKUP_PROFILE_MINUTES: Mapping[str, float] = {
    "p02": 2.0,
    "p05": 5.0,
    "p10": 10.0,
    "p15": 15.0,
}

#: The sweep set used by the pickup-sensitivity experiment (fixture D).
PICKUP_SENSITIVITY_MINUTES: tuple[float, ...] = (2.0, 5.0, 10.0, 15.0)

DEFAULT_PICKUP = PickupModel.of("p05")

__all__ = [
    "PickupModel",
    "PICKUP_PROFILE_MINUTES",
    "PICKUP_SENSITIVITY_MINUTES",
    "PROFILE_DISCLAIMER",
    "DEFAULT_PICKUP",
]
