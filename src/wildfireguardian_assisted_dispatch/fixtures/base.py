"""The fixture container.

Every fixture in this package carries its own hand calculation.  That is the
point: the validation strategy in this phase is not "the code agrees with
itself across refactors", it is "the code agrees with arithmetic a reviewer can
do on the back of an envelope".  A fixture whose expected windows were copied
out of a previous run is worthless, so ``hand_calculation`` must be readable
and must justify ``expected_windows`` line by line.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from ..feasibility.dispatch import (
    DispatchSweep,
    FeasibleDispatchSet,
    sweep_dispatch_times,
)
from ..hazards.scenario import ScenarioEnsemble
from ..missions.spec import MissionSpec


@dataclass(frozen=True)
class Fixture:
    """A synthetic scenario with a known answer."""

    key: str
    title: str
    summary: str
    spec: MissionSpec
    ensemble: ScenarioEnsemble
    grid: tuple[float, ...]
    threshold: float = 1.0
    hand_calculation: str = ""
    #: Feasible dispatch windows, as closed intervals of the sampled grid.
    expected_windows: tuple[tuple[float, float], ...] = ()
    #: Expected ``P_success`` at selected dispatch times (ensemble fixtures).
    expected_p_success: Mapping[float, float] = field(default_factory=dict)
    expected_monotone: bool = True
    notes: tuple[str, ...] = ()

    def sweep(self) -> DispatchSweep:
        return sweep_dispatch_times(self.spec, self.ensemble, self.grid)

    def feasible_set(self) -> FeasibleDispatchSet:
        return self.sweep().feasible_set(self.threshold)

    def describe(self) -> str:
        lines = [
            f"fixture {self.key.upper()} - {self.title}",
            f"  {self.summary}",
            f"  network  : {self.spec.network.name} "
            f"({len(self.spec.network.nodes)} nodes, "
            f"{len(self.spec.network.edges)} directed edges)",
            f"  {self.spec.pickup.describe()}",
            f"  policy   : {self.spec.policy.describe()}",
            f"  scenarios: {', '.join(s.name for s in self.ensemble)}",
            f"  grid     : {self.grid[0]:g}..{self.grid[-1]:g} min",
            f"  expected : {_fmt_windows(self.expected_windows)} "
            f"at q={self.threshold:g}",
        ]
        if self.hand_calculation:
            lines.append("  hand calculation:")
            lines += [f"    {line}" for line in self.hand_calculation.strip().splitlines()]
        for note in self.notes:
            lines.append(f"  note: {note}")
        return "\n".join(lines)


def _fmt_windows(windows: Sequence[tuple[float, float]]) -> str:
    if not windows:
        return "empty"
    return " U ".join(f"[{a:g}, {b:g}]" for a, b in windows)


__all__ = ["Fixture"]
