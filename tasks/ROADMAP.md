# Roadmap

Phases are ordered by what has to be *settled* before the next thing can be
trusted, not by effort.

---

## Phase 1 — Deterministic kernel and small ensembles ✅ complete

Settle the semantics against arithmetic. Everything hand-checkable.
See `COMPLETED.md` for the item-by-item record.

---

## Phase 2 — Structural extensions (next)

Each item changes answers, so each ships with a fixture that would fail if the
change were reverted.

### R-1 — Explicit waiting at allowed nodes
Implement `WaitingPolicy.EXPLICIT_AT_ALLOWED_NODES` (D-004). Requires:
a declared node allow-list on the mission spec; a `wait` leg in the log with its
own node-hazard assessment over the whole wait interval; the no-implicit-waiting
invariant updated to *require* that a wait be declared rather than to forbid all
waits; a search that branches on "wait here until the next reopening" rather
than on arbitrary durations.
**Expected effect:** `T` grows, and fixture F's gap partially fills — dispatch
at t = 5, drive to the resident, and hold at the address until the corridor
reopens. That is a different mission with different exposure, and the log must
say so.
**Fixture to add:** the F network with waiting enabled; the gap must shrink in a
way the arithmetic predicts exactly.

### R-2 — Time-dependent travel times
Relax D-007. Requires an explicit FIFO discipline (or a documented non-FIFO
model and the resulting "leave later, arrive earlier" effects separated from the
hazard-driven ones).
**Fixture to add:** a network where travel-time-driven and hazard-driven
non-monotonicity are both present and distinguishable.

### R-3 — Online / rolling-horizon planning ⚠ highest value
Relax full foresight (A-008). The planner sees a forecast, not the truth;
replanning happens at fixed intervals as the hazard field is revealed.
**Why it matters most:** every feasible set in this repository is currently an
*upper bound*. R-3 is what turns "a plan exists" into "a dispatcher could find
it", and it is the difference between a bound and an operating envelope.
**Fixture to add:** fixture F under a forecast that does not include the
reopening — the `[11, 13]` window should become unreachable.

### R-4 — Margin-aware route selection
Currently selection is earliest-arrival (D-011). Add a selectable objective:
maximise the minimum hazard margin, or lexicographic (feasible, then margin,
then time).
**Expected effect:** fixture E stops choosing the near refuge over the durable
shelter. That is a *better* mission and a *different* answer, which is why it is
a roadmap item and not a fix.

### R-5 — Richer destination semantics
Capacity (A-012), suitability, and a modelled cost of using a refuge rather than
a shelter.

---

## Phase 3 — Multi-entity dispatch

### R-6 — Multiple residents, one responder
Sequencing and the interaction between service durations and closures. A
scheduling problem layered on the current feasibility kernel.

### R-7 — Multiple responders
Assignment plus scheduling. Needs a clear statement of the objective (maximise
residents evacuated? minimise worst-case exposure?) before any code.

---

## Phase 4 — Interfaces to reality (explicitly not before phase 3)

### R-8 — Hazard field ingestion boundary
Define the adapter that turns *any* external time-varying hazard product into
corridor/node timelines. The adapter is the integration point; nothing upstream
of it enters this kernel.

### R-9 — Network ingestion boundary
Same, for road networks: OSM-style input to `RoadNetwork`, with corridor
identity preserved.

### R-10 — WildfireGuardian routing integration
**Blocked until the semantics above are fixed** (D-016). The integration
boundary should be designed after the questions "what happens mid-edge?",
"what does `P_success` mean?" and "what is `T`?" already have written answers —
which, as of phase 1, they do.

---

## Standing non-goals

Revisit only with a written decision record:

- fire-spread physics inside this repository;
- calibrated probabilities from hand-authored ensembles;
- any clinical interpretation of the pickup durations;
- reporting a single latest dispatch time for a non-monotone feasible set.
