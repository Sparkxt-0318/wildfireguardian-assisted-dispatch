# Decisions

Modelling and engineering decisions where a real alternative existed. Each one
states the alternative and why it was rejected, so that reversing it is a
deliberate act rather than a refactor.

---

### D-001 — Coherent scenarios, never independent edge probabilities
**Decision.** Uncertainty is a small weighted ensemble of whole, internally
consistent hazard scenarios. `P_success(t)` sums the weights of the scenarios in
which the *whole mission* succeeds.
**Alternative.** Per-edge survival probabilities multiplied along a route.
**Why rejected.** Wildfire hazard is strongly correlated in space and time, so
independence understates joint failure — exactly the case that kills a
responder. Missions also reuse the same corridor twice (fixture C), which a
product model treats as two independent coin flips of one road. The resulting
number would not be the probability of anything actionable.
**Enforced by.** `hazards/scenario.py`; fixture `b_ensemble`;
`test_feasibility.py::test_p_success_is_a_weight_sum_not_an_edge_product`.

### D-002 — Closed safety windows; `end` is the last safe instant
**Decision.** `closes_at(25)` is safe at exactly `t = 25`.
**Alternative.** Half-open `[start, end)`.
**Why rejected.** Fixture deadlines would read `arrival < T` and every hand
calculation would carry a boundary footnote. The difference is a measure-zero
set of instants with no physical content in a synthetic step-function hazard;
what matters is that it is stated once and obeyed everywhere.
**Enforced by.** `hazards/timeline.py`; `test_timeline.py`.

### D-003 — A mid-traversal closure catches the vehicle; no reverse is modelled
**Decision.** Losing safety while on a segment ends the mission at that instant,
reported as `CAUGHT_MID_EDGE` with segment, entry, loss instant and the exit that
never happened. Two admission policies (`FULL_INTERVAL`, `ENTRY_ONLY`) expose the
consequence; the audit is always full-interval.
**Alternative.** Model a U-turn, or a partial retreat to the nearest node.
**Why rejected.** It would require a half-edge travel time, an unmodelled
turnaround duration, and a behavioural claim about driving in smoke that no
synthetic fixture can support. Modelling escape would make the kernel optimistic
in precisely the situation where optimism is lethal.
**Enforced by.** `hazards/semantics.py`; fixtures `g`, `g_myopic`;
`test_mid_edge_closure.py`.

### D-004 — No waiting in phase 1
**Decision.** `WaitingPolicy.PROHIBITED` is the only implemented policy. Other
values raise at construction. If waiting is added it must be explicit, confined
to a declared node allow-list, and logged as its own leg with its own hazard
assessment.
**Alternative.** Allow the search to hold at nodes, which would enlarge `T`.
**Why rejected for now.** Waiting makes the search a scheduling problem and
makes every timestamp a scheduler output rather than a sum the reader can check.
The research plan explicitly permits prohibiting it first; doing so keeps the
no-implicit-waiting invariant verifiable.
**Enforced by.** `missions/policy.py`; `validation/invariants.py`;
`test_invariants.py`.

### D-005 — Each leg is a simple path (no node revisits) by default
**Decision.** `allow_node_revisits = False`.
**Alternative.** Allow revisits, as a plain graph search would.
**Why rejected.** Circulating (`base → home → base → home`) burns time without
any idle instant — waiting with the engine running. Permitting it silently would
put waiting into a model that advertises no waiting. The option remains, and
plans produced under it must be read as hold-by-circulation.
**Cost accepted.** Routes that legitimately need to pass a junction twice are
excluded. On five-node synthetic networks that cost is zero.
**Enforced by.** `search/time_expanded.py`; `validation/invariants.py`;
`test_search.py::test_simple_paths_only_by_default`.

### D-006 — Report the set; emit a deadline only when the deadline reading is true
*(amended by the v0.1 audit — see D-019.)*
**Decision.** The computed object is `T(q) = {t : P_success(t) ≥ q}`.
`dispatch_by_deadline()` raises `DispatchByDeadlineUndefined` unless the set is
a single component reaching the start of the studied range. `last_feasible_instant`
stays available unconditionally, labelled as a statement about the supremum
rather than about the set.
**Alternative.** Always return `sup T`, with a warning.
**Why rejected.** A warning next to a number gets dropped the moment the number
is copied into a slide. Fixture F's set is `{0} ∪ [11, 13]`; "leave before 13"
tells a dispatcher that t = 5 is fine, and it is not.
**Enforced by.** `feasibility/dispatch.py`; fixture `f`;
`test_non_monotonic.py`.

### D-007 — Constant travel times only
**Decision.** One travel model, `ConstantTravelModel`, trivially FIFO.
**Alternative.** Time-dependent speeds / congestion.
**Why rejected for now.** Non-FIFO travel times create "leave later, arrive
earlier" effects with *no hazard involved*, which would confound the
hazard-driven non-monotonicity this phase exists to isolate. The `TravelModel`
protocol leaves the seam open.
**Enforced by.** `network/travel.py`; A-007.

### D-008 — Minutes are the canonical unit
**Decision.** `float` minutes from a scenario epoch; `EPS = 1e-9`.
**Alternative.** Seconds, or an absolute datetime.
**Why rejected.** Hand-checkable arithmetic is the validation instrument;
minutes keep every fixture mentally verifiable. Datetimes would add timezone
questions that answer nothing here.

### D-009 — A destination requires a minimum safe dwell
**Decision.** Arrival at `z` qualifies only if the destination node is safe
throughout `[z, z + min_safe_dwell]`.
**Alternative.** Arrival at a currently-safe node is success.
**Why rejected.** That makes "arrived" and "evacuated" the same thing. A refuge
that is overrun ten minutes after arrival is the same emergency, relocated.
Fixture E depends on this distinction, and with `min_safe_dwell = 0` the same
fixture reports success for missions ending inside the fire perimeter.
**Enforced by.** `missions/spec.py`; fixture `e`.

### D-010 — Complete time-expanded enumeration, not label-setting
**Decision.** Search enumerates every reachable `(node, time)` state; earliest
arrival is never assumed dominant.
**Alternative.** Dijkstra-style earliest-arrival labelling.
**Why rejected.** With reopening hazards and no waiting, an earlier arrival can
be strictly worse: the pickup ends earlier, the egress starts earlier, and it
lands inside a closure window instead of after it. Settling each node once would
silently convert feasible missions into infeasible ones. Completeness is cheap
on synthetic fixtures and is worth far more than asymptotics here.
**Enforced by.** `search/time_expanded.py`;
`test_search.py::test_later_arrivals_are_kept_because_earliest_does_not_dominate`.

### D-011 — Deterministic route selection: earliest arrival, total tie-break
**Decision.** Minimise destination arrival; tie-break on destination priority,
then node id, then edge sequences.
**Alternative.** Maximise hazard margin, or minimise exposure.
**Why deferred.** Margin-aware selection changes answers (fixture E would pick
the durable shelter over the near refuge), so it is a modelling change, not an
improvement — roadmap R-4. The lexicographic tail exists so two runs produce
byte-identical logs; without that, fixtures prove nothing.

### D-012 — Report the failure that got furthest; horizon ranks lowest
**Decision.** When several branches fail differently, report the
furthest-progressed failure, tie-broken by earliest resident arrival.
`HORIZON_EXCEEDED` ranks below every hazard-based reason.
**Why.** A branch that circled the network until the clock ran out must never
outrank a branch that hit an actual closure. The horizon is a budget, not a
finding.
**Enforced by.** `missions/result.py::_PROGRESS_ORDER`; `missions/evaluator.py`.

### D-013 — Budget exhaustion raises; it never returns "infeasible"
**Decision.** Exceeding `max_states` raises `SearchBudgetExceeded`.
**Why.** A truncated search that reports infeasibility is the most dangerous
silent failure available to this package: it is indistinguishable from a real
answer and it errs towards "don't send anyone".
**Enforced by.** `search/time_expanded.py`;
`test_search.py::test_budget_exhaustion_raises_instead_of_reporting_infeasible`.

### D-014 — Strict configuration loading
**Decision.** Unknown config keys are errors. Hazard keys that match no network
element are errors.
**Why.** A silently-ignored `pickup_duration` (instead of `pickup`) produces a
plausible feasibility set for the wrong mission, and nothing downstream ever
notices.
**Enforced by.** `scenarios/config.py`; `test_config.py`.

### D-015 — Hazards key on corridors by default
**Decision.** A two-way road is two directed edges sharing a corridor id;
hazards attach to the corridor unless an edge-id key overrides it.
**Why.** A burning road is burning in both directions, and fixture C's
inbound/outbound conflict only exists if the reverse traversal consults the same
timeline.
**Enforced by.** `network/graph.py`; `hazards/scenario.py`; fixture `c`.

### D-016 — No integration with real WildfireGuardian routing in this phase
**Decision.** No real fire model, no real network, no routing integration.
**Why.** The integration boundary should be designed after the semantics are
fixed. Integrating first would make every semantic question ("what happens when
a road closes halfway across?") an integration question instead.
**Enforced by.** `SCOPE.md`; the absence of any such dependency.

### D-017 — ASCII feasibility output is primary; the PNG is optional
**Decision.** `wg-dispatch` always prints a character strip; matplotlib is an
optional extra, and its absence is reported rather than worked around.
**Why.** This is a terminal research tool, the feasible set is one-dimensional,
and a strip shows a hole in the set just as clearly as a figure — while working
over ssh, in CI logs and in a commit message.

---

## Amendments and additions from the v0.1 scientific audit

### D-018 — The exact interval solver is the primary feasible-set method
**Decision.** `feasibility/exact.py` computes `T_q` in closed form as a finite
union of closed intervals, with no time discretization. `wg-dispatch sweep`
runs it alongside the grid sweep and cross-checks the two. The grid sweep is
retained because `P_success(t)` as a *curve* (for plots, tables and threshold
studies) is naturally sampled.
**Alternative.** Keep sampling and simply recommend a finer grid.
**Why rejected.** Fixture N has a feasible window 0.1 minutes wide; no
recommendation protects a reader who does not know the feature size in advance,
and in general nobody does. The audit's requirement was to *detect and refine
reliably* or *report the resolution and refuse to imply exactness* — this does
both.
**Conditions.** Checked at call time, never assumed: constant travel times, no
waiting, simple paths, full-interval admission, bounded plan and scenario
counts. A failed condition raises `ExactSolverUnavailable` naming the condition;
it never degrades silently to sampling.
**Enforced by.** `tests/test_exact_solver.py`, `tests/test_temporal_resolution.py`;
fixtures `n`, `n_resolved`.

### D-019 — "Dispatch-by deadline" is a restricted phrase
**Decision.** `dispatch_by_deadline()` is defined only when the feasible set is
a single component reaching the start of the studied range. Otherwise the
vocabulary is *feasible dispatch set*, *feasible dispatch windows*, and *last
feasible dispatch instant*, and the API refuses the deadline reading rather than
qualifying it.
**Alternative.** Return `sup T` with a warning attached (the pre-audit
behaviour).
**Why rejected.** A warning next to a number survives exactly as long as it
takes someone to copy the number. Note also that grid monotonicity was the wrong
predicate: fixture `n_resolved` has a *single* feasible component and a
non-monotone sampled indicator, purely because the studied range starts before
the component does.
**Enforced by.** `tests/test_non_monotonic.py`, `docs/CLAIMS.md`.

### D-020 — The reference oracle duplicates path enumeration on purpose
**Decision.** `validation/brute_force.py` carries its own private DFS, its own
window scanning and its own timing arithmetic, rather than importing
`network.paths.simple_paths` or `hazards.semantics`.
**Why.** An oracle that shares its path enumeration with the solver it checks is
not an independent check of path enumeration. The duplication is the point, and
it is annotated as such in both modules so that a future tidy-up does not
"remove the redundancy".
**Enforced by.** `tests/test_reference_oracle.py`.

### D-021 — Monotonicity properties are scoped to closure-only worlds
**Decision.** The property-based tests that assert "longer pickup never helps",
"slower roads never help" and "earlier hazard never helps" generate worlds whose
timelines are closure-only.
**Why.** Those statements are *false* in general — fixture F and
`test_longer_pickup_can_help_when_hazard_reopens` are the counterexamples.
Asserting them universally would make the test suite stronger than the model,
which is worse than not testing them at all. The scope restriction is stated in
the test module docstring and re-checked by a test that the properties genuinely
fail outside it.
**Enforced by.** `tests/test_properties.py`.

### D-022 — Mutation testing is part of the release gate
**Decision.** `tools/mutation_test.py` introduces each defect the project claims
to defend against into the real source, runs the suite, and records which tests
caught it. A surviving mutant is a release blocker.
**Why.** A passing suite proves nothing on its own; it might be asserting
tautologies. Mutation results are the evidence that the invariants have teeth.
**Operational note.** The runner restores the tree on SIGINT/SIGTERM as well as
on normal exit, and refuses to start if a previous run leaked a mutation — both
added after an early version of the script left `allow_node_revisits = True` in
the working tree when it was interrupted.

### D-023 — `docs/CLAIMS.md` binds every output
**Decision.** A permitted-claims list and a prohibited-phrasing list, binding on
papers, plots, tables, README text, commit messages and conversation.
**Why.** The repository's product is trustworthy claims. Prohibiting "safe
route", "guaranteed rescue" and "lives saved" in writing is cheaper than
retracting them later.

### D-024 — The word "complete" requires stated conditions
**Decision.** "Complete" is used only as "complete under the conditions in
`ENUMERATION_COMPLETENESS.md` §3", and that document answers: is time continuous
or discretized, what creates candidate time states, can infinitely many arise,
under what assumptions enumeration is complete, what happens under reopening
hazards, under time-dependent travel, and under waiting.
**Why.** The pre-audit code and docs used "complete search" unqualified. It was
true under conditions nobody had written down, which is indistinguishable from
being wrong.
