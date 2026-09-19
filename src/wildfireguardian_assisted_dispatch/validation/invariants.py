"""Post-hoc invariants on mission records.

These checks are deliberately independent of the evaluator: they re-derive what
the record claims, straight from the network, the pickup model and the hazard
scenario.  If the evaluator ever grows a shortcut that fabricates time or
glosses over a closure, these are what catch it.

The no-implicit-waiting check is the load-bearing one.  "There is no waiting"
is a claim about *every minute of the mission clock*, and the only way to keep
that claim honest is to insist that consecutive log entries abut exactly and
that each entry's duration equals the physical quantity it represents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from ..hazards.scenario import HazardScenario
from ..hazards.semantics import assess_edge_traversal, assess_node_occupancy
from ..missions.result import FailureReason, MissionResult, Route
from ..missions.spec import MissionSpec
from ..units import approx, leq


class InvariantViolation(AssertionError):
    """A mission record contradicts the model it claims to come from."""


@dataclass
class InvariantReport:
    checks_run: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def record(self, name: str, condition: bool, message: str) -> None:
        self.checks_run.append(name)
        if not condition:
            self.violations.append(f"{name}: {message}")

    def raise_if_failed(self) -> "InvariantReport":
        if self.violations:
            raise InvariantViolation(
                f"{len(self.violations)} invariant violation(s):\n  - "
                + "\n  - ".join(self.violations)
            )
        return self

    def describe(self) -> str:
        head = "OK" if self.ok else f"{len(self.violations)} VIOLATION(S)"
        lines = [f"invariant report: {head} ({len(self.checks_run)} checks)"]
        lines += [f"  ! {v}" for v in self.violations]
        return "\n".join(lines)


def check_time_accounting(result: MissionResult, report: InvariantReport) -> None:
    """Consecutive log entries must abut, with no gap and no overlap."""
    entries = result.log
    if not entries:
        return
    report.record(
        "log.starts_at_dispatch",
        approx(entries[0].start_time, result.dispatch_time),
        f"first log entry starts at {entries[0].start_time}, "
        f"dispatch is at {result.dispatch_time}",
    )
    for previous, entry in zip(entries, entries[1:]):
        report.record(
            "log.contiguous",
            approx(previous.end_time, entry.start_time),
            f"gap or overlap between {previous.kind}@{previous.end_time:g} and "
            f"{entry.kind}@{entry.start_time:g}",
        )
        report.record(
            "log.non_negative_duration",
            leq(entry.start_time, entry.end_time),
            f"{entry.kind} entry runs backwards: "
            f"[{entry.start_time:g}, {entry.end_time:g}]",
        )


def check_no_implicit_waiting(result: MissionResult, spec: MissionSpec,
                              report: InvariantReport) -> None:
    """Every minute of the clock must be travel or declared service.

    A ``travel`` entry must last exactly the edge's travel time, and a
    ``service`` entry exactly the pickup duration.  Anything else means idle
    time was smuggled into a leg.
    """
    for entry in result.log:
        if entry.kind == "travel":
            edge = spec.network.edge(entry.element)
            expected = spec.travel.duration(edge, entry.start_time)
            report.record(
                "no_implicit_waiting.travel_duration",
                approx(entry.duration, expected),
                f"traversal of {entry.element} lasted {entry.duration:g} min "
                f"but the edge takes {expected:g} min",
            )
        elif entry.kind == "service":
            report.record(
                "no_implicit_waiting.service_duration",
                approx(entry.duration, spec.pickup.duration),
                f"service lasted {entry.duration:g} min but the pickup model "
                f"says {spec.pickup.duration:g} min",
            )
        elif entry.kind == "travel_aborted":
            edge = spec.network.edge(entry.element)
            full = spec.travel.duration(edge, entry.start_time)
            report.record(
                "no_implicit_waiting.aborted_travel_is_truncated",
                leq(entry.duration, full),
                f"aborted traversal of {entry.element} lasted "
                f"{entry.duration:g} min, longer than the edge itself "
                f"({full:g} min)",
            )
        elif entry.kind in {"dispatch", "arrival", "abort"}:
            report.record(
                "no_implicit_waiting.instant_events",
                approx(entry.duration, 0.0),
                f"{entry.kind} entry occupies {entry.duration:g} min; it must "
                "be instantaneous",
            )

    report.record(
        "no_implicit_waiting.no_wait_entries",
        not any(e.kind == "wait" for e in result.log),
        "the record contains a wait entry, but the policy prohibits waiting",
    )


def check_route_chaining(route: Route | None, leg: str, spec: MissionSpec,
                         report: InvariantReport) -> None:
    """A route's traversals must form an unbroken chain in space and time."""
    if route is None:
        return
    previous_head = route.origin
    previous_time = route.start_time
    seen = {route.origin}
    for traversal in route.traversals:
        edge = spec.network.edge(traversal.edge_id)
        report.record(
            f"{leg}.edge_endpoints",
            edge.tail == traversal.tail and edge.head == traversal.head,
            f"{traversal.edge_id} is recorded as "
            f"{traversal.tail}->{traversal.head} but the network says "
            f"{edge.tail}->{edge.head}",
        )
        report.record(
            f"{leg}.spatial_chain",
            traversal.tail == previous_head,
            f"{traversal.edge_id} starts at {traversal.tail}, "
            f"but the previous leg ended at {previous_head}",
        )
        report.record(
            f"{leg}.temporal_chain",
            approx(traversal.entry_time, previous_time),
            f"{traversal.edge_id} is entered at {traversal.entry_time:g}, "
            f"but the responder was free at {previous_time:g}",
        )
        if not spec.policy.allow_node_revisits:
            report.record(
                f"{leg}.simple_path",
                traversal.head not in seen,
                f"node {traversal.head} is visited twice on the {leg} leg, "
                "which the policy prohibits (it would be waiting by driving)",
            )
        seen.add(traversal.head)
        previous_head = traversal.head
        previous_time = traversal.exit_time


def check_full_interval_coverage(result: MissionResult, spec: MissionSpec,
                                 scenario: HazardScenario,
                                 report: InvariantReport) -> None:
    """Re-assess every occupied element over its whole interval, from scratch."""
    for leg, route in (("ingress", result.ingress_route),
                       ("egress", result.egress_route)):
        if route is None:
            continue
        for traversal in route.traversals:
            edge = spec.network.edge(traversal.edge_id)
            fresh = assess_edge_traversal(edge, traversal.entry_time,
                                          traversal.exit_time, scenario)
            report.record(
                f"{leg}.recorded_safety_matches_scenario",
                fresh.safe_throughout == traversal.safe_throughout,
                f"{traversal.edge_id} over "
                f"[{traversal.entry_time:g}, {traversal.exit_time:g}] is "
                f"recorded as safe_throughout={traversal.safe_throughout} but "
                f"the scenario says {fresh.safe_throughout}",
            )

    if result.mission_success:
        for leg, route in (("ingress", result.ingress_route),
                           ("egress", result.egress_route)):
            report.record(
                f"success.{leg}_is_safe",
                route is not None and route.is_safe,
                f"a successful mission has an unsafe {leg} traversal; "
                "full-interval auditing has been bypassed",
            )
        if result.pickup_start is not None and result.pickup_end is not None:
            service = assess_node_occupancy(spec.resident, result.pickup_start,
                                            result.pickup_end, scenario)
            report.record(
                "success.service_window_is_safe",
                service.safe_throughout,
                f"the pickup window [{result.pickup_start:g}, "
                f"{result.pickup_end:g}] is not safe at {spec.resident}",
            )


def check_record_consistency(result: MissionResult, spec: MissionSpec,
                             report: InvariantReport) -> None:
    """Success and failure records must each be internally complete."""
    if result.mission_success:
        report.record(
            "success.reason_is_none",
            result.failure_reason is FailureReason.NONE
            and result.hazard_conflict is None,
            f"successful mission carries failure reason "
            f"{result.failure_reason.value!r}",
        )
        required = {
            "ingress_route": result.ingress_route,
            "resident_arrival_time": result.resident_arrival_time,
            "pickup_start": result.pickup_start,
            "pickup_end": result.pickup_end,
            "egress_route": result.egress_route,
            "destination_arrival": result.destination_arrival,
            "destination_node": result.destination_node,
        }
        for name, value in required.items():
            report.record("success.record_complete", value is not None,
                          f"successful mission has no {name}")
        if (result.resident_arrival_time is not None
                and result.pickup_end is not None):
            report.record(
                "success.pickup_window_matches_model",
                approx(result.pickup_end - result.pickup_start,
                       spec.pickup.duration),
                "pickup window length does not match the pickup model",
            )
        if result.destination_node is not None:
            destination = spec.destination(result.destination_node)
            report.record(
                "success.destination_accepts_arrival",
                destination.accepts_arrival(result.destination_arrival),
                f"{destination.node} does not accept an arrival at "
                f"{result.destination_arrival:g}",
            )
    else:
        report.record(
            "failure.reason_is_set",
            result.failure_reason is not FailureReason.NONE,
            "failed mission carries no failure reason",
        )
        report.record(
            "failure.no_destination_arrival",
            result.destination_arrival is None,
            "failed mission reports a destination arrival",
        )


def validate_mission_result(result: MissionResult, spec: MissionSpec,
                            scenario: HazardScenario) -> InvariantReport:
    """Run every invariant against one mission record."""
    report = InvariantReport()
    check_time_accounting(result, report)
    check_no_implicit_waiting(result, spec, report)
    check_route_chaining(result.ingress_route, "ingress", spec, report)
    check_route_chaining(result.egress_route, "egress", spec, report)
    check_full_interval_coverage(result, spec, scenario, report)
    check_record_consistency(result, spec, report)
    return report


def validate_many(results: Sequence[MissionResult], spec: MissionSpec,
                  scenario: HazardScenario) -> InvariantReport:
    combined = InvariantReport()
    for result in results:
        single = validate_mission_result(result, spec, scenario)
        combined.checks_run.extend(single.checks_run)
        combined.violations.extend(
            f"[t={result.dispatch_time:g}] {v}" for v in single.violations
        )
    return combined


__all__ = [
    "InvariantViolation",
    "InvariantReport",
    "validate_mission_result",
    "validate_many",
    "check_no_implicit_waiting",
    "check_full_interval_coverage",
    "check_time_accounting",
    "check_route_chaining",
    "check_record_consistency",
]
