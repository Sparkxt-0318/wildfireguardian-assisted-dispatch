r"""Exact, grid-free computation of the feasible dispatch set.

Why this exists
---------------
A dispatch sweep samples :math:`t` on a grid, so a feasible window narrower
than the grid step and lying strictly between two samples is **invisible** to
it.  ``refine_transitions`` cannot help: it only refines transitions the grid
already saw.  That is a real, demonstrable defect of grid sampling (see
``fixtures/narrow_window.py`` and ``docs/TEMPORAL_RESOLUTION.md``), and the
honest fix is not a finer grid but a solver that does no sampling at all.

The observation that makes it possible
--------------------------------------
Under this repository's phase-1 model, for a *fixed* combinatorial plan
— a specific ingress path, a specific egress path, a specific destination —
every timing constraint has the form

.. math::   t + c \in [\text{window start}, \text{window end}]

or, for an element occupied over a non-zero duration,

.. math::  [t + c_{\rm in},\, t + c_{\rm out}] \subseteq [W_{\rm start}, W_{\rm end}]

where the offsets :math:`c` are constants determined by the plan alone (travel
times do not depend on :math:`t`, and no waiting is permitted).  Each
constraint therefore restricts :math:`t` to a finite union of closed
intervals, and the plan's feasible set is their intersection — again a finite
union of closed intervals.  The scenario's feasible set is the union over the
finitely many simple-path plans, and

.. math::  \mathcal T_q = \bigcup_{J:\, w(J) \ge q}\ \bigcap_{i \in J} S_i

is then exact.  No sampling, no tolerance beyond floating-point epsilon.

Conditions (checked at call time, never assumed)
------------------------------------------------
1. travel times are constant in time (``ConstantTravelModel``);
2. waiting is prohibited;
3. each leg is a simple path (``allow_node_revisits`` is false);
4. admission is ``FULL_INTERVAL``, so feasibility is "a safe plan exists"
   rather than a property of a planner's selection rule;
5. hazard timelines are finite unions of closed intervals (always true here);
6. the plan and scenario-subset counts stay under the stated caps.

If any condition fails the solver raises :class:`ExactSolverUnavailable` rather
than returning an approximation.  In particular condition 4 is a genuine
limitation: under entry-time-only admission, feasibility depends on *which*
plan a myopic planner picks, which is not expressible as a union of per-plan
interval constraints.  That case is covered by the brute-force oracle instead.

A corollary worth stating: because every window is closed, every constraint set
is closed, and finite unions and intersections of closed sets are closed —
so :math:`\mathcal T_q` is **closed**.  When it is non-empty and bounded, its
supremum is attained, i.e. the last feasible dispatch instant is itself
feasible.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

from ..hazards.scenario import HazardScenario, ScenarioEnsemble
from ..hazards.semantics import TraversalAdmission
from ..hazards.timeline import Timeline
from ..missions.policy import WaitingPolicy
from ..missions.spec import Destination, MissionSpec
from ..network.paths import simple_paths
from ..network.travel import ConstantTravelModel
from ..units import EPS, INFINITY


class ExactSolverUnavailable(RuntimeError):
    """The exact solver's stated conditions do not hold for this problem."""


# ---------------------------------------------------------------------------
# Closed-interval set arithmetic
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClosedInterval:
    lo: float
    hi: float

    def __post_init__(self) -> None:
        if self.lo > self.hi + EPS:
            raise ValueError(f"interval [{self.lo}, {self.hi}] is reversed")

    @property
    def is_degenerate(self) -> bool:
        return abs(self.hi - self.lo) <= EPS

    @property
    def length(self) -> float:
        return max(0.0, self.hi - self.lo)

    def __str__(self) -> str:  # pragma: no cover - display
        if self.is_degenerate:
            return f"[{self.lo:g}]"
        hi = "inf" if self.hi == INFINITY else f"{self.hi:g}"
        return f"[{self.lo:g}, {hi}]"


class IntervalSet:
    """A finite union of closed intervals, kept normalised."""

    __slots__ = ("_parts",)

    def __init__(self, parts: Iterable[ClosedInterval | tuple[float, float]] = ()) -> None:
        raw = [p if isinstance(p, ClosedInterval) else ClosedInterval(p[0], p[1])
               for p in parts]
        raw = [p for p in raw if p.lo <= p.hi + EPS]
        merged: list[ClosedInterval] = []
        for part in sorted(raw, key=lambda p: (p.lo, p.hi)):
            if merged and part.lo <= merged[-1].hi + EPS:
                merged[-1] = ClosedInterval(merged[-1].lo, max(merged[-1].hi, part.hi))
            else:
                merged.append(part)
        self._parts: tuple[ClosedInterval, ...] = tuple(merged)

    # -- constructors -------------------------------------------------------
    @classmethod
    def empty(cls) -> "IntervalSet":
        return cls(())

    @classmethod
    def whole(cls) -> "IntervalSet":
        return cls([ClosedInterval(-INFINITY, INFINITY)])

    # -- queries ------------------------------------------------------------
    @property
    def parts(self) -> tuple[ClosedInterval, ...]:
        return self._parts

    @property
    def is_empty(self) -> bool:
        return not self._parts

    @property
    def infimum(self) -> float | None:
        return self._parts[0].lo if self._parts else None

    @property
    def supremum(self) -> float | None:
        return self._parts[-1].hi if self._parts else None

    @property
    def measure(self) -> float:
        return sum(p.length for p in self._parts)

    def contains(self, t: float) -> bool:
        return any(p.lo - EPS <= t <= p.hi + EPS for p in self._parts)

    # -- algebra ------------------------------------------------------------
    def intersect(self, other: "IntervalSet") -> "IntervalSet":
        out: list[ClosedInterval] = []
        for a in self._parts:
            for b in other._parts:
                lo, hi = max(a.lo, b.lo), min(a.hi, b.hi)
                if lo <= hi + EPS:
                    out.append(ClosedInterval(lo, hi))
        return IntervalSet(out)

    def union(self, other: "IntervalSet") -> "IntervalSet":
        return IntervalSet(self._parts + other._parts)

    def shift(self, delta: float) -> "IntervalSet":
        return IntervalSet([ClosedInterval(p.lo + delta, p.hi + delta)
                            for p in self._parts])

    def issubset(self, other: "IntervalSet") -> bool:
        """Is every point of this set inside ``other`` (within EPS)?"""
        return self.intersect(other) == self

    def gaps(self) -> tuple[ClosedInterval, ...]:
        """The open stretches between consecutive components."""
        return tuple(ClosedInterval(self._parts[i].hi, self._parts[i + 1].lo)
                     for i in range(len(self._parts) - 1))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, IntervalSet):
            return NotImplemented
        if len(self._parts) != len(other._parts):
            return False
        return all(abs(a.lo - b.lo) <= EPS and abs(a.hi - b.hi) <= EPS
                   for a, b in zip(self._parts, other._parts))

    def __len__(self) -> int:
        return len(self._parts)

    def __iter__(self):
        return iter(self._parts)

    def __repr__(self) -> str:  # pragma: no cover - display
        return f"IntervalSet({self})"

    def __str__(self) -> str:
        return " U ".join(str(p) for p in self._parts) if self._parts else "empty"


# ---------------------------------------------------------------------------
# Constraint construction
# ---------------------------------------------------------------------------

def _occupancy_constraint(timeline: Timeline, offset_in: float,
                          offset_out: float) -> IntervalSet:
    r"""Values of ``t`` for which ``[t+offset_in, t+offset_out]`` is safe.

    ``[t + a, t + b] ⊆ [W.start, W.end]`` ⟺
    ``t ∈ [W.start − a, W.end − b]``, which is empty when the window is shorter
    than the occupancy duration.
    """
    parts: list[ClosedInterval] = []
    for window in timeline.windows:
        lo = window.start - offset_in
        hi = window.end - offset_out
        if lo <= hi + EPS:
            parts.append(ClosedInterval(lo, hi))
    return IntervalSet(parts)


def _instant_constraint(timeline: Timeline, offset: float) -> IntervalSet:
    """Values of ``t`` for which the element is safe at ``t + offset``."""
    return _occupancy_constraint(timeline, offset, offset)


@dataclass(frozen=True)
class PlanConstraints:
    """One combinatorial plan and the exact dispatch times it supports."""

    ingress_edges: tuple[str, ...]
    egress_edges: tuple[str, ...]
    destination: str
    resident_offset: float
    pickup_offset: float
    arrival_offset: float
    feasible_t: IntervalSet

    @property
    def mission_duration(self) -> float:
        return self.arrival_offset


def _check_conditions(spec: MissionSpec) -> None:
    policy = spec.policy
    if not isinstance(spec.travel, ConstantTravelModel):
        raise ExactSolverUnavailable(
            "the exact solver requires constant travel times; got "
            f"{type(spec.travel).__name__}"
        )
    if policy.waiting is not WaitingPolicy.PROHIBITED:
        raise ExactSolverUnavailable(
            "the exact solver assumes no waiting; plan offsets would no longer "
            "be constants"
        )
    if policy.allow_node_revisits:
        raise ExactSolverUnavailable(
            "the exact solver enumerates simple paths; with node revisits "
            "allowed the plan set is bounded only by the horizon"
        )
    if policy.admission is not TraversalAdmission.FULL_INTERVAL:
        raise ExactSolverUnavailable(
            "the exact solver computes 'a safe plan exists'; under "
            f"{policy.admission.value!r} admission feasibility depends on which "
            "plan a myopic planner selects, which is not a per-plan interval "
            "constraint. Use the brute-force oracle for that case."
        )


def plan_constraints(spec: MissionSpec, scenario: HazardScenario, *,
                     max_plans: int = 5000) -> list[PlanConstraints]:
    """Exact dispatch-time support of every simple-path plan."""
    _check_conditions(spec)
    horizon = spec.policy.horizon
    pickup = spec.pickup.duration
    out: list[PlanConstraints] = []

    base_ok = _instant_constraint(scenario.node_timeline(spec.base), 0.0)

    for ingress in simple_paths(spec.network, spec.base, spec.resident, max_paths=max_plans):
        constraints = [base_ok]
        offset = 0.0
        for edge_id in ingress:
            edge = spec.network.edge(edge_id)
            entry, exit_ = offset, offset + edge.travel_time
            constraints.append(
                _occupancy_constraint(scenario.edge_timeline(edge), entry, exit_))
            constraints.append(
                _instant_constraint(scenario.node_timeline(edge.head), exit_))
            offset = exit_
        resident_offset = offset
        pickup_offset = resident_offset + pickup
        constraints.append(_occupancy_constraint(
            scenario.node_timeline(spec.resident), resident_offset, pickup_offset))

        for destination in spec.destinations:
            for egress in simple_paths(spec.network, spec.resident,
                                       destination.node, max_paths=max_plans):
                leg = list(constraints)
                offset = pickup_offset
                for edge_id in egress:
                    edge = spec.network.edge(edge_id)
                    entry, exit_ = offset, offset + edge.travel_time
                    leg.append(_occupancy_constraint(
                        scenario.edge_timeline(edge), entry, exit_))
                    leg.append(_instant_constraint(
                        scenario.node_timeline(edge.head), exit_))
                    offset = exit_
                arrival_offset = offset

                leg.append(_destination_constraint(destination, arrival_offset,
                                                   scenario))
                # Horizon: the search abandons any traversal that would end past
                # the horizon, and the latest instant of the plan is the arrival.
                leg.append(IntervalSet([ClosedInterval(-INFINITY,
                                                       horizon - arrival_offset)]))

                feasible = leg[0]
                for constraint in leg[1:]:
                    feasible = feasible.intersect(constraint)
                    if feasible.is_empty:
                        break

                out.append(PlanConstraints(
                    ingress_edges=ingress, egress_edges=egress,
                    destination=destination.node,
                    resident_offset=resident_offset,
                    pickup_offset=pickup_offset,
                    arrival_offset=arrival_offset,
                    feasible_t=feasible,
                ))
    return out


def _destination_constraint(destination: Destination, arrival_offset: float,
                            scenario: HazardScenario) -> IntervalSet:
    availability = IntervalSet([ClosedInterval(
        destination.available_from - arrival_offset,
        destination.available_until - arrival_offset,
    )])
    dwell = _occupancy_constraint(
        scenario.node_timeline(destination.node), arrival_offset,
        arrival_offset + destination.min_safe_dwell)
    return availability.intersect(dwell)


def scenario_feasible_set(spec: MissionSpec, scenario: HazardScenario, *,
                          max_plans: int = 5000) -> IntervalSet:
    r"""Exact :math:`S_i = \{t : \text{a safe plan exists under } m_i\}`."""
    result = IntervalSet.empty()
    for plan in plan_constraints(spec, scenario, max_plans=max_plans):
        if not plan.feasible_t.is_empty:
            result = result.union(plan.feasible_t)
    return result


@dataclass(frozen=True)
class ExactFeasibleSet:
    r"""The exact set :math:`\mathcal T_q`, with no temporal discretization."""

    threshold: float
    interval_set: IntervalSet
    study_range: tuple[float, float]
    scenario_sets: tuple[tuple[str, IntervalSet], ...]

    @property
    def components(self) -> tuple[ClosedInterval, ...]:
        r"""The connected components :math:`[a_k, b_k]` of :math:`\mathcal T_q`."""
        return self.interval_set.parts

    @property
    def is_empty(self) -> bool:
        return self.interval_set.is_empty

    @property
    def gaps(self) -> tuple[ClosedInterval, ...]:
        return self.interval_set.gaps()

    @property
    def last_feasible_instant(self) -> float | None:
        r""":math:`\sup \mathcal T_q`, which is attained because the set is closed.

        This is **not** a dispatch-by deadline unless the set is a single
        component reaching the start of the study range; see
        :attr:`is_dispatch_by_deadline`.
        """
        return self.interval_set.supremum

    @property
    def is_single_component(self) -> bool:
        return len(self.interval_set) == 1

    @property
    def is_dispatch_by_deadline(self) -> bool:
        """True iff "dispatch any time up to X" is a true statement here.

        Requires a single component that starts at (or before) the beginning of
        the studied range: only then does feasibility hold for *every* earlier
        dispatch time in the range.
        """
        if not self.is_single_component:
            return False
        return self.components[0].lo <= self.study_range[0] + EPS

    def contains(self, t: float) -> bool:
        return self.interval_set.contains(t)

    def describe(self) -> str:
        lines = [
            f"exact feasible dispatch set T_q, q = {self.threshold:g} "
            f"(no temporal discretization)",
            f"  studied range : [{self.study_range[0]:g}, {self.study_range[1]:g}]",
            f"  T_q           : {self.interval_set}",
            f"  components    : {len(self.interval_set)}",
        ]
        if not self.is_empty:
            lines.append(f"  last feasible dispatch instant : "
                         f"{self.last_feasible_instant:g} (attained: T_q is closed)")
            if self.is_dispatch_by_deadline:
                lines.append("  this set IS a dispatch-by deadline: every earlier "
                             "dispatch time in the studied range is feasible")
            else:
                lines.append("  this set is NOT a dispatch-by deadline: earlier "
                             "dispatch times are not all feasible")
        for gap in self.gaps:
            lines.append(f"  infeasible gap: ({gap.lo:g}, {gap.hi:g})")
        return "\n".join(lines)


def exact_feasible_set(spec: MissionSpec, ensemble: ScenarioEnsemble,
                       study_range: tuple[float, float], *,
                       threshold: float = 1.0,
                       max_plans: int = 5000,
                       max_scenarios: int = 16) -> ExactFeasibleSet:
    r"""Compute :math:`\mathcal T_q = \{t : P_{success}(t) \ge q\}` exactly."""
    _check_conditions(spec)
    ensemble.validate(spec.network)
    scenarios = tuple(ensemble)
    if len(scenarios) > max_scenarios:
        raise ExactSolverUnavailable(
            f"the exact solver enumerates scenario subsets; {len(scenarios)} "
            f"scenarios exceeds the cap of {max_scenarios}"
        )

    sets = [(s.name, scenario_feasible_set(spec, s, max_plans=max_plans))
            for s in scenarios]
    weights = [s.weight for s in scenarios]

    window = IntervalSet([ClosedInterval(study_range[0], study_range[1])])
    total = IntervalSet.empty()
    indices = range(len(scenarios))
    for size in indices:
        for subset in combinations(indices, size + 1):
            if sum(weights[i] for i in subset) < threshold - EPS:
                continue
            piece = sets[subset[0]][1]
            for i in subset[1:]:
                piece = piece.intersect(sets[i][1])
                if piece.is_empty:
                    break
            total = total.union(piece)

    return ExactFeasibleSet(
        threshold=threshold,
        interval_set=total.intersect(window),
        study_range=study_range,
        scenario_sets=tuple(sets),
    )


__all__ = [
    "ExactSolverUnavailable",
    "ClosedInterval",
    "IntervalSet",
    "PlanConstraints",
    "plan_constraints",
    "scenario_feasible_set",
    "ExactFeasibleSet",
    "exact_feasible_set",
]
