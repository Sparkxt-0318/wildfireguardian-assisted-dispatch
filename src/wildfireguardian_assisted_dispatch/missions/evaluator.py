"""Deterministic mission evaluator.

One call answers one question:

    Dispatched at ``t``, under coherent hazard scenario ``m``, can the responder
    complete  base -> resident -> pickup -> safe destination ?

and returns the whole timeline, not a boolean.

Structure of the evaluation
---------------------------
1. **Dispatch.**  The base must be a safe place to be at ``t``.
2. **Ingress.**   Enumerate *every* arrival time at the resident's address.
3. **Service.**   For each such arrival, the pickup occupies
   ``[arrival, arrival + pickup_duration]`` at the resident's node, with no
   implicit waiting before it starts.
4. **Egress.**    From the end of the pickup, enumerate every arrival at every
   declared destination, and keep the ones the destination actually accepts.
5. **Selection.** Earliest destination arrival wins, ties broken by declared
   destination priority and then lexicographically, so the result is
   reproducible byte for byte.
6. **Audit.**     Whatever the admission policy, the selected plan is re-checked
   over full traversal intervals.  A plan that spends an instant on an unsafe
   element is reported as ``CAUGHT_MID_EDGE``, never as a success.

Step 2 branching over all arrival times (not just the earliest) is what makes
the evaluator correct under reopening hazards, and it is also the mechanism
behind the non-monotonic feasibility result in fixture F.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..hazards.scenario import HazardScenario, ScenarioEnsemble
from ..hazards.semantics import assess_node_occupancy
from ..search.router import arrivals_at, route_from_arrival
from ..search.time_expanded import Arrival, Exploration, explore
from ..units import INFINITY, gt
from .result import (
    FailureReason,
    HazardConflict,
    LogEntry,
    MissionResult,
    Route,
    progress_rank,
)
from .spec import Destination, MissionSpec


class ArrivalBranchBudgetExceeded(RuntimeError):
    """More distinct resident-arrival times exist than the evaluator may branch on.

    Raised rather than silently truncated.  Because an earlier arrival does not
    dominate a later one under reopening hazards, dropping arrival times can
    turn a feasible mission into an infeasible one - the same class of silent
    failure that :class:`~...search.time_expanded.SearchBudgetExceeded` exists
    to prevent (D-013).  Raise
    :attr:`~.policy.MissionPolicy.max_resident_arrivals` if the branching is
    genuinely needed.
    """


@dataclass(frozen=True)
class _Plan:
    """A complete candidate mission, before auditing."""

    ingress: Route
    resident_arrival: float
    pickup_start: float
    pickup_end: float
    egress: Route
    destination: Destination
    destination_arrival: float

    @property
    def sort_key(self) -> tuple:
        return (
            self.destination_arrival,
            -self.destination.priority,
            self.destination.node,
            self.ingress.edge_sequence,
            self.egress.edge_sequence,
        )


@dataclass(frozen=True)
class _Failure:
    reason: FailureReason
    conflict: HazardConflict | None
    resident_arrival: float | None = None
    pickup_start: float | None = None
    pickup_end: float | None = None
    ingress: Route | None = None

    @property
    def rank(self) -> tuple[int, float]:
        """Sort key for "which failure is worth reporting".

        Furthest-progressed first; among equally-progressed branches, the one
        built on the *earliest* resident arrival, since that is the plan a
        reader would have tried first.
        """
        arrival = self.resident_arrival if self.resident_arrival is not None else 0.0
        return (progress_rank(self.reason), -arrival)


def evaluate_mission(spec: MissionSpec, dispatch_time: float,
                     scenario: HazardScenario) -> MissionResult:
    """Evaluate one mission at one dispatch time under one coherent scenario."""
    policy = spec.policy
    scenario.validate(spec.network)

    def fail(reason: FailureReason, conflict: HazardConflict | None,
             *, ingress: Route | None = None, resident_arrival: float | None = None,
             pickup_start: float | None = None, pickup_end: float | None = None,
             log: Sequence[LogEntry] = (), notes: Sequence[str] = ()) -> MissionResult:
        return MissionResult(
            dispatch_time=dispatch_time,
            scenario=scenario.name,
            mission_success=False,
            failure_reason=reason,
            hazard_conflict=conflict,
            ingress_route=ingress,
            resident_arrival_time=resident_arrival,
            pickup_start=pickup_start,
            pickup_end=pickup_end,
            log=tuple(log),
            policy=policy.describe(),
            mission_name=spec.name,
            pickup_duration=spec.pickup.duration,
            notes=tuple(notes),
        )

    # -- 1. dispatch --------------------------------------------------------
    base_state = assess_node_occupancy(spec.base, dispatch_time, dispatch_time, scenario)
    if not base_state.safe_throughout:
        return fail(
            FailureReason.BASE_UNSAFE_AT_DISPATCH,
            HazardConflict.from_assessment(base_state, "dispatch"),
        )
    if gt(dispatch_time, policy.horizon):
        return fail(
            FailureReason.HORIZON_EXCEEDED, None,
            notes=[f"dispatch time {dispatch_time:g} is beyond the "
                   f"{policy.horizon:g} min planning horizon"],
        )

    # -- 2. ingress ---------------------------------------------------------
    ingress_search = _search(spec, scenario, spec.base, dispatch_time)
    resident_arrivals = arrivals_at(ingress_search, spec.resident)
    if not resident_arrivals:
        return fail(*_diagnose_unreachable(
            ingress_search, spec.resident, "ingress",
            FailureReason.NO_SAFE_ROUTE_INGRESS,
            FailureReason.RESIDENT_NODE_UNSAFE_ON_ARRIVAL,
        ))

    if len(resident_arrivals) > policy.max_resident_arrivals:
        raise ArrivalBranchBudgetExceeded(
            f"{len(resident_arrivals)} distinct arrival times at "
            f"{spec.resident!r} exceed max_resident_arrivals="
            f"{policy.max_resident_arrivals}. Truncating them could hide a "
            "feasible mission, because a later arrival is not dominated by an "
            "earlier one under reopening hazards."
        )

    plans: list[_Plan] = []
    failures: list[_Failure] = []

    for arrival in resident_arrivals:
        ingress_route = route_from_arrival(spec.base, dispatch_time, arrival)
        pickup_start, pickup_end = spec.pickup.window(arrival.time)

        # -- 3. service -----------------------------------------------------
        service = assess_node_occupancy(spec.resident, pickup_start, pickup_end, scenario)
        if not service.safe_throughout:
            failures.append(_Failure(
                FailureReason.SERVICE_WINDOW_UNSAFE,
                HazardConflict.from_assessment(
                    service, "service",
                    detail=(f"the {spec.pickup.duration:g} min pickup would occupy "
                            f"{spec.resident} over [{pickup_start:g}, {pickup_end:g}]; "
                            + service.explain()),
                ),
                resident_arrival=arrival.time, pickup_start=pickup_start,
                pickup_end=pickup_end, ingress=ingress_route,
            ))
            continue
        if gt(pickup_end, policy.horizon):
            failures.append(_Failure(
                FailureReason.HORIZON_EXCEEDED, None,
                resident_arrival=arrival.time, pickup_start=pickup_start,
                pickup_end=pickup_end, ingress=ingress_route,
            ))
            continue

        # -- 4. egress ------------------------------------------------------
        egress_search = _search(spec, scenario, spec.resident, pickup_end)
        reached_any = False
        for destination in spec.destinations:
            for dest_arrival in arrivals_at(egress_search, destination.node):
                reached_any = True
                plan_or_failure = _qualify_destination(
                    spec, scenario, destination, dest_arrival, ingress_route,
                    arrival, pickup_start, pickup_end, egress_search,
                )
                if isinstance(plan_or_failure, _Plan):
                    plans.append(plan_or_failure)
                else:
                    failures.append(plan_or_failure)
        if not reached_any:
            reason, conflict = _diagnose_unreachable(
                egress_search, spec.destination_nodes, "egress",
                FailureReason.NO_SAFE_ROUTE_EGRESS,
                FailureReason.NO_SAFE_ROUTE_EGRESS,
            )
            failures.append(_Failure(
                reason, conflict, resident_arrival=arrival.time,
                pickup_start=pickup_start, pickup_end=pickup_end,
                ingress=ingress_route,
            ))

    if not plans:
        worst = max(failures, key=lambda f: f.rank) if failures else None
        if worst is None:  # pragma: no cover - defensive
            return fail(FailureReason.NO_SAFE_ROUTE_EGRESS, None)
        return fail(worst.reason, worst.conflict, ingress=worst.ingress,
                    resident_arrival=worst.resident_arrival,
                    pickup_start=worst.pickup_start, pickup_end=worst.pickup_end)

    # -- 5. selection -------------------------------------------------------
    plan = min(plans, key=lambda p: p.sort_key)

    # -- 6. audit -----------------------------------------------------------
    return _audit_and_record(spec, scenario, dispatch_time, plan)


def _search(spec: MissionSpec, scenario: HazardScenario, origin: str,
            start_time: float) -> Exploration:
    return explore(
        spec.network, spec.travel, scenario, origin, start_time,
        admission=spec.policy.admission,
        horizon=spec.policy.horizon,
        max_states=spec.policy.max_states,
        allow_node_revisits=spec.policy.allow_node_revisits,
    )


def _qualify_destination(spec: MissionSpec, scenario: HazardScenario,
                         destination: Destination, dest_arrival: Arrival,
                         ingress_route: Route, resident_arrival: Arrival,
                         pickup_start: float, pickup_end: float,
                         egress_search: Exploration) -> "_Plan | _Failure":
    """Check that arriving at ``destination`` at this time is actually the end
    of the mission, rather than merely a change of scenery."""
    egress_route = route_from_arrival(spec.resident, pickup_end, dest_arrival)

    if not destination.accepts_arrival(dest_arrival.time):
        return _Failure(
            FailureReason.DESTINATION_UNAVAILABLE,
            HazardConflict(
                element_id=destination.node, element_type="destination",
                leg="egress", entry_time=dest_arrival.time,
                exit_time=dest_arrival.time, safety_lost_at=None,
                next_opening=None,
                timeline=(f"accepts arrivals in [{destination.available_from:g}, "
                          f"{_fmt(destination.available_until)}]"),
                detail=(f"destination {destination.node} does not accept an "
                        f"arrival at t={dest_arrival.time:g}"),
            ),
            resident_arrival=resident_arrival.time, pickup_start=pickup_start,
            pickup_end=pickup_end, ingress=ingress_route,
        )

    dwell_end = dest_arrival.time + destination.min_safe_dwell
    dwell = assess_node_occupancy(destination.node, dest_arrival.time, dwell_end, scenario)
    if not dwell.safe_throughout:
        return _Failure(
            FailureReason.REFUGE_DWELL_UNSAFE,
            HazardConflict.from_assessment(
                dwell, "egress",
                detail=(f"{destination.node} must stay safe for "
                        f"{destination.min_safe_dwell:g} min after arrival at "
                        f"t={dest_arrival.time:g}; " + dwell.explain()),
            ),
            resident_arrival=resident_arrival.time, pickup_start=pickup_start,
            pickup_end=pickup_end, ingress=ingress_route,
        )

    return _Plan(
        ingress=ingress_route,
        resident_arrival=resident_arrival.time,
        pickup_start=pickup_start,
        pickup_end=pickup_end,
        egress=egress_route,
        destination=destination,
        destination_arrival=dest_arrival.time,
    )


def _diagnose_unreachable(search: Exploration, target: str | Sequence[str],
                          leg: str, generic: FailureReason,
                          node_specific: FailureReason) -> tuple[FailureReason, HazardConflict | None]:
    """Explain why a target was never reached."""
    targets = {target} if isinstance(target, str) else set(target)
    conflicts = search.blocking_conflicts()
    for assessment in conflicts:
        if assessment.element_type == "node" and assessment.element_id in targets:
            return node_specific, HazardConflict.from_assessment(assessment, leg)
    if search.origin_blocked is not None:
        return generic, HazardConflict.from_assessment(search.origin_blocked, leg)
    if conflicts:
        return generic, HazardConflict.from_assessment(
            conflicts[0], leg,
            detail=("no admissible route; the nearest-viable blocking element was "
                    + conflicts[0].explain()),
        )
    return generic, None


def _audit_and_record(spec: MissionSpec, scenario: HazardScenario,
                      dispatch_time: float, plan: _Plan) -> MissionResult:
    """Re-check the selected plan over full traversal intervals and build the log."""
    log: list[LogEntry] = [LogEntry(
        kind="dispatch", start_time=dispatch_time, end_time=dispatch_time,
        element=spec.base, detail="responder dispatched from base",
    )]

    caught = None
    for traversal in plan.ingress.traversals:
        log.append(_travel_entry(traversal))
        if not traversal.safe_throughout:
            caught = (traversal, "ingress")
            break

    if caught is None:
        log.append(LogEntry(
            kind="arrival", start_time=plan.resident_arrival,
            end_time=plan.resident_arrival, element=spec.resident,
            detail="responder reaches the resident",
        ))
        log.append(LogEntry(
            kind="service", start_time=plan.pickup_start, end_time=plan.pickup_end,
            element=spec.resident,
            detail=(f"pickup, {spec.pickup.duration:g} min "
                    f"({spec.pickup.profile})"),
        ))
        for traversal in plan.egress.traversals:
            log.append(_travel_entry(traversal))
            if not traversal.safe_throughout:
                caught = (traversal, "egress")
                break

    if caught is not None:
        traversal, leg = caught
        lost_at = (traversal.safety_lost_at if traversal.safety_lost_at is not None
                   else traversal.entry_time)
        log.append(LogEntry(
            kind="abort", start_time=lost_at, end_time=lost_at,
            element=traversal.edge_id,
            detail=("mission ends here: the segment became unsafe mid-traversal "
                    "and there is no modelled escape"),
        ))
        occupants = ("responder" if leg == "ingress"
                     else "responder and resident")
        conflict = HazardConflict(
            element_id=traversal.edge_id, element_type="edge", leg=leg,
            entry_time=traversal.entry_time, exit_time=traversal.exit_time,
            safety_lost_at=traversal.safety_lost_at, next_opening=None,
            timeline="",
            detail=(f"{occupants} caught on {traversal.edge_id} at "
                    f"t={_fmt(traversal.safety_lost_at)}: entered at "
                    f"{traversal.entry_time:g}, would have cleared at "
                    f"{traversal.exit_time:g}"),
        )
        return MissionResult(
            dispatch_time=dispatch_time, scenario=scenario.name,
            mission_success=False, failure_reason=FailureReason.CAUGHT_MID_EDGE,
            hazard_conflict=conflict,
            ingress_route=plan.ingress,
            resident_arrival_time=None if leg == "ingress" else plan.resident_arrival,
            pickup_start=None if leg == "ingress" else plan.pickup_start,
            pickup_end=None if leg == "ingress" else plan.pickup_end,
            egress_route=plan.egress if leg == "egress" else None,
            destination_node=None, destination_arrival=None,
            log=tuple(log), policy=spec.policy.describe(), mission_name=spec.name,
            pickup_duration=spec.pickup.duration,
            notes=(
                f"the planner admitted this traversal under "
                f"{spec.policy.admission.value!r} admission, which checks only the "
                f"entry instant; the full-interval audit rejects it",
                f"the plan would have reached {plan.destination.node} at "
                f"t={plan.destination_arrival:g} had the segment held",
            ),
        )

    log.append(LogEntry(
        kind="arrival", start_time=plan.destination_arrival,
        end_time=plan.destination_arrival, element=plan.destination.node,
        detail="resident delivered to a safe destination",
    ))
    if plan.destination.min_safe_dwell:
        log.append(LogEntry(
            kind="dwell", start_time=plan.destination_arrival,
            end_time=plan.destination_arrival + plan.destination.min_safe_dwell,
            element=plan.destination.node,
            detail=(f"required safe dwell of "
                    f"{plan.destination.min_safe_dwell:g} min satisfied"),
        ))

    return MissionResult(
        dispatch_time=dispatch_time, scenario=scenario.name, mission_success=True,
        failure_reason=FailureReason.NONE, hazard_conflict=None,
        ingress_route=plan.ingress, resident_arrival_time=plan.resident_arrival,
        pickup_start=plan.pickup_start, pickup_end=plan.pickup_end,
        egress_route=plan.egress, destination_node=plan.destination.node,
        destination_arrival=plan.destination_arrival, log=tuple(log),
        policy=spec.policy.describe(), mission_name=spec.name,
        pickup_duration=spec.pickup.duration,
    )


def _travel_entry(traversal) -> LogEntry:
    """One travel line of the mission log.

    An unsafe traversal is logged as ``travel_aborted`` and is truncated at the
    instant safety was lost, because that is when the vehicle stopped moving
    towards anywhere. Logging the full planned duration would put minutes on
    the clock that the mission never got to spend.
    """
    if not traversal.safe_throughout:
        lost_at = (traversal.safety_lost_at if traversal.safety_lost_at is not None
                   else traversal.entry_time)
        return LogEntry(
            kind="travel_aborted", start_time=traversal.entry_time,
            end_time=lost_at, element=traversal.edge_id,
            detail=(f"segment safety lost at t={_fmt(traversal.safety_lost_at)}, "
                    f"{traversal.exit_time - lost_at:g} min short of the far end"),
        )
    margin = traversal.margin
    if margin is None or margin == INFINITY:
        detail = "clear"
    else:
        detail = f"clear, {margin:g} min margin"
    return LogEntry(
        kind="travel", start_time=traversal.entry_time,
        end_time=traversal.exit_time, element=traversal.edge_id, detail=detail,
    )


def _fmt(value: float | None) -> str:
    if value is None:
        return "never"
    if value == INFINITY:
        return "inf"
    return f"{value:g}"


def evaluate_over_ensemble(spec: MissionSpec, dispatch_time: float,
                           ensemble: ScenarioEnsemble) -> tuple[MissionResult, ...]:
    """Evaluate one dispatch time against every scenario, independently.

    Scenario-by-scenario is the only correct way to aggregate here: each
    scenario is one coherent fire, and success is a property of the whole
    mission within that fire.  Nothing is multiplied across edges.
    """
    return tuple(evaluate_mission(spec, dispatch_time, s) for s in ensemble)


__all__ = ["evaluate_mission", "evaluate_over_ensemble",
           "ArrivalBranchBudgetExceeded"]
