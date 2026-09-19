r"""Dispatch-time feasibility.

The research question is a *set* question, not a deadline question:

.. math::

    \mathcal{T} = \{\, t : P_{\text{success}}(t) \ge q \,\}

where :math:`P_{\text{success}}(t)` is the total weight of the coherent hazard
scenarios in which the whole mission — dispatch, ingress, pickup, egress,
arrival — completes when the responder leaves the base at time :math:`t`.

Why this module refuses to hand out a single deadline
-----------------------------------------------------
It is very tempting to compress :math:`\mathcal{T}` into

.. math::  t^\dagger = \sup \mathcal{T}

and tell the dispatcher "leave before :math:`t^\dagger`".  That summary is only
*true* when :math:`\mathcal{T}` is downward closed on the studied range, i.e.
when feasibility is monotonically non-increasing in dispatch time.  It is not
in general: a corridor that reopens, or a refuge that only opens later, can
make a later dispatch succeed where an earlier one fails (fixture F).

So :class:`FeasibleDispatchSet` reports the whole set, states plainly whether
it is monotone, and refuses to produce ``latest_dispatch`` when it is not,
unless the caller explicitly asks for the unsafe summary and accepts the
attached warning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ..hazards.scenario import ScenarioEnsemble
from ..missions.evaluator import evaluate_over_ensemble
from ..missions.result import FailureReason, MissionResult, progress_rank
from ..missions.spec import MissionSpec
from ..units import EPS, geq, quantize


class NonMonotonicFeasibilityError(ValueError):
    """Raised when a single latest-dispatch summary would misrepresent the set."""


def dispatch_grid(start: float, stop: float, step: float) -> tuple[float, ...]:
    """Inclusive grid ``[start, stop]`` with spacing ``step``."""
    if step <= 0:
        raise ValueError("dispatch grid step must be positive")
    if stop < start:
        raise ValueError("dispatch grid stop precedes start")
    n = int(round((stop - start) / step))
    return tuple(quantize(start + i * step) for i in range(n + 1))


@dataclass(frozen=True)
class DispatchOutcome:
    """Every scenario's verdict at one dispatch time."""

    dispatch_time: float
    results: tuple[MissionResult, ...]
    #: Scenario weights, positionally aligned with ``results``.
    weights: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if len(self.weights) != len(self.results):
            raise ValueError("weights must align positionally with results")

    @property
    def p_success(self) -> float:
        return sum(w for w, r in zip(self.weights, self.results) if r.mission_success)

    @property
    def successes(self) -> tuple[str, ...]:
        return tuple(r.scenario for r in self.results if r.mission_success)

    @property
    def failures(self) -> tuple[MissionResult, ...]:
        return tuple(r for r in self.results if not r.mission_success)

    @property
    def dominant_failure(self) -> FailureReason:
        """The furthest-progressed failure across scenarios at this dispatch time."""
        failures = self.failures
        if not failures:
            return FailureReason.NONE
        return max(failures, key=lambda r: progress_rank(r.failure_reason)).failure_reason

    def result_for(self, scenario: str) -> MissionResult:
        for r in self.results:
            if r.scenario == scenario:
                return r
        raise KeyError(f"no result for scenario {scenario!r}")


@dataclass(frozen=True)
class FeasibleDispatchSet:
    r"""The sampled set :math:`\mathcal{T} = \{t : P_{success}(t) \ge q\}`."""

    threshold: float
    grid: tuple[float, ...]
    flags: tuple[bool, ...]
    resolution: float

    def __post_init__(self) -> None:
        if len(self.grid) != len(self.flags):
            raise ValueError("grid and flags must have the same length")

    @property
    def points(self) -> tuple[float, ...]:
        return tuple(t for t, ok in zip(self.grid, self.flags) if ok)

    @property
    def is_empty(self) -> bool:
        return not any(self.flags)

    @property
    def intervals(self) -> tuple[tuple[float, float], ...]:
        """Maximal runs of feasible grid points, as closed sampled intervals.

        These are statements about the *sampled* grid, accurate to
        ``resolution``; the true boundary lies somewhere in the half-step
        beyond each endpoint.  Use :mod:`.refine` to pin it down.
        """
        runs: list[tuple[float, float]] = []
        start: int | None = None
        for i, ok in enumerate(self.flags):
            if ok and start is None:
                start = i
            elif not ok and start is not None:
                runs.append((self.grid[start], self.grid[i - 1]))
                start = None
        if start is not None:
            runs.append((self.grid[start], self.grid[-1]))
        return tuple(runs)

    @property
    def gaps(self) -> tuple[tuple[float, float], ...]:
        """Infeasible stretches *between* feasible ones.

        A non-empty ``gaps`` is the whole non-monotonicity story: dispatching
        later than a feasible window can become possible again.
        """
        intervals = self.intervals
        return tuple((intervals[i][1], intervals[i + 1][0])
                     for i in range(len(intervals) - 1))

    @property
    def is_monotone(self) -> bool:
        """True iff feasibility never returns after being lost on this grid."""
        seen_infeasible = False
        for ok in self.flags:
            if not ok:
                seen_infeasible = True
            elif seen_infeasible:
                return False
        return True

    @property
    def is_prefix(self) -> bool:
        """True iff the set is an initial run of the grid (a pure deadline)."""
        return self.is_monotone and bool(self.flags) and self.flags[0]

    @property
    def supremum(self) -> float | None:
        r"""The raw :math:`\sup \mathcal{T}` on the grid, with no claim attached."""
        points = self.points
        return points[-1] if points else None

    def latest_dispatch(self, *, allow_non_monotonic: bool = False) -> float | None:
        r"""The single latest dispatch time :math:`t^\dagger = \sup \mathcal{T}`.

        Only meaningful when the feasible set is monotone on the studied grid.
        Otherwise this raises, because reporting a lone number for a set with a
        hole in it tells the dispatcher that every earlier time is fine when
        some of them are not.  Pass ``allow_non_monotonic=True`` only when the
        caller is going to print :attr:`warnings` alongside it.
        """
        if not self.is_monotone and not allow_non_monotonic:
            raise NonMonotonicFeasibilityError(
                "feasible dispatch set is not monotone on this grid "
                f"(feasible windows: {self.format_intervals()}; infeasible gaps: "
                f"{self._fmt(self.gaps)}). A single latest dispatch time would "
                "imply that every earlier dispatch also works, which is false "
                "here. Report the set, or the individual windows."
            )
        return self.supremum

    @property
    def warnings(self) -> tuple[str, ...]:
        out: list[str] = []
        if self.is_empty:
            out.append("no sampled dispatch time meets the threshold")
        if not self.is_monotone:
            out.append(
                "feasibility is NOT monotone in dispatch time: it is regained "
                f"after being lost ({len(self.gaps)} gap(s): {self._fmt(self.gaps)}). "
                "A single latest-dispatch summary is invalid here."
            )
        if self.flags and self.flags[-1]:
            out.append(
                "the last sampled dispatch time is still feasible; the studied "
                "range does not bracket the end of the feasible set"
            )
        return tuple(out)

    def _fmt(self, spans: Sequence[tuple[float, float]]) -> str:
        return "[" + ", ".join(f"({a:g}, {b:g})" for a, b in spans) + "]"

    def format_intervals(self) -> str:
        """Feasible windows as a readable string."""
        return "[" + ", ".join(f"[{a:g}, {b:g}]" for a, b in self.intervals) + "]"

    def describe(self) -> str:
        lines = [
            f"feasible dispatch set at threshold q = {self.threshold:g} "
            f"(grid resolution {self.resolution:g} min)",
            f"  windows : {self.format_intervals() if self.intervals else 'empty'}",
            f"  monotone: {self.is_monotone}",
        ]
        if self.is_monotone and not self.is_empty:
            lines.append(f"  t_dagger = sup T = {self.supremum:g} "
                         "(meaningful: the set is monotone here)")
        elif not self.is_empty:
            lines.append(f"  sup T = {self.supremum:g} "
                         "(NOT a valid latest-dispatch summary; see warnings)")
        for w in self.warnings:
            lines.append(f"  warning: {w}")
        return "\n".join(lines)


@dataclass(frozen=True)
class DispatchSweep:
    """``P_success`` evaluated across a grid of dispatch times."""

    mission: str
    ensemble_size: int
    outcomes: tuple[DispatchOutcome, ...]
    resolution: float
    pickup_duration: float | None = None
    policy: str = ""

    @property
    def grid(self) -> tuple[float, ...]:
        return tuple(o.dispatch_time for o in self.outcomes)

    @property
    def p_success(self) -> tuple[float, ...]:
        return tuple(o.p_success for o in self.outcomes)

    def outcome_at(self, t: float) -> DispatchOutcome:
        for o in self.outcomes:
            if abs(o.dispatch_time - t) <= EPS:
                return o
        raise KeyError(f"dispatch time {t!r} is not on the sweep grid")

    def feasible_set(self, threshold: float = 1.0) -> FeasibleDispatchSet:
        flags = tuple(geq(o.p_success, threshold) for o in self.outcomes)
        return FeasibleDispatchSet(
            threshold=threshold, grid=self.grid, flags=flags,
            resolution=self.resolution,
        )

    def rows(self) -> list[dict]:
        """Flat records, one per (dispatch time, scenario)."""
        out: list[dict] = []
        for outcome in self.outcomes:
            for result in outcome.results:
                row = result.to_row()
                row["p_success_at_dispatch"] = outcome.p_success
                out.append(row)
        return out

    def summary_rows(self) -> list[dict]:
        """One record per dispatch time."""
        return [
            {
                "dispatch_time": o.dispatch_time,
                "p_success": o.p_success,
                "n_scenarios": len(o.results),
                "n_success": len(o.successes),
                "dominant_failure": o.dominant_failure.value,
                "mission": self.mission,
                "pickup_duration": self.pickup_duration,
                "policy": self.policy,
            }
            for o in self.outcomes
        ]

    def describe(self, threshold: float = 1.0) -> str:
        return self.feasible_set(threshold).describe()


def sweep_dispatch_times(spec: MissionSpec, ensemble: ScenarioEnsemble,
                         times: Iterable[float]) -> DispatchSweep:
    """Evaluate the mission at every dispatch time, scenario by scenario."""
    ensemble.validate(spec.network)
    grid = tuple(float(t) for t in times)
    weights = tuple(s.weight for s in ensemble)
    outcomes = tuple(
        DispatchOutcome(
            dispatch_time=t,
            results=evaluate_over_ensemble(spec, t, ensemble),
            weights=weights,
        )
        for t in grid
    )
    resolution = (grid[1] - grid[0]) if len(grid) > 1 else 0.0
    return DispatchSweep(
        mission=spec.name, ensemble_size=len(ensemble), outcomes=outcomes,
        resolution=resolution, pickup_duration=spec.pickup.duration,
        policy=spec.policy.describe(),
    )


def p_success(spec: MissionSpec, dispatch_time: float,
              ensemble: ScenarioEnsemble) -> float:
    r"""``P_success(t)``: total weight of scenarios in which the mission completes.

    Note what this is *not*: it is not a product of per-edge survival
    probabilities.  Each scenario is evaluated whole, and its weight counts once.
    """
    results = evaluate_over_ensemble(spec, dispatch_time, ensemble)
    return sum(s.weight for s, r in zip(ensemble, results) if r.mission_success)


__all__ = [
    "NonMonotonicFeasibilityError",
    "dispatch_grid",
    "DispatchOutcome",
    "FeasibleDispatchSet",
    "DispatchSweep",
    "sweep_dispatch_times",
    "p_success",
]
