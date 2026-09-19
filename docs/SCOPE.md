# Scope

## In scope (phase 1, complete)

- Synthetic directed road graphs with corridor identity for two-way roads.
- Synthetic time-varying hazard fields as piecewise-constant safety timelines on
  corridors and nodes, including **reopening**.
- The full mission timeline: dispatch, ingress, pickup/service, egress,
  destination arrival, with a required safe dwell at the destination.
- The full-traversal-interval availability operator `A_e([t_in, t_out], m)`, and
  explicit semantics for mid-traversal closure.
- A complete time-expanded search over `(node, time)` states, with no waiting.
- Deterministic mission evaluation producing a full record and a detailed
  failure reason.
- Small, hand-authored coherent scenario ensembles and `P_success(t)`.
- The feasible dispatch set `T(q)`, its monotonicity, its gaps, and boundary
  refinement by bisection.
- Pickup-duration sensitivity across the four scenario durations.
- Seven synthetic fixtures (A–G) with hand calculations, plus two variants.
- A command line tool, declarative configs, parquet/CSV output, feasibility
  rendering.

## Explicitly out of scope, and why

| Not here | Why |
|---|---|
| **Real wildfire models** (FARSITE/FlamMap-style spread, weather coupling) | The point of this phase is to settle semantics against arithmetic. Real spread models make every result unfalsifiable by hand. |
| **Real Korean road networks** (or any real network) | Same reason, plus: a real network invites operational interpretation of results that assume perfect foresight (A-008). |
| **WildfireGuardian routing integration** | Explicitly deferred. The integration boundary should be designed *after* the semantics are fixed, not during. |
| **Multi-responder / multi-resident dispatch** | A genuinely different problem (assignment + scheduling). Phase 1 is one responder, one resident (A-002, A-003). |
| **Vehicle capacity, fuel, crew hours** | Would add constraints that mask the hazard-timing effects this phase is isolating (A-011). |
| **Congestion and evacuation traffic** | Travel times are constant (D-007). Congestion is a strong effect and deserves its own phase, with its own fixtures. |
| **Online / partially-observed planning** | The planner has full foresight within a scenario (A-008). Rolling-horizon replanning is roadmap item R-3. |
| **Calibrated probabilities** | Ensemble weights are hand-authored sensitivity dials, not forecasts (A-006). |
| **Medical triage modelling** | The pickup durations are scenario parameters with neutral names. This project makes no clinical claim (A-004). |
| **Mid-edge U-turns, shelter-in-place, ad-hoc refuges** | Each would require behavioural assumptions no synthetic fixture can support (D-003). |
| **Geometry, turn restrictions, elevation** | Not needed to answer the question; would obscure the hand calculations. |

## Scope guard

If a proposed change makes it impossible for a reviewer to re-derive a fixture's
expected windows with a pencil, it belongs in a later phase. That is the
operative test, and it is the reason most of the table above says "no".
