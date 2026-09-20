# Glossary

**Admission policy** — which traversals the *planner* may commit to:
`FULL_INTERVAL` (only segments it can provably clear; the default) or
`ENTRY_ONLY` (anything safe at the entry instant; the red-team policy). The
*audit* is always full-interval regardless.

**`A_e([t_in, t_out], m)`** — the availability operator. Whether edge `e` is safe
over the whole closed occupancy interval under scenario `m`. Reports
`safe_at_entry`, `safe_throughout`, `safety_lost_at` and `margin`.

**Base** — the responder's starting node. Must be safe at the dispatch instant.

**Caught mid-edge** — the vehicle was on a segment when its safety was lost. The
mission ends there; no reverse is modelled (D-003).

**Circulation** — burning time by driving a loop instead of idling. Waiting with
the engine running; prohibited by the simple-path rule (D-005).

**Coherent scenario** — one deterministic, internally consistent assignment of
safety timelines to every corridor and node. The unit of uncertainty in this
project; never decomposed into per-edge probabilities.

**Corridor** — the undirected identity of a road. Both directed edges of a
two-way road share it, so a hazard on the corridor applies to both directions
(D-015).

**Dispatch time (`t`)** — the instant the responder leaves the base. The decision
variable.

**Dwell (`min_safe_dwell`)** — how long a destination must *remain* safe after
arrival for the mission to count as complete. Distinguishes a shelter from a
temporary refuge (D-009).

**Egress** — the leg from the resident's address to a safe destination, starting
at the end of the pickup.

**Ensemble** — a small, hand-authored set of weighted coherent scenarios. A
sensitivity device, not a calibrated forecast (A-006).

**Feasible dispatch set (`T(q)`)** — `{t : P_success(t) ≥ q}`. The output of this
project.

**Full foresight** — the planner knows each scenario's entire hazard timeline in
advance. Makes every result an optimistic upper bound (A-008).

**Gap** — an infeasible stretch of dispatch times lying *between* two feasible
ones. A non-empty gap list is exactly the evidence of non-monotonicity.

**Hazard conflict** — the record of the specific element, leg, interval and
instant responsible for a failure.

**Horizon** — the clock time after which a mission is abandoned. A search budget,
not a finding; `HORIZON_EXCEEDED` ranks below every hazard-based failure.

**Ingress** — the leg from the base to the resident's address.

**Leg** — one segment of the mission timeline: dispatch, ingress, service,
egress, arrival, dwell.

**Margin** — spare minutes between clearing an element and losing it. A mission's
`min_margin` is the tightest such value anywhere on it. Zero is possible and is
reported honestly.

**Mission** — the whole thing: base → resident → pickup → safe destination.

**Monotone (feasibility)** — feasibility, once lost as `t` increases, is never
regained on the studied grid. Necessary but *not sufficient* for a deadline: a
set whose single component starts after the beginning of the studied range is
non-monotone on that grid and still has no hole in it (fixture `n_resolved`).
The predicate that licenses a deadline is `is_dispatch_by_deadline` (D-019).

**`P_success(t)`** — the total weight of the scenarios in which the *whole*
mission succeeds when dispatched at `t`. A sum over scenarios, never a product
over edges (D-001).

**Pickup / service** — the on-scene interval `[a, a + p]` during which responder
and resident are both stationary at the address. Its duration is a scenario
parameter, **not** a medical category (A-004).

**Refuge** — a destination that may stop being safe. Handled by `min_safe_dwell`
and by node hazard timelines, not by a separate mechanism.

**Reopening** — a corridor that becomes safe again after a closure. The
mechanism behind the only intrinsic non-monotonicity in the model.

**Resident** — the mobility-limited person who cannot self-evacuate. The node the
mission must reach before it can leave.

**Safety horizon** — for a timeline and an instant `t`, the end of the safe window
containing `t` (`None` if already unsafe, `∞` if never closing). The single query
the full-interval assessment is built on.

**Simple path** — a leg that visits no node twice. The default (D-005).

**Last feasible dispatch instant** — `sup 𝒯_q`. Because `𝒯_q` is closed it is
*attained*: dispatching at exactly that instant works. On its own it says
nothing about earlier instants, so it is **not** a deadline.

**Dispatch-by deadline** — the value `X` for which "dispatch any time up to `X`"
is true. Defined only when `𝒯_q` is a single component reaching the start of the
studied range; `dispatch_by_deadline()` refuses otherwise (D-019). For every
other shape, say *feasible dispatch set*, *feasible dispatch windows*, or *last
feasible dispatch instant*, and say which you mean.

**Connected components** — the maximal closed intervals `[a_k, b_k]` whose union
is `𝒯_q`. The exact solver reports them directly; `K > 1` is precisely the case
in which no deadline exists.

**Exact (interval) solver** — `feasibility/exact.py`. Computes `𝒯_q` in closed
form by interval arithmetic over the finitely many combinatorial plans, with no
time discretization, under conditions it checks rather than assumes (D-018).

**Oracle feasibility envelope** / **physical feasibility upper bound** — the
approved names for what this repository computes: what was physically possible
given complete knowledge of the scenario's future. Never "operating envelope"
(A-008, `ORACLE_FEASIBILITY_LIMIT.md`).

**Reference oracle** — `validation/brute_force.py`. A deliberately slow second
implementation that enumerates plans by hand and shares no search, timing or
hazard-assessment code with the main solver (D-020).

**Mutation testing** — deliberately introducing a defect into the real source to
check that the suite rejects it. A *killed* mutant was caught; a *survivor* is a
hole in the suite (D-022, `reports/MUTATION_TESTING.md`).

**Temporal resolution** — the grid step of a dispatch sweep. Sampled results are
accurate only to it, and a window narrower than it can be missed entirely
(`TEMPORAL_RESOLUTION.md`).

**Time-expanded state** — a `(node, arrival time)` pair. The search enumerates
these completely rather than settling each node once, because earliest arrival
does not dominate under reopening hazards (D-010).

**Timeline** — a set of disjoint closed intervals during which an element is safe.
Windows are closed; `end` is the last safe instant (D-002).

**Traversal** — one edge occupied over one closed time interval.

**Waiting** — deliberately holding position. Prohibited in phase 1; if ever added
it must be explicit, node-restricted, and logged (D-004).
