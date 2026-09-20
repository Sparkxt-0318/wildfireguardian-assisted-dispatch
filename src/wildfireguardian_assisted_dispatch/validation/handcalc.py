"""Checking fixtures against their own hand calculations.

The fixtures carry expected feasible windows derived with arithmetic, not
recorded from a previous run.  This module is what compares the two, and it is
used both by the test suite and by ``wg-dispatch fixtures --check``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..fixtures.base import Fixture
from ..units import approx
from .brute_force import reference_p_success
from ..feasibility.exact import ExactSolverUnavailable, exact_feasible_set
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
    expected_exact: tuple[tuple[float, float], ...] = ()
    actual_exact: tuple[tuple[float, float], ...] = ()
    exact_unavailable_reason: str | None = None
    exact_expected_to_apply: bool = True
    oracle_disagreements: list[str] = field(default_factory=list)
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
    def exact_match(self) -> bool:
        if not self.exact_expected_to_apply:
            # The fixture asserts the solver should refuse; it must have.
            return self.exact_unavailable_reason is not None
        if self.exact_unavailable_reason is not None:
            return False
        if len(self.expected_exact) != len(self.actual_exact):
            return False
        return all(
            approx(a[0], b[0]) and approx(a[1], b[1])
            for a, b in zip(self.expected_exact, self.actual_exact)
        )

    @property
    def ok(self) -> bool:
        return (
            self.windows_match
            and self.exact_match
            and self.expected_monotone == self.actual_monotone
            and not self.oracle_disagreements
            and not self.p_success_mismatches
            and (self.invariants is None or self.invariants.ok)
        )

    def describe(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        lines = [f"[{status}] fixture {self.key} - {self.title}"]
        lines.append(f"    sampled   expected: {_fmt(self.expected_windows)}")
        lines.append(f"    sampled   actual  : {_fmt(self.actual_windows)}")
        if self.exact_expected_to_apply:
            lines.append(f"    exact     expected: {_fmt(self.expected_exact)}")
            lines.append(f"    exact     actual  : "
                         f"{_fmt(self.actual_exact) if self.exact_unavailable_reason is None else 'UNAVAILABLE'}")
            if self.exact_unavailable_reason:
                lines.append(f"    exact solver refused: {self.exact_unavailable_reason}")
        else:
            lines.append("    exact solver: correctly does not apply "
                         f"({(self.exact_unavailable_reason or 'BUT IT DID NOT REFUSE')[:70]})")
        for disagreement in self.oracle_disagreements:
            lines.append(f"    oracle: {disagreement}")
        if self.expected_monotone != self.actual_monotone:
            lines.append(f"    monotone: expected {self.expected_monotone}, "
                         f"got {self.actual_monotone}")
        for mismatch in self.p_success_mismatches:
            lines.append(f"    {mismatch}")
        if self.invariants is not None and not self.invariants.ok:
            lines += [f"    {v}" for v in self.invariants.violations]
        return "\n".join(lines)


def check_fixture(fixture: Fixture, *, check_invariants: bool = True,
                  check_oracle: bool = True) -> FixtureCheck:
    """Run a fixture and compare it with the arithmetic in its docstring.

    Three independent comparisons, not one:

    1. the sampled sweep against the fixture's hand-derived grid windows;
    2. the exact interval solver against the fixture's hand-derived components;
    3. the brute-force reference oracle against the main solver, point by point
       on the grid.

    (2) and (3) exist because (1) alone can only tell us the main solver is
    self-consistent.
    """
    sweep = fixture.sweep()
    feasible = sweep.feasible_set(fixture.threshold)

    actual_exact: tuple[tuple[float, float], ...] = ()
    unavailable: str | None = None
    try:
        exact = exact_feasible_set(
            fixture.spec, fixture.ensemble,
            (fixture.grid[0], fixture.grid[-1]), threshold=fixture.threshold)
        actual_exact = tuple((c.lo, c.hi) for c in exact.components)
    except ExactSolverUnavailable as exc:
        unavailable = str(exc)

    disagreements: list[str] = []
    if check_oracle:
        for t, sampled in zip(sweep.grid, feasible.flags):
            oracle = reference_p_success(fixture.spec, t, fixture.ensemble)
            oracle_flag = oracle >= fixture.threshold - 1e-9
            if oracle_flag != sampled:
                disagreements.append(
                    f"t={t:g}: main solver says {sampled}, reference oracle "
                    f"says {oracle_flag} (P={oracle:g})")

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
        expected_exact=fixture.expected_exact_components,
        actual_exact=actual_exact,
        exact_unavailable_reason=unavailable,
        exact_expected_to_apply=fixture.exact_solver_applies,
        oracle_disagreements=disagreements,
        p_success_mismatches=mismatches,
        invariants=invariants,
    )


def _fmt(windows) -> str:
    if not windows:
        return "empty"
    return " U ".join(f"[{a:g}, {b:g}]" for a, b in windows)


__all__ = ["FixtureCheck", "check_fixture"]
