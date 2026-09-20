# Claim discipline

This repository's only product is *trustworthy claims*. This document is the
list of claims it is allowed to make, and the list it is forbidden to make.
It binds every output: papers, plots, tables, README text, commit messages,
issue comments, and conversations about the work.

**If a result cannot be stated using the permitted vocabulary below, the result
is not ready to be stated.**

---

## Permitted claims (v0.1)

Each is followed by the evidence that supports it.

### C-1 — The implementation evaluates complete assisted-evacuation missions
Responder ingress, on-scene pickup/service, and egress to a declared
destination, with the destination required to remain safe for a declared dwell.
*Evidence:* `docs/MISSION_MODEL.md`; every mission record carries the full
timeline; `validation/invariants.py` checks that every minute of the mission
clock is travel or declared service.

### C-2 — Road feasibility is evaluated over traversal intervals, not at edge entry
`A_e([t_in, t_out], m)` is evaluated over the whole closed occupancy interval,
and a plan that spends any instant on an unsafe element is never reported as a
success.
*Evidence:* `docs/HAZARD_SEMANTICS.md`; fixtures `g` / `g_myopic`; the
`success.{ingress,egress}_is_safe` invariant; mutation `entry_only_admission`
is killed by the suite.

### C-3 — Mission success can be evaluated across coherent weighted hazard scenarios
`P_success(t) = Σ w_i S(t, m_i)`, a weighted count over whole scenarios.
*Evidence:* fixture `b_ensemble` with hand-checkable values 1.0 / 0.8 / 0.0;
mutation `probability_product` is killed.

### C-4 — Feasible dispatch times need not form a single monotone interval
The feasible set can have gaps, isolated points, and components far from the
epoch.
*Evidence:* fixture `f` (`𝒯_1 = {0} ∪ [11, 13]`), fixture `g_myopic`, fixture
`n`; the exact solver reports connected components directly.

### C-5 — The solver computes oracle-conditioned physical feasibility under declared assumptions
Given a fully specified hazard scenario, it decides whether a mission
dispatched at `t` was physically possible.
*Evidence:* `docs/MATHEMATICAL_SPECIFICATION.md` §4(a); `docs/ASSUMPTIONS.md`
A-001 … A-015; `docs/ORACLE_FEASIBILITY_LIMIT.md`.

### C-6 — For the phase-1 model class, the feasible dispatch set is computed exactly
Under the conditions checked in `feasibility/exact.py`, `𝒯_q` is a finite union
of closed intervals computed in closed form, with no time discretization.
*Evidence:* `docs/MATHEMATICAL_SPECIFICATION.md` §3; fixture `n`, where the
sampled sweep finds nothing and the exact solver finds `[11.3, 11.4]`.

### C-7 — The results reproduce under an independent implementation
Every fixture is cross-checked against a brute-force oracle that shares no
search, timing, or hazard-assessment code with the main solver.
*Evidence:* `validation/brute_force.py`; `tests/test_reference_oracle.py`.

### C-8 — Staging location changes the feasible dispatch set, and nearer is not always wider
*Evidence:* fixture `h_north` / `h_south` — the base ten minutes closer has the
*smaller* feasible set (`[0, 12]` against `[0, 15]`).

---

## Prohibited claims

These must not appear in any output of this repository, in any phrasing, with
or without hedging.

| ❌ Prohibited | Why | Say instead |
|---|---|---|
| **"safe route"** | Nothing here establishes safety. It establishes that a route was passable in a *stipulated* scenario. | "a route feasible under scenario `m`" |
| **"guaranteed rescue"** | Nothing is guaranteed. Success is conditional on a synthetic scenario and fifteen numbered assumptions. | "the mission is physically feasible under the stated scenario and assumptions" |
| **"operational dispatch recommendation"** | Recommendations require availability, crewing, comms, prioritisation and accountability — none modelled (A-002, A-009, A-011, A-012). | "oracle-conditioned feasibility result" |
| **"validated Korean rescue deadline"** | No real Korean network, no real incident data, no validation against reality (A-001, D-016). And "deadline" is itself restricted — see below. | "a synthetic-fixture last feasible dispatch instant" |
| **"lives saved"** | The model has no casualty model, no population, and no counterfactual. | nothing — this quantity does not exist here |
| **"real-world probability of survival"** | `P_success` is a weighted count over hand-authored scenarios, not a calibrated probability, and not about survival (A-006, A-014). | "weight of the scenarios in which the mission completes" |

### Further restricted vocabulary

- **"dispatch-by deadline"** — permitted **only** when the feasible set is a
  single component reaching the start of the studied range, which
  `dispatch_by_deadline()` enforces and `is_dispatch_by_deadline` reports.
  Otherwise say *feasible dispatch set*, *feasible dispatch windows*, or *last
  feasible dispatch instant*, and say which you mean.
- **"operating envelope"** — never. The permitted terms are *oracle feasibility
  envelope* and *physical feasibility upper bound*
  (`docs/ORACLE_FEASIBILITY_LIMIT.md` §4).
- **"complete search"** — only as *"complete under the conditions in
  `ENUMERATION_COMPLETENESS.md` §3"*.
- **Pickup profiles** — never described as medical, clinical or triage
  categories; they are scenario parameters (A-004).
- **Any number from a grid sweep** — never quoted at finer precision than the
  grid step, and an empty sampled result is never reported as an empty feasible
  set (`TEMPORAL_RESOLUTION.md` §4).

---

## The test to apply before writing anything down

1. Which permitted claim (C-1 … C-8) is this an instance of?
2. Which fixture, test, or document is the evidence?
3. Does the sentence survive the reader asking *"under what assumptions?"*
   without further qualification? If not, add the qualifier — it is part of the
   claim, not decoration.
4. Would the sentence still be true if the reader assumed the planner did not
   know the future? If not, it needs the oracle qualifier (A-008).

If any of the four fails, the sentence is not yet a claim this repository can
make.
