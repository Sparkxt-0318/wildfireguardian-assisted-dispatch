"""``wg-dispatch`` - the command line front end.

    wg-dispatch evaluate config.yaml
    wg-dispatch sweep config.yaml --out results.parquet
    wg-dispatch plot-feasibility results.parquet

plus two commands that exist because the fixtures are the validation
instrument and deserve to be runnable without writing a config file::

    wg-dispatch fixtures --list
    wg-dispatch fixtures --check
    wg-dispatch pickup-sweep config.yaml

Every command prints the model's own caveats along with its numbers.  A
feasibility result without its monotonicity warning is not a result.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from ..feasibility.dispatch import FeasibleDispatchSet, sweep_dispatch_times
from ..feasibility.exact import ExactSolverUnavailable, exact_feasible_set
from ..feasibility.refine import refine_transitions
from ..feasibility.sensitivity import sweep_pickup_durations
from ..fixtures import FIXTURES, load as load_fixture
from ..missions.evaluator import evaluate_mission
from ..scenarios.config import ConfigError, StudyConfig, load_config
from ..scenarios.io import read_rows, write_json, write_rows
from ..service.pickup import PICKUP_SENSITIVITY_MINUTES
from ..validation.handcalc import check_fixture
from ..validation.invariants import validate_mission_result
from ..version import __version__
from .plotting import ascii_strip, has_matplotlib, plot_feasibility

PROLOGUE = (
    "wildfireguardian-assisted-dispatch: synthetic phase. Networks and hazards "
    "are synthetic; no real wildfire model or real road network is involved."
)


def _load(path: str) -> StudyConfig:
    if path in FIXTURES:
        fixture = load_fixture(path)
        return StudyConfig(
            name=f"fixture-{fixture.key}", spec=fixture.spec,
            ensemble=fixture.ensemble, grid=fixture.grid,
            threshold=fixture.threshold, source=f"<fixture {fixture.key}>",
            fixture_key=fixture.key,
        )
    return load_config(path)


# -- commands ---------------------------------------------------------------

def cmd_evaluate(args: argparse.Namespace) -> int:
    study = _load(args.config)
    dispatch_time = (args.dispatch_time if args.dispatch_time is not None
                     else study.dispatch_time)
    if dispatch_time is None:
        dispatch_time = study.grid[0]

    print(study.describe())
    print()
    payload = []
    for scenario in study.ensemble:
        result = evaluate_mission(study.spec, dispatch_time, scenario)
        print(result.render())
        report = validate_mission_result(result, study.spec, scenario)
        if not report.ok:
            print("  " + report.describe().replace("\n", "\n  "))
        print()
        payload.append(result.to_dict())

    if len(study.ensemble) > 1:
        successes = sum(s.weight for s, p in zip(study.ensemble, payload)
                        if p["mission_success"])
        print(f"P_success({dispatch_time:g}) = {successes:g} "
              f"over {len(study.ensemble)} coherent scenario(s)")
        print("  (a sum of scenario weights, not a product of edge probabilities)")

    if args.json:
        path = write_json({"dispatch_time": dispatch_time,
                           "study": study.name,
                           "results": payload}, args.json)
        print(f"\nwrote {path}")
    return 0


def cmd_sweep(args: argparse.Namespace) -> int:
    study = _load(args.config)
    threshold = args.threshold if args.threshold is not None else study.threshold
    print(study.describe())
    print()

    sweep = sweep_dispatch_times(study.spec, study.ensemble, study.grid)
    feasible = sweep.feasible_set(threshold)

    print(ascii_strip(feasible, title=f"sampled feasible dispatch set - "
                                     f"{study.name}").render())
    print()

    if not args.no_exact:
        try:
            exact = exact_feasible_set(
                study.spec, study.ensemble,
                (study.grid[0], study.grid[-1]), threshold=threshold)
        except ExactSolverUnavailable as exc:
            print("EXACT SOLVER NOT APPLICABLE")
            print(f"  {exc}")
            print("  The sampled windows above are therefore the only available "
                  "answer, and they are accurate only to the grid resolution.")
        else:
            print(exact.describe())
            _cross_check(feasible, exact)
        print()

    if args.refine:
        transitions = refine_transitions(study.spec, study.ensemble, sweep,
                                         threshold=threshold,
                                         tolerance=args.tolerance)
        if transitions:
            print("refined boundaries:")
            for transition in transitions:
                print(f"  {transition.describe()}")
        else:
            print("no feasibility transitions on this grid")
        print()

    if args.out:
        rows = sweep.rows() if args.detail else sweep.summary_rows()
        written = write_rows(rows, args.out)
        print(written.describe())
    return 0


def _cross_check(sampled: FeasibleDispatchSet, exact) -> None:
    """Report any disagreement between the sampled and exact feasible sets.

    Disagreement is expected whenever a feature is narrower than the grid step;
    it is reported, never smoothed over.
    """
    mismatches = [t for t, flag in zip(sampled.grid, sampled.flags)
                  if flag != exact.contains(t)]
    if mismatches:
        print(f"  DISAGREEMENT at {len(mismatches)} sampled point(s), e.g. "
              f"t={mismatches[0]:g}: this is a solver defect, not a resolution "
              "artefact, because both methods were asked about the same instant")
        return
    sampled_measure = sum(hi - lo for lo, hi in sampled.intervals)
    exact_measure = exact.interval_set.measure
    if exact_measure > sampled_measure + sampled.resolution + 1e-9:
        print("  note: the exact set is larger than the sampled one; the grid "
              "is missing feasible time that lies between its samples")
    elif not sampled.intervals and not exact.is_empty:
        print("  note: the grid found NO feasible dispatch time, but the exact "
              "set is non-empty - the window is narrower than the grid step")


def cmd_pickup_sweep(args: argparse.Namespace) -> int:
    study = _load(args.config)
    threshold = args.threshold if args.threshold is not None else study.threshold
    durations = args.durations or list(PICKUP_SENSITIVITY_MINUTES)
    sensitivity = sweep_pickup_durations(study.spec, study.ensemble, study.grid,
                                         durations, threshold=threshold)
    print(sensitivity.describe())
    print()
    print("reminder: pickup durations are scenario parameters, not validated "
          "medical or triage categories.")
    if args.out:
        print(write_rows(sensitivity.rows(), args.out).describe())
    return 0


def cmd_plot(args: argparse.Namespace) -> int:
    rows = read_rows(args.results)
    if not rows:
        print(f"{args.results} contains no rows", file=sys.stderr)
        return 2

    by_time: dict[float, float] = {}
    for row in rows:
        try:
            t = float(row["dispatch_time"])
            p = float(row.get("p_success", row.get("p_success_at_dispatch")))
        except (KeyError, TypeError, ValueError) as exc:
            print(f"{args.results}: rows need 'dispatch_time' and 'p_success' "
                  f"(or 'p_success_at_dispatch'): {exc}", file=sys.stderr)
            return 2
        by_time[t] = p

    grid = tuple(sorted(by_time))
    values = tuple(by_time[t] for t in grid)
    resolution = (grid[1] - grid[0]) if len(grid) > 1 else 0.0
    feasible = FeasibleDispatchSet(
        threshold=args.threshold, grid=grid,
        flags=tuple(v >= args.threshold - 1e-9 for v in values),
        resolution=resolution,
    )

    print(ascii_strip(feasible, title=f"sampled feasible dispatch set - "
                                      f"{Path(args.results).name}").render())

    if args.out:
        if not has_matplotlib():
            print("\nmatplotlib is not installed, so no PNG was written; "
                  "install the 'plots' extra. The strip above is the same "
                  "information.", file=sys.stderr)
            return 0
        path = plot_feasibility(
            grid, values, feasible, args.out,
            title=args.title or "Oracle dispatch feasibility (sampled)")
        print(f"\nwrote {path}")
    return 0


def cmd_fixtures(args: argparse.Namespace) -> int:
    if args.check:
        failures = 0
        for key in FIXTURES:
            check = check_fixture(load_fixture(key))
            print(check.describe())
            failures += 0 if check.ok else 1
        print()
        print(f"{len(FIXTURES) - failures}/{len(FIXTURES)} fixtures agree with "
              "their hand calculations, the exact solver and the independent "
              "reference oracle")
        return 1 if failures else 0

    if args.show:
        print(load_fixture(args.show).describe())
        return 0

    for key, builder in FIXTURES.items():
        fixture = builder()
        print(f"  {key:<12} {fixture.title:<44} {fixture.summary}")
    return 0


# -- argument parsing -------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wg-dispatch",
        description=PROLOGUE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version",
                        version=f"wg-dispatch {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    config_help = ("path to a YAML/JSON study config, or the key of a built-in "
                   f"fixture ({', '.join(FIXTURES)})")

    evaluate = sub.add_parser("evaluate",
                              help="evaluate one dispatch time in full detail")
    evaluate.add_argument("config", help=config_help)
    evaluate.add_argument("--dispatch-time", type=float, default=None,
                          help="dispatch time in minutes (default: the config's, "
                               "else the start of the sweep grid)")
    evaluate.add_argument("--json", default=None,
                          help="also write the full mission records here")
    evaluate.set_defaults(func=cmd_evaluate)

    sweep = sub.add_parser("sweep",
                           help="compute the feasible dispatch set over a grid")
    sweep.add_argument("config", help=config_help)
    sweep.add_argument("--out", default=None,
                       help="write results to .parquet / .csv / .json")
    sweep.add_argument("--detail", action="store_true",
                       help="write one row per (dispatch time, scenario) "
                            "instead of one row per dispatch time")
    sweep.add_argument("--threshold", type=float, default=None,
                       help="feasibility threshold q (default: the config's)")
    sweep.add_argument("--refine", action="store_true",
                       help="bisect each feasibility boundary below grid "
                            "resolution")
    sweep.add_argument("--tolerance", type=float, default=0.01,
                       help="bisection tolerance in minutes (default 0.01)")
    sweep.add_argument("--no-exact", action="store_true",
                       help="skip the discretization-free exact solver and "
                            "report only the sampled grid result")
    sweep.set_defaults(func=cmd_sweep)

    pickup = sub.add_parser("pickup-sweep",
                            help="feasibility across pickup durations")
    pickup.add_argument("config", help=config_help)
    pickup.add_argument("--durations", type=float, nargs="+", default=None,
                        help="pickup durations in minutes "
                             "(default 2 5 10 15)")
    pickup.add_argument("--threshold", type=float, default=None)
    pickup.add_argument("--out", default=None)
    pickup.set_defaults(func=cmd_pickup_sweep)

    plot = sub.add_parser("plot-feasibility",
                          help="render a feasibility strip, and a PNG if asked")
    plot.add_argument("results", help="a table written by 'wg-dispatch sweep'")
    plot.add_argument("--out", default=None, help="write a PNG here")
    plot.add_argument("--threshold", type=float, default=1.0)
    plot.add_argument("--title", default=None)
    plot.set_defaults(func=cmd_plot)

    fixtures = sub.add_parser("fixtures",
                              help="list, show or check the built-in fixtures")
    fixtures.add_argument("--list", action="store_true",
                          help="list fixtures (the default)")
    fixtures.add_argument("--show", default=None,
                          help="print one fixture's definition and hand "
                               "calculation")
    fixtures.add_argument("--check", action="store_true",
                          help="re-run every fixture against its hand "
                               "calculation")
    fixtures.set_defaults(func=cmd_fixtures)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, FileNotFoundError, KeyError, ValueError) as exc:
        print(f"wg-dispatch: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
