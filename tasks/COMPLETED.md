# Completed

## Phase 1 — Deterministic kernel and small ensembles

### Exit criteria

| Criterion | Status | Evidence |
|---|---|---|
| Deterministic mission evaluator works | ✅ | `missions/evaluator.py`; `test_missions.py` |
| Time-dependent edge behaviour is explicit | ✅ | `hazards/semantics.py`; `docs/HAZARD_SEMANTICS.md`; fixtures `g` / `g_myopic` |
| Dispatch-time set is computed | ✅ | `feasibility/dispatch.py`; `test_feasibility.py` |
| A non-monotonic example exists | ✅ | fixture `f`: `T = {0} ∪ [11, 13]`; `test_non_monotonic.py` |
| Scenario ensembles work | ✅ | fixture `b_ensemble`; `P_success` = 1.0 / 0.8 / 0.0 |
| Pickup sensitivity works | ✅ | fixture `d`; `t ≤ 30 − p` for p ∈ {2, 5, 10, 15} |
| Hand-calculable fixtures pass | ✅ | 9/9 via `wg-dispatch fixtures --check` |
| Detailed failure reasons are emitted | ✅ | 9 `FailureReason` values, each with a `HazardConflict` |
| Documentation is complete | ✅ | 11 documents in `docs/` |

### What was built

**Semantics (Agent A)**
- Mission timeline with every instant accounted for by a modelled quantity
  (`docs/MISSION_MODEL.md`).
- The full-traversal-interval operator `A_e([t_in, t_out], m)`, with explicit
  mid-edge closure behaviour and two admission policies (D-003).
- Waiting semantics: prohibited in phase 1, with the conditions any future
  implementation must meet (D-004), plus the waiting-by-driving loophole closed
  (D-005).
- Closure semantics: closed windows, reopening, node closure, refuge dwell
  (D-002, D-009).
- Probabilistic interpretation: coherent scenarios and weight sums, with a
  written refusal of independent edge products (D-001).

**Implementation (Agent B)**
- `network/` — directed graphs with corridor identity; constant travel model.
- `hazards/` — normalising timelines, coherent scenarios, weighted ensembles,
  the availability operator.
- `search/` — complete time-expanded enumeration over `(node, time)` states,
  simple-path by default, budget-guarded (D-010, D-013).
- `missions/` — spec, policies, evaluator with branch-over-all-arrival-times,
  full mission records, nine failure reasons.
- `service/` — the pickup model and its four scenario durations.
- `feasibility/` — `P_success`, the set `T(q)`, monotonicity and gaps,
  boundary bisection, pickup sensitivity.
- `scenarios/` — strict YAML/JSON config loading; parquet/CSV/JSON output.
- `validation/` — independent invariants and hand-calculation checking.
- `cli/` — `wg-dispatch` with `evaluate`, `sweep`, `pickup-sweep`,
  `plot-feasibility` and `fixtures`; ASCII strip primary, PNG optional.

**Red team (Agent C)**
- `c` — inbound-only checking is wrong by 13 minutes on a 4-node network.
- `e` — a refuge that is reachable but does not hold; "arrived" ≠ "evacuated".
- `f` — reopening hazard makes feasibility non-monotone; `latest_dispatch()`
  now refuses to summarise such a set.
- `g_myopic` — entry-time-only admission gets the responder *and the resident*
  caught mid-segment, and manufactures a hole in `T` that correct semantics does
  not have.

### Decisions recorded

D-001 … D-017 in `docs/DECISIONS.md`. Each states the alternative that was
rejected and why.

### Assumptions recorded

A-001 … A-015 in `docs/ASSUMPTIONS.md`, with A-008 (full foresight) flagged as
the one that most limits how results may be read.

### Test suite

153 tests, covering: timeline algebra and the boundary convention; the
availability operator and both admission policies; network construction guards;
search completeness, the simple-path rule, and budget behaviour; mission
evaluation and every failure reason; all nine fixtures against their hand
calculations; the non-monotonic result and its boundary refinement; mid-edge
closure semantics under both policies; feasibility sets, thresholds and ensemble
aggregation; pickup sensitivity; the invariants, including negative tests that
tamper with genuine records; the config loader's strictness; and the full CLI.

### Explicitly not done

Real wildfire models, real road networks, and WildfireGuardian routing
integration — all deferred by design (D-016, `docs/SCOPE.md`).
