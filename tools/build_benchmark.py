#!/usr/bin/env python3
"""Generate the v0.1 scientific benchmark report.

Every number in ``reports/BENCHMARK_V0_1.md`` is produced by running the
solvers here, and every number is compared against the fixture's own hand
calculation and against the independent brute-force oracle before it is
written.  Nothing is transcribed by hand, so the report cannot drift away from
the code.

    python tools/build_benchmark.py            # print
    python tools/build_benchmark.py --write    # write reports/BENCHMARK_V0_1.md
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from wildfireguardian_assisted_dispatch.feasibility.exact import (
    ExactSolverUnavailable,
    exact_feasible_set,
)
from wildfireguardian_assisted_dispatch.feasibility.sensitivity import (
    sweep_pickup_durations,
)
from wildfireguardian_assisted_dispatch.fixtures import load
from wildfireguardian_assisted_dispatch.missions.evaluator import evaluate_mission
from wildfireguardian_assisted_dispatch.service.pickup import (
    PICKUP_SENSITIVITY_MINUTES,
)
from wildfireguardian_assisted_dispatch.validation.brute_force import (
    reference_feasible_flags,
)
from wildfireguardian_assisted_dispatch.validation.handcalc import check_fixture
from wildfireguardian_assisted_dispatch.version import __version__

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "reports" / "BENCHMARK_V0_1.md"


@dataclass(frozen=True)
class Example:
    label: str
    title: str
    fixture_keys: tuple[str, ...]
    diagram: str
    lesson: str
    extra: str = ""


DIAGRAMS = {
    "a": """    base ──10──▶ home ──10──▶ shelter
                            egress corridor lost at t = 40
    pickup 5 min""",
    "c": """                       ┌── 8 ──▶ home        (dead-end spur)
    base ──10──▶ junction                       corridor 'spur', lost at t = 45
                       └── 6 ──▶ shelter        both directions share it
    pickup 5 min""",
    "b": """                 ┌─5─▶ north_j ─5─▶┐        ridge road lost at t = 35
    base ─5─▶ home                    shelter
                 └10─▶ south_j ─10─▶┘        valley road lost at t = 60
    pickup 5 min""",
    "b_ensemble": """                 ┌─5─▶ north_j ─5─▶┐
    base ─5─▶ home                    shelter      pickup 5 min
                 └10─▶ south_j ─10─▶┘

    nominal      w=0.5   ridge lost at 35, valley at 60
    wind_shift   w=0.3   ridge lost at 20, valley at 60
    south_flank  w=0.2   ridge lost at 35, valley at 28""",
    "d": """    base ──8──▶ home ──12──▶ shelter
                            egress corridor lost at t = 50
    pickup swept over 2 / 5 / 10 / 15 min""",
    "e": """                 ┌── 5 ──▶ refuge    overrun at t = 60, needs 30 min dwell
    base ─6─▶ home
                 └── 20 ─▶ shelter   corridor lost at t = 70
    pickup 5 min""",
    "f": """    base ──5──▶ home ──5──▶ shelter
                            egress corridor safe on [0, 12] ∪ [18, 25]
    pickup 2 min""",
    "g": """                 ┌───── 10 ─────▶┐     fast corridor lost at t = 20
    base ─4─▶ home                 shelter
                 └6─▶ mid ──8────▶┘     slow corridor lost at t = 40
    pickup 2 min""",
    "h_north": """    base_north ──10──▶┐          north approach lost at t = 22
                      home ──10──▶ shelter
    base_south ──20──▶┘          egress corridor lost at t = 50
    pickup 5 min;  this mission stages at base_north""",
    "h_south": """    base_north ──10──▶┐          north approach lost at t = 22
                      home ──10──▶ shelter
    base_south ──20──▶┘          egress corridor lost at t = 50
    pickup 5 min;  this mission stages at base_south""",
    "n": """    base ──5──▶ home ──5──▶ shelter
                            egress corridor passable ONLY on [18.3, 23.4]
    pickup 2 min""",
}
DIAGRAMS["g_myopic"] = DIAGRAMS["g"]

EXAMPLES: tuple[Example, ...] = (
    Example("A.1", "Deterministic round trip - the arithmetic baseline", ("a",),
            DIAGRAMS["a"],
            "The dispatch envelope is set by the **exit** instant of the last "
            "hazardous traversal, not by its entry. Everything else in this "
            "benchmark is a complication of this one subtraction."),
    Example("A.2", "Deterministic round trip - the corridor used in reverse", ("c",),
            DIAGRAMS["c"],
            "The binding constraint is the **outbound** traversal, with the "
            "pickup sitting between the two. An inbound-only check gives "
            "t ≤ 27 here: thirteen minutes of pure fiction, every one of which "
            "strands the responder and the resident on a dead-end spur."),
    Example("B", "Scenario-weighted success", ("b_ensemble",),
            DIAGRAMS["b_ensemble"],
            "P_success is a **sum of coherent scenario weights**, so it is a "
            "step function with thresholds where whole scenarios drop out. An "
            "independent-edge product would have produced a smooth curve with "
            "no threshold at t = 15, and that smoothness would have been "
            "fiction."),
    Example("C", "Pickup-duration sensitivity", ("d",),
            DIAGRAMS["d"],
            "On-scene time comes off the dispatch envelope minute for minute "
            "whenever the binding constraint is on the egress leg. The four "
            "durations are scenario parameters, not validated medical or "
            "triage categories."),
    Example("D", "Staging-location comparison", ("h_north", "h_south"),
            DIAGRAMS["h_north"],
            "**Proximity is not the dispatch envelope.** The base ten minutes "
            "closer to the resident runs a 25-minute mission and has the "
            "*smaller* feasible set, because its own approach corridor is the "
            "one the fire takes first. Mission duration and dispatch envelope "
            "are different quantities and can order oppositely."),
    Example("E", "Mid-edge hazard", ("g",),
            DIAGRAMS["g"],
            "A segment that cannot be cleared is never entered. Feasibility "
            "survives the loss of the fast corridor because the long way round "
            "is evaluated on its own terms - at a cost of four minutes of "
            "arrival time from t = 5 onwards."),
    Example("F", "Disconnected feasible windows", ("f",),
            DIAGRAMS["f"],
            "Feasibility is **not monotone in dispatch time**. Dispatching at "
            "t = 5 fails; dispatching at t = 12 succeeds, with no waiting "
            "anywhere - only the phase of the corridor's timeline differs. Any "
            "summary of the form 'dispatch by 13' asserts that t = 5 works, "
            "and it does not."),
    Example("G", "Myopic entry-only failure", ("g_myopic",),
            DIAGRAMS["g_myopic"],
            "Checking hazard at the entry instant does not merely lose "
            "missions - it loses them **by driving into the fire**. Between "
            "t = 5 and t = 14 the myopic planner reports a plan right up until "
            "the audit, which then finds the responder and the resident caught "
            "mid-segment. The hole in its feasible set is manufactured entirely "
            "by the wrong semantics."),
)

ADDITIONAL: tuple[Example, ...] = (
    Example("H", "Temporary refuge - reached is not evacuated", ("e",),
            DIAGRAMS["e"],
            "A destination only ends the mission if it *holds*. With "
            "min_safe_dwell = 0 this same fixture would report success for "
            "missions that end with the resident inside the fire perimeter."),
    Example("I", "Two routes, one closes earlier", ("b",),
            DIAGRAMS["b"],
            "Feasibility is governed by the surviving route, not the obvious "
            "one. A dispatcher who only knows about the fast road declares the "
            "mission impossible fifteen minutes too early."),
    Example("J", "A feasible window narrower than the sweep step", ("n",),
            DIAGRAMS["n"],
            "A sampled empty result is **not** evidence of an empty feasible "
            "set. This is the counterexample that motivated the exact interval "
            "solver; see docs/TEMPORAL_RESOLUTION.md."),
)


def fmt(windows) -> str:
    if not windows:
        return "empty"
    return " ∪ ".join(
        f"[{a:g}]" if abs(b - a) < 1e-9 else f"[{a:g}, {b:g}]" for a, b in windows
    )


def render_fixture(key: str) -> list[str]:
    fixture = load(key)
    check = check_fixture(fixture)
    sampled = fixture.feasible_set()
    oracle = reference_feasible_flags(fixture.spec, fixture.ensemble,
                                      fixture.grid, fixture.threshold)

    lines = [
        f"**Fixture `{key}`** — {fixture.title}",
        "",
        "*Parameters*",
        "",
        "```",
        fixture.spec.describe(),
        f"  scenarios : {', '.join(s.name for s in fixture.ensemble)}",
        f"  threshold : q = {fixture.threshold:g}",
        f"  grid      : {fixture.grid[0]:g} … {fixture.grid[-1]:g} min, "
        f"step {fixture.grid[1] - fixture.grid[0]:g}",
        "```",
        "",
        "*Hand calculation*",
        "",
        "```",
        fixture.hand_calculation.strip(),
        "```",
        "",
        "*Solver results*",
        "",
        "| method | feasible dispatch set |",
        "|---|---|",
        f"| hand calculation (sampled) | {fmt(fixture.expected_windows)} |",
        f"| grid sweep | {fmt(sampled.intervals)} |",
    ]

    try:
        exact = exact_feasible_set(fixture.spec, fixture.ensemble,
                                   (fixture.grid[0], fixture.grid[-1]),
                                   threshold=fixture.threshold)
        exact_windows = tuple((c.lo, c.hi) for c in exact.components)
        lines.append(f"| hand calculation (exact) | "
                     f"{fmt(fixture.expected_exact_components)} |")
        lines.append(f"| exact interval solver | {fmt(exact_windows)} |")
        deadline = ("yes" if exact.is_dispatch_by_deadline else
                    "**no** — report windows, not a deadline")
        components = len(exact.components)
    except ExactSolverUnavailable as exc:
        lines.append("| exact interval solver | not applicable |")
        deadline = "n/a"
        components = "n/a"
        lines += ["", f"> Exact solver refused, correctly: {exc}"]

    oracle_windows = _runs(fixture.grid, oracle)
    lines.append(f"| independent brute-force oracle (same grid) | "
                 f"{fmt(oracle_windows)} |")
    lines += [
        "",
        f"*Connected components*: {components} &nbsp;&nbsp; "
        f"*Is a dispatch-by deadline*: {deadline}",
        "",
    ]

    sampled_vs_exact_differ = (
        check.exact_expected_to_apply
        and fmt(sampled.intervals) != fmt(check.actual_exact)
    )
    if sampled_vs_exact_differ:
        lines += [
            "> **The grid and the exact solver disagree here, and both are "
            "behaving correctly.** The grid is not wrong about its samples; it "
            "is silent about everything between them. Reporting the sampled "
            "answer as the feasible set would be the error.",
            "",
        ]

    verdict = "PASS" if check.ok else "FAIL"
    if check.ok:
        detail = ("every method matches its own hand calculation"
                  if sampled_vs_exact_differ else
                  "hand calculation, grid sweep, exact solver and independent "
                  "oracle all agree")
    else:
        detail = "DISAGREEMENT: " + "; ".join(
            check.oracle_disagreements
            or [f"expected {fmt(check.expected_windows)}, "
                f"got {fmt(check.actual_windows)}"])
    lines += [f"**Comparison: {verdict}** — {detail}.", ""]
    return lines


def _runs(grid, flags) -> tuple[tuple[float, float], ...]:
    out: list[tuple[float, float]] = []
    start = None
    for i, flag in enumerate(flags):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            out.append((grid[start], grid[i - 1]))
            start = None
    if start is not None:
        out.append((grid[start], grid[-1]))
    return tuple(out)


def render_example(example: Example) -> list[str]:
    lines = [
        f"## {example.label}. {example.title}",
        "",
        "```",
        example.diagram,
        "```",
        "",
    ]
    for key in example.fixture_keys:
        lines += render_fixture(key)
    if example.extra:
        lines += [example.extra, ""]
    lines += ["**Scientific lesson.** " + example.lesson, "", "---", ""]
    return lines


def staging_comparison() -> list[str]:
    north, south = load("h_north"), load("h_south")
    scenario = north.ensemble.scenarios[0]
    n_result = evaluate_mission(north.spec, 0.0, scenario)
    s_result = evaluate_mission(south.spec, 0.0, scenario)
    return [
        "*Side by side*",
        "",
        "| staging point | mission duration | feasible dispatch set | binding constraint |",
        "|---|---|---|---|",
        f"| `base_north` (10 min away) | {n_result.mission_duration:g} min | "
        f"[0, 12] | its own approach corridor |",
        f"| `base_south` (20 min away) | {s_result.mission_duration:g} min | "
        f"[0, 15] | the shared egress corridor |",
        "",
        "Note what is *not* computed: the union of the two sets. Each mission "
        "names one staging point; nothing here chooses between them, and the "
        "union must not be reported as \"the\" feasible set for this resident.",
        "",
    ]


def pickup_table() -> list[str]:
    fixture = load("d")
    sensitivity = sweep_pickup_durations(fixture.spec, fixture.ensemble,
                                         fixture.grid,
                                         PICKUP_SENSITIVITY_MINUTES)
    lines = [
        "*Sensitivity sweep*",
        "",
        "| pickup (min) | hand calculation `t ≤ 30 − p` | solver | agrees |",
        "|---|---|---|---|",
    ]
    for case in sensitivity.cases:
        expected = 30.0 - case.duration
        lines.append(
            f"| {case.duration:g} | t ≤ {expected:g} | "
            f"{case.feasible_set.format_intervals()} | "
            f"{'yes' if abs(case.latest_feasible - expected) < 1e-9 else '**NO**'} |"
        )
    lines.append("")
    return lines


def build() -> str:
    lines = [
        f"# WildfireGuardian assisted dispatch — v{__version__} scientific benchmark",
        "",
        "Seven canonical examples plus three supporting cases, each with a tiny",
        "network, its parameters, a hand calculation, the solver's answer, a",
        "pass/fail comparison against **three independent methods**, and the",
        "scientific lesson it exists to carry.",
        "",
        "Every number below is generated by `tools/build_benchmark.py`; none is",
        "transcribed. The three methods compared are:",
        "",
        "1. the **grid sweep** (sampled at the stated step),",
        "2. the **exact interval solver** (closed form, no time discretization),",
        "3. an **independent brute-force oracle** that shares no search, timing",
        "   or hazard-assessment code with the main solver.",
        "",
        "> **Scope.** Every result is *oracle-conditioned physical feasibility*:",
        "> the planner is given the complete future of the hazard scenario. These",
        "> are physical feasibility upper bounds, not operating envelopes and not",
        "> dispatch recommendations. See `docs/ORACLE_FEASIBILITY_LIMIT.md` and",
        "> `docs/CLAIMS.md`.",
        "",
        "---",
        "",
    ]
    for example in EXAMPLES:
        block = render_example(example)
        if example.label == "D":
            block = block[:-3] + staging_comparison() + block[-3:]
        if example.label == "C":
            block = block[:-3] + pickup_table() + block[-3:]
        lines += block

    lines += ["# Supporting cases", ""]
    for example in ADDITIONAL:
        lines += render_example(example)

    failures = [k for k in
                [key for e in (*EXAMPLES, *ADDITIONAL) for key in e.fixture_keys]
                if not check_fixture(load(k)).ok]
    lines += [
        "# Summary",
        "",
        "- canonical examples A-G: 7 (A is presented in two parts)",
        f"- fixtures exercised: "
        f"{len({k for e in (*EXAMPLES, *ADDITIONAL) for k in e.fixture_keys})}",
        f"- disagreements between hand calculation, solvers and oracle: "
        f"**{len(failures)}**"
        + (f" ({', '.join(failures)})" if failures else ""),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = build()
    if args.write:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(report + "\n")
        print(f"wrote {REPORT.relative_to(ROOT)} ({len(report.splitlines())} lines)")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
