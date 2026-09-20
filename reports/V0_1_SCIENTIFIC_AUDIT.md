# v0.1 scientific audit

An adversarial audit of the phase-1 assisted-dispatch kernel, conducted before
freezing it as a benchmark release. The brief was to try to make the kernel
lie, fix what it found, and change any claim that turned out to be wrong.

**Summary.** The mission model survived. Two genuine defects were found, both
in how results are *reported* rather than in how missions are evaluated: a
dispatch-grid sweep can miss feasible windows entirely, and the predicate
licensing a "dispatch by X" summary was the wrong one. A third, latent
silent-truncation path was found in the evaluator's arrival branching and
closed. All three are fixed, and each has a fixture or test that would fail if
the fix were reverted. An independent second implementation was built and
reproduces every fixture; eight deliberate defects were introduced and all
eight were rejected by the suite.

- suite: **301 tests**
- fixtures: **13**, each cross-checked three ways
- mutants killed: **8 / 8**
- disagreements between hand calculation, solvers and oracle: **0**

---

## 1. What is mathematically exact?

| quantity | status | why |
|---|---|---|
| `A_x([t_in, t_out], m)` | **exact** | an interval containment test against closed windows; tolerance `EPS = 1e-9` min guards float dust in sums of fixture constants, nothing else |
| mission evaluation `S(t, m)` at a given `t` | **exact** | arrival times are exact sums of travel times and the pickup duration; no time is discretized anywhere in the evaluation |
| `P_success(t)` at a given `t` | **exact** | a weighted sum of exact booleans |
| the feasible dispatch set `𝒯_q` via `feasibility/exact.py` | **exact** | closed-form interval arithmetic over the finitely many simple-path plans; `𝒯_q = ⋃_k [a_k, b_k]` (see `docs/MATHEMATICAL_SPECIFICATION.md` §3) |
| closedness of `𝒯_q`, hence `sup 𝒯_q ∈ 𝒯_q` | **exact, and proved** | finite unions and intersections of closed sets are closed; asserted over every fixture and over random generated worlds |
| state-space enumeration for a given `t` | **exact and complete under stated conditions** | conditions listed in `docs/ENUMERATION_COMPLETENESS.md` §3; violating one raises rather than degrades |
| pickup-duration sensitivity `t ≤ 30 − p` | **exact** | an algebraic consequence of the above; matched to the minute for p ∈ {2, 5, 10, 15} |

## 2. What is numerically approximated?

| quantity | approximation | discipline applied |
|---|---|---|
| `𝒯_q` via a **grid sweep** | sampled at the grid step; features narrower than the step can be missed entirely | labelled `SAMPLED`; an unconditional warning naming the resolution; an empty sampled result states it is not evidence of emptiness; the exact solver runs alongside and the two are cross-checked |
| boundary **refinement** (`refine_transitions`) | bisection to a stated tolerance, and **only** for transitions the grid already bracketed | the tolerance is reported with the answer; it cannot discover a window the grid never touched |
| `P_success(t)` as a **curve** (for plots and tables) | sampled | plots are labelled with the grid step |
| float comparisons | `EPS = 1e-9` minutes | one definition, in `units.py`, used everywhere |

Nothing else is approximated. In particular the mission model itself is not
discretized: the only sampling in the whole pipeline is the scan over dispatch
times, which is exactly where the defect in §4 lived.

## 3. What assumptions are required for each result?

All results require **A-001** (everything synthetic) and **A-008** (the planner
has full foresight within a scenario). Beyond that:

| result | additionally requires |
|---|---|
| any mission evaluation | A-002 single responder, A-003 single resident, A-005 exogenous deterministic hazard, A-009 instantaneous dispatch, A-010 resident present, A-013 point nodes |
| travel-time arithmetic | A-007 constant FIFO travel times |
| pickup sensitivity | A-004 durations are scenario parameters, **not** medical categories |
| `P_success` and thresholds | A-006 weights are hand-authored, not calibrated |
| the **exact** feasible set | A-016 hazard timelines are finite unions of closed intervals, plus the solver's five checked conditions (constant travel, no waiting, simple paths, full-interval admission, bounded plan/scenario counts) |
| destination results | A-012 unlimited capacity, A-015 destinations differ only by arrival time, dwell, availability and priority |
| "a feasible plan exists" | A-017 existence is not findability — under entry-only admission the planner demonstrably does not find it |

Every assumption is numbered in `docs/ASSUMPTIONS.md` with its consequence if
violated. **A-008 is the one that most limits how any result may be read**, and
now has its own document: `docs/ORACLE_FEASIBILITY_LIMIT.md`.

## 4. What counterexamples were found?

### Finding 1 — A grid sweep can report an empty feasible set that is not empty ⚠ *(defect, fixed)*

Constructed fixture **N**: `base --5-- home --5-- shelter`, pickup 2 min, egress
corridor passable only on `[18.3, 23.4]`. The egress leg occupies `[t+7, t+12]`,
so the true feasible set is `[11.3, 11.4]` — 0.1 minutes wide.

The default one-minute sweep samples `t = 11` and `t = 12`, finds neither
feasible, and reports **empty**. `refine_transitions` cannot help: with no
observed transition there is nothing to bisect. This is not a precision
question; the window is invisible.

The same defect was already latent in the shipped fixture F, whose feasible set
is `{0} ∪ [11, 13]`. Its first component is a single instant, found only because
the default grid happened to start at exactly `t = 0`. A sweep over `[0.5, 20]`
would have reported one component instead of two, silently weakening the
headline non-monotonicity result by an arbitrary choice of grid offset.

**Fix.** `feasibility/exact.py` computes `𝒯_q` in closed form with no time
discretization, under conditions it checks rather than assumes. `wg-dispatch
sweep` runs it by default alongside the grid and cross-checks. Every sampled
result now carries its resolution unconditionally and is labelled `SAMPLED`.
See `docs/TEMPORAL_RESOLUTION.md`.

### Finding 2 — Grid monotonicity was the wrong predicate for a deadline ⚠ *(defect, fixed)*

The pre-audit API emitted a single "latest dispatch" whenever the sampled
feasibility indicator was non-increasing. That is the wrong test in **both**
directions:

- a set whose single component starts *after* the beginning of the studied
  range has a non-monotone sampled indicator and no hole in it (fixture
  `n_resolved`) — the API refused a summary that was in fact fine;
- more seriously, the test says nothing about whether the set reaches the
  beginning of the studied range, which is precisely what "dispatch by X"
  asserts.

**Fix.** `dispatch_by_deadline()` is defined only when the set is a *single
component reaching the start of the studied range*, and raises
`DispatchByDeadlineUndefined` otherwise. `last_feasible_instant` is always
available and is named so it cannot be mistaken for a deadline. Terminology is
fixed in `docs/CLAIMS.md` and `docs/GLOSSARY.md` (D-019).

### Finding 3 — A silent truncation in the evaluator's arrival branching ⚠ *(latent defect, fixed)*

The evaluator branched over `resident_arrivals[:max_resident_arrivals]`. Because
an earlier arrival does not dominate a later one under reopening hazards,
dropping the tail could turn a feasible mission into an infeasible one — the
same class of silent failure that D-013 forbids for the state search, sitting
undetected one layer up. It never bit on the shipped fixtures (simple paths on
five-node networks never produce 64 distinct arrival times), which is exactly
why it survived the first release.

**Fix.** Exceeding the budget now raises `ArrivalBranchBudgetExceeded`.

### Finding 4 — "Complete enumeration" was asserted without conditions *(claim defect, fixed)*

The search was described as "complete". It is — under conditions nobody had
written down, which is indistinguishable from being wrong.
`docs/ENUMERATION_COMPLETENESS.md` now answers: time is continuous while the
reachable state set is finite; candidate times are created only by travel and
service; infinitely many states arise if both the simple-path rule and the
horizon are removed; reopening hazards are why earliest-arrival dominance is
refused; time-dependent travel would break the exact solver's premise; and
waiting would make `(node, time)` a continuum unless wait-until instants are
restricted to hazard breakpoints (D-024).

### Finding 5 — Claim language was under-specified *(claim defect, fixed)*

The oracle limitation existed only as assumption bullet A-008. Nothing stopped a
reader calling a feasible set an "operating envelope", and no document listed
the phrasings that are forbidden outright. Added
`docs/ORACLE_FEASIBILITY_LIMIT.md` (with fixture F worked through) and
`docs/CLAIMS.md` (eight permitted claims, six prohibited ones, and restricted
vocabulary for "dispatch-by deadline", "operating envelope", "complete search"
and pickup profiles).

### Finding 6 — An error in a hand calculation, caught by the suite *(no code defect)*

While writing the counterexample that keeps the pickup-monotonicity property
honest, the audit asserted that a 6-minute pickup would rescue a dispatch that a
2-minute pickup loses in fixture F. It does not: the egress must start at or
after `t = 18`, which needs `p ≥ 7`. The test failed, the arithmetic was
redone, and the fixed counterexample uses `p = 8` and now also pins the pickup
window and arrival time. Reported because it is direct evidence that the suite
catches wrong arithmetic rather than absorbing it.

### Finding 7 — The audit's own tooling committed a mutation *(process defect, fixed)*

An early version of `tools/mutation_test.py` restored the mutated file in a
`finally` block, which does not run when the process is killed. Interrupting a
slow run left `allow_node_revisits = True` in the working tree. Nothing was
committed, but it would have been a research-integrity failure of exactly the
kind this repository exists to prevent.

**Fix.** The runner installs SIGINT/SIGTERM handlers that restore before
exiting, refuses to start if a previous run leaked a mutation, and bounds each
run with a timeout that falls back to a stop-at-first-failure pass rather than
hanging (D-022).

### What did *not* break

- **The mission model.** Thirteen fixtures, every dispatch time on every grid,
  reproduced exactly by an independent implementation that shares no search,
  timing or hazard-assessment code.
- **The boundary convention.** Every exact-equality case behaves as the closed
  window convention predicts, in both implementations. The consequences —
  including a zero-margin success, and a refuge lost exactly on arrival counting
  as success when `min_safe_dwell = 0` — are now tabulated in
  `docs/TIME_SEMANTICS.md` rather than left to be discovered.
- **The ensemble aggregation.** `P_success` is a weighted count; the mutation
  that replaced it with an independence product was killed by eight tests.
- **The invariants.** All negative tests still fail when a record is tampered
  with.

## 5. Which tests caught them?

| finding | caught / pinned by |
|---|---|
| 1 — grid misses narrow windows | `tests/test_temporal_resolution.py` (11 tests), fixtures `n` / `n_resolved`, `tests/test_exact_solver.py::test_fixture_f_first_component_is_a_single_instant` |
| 2 — wrong deadline predicate | `tests/test_non_monotonic.py::test_dispatch_by_deadline_refuses_to_summarise_a_set_with_a_hole`, `tests/test_temporal_resolution.py::test_the_resolved_fixture_agrees_with_the_exact_answer` |
| 3 — silent arrival truncation | `tests/test_missions.py::test_branching_over_arrival_times_refuses_to_truncate` |
| 4 — unconditioned "complete" | no test; a documentation defect, fixed in documentation |
| 5 — claim language | no test; `docs/CLAIMS.md` is the control |
| 6 — wrong hand calculation | `tests/test_properties.py::test_longer_pickup_can_help_when_hazard_reopens` failed on the wrong value |
| 7 — mutation runner leak | `tools/mutation_test.py::_assert_tree_is_clean` now refuses to start on a dirty tree |

Mutation testing results (`reports/MUTATION_TESTING.md`), all eight killed:

| defect introduced | tests that rejected it |
|---|---|
| edge safety checked only at entry | 32 |
| scenario success as a product | 8 |
| pickup duration ignored | 120 |
| legs may revisit nodes (waiting by circling) | ≥1 (full pass timed out; the mutant also makes the suite pathologically slow, which is itself a signal) |
| deadline emitted from any set shape | 1 |
| search budget exhaustion returns "infeasible" | 1 |
| travel continues after a mid-edge failure | 12 |
| unsafe refuge accepted as a destination | 10 |

## 6. What remains scientifically unresolved?

1. **The oracle→forecast gap.** Every result is conditioned on complete
   knowledge of the scenario's future. How much of `𝒯_q` survives when the
   planner may only condition on a forecast is unmeasured, and fixture F
   suggests the answer can be "the interesting part does not".
2. **Ensemble semantics.** Weights are hand-authored. What would make a larger
   ensemble *meaningful* rather than merely larger — and what `q` means as a
   risk appetite when applied to an oracle quantity — is unresolved.
3. **Route-selection objective.** Selection is earliest-arrival. Fixture E
   therefore chooses a near refuge over a durable shelter whenever the refuge
   qualifies. Correct under the stated objective, arguably wrong operationally.
4. **The exact solver's conditions are not universal.** Under entry-only
   admission, node revisits, waiting, or time-dependent travel, the feasible set
   is resolution-limited again. Any such feature must ship with that statement.
5. **Waiting.** Specified (D-004) and unimplemented. The finiteness repair —
   restricting wait-until instants to hazard breakpoints — is sketched but
   unproven here.
6. **Adaptive grid refinement.** Even with the exact solver available, the
   sampled `P_success` curve used for plots can alias. Whether the sweep should
   refine adaptively where `P_success` changes is open.
7. **Nothing about frequency.** The fixtures show non-monotone feasible sets are
   *possible*. Nothing here says how often that happens in real road networks
   under real fires, and nothing here could.

## 7. Which future repository should own each unresolved problem?

| unresolved | owner | why not here |
|---|---|---|
| 1 oracle→forecast gap | a **forecast-value / OSSE** repository | needs a forecast object, an information-availability model and a regret metric. This repository's job in such a study is to supply the oracle term exactly, with assumptions attached |
| 2 ensemble semantics and `q` | the same **forecast / uncertainty** repository | calibrated weights require data and a verification framework, both out of scope (A-006, A-001) |
| 3 route-selection objective | **here** (roadmap R-4) | it is a property of the feasibility kernel and changes answers, so it needs a fixture, not a refactor |
| 4 exact-solver conditions | **here**, alongside whichever feature breaks them | the condition checks live with the solver |
| 5 waiting | **here** (roadmap R-1) | the semantics are already written down; only implementation and one fixture are missing |
| 6 adaptive refinement | **here** (roadmap R-6) | a property of the sweep, not of the model |
| 7 real-world frequency | a **network / hazard ingestion** repository, then an empirical study | requires real networks and real hazard products, both explicitly out of scope (D-016) |
| multi-responder / multi-resident | a **dispatch scheduling** repository | assignment plus scheduling is a different problem that should consume this kernel, not extend it |
| operational recommendation | **no repository yet** | requires availability, crewing, comms, accountability and validation; prohibited as a claim until it exists (`docs/CLAIMS.md`) |

## 8. What interface should eventually be exposed to the integration layer?

The kernel should be consumed as an **oracle/feasibility service**, never as a
planner. The proposed boundary, in the vocabulary already implemented:

```python
# Query — everything the kernel needs, and nothing operational
FeasibilityQuery(
    network:        RoadNetwork,          # via a network adapter
    scenarios:      ScenarioEnsemble,     # via a hazard adapter
    base:           str,
    resident:       str,
    destinations:   tuple[Destination, ...],
    pickup:         PickupModel,
    policy:         MissionPolicy,        # admission, waiting, revisits, horizon
    study_range:    tuple[float, float],
    threshold:      float,                # q
)

# Answer — a set, its provenance, and its conditioning
FeasibilityAnswer(
    components:              tuple[ClosedInterval, ...],   # ⋃_k [a_k, b_k]
    last_feasible_instant:   float | None,
    is_dispatch_by_deadline: bool,
    method:                  "exact" | "sampled",
    resolution:              float | None,   # None iff method == "exact"
    conditions_checked:      tuple[str, ...],
    conditioning:            "oracle",       # never anything else, in this phase
    assumptions:             tuple[str, ...],  # the A-### set in force
    per_scenario_sets:       Mapping[str, IntervalSet],
    per_scenario_records:    Mapping[str, MissionResult],  # full timelines
)
```

Four contract rules follow from this audit and should be enforced at the
boundary, not left to callers:

1. **`conditioning` travels with the answer.** A consumer that drops it is
   converting a benchmark quantity into an operational claim. It should be a
   required field, not metadata.
2. **`method` and `resolution` travel with the answer.** A sampled answer
   without its resolution is unusable, and an empty sampled answer must never be
   serialised as "infeasible".
3. **No boolean-only endpoint.** The kernel returns sets and full mission
   records; an `is_feasible(t) -> bool` convenience would be adopted
   immediately and would discard every qualifier that makes the answer true.
4. **Adapters convert, they do not interpret.** A hazard adapter turns an
   external product into closed-window timelines and nothing else; if the
   external product cannot be expressed that way, the adapter fails loudly
   rather than approximating (A-016).

The two adapters — hazard product → timelines, and road network → `RoadNetwork`
with corridor identity preserved — are the *only* places real data should enter,
and they belong to the ingestion repository, not to this one (roadmap R-8, R-9).

---

## Release decision

Phase-1 goals met; three defects found and fixed; every fix carries a test or
fixture that would fail if it were reverted; no claim was found to be
unsupportable that has not been narrowed or removed. **Frozen as `v0.1.0`.**
