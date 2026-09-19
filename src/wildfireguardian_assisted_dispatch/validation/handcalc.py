"""Checking fixtures against their own hand calculations.

The fixtures carry expected feasible windows derived with arithmetic, not
recorded from a previous run.  This module is what compares the two, and it is
used both by the test suite and by ``wg-dispatch fixtures --check``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..fixtures.base import Fixture
from ..units import approx
from .invariants import InvariantReport, validate_many


@dataclass
class FixtureCheck:
    """The outcome of checking one fixture against its hand calculation."""

    key: str
    title: str
    expected_windows: tuple[tuple[float, float], ...]
    actual_windows: tuple[tuple[float, float], ...]
    expected_monotone: bool
    actual_monotone: bool
    p_success_mismatches: list[str] = field(default_factory=list)
    invariants: InvariantReport | None = None

    @property
    def windows_match(self) -> bool:
        if len(self.expected_windows) != len(self.actual_windows):
            return False
        return all(
            approx(a[0], b[0]) and approx(a[1], b[1])
            for a, b in zip(self.expected_windows, self.actual_windows)
        )

    @property
    def ok(self) -> bool:
        return (
            self.windows_match
            and self.expected_monotone == self.actual_monotone
            and not self.p_success_mismatches
            and (self.invariants is None or self.invariants.ok)
        )

    def describe(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        lines = [f"[{status}] fixture {self.key} - {self.title}"]
        lines.append(f"    expected windows: {_fmt(self.expected_windows)}")
        lines.append(f"    actual   windows: {_fmt(self.actual_windows)}")
        if self.expected_monotone != self.actual_monotone:
            lines.append(f"    monotone: expected {self.expected_monotone}, "
                         f"got {self.actual_monotone}")
        for mismatch in self.p_success_mismatches:
            lines.append(f"    {mismatch}")
        if self.invariants is not None and not self.invariants.ok:
            lines += [f"    {v}" for v in self.invariants.violations]
        return "\n".join(lines)


def check_fixture(fixture: Fixture, *, check_invariants: bool = True) -> FixtureCheck:
    """Run a fixture and compare it with the arithmetic in its docstring."""
    sweep = fixture.sweep()
    feasible = sweep.feasible_set(fixture.threshold)

    mismatches: list[str] = []
    for t, expected in fixture.expected_p_success.items():
        actual = sweep.outcome_at(t).p_success
        if not approx(actual, expected):
            mismatches.append(
                f"P_success({t:g}) = {actual:g}, hand calculation says {expected:g}"
            )

    invariants: InvariantReport | None = None
    if check_invariants:
        invariants = InvariantReport()
        for scenario in fixture.ensemble:
            results = [o.result_for(scenario.name) for o in sweep.outcomes]
            single = validate_many(results, fixture.spec, scenario)
            invariants.checks_run.extend(single.checks_run)
            invariants.violations.extend(
                f"[{scenario.name}] {v}" for v in single.violations
            )

    return FixtureCheck(
        key=fixture.key,
        title=fixture.title,
        expected_windows=fixture.expected_windows,
        actual_windows=feasible.intervals,
        expected_monotone=fixture.expected_monotone,
        actual_monotone=feasible.is_monotone,
        p_success_mismatches=mismatches,
        invariants=invariants,
    )


def _fmt(windows) -> str:
    if not windows:
        return "empty"
    return " U ".join(f"[{a:g}, {b:g}]" for a, b in windows)


__all__ = ["FixtureCheck", "check_fixture"]
