# Current work

**Status:** phase 1 is complete and the tree is green. No work is in progress.

```
pytest                        ->  153 passed
wg-dispatch fixtures --check  ->  9/9 fixtures match their hand calculations
```

## Where things stand

The deterministic kernel, the hazard semantics, the dispatch-time feasibility
set, the scenario ensembles, the pickup sensitivity, the fixtures, the CLI and
the documentation are all done and validated. Phase-1 exit criteria are all met
— see `COMPLETED.md`.

## What a reader should look at first

1. `wg-dispatch sweep f` — the non-monotonic feasible set, `{0} ∪ [11, 13]`, and
   the reason no single deadline describes it.
2. `wg-dispatch evaluate g_myopic --dispatch-time 6` — a responder caught
   mid-segment by entry-time-only hazard checking, with the full log.
3. `wg-dispatch fixtures --show c` — the inbound/outbound conflict, and the
   thirteen minutes an inbound-only check invents.

## Next up

`tasks/ROADMAP.md` R-3 (online / rolling-horizon planning) is the highest-value
next item, because it is what converts every current result from an upper bound
into an achievable envelope. R-1 (explicit waiting) is the smallest well-defined
increment and is a good warm-up: the semantics are already written down in
`docs/DECISIONS.md` D-004, so the work is implementation plus one fixture.

## Open questions carried forward

- **Margin-aware selection (R-4).** Fixture E currently picks the near refuge
  over the durable shelter whenever the refuge qualifies. Correct under the
  stated objective, arguably wrong operationally. Needs a decision on the
  objective before code.
- **Ensemble size.** Three coherent scenarios is enough to demonstrate the
  aggregation rule. It is not enough for any claim about distributions, and the
  weights are hand-authored anyway (A-006). What would make a larger ensemble
  meaningful rather than merely larger?
- **Grid resolution policy.** `refine_transitions` finds boundaries inside a
  cell, but a feasible window entirely between two grid points is still
  invisible (`FAILURE_MODES.md` F-8). Should the sweep adaptively refine where
  `P_success` changes?

## Do not do

- Do not integrate real WildfireGuardian routing (D-016).
- Do not add a real fire model or a real road network in this phase
  (`docs/SCOPE.md`).
- Do not change a fixture's expected windows to match new output. If an answer
  changes, the arithmetic changes first, in the fixture's `hand_calculation`.
