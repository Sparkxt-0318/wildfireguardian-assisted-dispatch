#!/usr/bin/env python3
"""Mutation testing: break the kernel on purpose and check the tests notice.

A passing test suite proves nothing on its own — it might be asserting
tautologies.  This script introduces each of the defects the project claims to
defend against, one at a time, runs the whole suite against the mutant, and
records which tests caught it.  A mutant that survives is a hole in the suite
and is reported as such.

Each mutation is a single textual patch applied in place and reverted
afterwards (in a ``finally``, so an interrupted run still restores the tree).
Nothing is monkeypatched at import time: the mutant is the real source, so the
result is what a reviewer would get if the defect were committed.

    python tools/mutation_test.py                 # run and print a report
    python tools/mutation_test.py --write         # also write reports/MUTATION_TESTING.md
    python tools/mutation_test.py --only entry_only_admission
"""

from __future__ import annotations

import argparse
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "wildfireguardian_assisted_dispatch"
REPORT = ROOT / "reports" / "MUTATION_TESTING.md"


@dataclass(frozen=True)
class Mutation:
    """One deliberate defect."""

    key: str
    title: str
    defends: str          # which project claim this mutation attacks
    path: Path
    old: str
    new: str
    note: str = ""


@dataclass
class MutationResult:
    mutation: Mutation
    killed: bool
    failed: int
    passed: int
    failing_tests: list[str] = field(default_factory=list)
    duration: float = 0.0
    mode: str = "full suite"


MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        key="entry_only_admission",
        title="Edge safety checked only at the entry instant",
        defends="Full traversal intervals (D-003)",
        path=SRC / "hazards" / "semantics.py",
        old="""    if admission is TraversalAdmission.FULL_INTERVAL:
        return assessment.safe_throughout""",
        new="""    if admission is TraversalAdmission.FULL_INTERVAL:
        return assessment.safe_at_entry  # MUTANT""",
        note="The single most dangerous defect available: it approves segments "
             "that close under the vehicle.",
    ),
    Mutation(
        key="probability_product",
        title="Scenario success combined as a product instead of a weight sum",
        defends="Coherent scenarios, never independent products (D-001)",
        path=SRC / "feasibility" / "dispatch.py",
        old="""    @property
    def p_success(self) -> float:
        return sum(w for w, r in zip(self.weights, self.results) if r.mission_success)""",
        new="""    @property
    def p_success(self) -> float:
        # MUTANT: the independence blunder - 1 - prod(1 - w_i S_i)
        product = 1.0
        for w, r in zip(self.weights, self.results):
            product *= (1.0 - w) if r.mission_success else 1.0
        return 1.0 - product""",
        note="Note what this mutation had to invent. The codebase holds no "
             "per-edge probability object to corrupt, because D-001 never "
             "created one; the nearest available product is over scenarios.",
    ),
    Mutation(
        key="ignore_pickup",
        title="Pickup duration ignored (service takes no time)",
        defends="The mission includes an on-scene service interval",
        path=SRC / "service" / "pickup.py",
        old="        return (arrival_time, arrival_time + self.duration)",
        new="        return (arrival_time, arrival_time)  # MUTANT",
    ),
    Mutation(
        key="implicit_waiting",
        title="Legs may revisit nodes (waiting by driving in circles)",
        defends="No implicit waiting (D-004, D-005)",
        path=SRC / "missions" / "policy.py",
        old="    allow_node_revisits: bool = False",
        new="    allow_node_revisits: bool = True  # MUTANT",
    ),
    Mutation(
        key="deadline_from_non_monotone_set",
        title="sup(T) reported as a dispatch-by deadline regardless of shape",
        defends="The answer is a set; a deadline is a claim (D-006)",
        path=SRC / "feasibility" / "dispatch.py",
        old="""        if not self.is_prefix:
            raise DispatchByDeadlineUndefined(""",
        new="""        if False:  # MUTANT: never refuse
            raise DispatchByDeadlineUndefined(""",
    ),
    Mutation(
        key="silent_budget_truncation",
        title="Search budget exhaustion returns 'infeasible' instead of raising",
        defends="No silent fallbacks (D-013)",
        path=SRC / "search" / "time_expanded.py",
        old="""        if result.states_expanded > max_states:
            raise SearchBudgetExceeded(""",
        new="""        if result.states_expanded > max_states:
            return result  # MUTANT: silently report what we have
        if False:
            raise SearchBudgetExceeded(""",
    ),
    Mutation(
        key="travel_after_mid_edge_failure",
        title="A mid-edge closure does not stop the mission",
        defends="A caught vehicle is a lost mission (D-003)",
        path=SRC / "missions" / "evaluator.py",
        old="""        for traversal in plan.egress.traversals:
            log.append(_travel_entry(traversal))
            if not traversal.safe_throughout:
                caught = (traversal, "egress")
                break""",
        new="""        for traversal in plan.egress.traversals:
            log.append(_travel_entry(traversal))
            if False:  # MUTANT: drive on through the closure
                caught = (traversal, "egress")
                break""",
    ),
    Mutation(
        key="unsafe_refuge_accepted",
        title="A refuge that does not hold still counts as a completed mission",
        defends="Reached is not evacuated (D-009)",
        path=SRC / "missions" / "evaluator.py",
        old="""    dwell = assess_node_occupancy(destination.node, dest_arrival.time, dwell_end, scenario)
    if not dwell.safe_throughout:""",
        new="""    dwell = assess_node_occupancy(destination.node, dest_arrival.time, dwell_end, scenario)
    if False:  # MUTANT: ignore the dwell requirement""",
    ),
)


#: Some mutants make the suite pathologically slow rather than merely wrong -
#: ``implicit_waiting`` turns every leg into an unbounded walk, so the search
#: grinds towards its state budget on every call. That is itself evidence, but
#: it must not hang the run, so a timed-out full pass falls back to a
#: stop-at-first-failure pass and the report says which mode produced it.
FULL_RUN_TIMEOUT = 240
FIRST_FAILURE_TIMEOUT = 300


def _pytest(extra: list[str], timeout: int) -> tuple[str, int] | None:
    try:
        proc = subprocess.run(
            # NB: pyproject already puts -q in addopts. Passing -q again makes
            # it -qq, which suppresses the summary line this script parses.
            [sys.executable, "-m", "pytest", "--tb=no", "-rf",
             "-p", "no:cacheprovider", *extra],
            cwd=ROOT, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None
    return proc.stdout + proc.stderr, proc.returncode


def _parse(out: str, returncode: int) -> tuple[int, int, list[str]]:
    failing = re.findall(r"^FAILED (\S+)", out, flags=re.MULTILINE)
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", out)) else 0
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", out)) else 0
    errors = int(m.group(1)) if (m := re.search(r"(\d+) error", out)) else 0
    failed += errors
    if failed == 0 and returncode != 0 and not failing:
        # A collection or import error counts as "caught", but name it honestly.
        failing = ["<collection or import error>"]
        failed = 1
    return failed, passed, failing


def run_suite() -> tuple[int, int, list[str], str]:
    """Run pytest; return (failed, passed, failing ids, mode)."""
    result = _pytest([], FULL_RUN_TIMEOUT)
    if result is not None:
        return (*_parse(*result), "full suite")

    # The mutant is too slow for a full pass. Stop at the first failure - which
    # still answers "does the suite catch it", just not "how many tests do".
    result = _pytest(["-x"], FIRST_FAILURE_TIMEOUT)
    if result is None:
        return (0, 0, ["<suite did not terminate>"], "timed out entirely")
    failed, passed, failing = _parse(*result)
    return failed, passed, failing, "stopped at first failure (full pass timed out)"


def apply_mutation(mutation: Mutation) -> str:
    original = mutation.path.read_text()
    if mutation.old not in original:
        raise SystemExit(
            f"mutation {mutation.key!r} does not apply: its anchor text is not "
            f"in {mutation.path.relative_to(ROOT)}. The source has moved; fix "
            "the mutation rather than skipping it."
        )
    if original.count(mutation.old) != 1:
        raise SystemExit(
            f"mutation {mutation.key!r} anchor is ambiguous "
            f"({original.count(mutation.old)} matches)"
        )
    mutation.path.write_text(original.replace(mutation.old, mutation.new, 1))
    return original


def run_mutation(mutation: Mutation) -> MutationResult:
    started = time.time()
    original = apply_mutation(mutation)

    def restore(*_args) -> None:
        mutation.path.write_text(original)

    # A killed runner must not leave a mutant in the tree. `finally` handles the
    # ordinary paths; these handle SIGINT/SIGTERM, which is how the first
    # version of this script managed to commit a mutation by accident.
    previous = {sig: signal.signal(sig, lambda s, f: (restore(), sys.exit(130)))
                for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        failed, passed, failing, mode = run_suite()
    finally:
        restore()
        for sig, handler in previous.items():
            signal.signal(sig, handler)

    return MutationResult(
        mutation=mutation, killed=failed > 0, failed=failed, passed=passed,
        failing_tests=failing, duration=time.time() - started, mode=mode,
    )


def render(results: list[MutationResult], baseline: tuple[int, int]) -> str:
    killed = sum(1 for r in results if r.killed)
    lines = [
        "# Mutation testing report",
        "",
        "Generated by `tools/mutation_test.py`. Each row is a defect this",
        "project claims to defend against, introduced into the real source and",
        "then reverted. A **killed** mutant is one the test suite rejected; a",
        "**survivor** is a hole in the suite.",
        "",
        f"- baseline: {baseline[1]} passed, {baseline[0]} failed",
        f"- mutants killed: **{killed} / {len(results)}**",
        "",
        "| # | mutation | defends | killed | tests failing |",
        "|---|---|---|---|---|",
    ]
    for i, r in enumerate(results, 1):
        lines.append(
            f"| {i} | {r.mutation.title} | {r.mutation.defends} | "
            f"{'yes' if r.killed else '**NO**'} | {r.failed} |"
        )
    lines += ["", "## Detail", ""]
    for i, r in enumerate(results, 1):
        lines += [
            f"### {i}. {r.mutation.title}",
            "",
            f"- **key**: `{r.mutation.key}`",
            f"- **attacks**: {r.mutation.defends}",
            f"- **patched**: `{r.mutation.path.relative_to(ROOT)}`",
            f"- **result**: {'KILLED' if r.killed else 'SURVIVED'} "
            f"({r.failed} failed, {r.passed} passed, {r.duration:.1f}s, "
            f"{r.mode})",
        ]
        if r.mutation.note:
            lines.append(f"- **note**: {r.mutation.note}")
        if r.failing_tests:
            shown = r.failing_tests[:12]
            lines += ["- **first tests to catch it**:", ""]
            lines += [f"  - `{t}`" for t in shown]
            if len(r.failing_tests) > len(shown):
                lines.append(f"  - ...and {len(r.failing_tests) - len(shown)} more")
        else:
            lines.append("- **no test failed**: this defect could be committed "
                         "without the suite noticing")
        lines.append("")
    return "\n".join(lines)


def _assert_tree_is_clean() -> None:
    """Refuse to start if a previous run left a mutation behind."""
    leaked = [p for p in SRC.rglob("*.py") if "# MUTANT" in p.read_text()]
    if leaked:
        raise SystemExit(
            "refusing to run: these files still contain a mutation from an "
            "earlier run - restore them first:\n  "
            + "\n  ".join(str(p.relative_to(ROOT)) for p in leaked)
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help=f"write {REPORT.relative_to(ROOT)}")
    parser.add_argument("--only", default=None, help="run a single mutation by key")
    args = parser.parse_args()

    selected = [m for m in MUTATIONS if args.only in (None, m.key)]
    if not selected:
        raise SystemExit(f"no mutation named {args.only!r}; "
                         f"known: {', '.join(m.key for m in MUTATIONS)}")

    _assert_tree_is_clean()

    print("baseline (unmutated) suite ...", flush=True)
    baseline = run_suite()[:2]
    print(f"  {baseline[1]} passed, {baseline[0]} failed", flush=True)
    if baseline[0]:
        raise SystemExit("the suite is already failing; fix that before "
                         "mutation testing means anything")

    results: list[MutationResult] = []
    for mutation in selected:
        print(f"mutating: {mutation.key} ...", end=" ", flush=True)
        result = run_mutation(mutation)
        results.append(result)
        print(f"{'KILLED' if result.killed else 'SURVIVED'} "
              f"({result.failed} tests failed, {result.mode})", flush=True)

    report = render(results, baseline)
    if args.write:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(report + "\n")
        print(f"\nwrote {REPORT.relative_to(ROOT)}")
    survivors = [r for r in results if not r.killed]
    if survivors:
        print(f"\n{len(survivors)} mutant(s) SURVIVED: "
              f"{', '.join(r.mutation.key for r in survivors)}")
        return 1
    print(f"\nall {len(results)} mutants killed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
