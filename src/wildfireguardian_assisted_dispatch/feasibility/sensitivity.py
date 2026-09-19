"""Pickup-duration sensitivity.

Fixture D's question: how much of the dispatch envelope does on-scene time cost?

Every minute spent at the address is a minute the egress happens later, so a
longer pickup shifts the whole egress leg into a more hazardous part of the
timeline.  The sensitivity sweep makes that trade explicit rather than leaving
it as an intuition.

The durations swept are scenario parameters.  They are not validated medical or
triage categories (see :mod:`...service.pickup`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ..hazards.scenario import ScenarioEnsemble
from ..missions.spec import MissionSpec
from ..service.pickup import PICKUP_SENSITIVITY_MINUTES, PickupModel
from .dispatch import DispatchSweep, FeasibleDispatchSet, sweep_dispatch_times


@dataclass(frozen=True)
class PickupCase:
    """One pickup duration's feasibility picture."""

    duration: float
    sweep: DispatchSweep
    feasible_set: FeasibleDispatchSet

    @property
    def feasible_measure(self) -> float:
        """Total sampled length of the feasible set, in minutes.

        Grid-resolution units: the count of feasible sample points times the
        grid step.  It is a comparison statistic across pickup durations, not a
        measure of the true set.
        """
        return len(self.feasible_set.points) * (self.feasible_set.resolution or 1.0)

    @property
    def latest_feasible(self) -> float | None:
        return self.feasible_set.supremum


@dataclass(frozen=True)
class PickupSensitivity:
    """Feasibility across a set of pickup durations."""

    mission: str
    threshold: float
    cases: tuple[PickupCase, ...]

    def case(self, duration: float) -> PickupCase:
        for c in self.cases:
            if abs(c.duration - duration) < 1e-9:
                return c
        raise KeyError(f"no case for pickup duration {duration!r}")

    @property
    def is_monotone_in_pickup(self) -> bool:
        """True iff a longer pickup never enlarges the feasible set.

        Expected to hold whenever the pickup only shifts the egress later, but
        it is *checked*, not assumed: with reopening corridors a longer pickup
        can delay egress into a window that has reopened.
        """
        measures = [c.feasible_measure for c in self.cases]
        return all(b <= a + 1e-9 for a, b in zip(measures, measures[1:]))

    def rows(self) -> list[dict]:
        return [
            {
                "mission": self.mission,
                "threshold": self.threshold,
                "pickup_duration": c.duration,
                "n_feasible_points": len(c.feasible_set.points),
                "feasible_measure": c.feasible_measure,
                "latest_feasible": c.latest_feasible,
                "is_monotone": c.feasible_set.is_monotone,
                "windows": c.feasible_set.format_intervals(),
            }
            for c in self.cases
        ]

    def describe(self) -> str:
        lines = [f"pickup sensitivity for mission {self.mission!r} "
                 f"at threshold q={self.threshold:g}"]
        for c in self.cases:
            latest = "none" if c.latest_feasible is None else f"{c.latest_feasible:g}"
            lines.append(
                f"  pickup {c.duration:5g} min -> "
                f"{len(c.feasible_set.points):3d} feasible sample(s), "
                f"sup T = {latest}, windows {c.feasible_set.format_intervals()}"
            )
        if not self.is_monotone_in_pickup:
            lines.append("  note: the feasible set is NOT monotone in pickup "
                         "duration on this grid")
        return "\n".join(lines)


def sweep_pickup_durations(spec: MissionSpec, ensemble: ScenarioEnsemble,
                           times: Sequence[float],
                           durations: Iterable[float] = PICKUP_SENSITIVITY_MINUTES,
                           *, threshold: float = 1.0) -> PickupSensitivity:
    """Re-run the dispatch sweep once per pickup duration."""
    cases: list[PickupCase] = []
    for duration in sorted(float(d) for d in durations):
        variant = spec.with_pickup(
            PickupModel(duration=duration, profile=f"sweep-{duration:g}min")
        )
        sweep = sweep_dispatch_times(variant, ensemble, times)
        cases.append(PickupCase(duration=duration, sweep=sweep,
                                feasible_set=sweep.feasible_set(threshold)))
    return PickupSensitivity(mission=spec.name, threshold=threshold,
                             cases=tuple(cases))


__all__ = ["PickupCase", "PickupSensitivity", "sweep_pickup_durations"]
