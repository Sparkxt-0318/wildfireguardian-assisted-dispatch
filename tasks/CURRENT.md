# Current work

**Status:** v0.1.0 — audited and frozen as a benchmark release. The tree is
green and no work is in progress.

```
pytest                        ->  301 passed
wg-dispatch fixtures --check  ->  13/13 fixtures: hand calculation, exact
                                  solver and independent oracle all agree
python tools/mutation_test.py ->  8/8 mutants killed
```

## What this release is

An **oracle / physical-feasibility layer**, not a dispatcher. Given a fully
specified hazard scenario, it decides whether a complete assisted-evacuation
mission was physically possible at each dispatch time, and returns the feasible
dispatch set exactly.

Read `docs/CLAIMS.md` before quoting anything from it.

## What the audit changed

Three defects, found and fixed (`reports/V0_1_SCIENTIFIC_AUDIT.md` §4):

1. **A grid sweep could report an empty feasible set that was not empty.**
   Fixture N has a true window of `[11.3, 11.4]`; the default sweep missed it
   entirely. Fixed with an exact, discretization-free solver, plus mandatory
   resolution reporting on every sampled result.
2. **Grid monotonicity was the wrong predicate for a deadline.** Replaced with
   `is_dispatch_by_deadline` (single component reaching the start of the studied
   range); `last_feasible_instant` is now always available and is named so it
   cannot be mistaken for a deadline.
3. **A silent truncation in arrival branching.** Now raises
   `ArrivalBranchBudgetExceeded`.

Plus: an independent brute-force oracle, property-based tests, adversarial
boundary tests, mutation testing, and five new documents —
`MATHEMATICAL_SPECIFICATION`, `ORACLE_FEASIBILITY_LIMIT`,
`ENUMERATION_COMPLETENESS`, `TEMPORAL_RESOLUTION`, `CLAIMS`.

## What a reader should look at first

1. `reports/BENCHMARK_V0_1.md` — the seven canonical examples end to end.
2. `wg-dispatch sweep n` — the grid and the exact solver disagreeing, both
   behaving correctly.
3. `wg-dispatch sweep f` — the non-monotonic feasible set, and why no single
   deadline describes it.
4. `wg-dispatch evaluate g_myopic --dispatch-time 6` — a responder caught
   mid-segment by entry-time-only hazard checking.

## Next up

`tasks/ROADMAP.md` R-3 (online / rolling-horizon planning) remains the
highest-value next item, and after the audit it is also the best-specified: the
oracle→forecast gap now has its own document, its own vocabulary, and a worked
example in fixture F. R-1 (explicit waiting) is still the smallest well-defined
increment, and `ENUMERATION_COMPLETENESS.md` §7 now sketches the finiteness
repair it will need.

## Open questions carried forward

- **Margin-aware selection (R-4).** Unchanged by the audit: fixture E still
  picks the near refuge over the durable shelter whenever the refuge qualifies.
- **Ensemble semantics.** What would make a larger ensemble *meaningful*, and
  what `q` means as a risk appetite applied to an oracle quantity.
- **Adaptive grid refinement.** The exact solver handles the feasible *set*,
  but the `P_success` curve used for plots is still sampled and can alias.
- **The exact solver's conditions are not universal.** Any future feature that
  breaks one of them returns the feasible set to being resolution-limited, and
  must say so.

## Do not do

- Do not integrate real WildfireGuardian routing (D-016).
- Do not add forecasting, OSSE observations, traffic simulation, wildfire spread
  models, personal-data systems, optimisation across villages, or production
  integrations. This repository owns one question.
- Do not describe any result as an operating envelope, a dispatch
  recommendation, or a safety claim (`docs/CLAIMS.md`).
- Do not change a fixture's expected windows to match new output. If an answer
  changes, the arithmetic changes first, in the fixture's `hand_calculation`.
