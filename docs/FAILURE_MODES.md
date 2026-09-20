# Failure modes

Two different things are called "failure" here, and conflating them is itself a
failure mode. Part 1 is **how a mission fails** — the model's output. Part 2 is
**how this project could mislead you** — the model's own risks.

---

## Part 1 — Mission failure reasons

Every failed evaluation carries a `FailureReason` and, where a hazard is
responsible, a `HazardConflict` naming the element, the leg, the attempted
occupancy interval, the instant safety was lost, and the next reopening.

| Reason | Meaning | Typically caused by |
|---|---|---|
| `BASE_UNSAFE_AT_DISPATCH` | the base is not a safe place to be at `t` | the fire reaching the staging area |
| `NO_SAFE_ROUTE_INGRESS` | no admissible route base → resident | every approach corridor lost |
| `RESIDENT_NODE_UNSAFE_ON_ARRIVAL` | the address itself is unsafe when the responder would arrive | node closure, not corridor closure |
| `SERVICE_WINDOW_UNSAFE` | arrival is fine; standing there for `p` minutes is not | the pickup duration crossing a node closure |
| `NO_SAFE_ROUTE_EGRESS` | no admissible route resident → any destination | the outbound corridor lost while the pickup was happening |
| `DESTINATION_UNAVAILABLE` | the destination is reached outside its availability window | administrative window, not hazard |
| `REFUGE_DWELL_UNSAFE` | reached, but the place does not hold long enough | a temporary refuge about to be overrun |
| `CAUGHT_MID_EDGE` | the vehicle was on a segment when its safety was lost | entry-time-only admission (never possible under the default policy) |
| `HORIZON_EXCEEDED` | the plan ran past the planning horizon | a budget artefact, ranked below every hazard reason |

Two design rules govern this table:

- **"Infeasible" alone is never acceptable output.** Every failure says where
  and when.
- **The reported failure is the one that got furthest**, tie-broken by earliest
  resident arrival — so the message describes the most nearly successful plan,
  not whatever the search happened to try last (D-012).

### Reading the diagnostic

When no route exists at all, the evaluator quotes the *most informative* blocked
element: a near miss ("safe at entry 21, loses safety at 30, traversal would end
at 31") outranks a hopeless one ("already unsafe at entry 95"), and within each
class the earliest conflict wins.

---

## Part 2 — Ways this project could mislead you

These are the failure modes of the research, not of the mission. Several have
fixtures attached specifically so that a regression would be caught.

### F-1 — Reading the last feasible instant as a deadline ⚠
`sup T = 13` with `T = {0} ∪ [11, 13]` is true about the supremum and false
about the set. Dispatching at t = 5 fails.
**Mitigation.** `dispatch_by_deadline()` is defined only when the set is a
single component reaching the start of the studied range, and raises otherwise;
`last_feasible_instant` is always available and is named so that it cannot be
mistaken for a deadline (D-006, D-019). The CLI prints the windows and the
warning, not just the number. Fixture `f`.

### F-2 — Checking hazard at the entry instant ⚠
The classic error. It approves segments that close under the vehicle.
**Mitigation.** `A_e` is defined over the whole interval; the audit is always
full-interval whatever the admission policy; `ENTRY_ONLY` exists only to measure
the damage (D-003). Fixtures `g` / `g_myopic` — ten dispatch minutes lost by
driving into the fire.

### F-3 — Checking only the inbound traversal
The responder gets in comfortably and cannot get out. On a dead-end spur the
inbound-only answer is wrong by the round trip plus the pickup.
**Mitigation.** Corridor-keyed hazards (D-015) and an egress leg that is
evaluated in its own right. Fixture `c`: t ≤ 14, not t ≤ 27.

### F-4 — Multiplying independent edge probabilities
Produces a smooth, higher, meaningless survival number with no threshold where
the real one is.
**Mitigation.** Scenario-by-scenario evaluation; nothing in the package exposes
a per-edge probability at all (D-001). Fixture `b_ensemble`.

### F-5 — Implicit waiting
An idle minute inserted by a scheduling rule makes every downstream timestamp
unverifiable and quietly enlarges `T`.
**Mitigation.** No waiting is implemented; the log must account for every minute
as travel or declared service; the invariant runs over every fixture and every
dispatch time (D-004). Note the subtler variant, **waiting by driving**, handled
by the simple-path rule (D-005).

### F-6 — Treating "arrived" as "evacuated"
A refuge reached five minutes before it burns is not a completed mission.
**Mitigation.** `min_safe_dwell` (D-009). Fixture `e` — and the same fixture with
`min_safe_dwell = 0` would report success for missions ending inside the fire.

### F-7 — Silent search truncation
A search that hits its budget and returns "no route" is indistinguishable from a
genuine infeasibility, and errs towards not sending anyone.
**Mitigation.** `SearchBudgetExceeded` is raised, never swallowed (D-013).

### F-8 — Grid aliasing ⚠ *(a confirmed defect, found and fixed by the v0.1 audit)*
A feasible window narrower than the sweep step and lying between two samples is
**invisible** to a grid sweep — not approximated, invisible. `refine_transitions`
cannot help, because there is no observed transition to refine.

This was not hypothetical. Fixture N has a true feasible set of `[11.3, 11.4]`
and the default one-minute sweep reports **empty**. Fixture F, shipped in the
original release, has an isolated feasible *point* at `t = 0` that the default
grid found only because the grid happened to start there.

**Mitigation.** An exact, discretization-free solver
(`feasibility/exact.py`, D-018) now computes the feasible set in closed form and
is run alongside the sweep by default, with the two cross-checked. Every sampled
result carries its resolution in an unconditional warning, is labelled `SAMPLED`,
and an empty sampled result says in as many words that it is not evidence of an
empty feasible set. See `TEMPORAL_RESOLUTION.md`.
**Residual risk:** the exact solver has stated conditions. Where they do not
hold — entry-only admission, node revisits, waiting — the answer is
resolution-limited again, and must be reported as such.

### F-9 — Over-reading ensemble weights
`P_success = 0.8` is "the mission works in the scenarios carrying 80% of our
hand-assigned weight", not a calibrated probability (A-006).
**Mitigation.** Documented here and in `HAZARD_SEMANTICS.md`; the CLI prints the
reminder alongside the number. **Residual risk:** high. This is the easiest
number in the repository to quote out of context.

### F-10 — Treating pickup profiles as clinical categories ⚠
The four durations are sensitivity values with deliberately content-free names
(A-004).
**Mitigation.** The disclaimer is attached to the model object, printed by
`pickup-sweep`, and asserted in the test suite. **Residual risk:** high, if
results are re-plotted elsewhere.

### F-11 — Forgetting that the planner has full foresight ⚠⚠
The single largest interpretive risk. Every feasible set here is an
**optimistic upper bound**: the search knows each scenario's whole future,
including reopenings that have not happened (A-008). Fixture F's second window
`[11, 13]` is only exploitable by someone who already knows the corridor reopens
at t = 18.
**Mitigation.** Documented in `RESEARCH_QUESTION.md` and `ASSUMPTIONS.md`.
**Residual risk:** high. Closing this gap with rolling-horizon replanning is
roadmap R-3, and until then no result here should be read as an achievable
operating envelope.

### F-13 — Quoting an oracle result as an operating envelope ⚠⚠
Closely related to F-11 and worth separating: even a *correct* feasible set here
describes what was physically possible given complete knowledge of the fire's
future. Calling it an operating envelope, a dispatch window, or a
recommendation converts a benchmark quantity into an operational claim the
repository cannot support.
**Mitigation.** `docs/ORACLE_FEASIBILITY_LIMIT.md` fixes the vocabulary
(*oracle feasibility envelope*, *physical feasibility upper bound*);
`docs/CLAIMS.md` prohibits the alternatives outright.

### F-14 — Asserting a property the model does not have
A subtler research failure: writing a test that says "later dispatch is never
better" would pass on most fixtures, feel like a safety net, and quietly encode
the exact error this project exists to refute.
**Mitigation.** Monotonicity properties are scoped to closure-only generated
worlds (D-021), and a test asserts that they genuinely *fail* on the reopening
fixture. Guard rails need guard rails.

### F-12 — Generalising from synthetic fixtures
Five-node networks with round-number travel times are an instrument for checking
semantics, not evidence about real road systems. Nothing here supports a claim
about how often real dispatch windows are non-monotone — only that
non-monotonicity is possible and that a single-deadline summary is therefore
unsound in general.
