"""Locating feasibility boundaries more precisely than the sweep grid.

A grid sweep says "feasible at t = 13, infeasible at t = 14".  The actual switch
is somewhere in between, and for a hand-checkable fixture the exact value is
the thing being validated.  Bisection finds it to any tolerance, at the cost of
a handful of extra mission evaluations per transition.

The bisection assumes only that feasibility does not flip *more than once*
inside a single grid cell.  That is a statement about grid resolution, not
about monotonicity of the whole set, and it is reported honestly: refinement
returns a bracket, and the caller can shrink the grid if it distrusts it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..hazards.scenario import ScenarioEnsemble
from ..missions.spec import MissionSpec
from ..units import geq
from .dispatch import DispatchSweep, p_success


@dataclass(frozen=True)
class Transition:
    """A feasibility switch located inside one grid cell."""

    kind: str          # "gain" (infeasible -> feasible) or "loss"
    lower: float       # last time on the pre-transition side
    upper: float       # first time on the post-transition side
    tolerance: float

    @property
    def boundary(self) -> float:
        """Midpoint of the final bracket."""
        return 0.5 * (self.lower + self.upper)

    def describe(self) -> str:
        if self.kind == "loss":
            return (f"feasibility is lost between t={self.lower:g} and "
                    f"t={self.upper:g} (+/- {self.tolerance:g} min)")
        return (f"feasibility is regained between t={self.lower:g} and "
                f"t={self.upper:g} (+/- {self.tolerance:g} min)")


def refine_transitions(spec: MissionSpec, ensemble: ScenarioEnsemble,
                       sweep: DispatchSweep, *, threshold: float = 1.0,
                       tolerance: float = 0.01,
                       max_iterations: int = 60) -> tuple[Transition, ...]:
    """Bisect every feasibility flip observed on the sweep grid."""
    if tolerance <= 0:
        raise ValueError("tolerance must be positive")
    flags = [geq(o.p_success, threshold) for o in sweep.outcomes]
    grid = sweep.grid
    out: list[Transition] = []

    for i in range(len(grid) - 1):
        if flags[i] == flags[i + 1]:
            continue
        kind = "loss" if flags[i] else "gain"
        lo, hi = grid[i], grid[i + 1]
        lo_feasible = flags[i]
        iterations = 0
        while hi - lo > tolerance and iterations < max_iterations:
            mid = 0.5 * (lo + hi)
            mid_feasible = geq(p_success(spec, mid, ensemble), threshold)
            if mid_feasible == lo_feasible:
                lo = mid
            else:
                hi = mid
            iterations += 1
        out.append(Transition(kind=kind, lower=lo, upper=hi, tolerance=hi - lo))
    return tuple(out)


__all__ = ["Transition", "refine_transitions"]
