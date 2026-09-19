# Hazard semantics

## Representation

A hazard is a **safety timeline** attached to a network element: a set of
disjoint closed intervals during which the element may be occupied.

```python
Timeline.closes_at(40)                     # safe on [0, 40]
Timeline.opens_at(18)                      # safe on [18, ∞)
Timeline.closed_between(12, 18)            # safe on [0, 12] ∪ [18, ∞)
Timeline.from_windows([[0, 12], [18, 25]]) # a flare front, then a final loss
```

Timelines attach to:

- **corridors** — the undirected identity of a road. This is the default,
  because a burning road is burning in both directions. It is what makes
  fixture C work: the responder drives in along the spur and back out along the
  same corridor, consulting the same timeline both times.
- **directed edges** — an edge-id key overrides the corridor key for that
  direction, for the rare case where directionality genuinely matters.
- **nodes** — places. A node closure is what ends a pickup or overruns a refuge.

A hazard key that matches nothing in the network is a **hard error**
(`HazardScenario.validate`). A typo'd corridor id would otherwise silently
produce a hazard-free network and a confidently wrong feasibility set.

## The availability operator

```
A_e([t_in, t_out], m)
```

is evaluated over the **whole closed occupancy interval**, and returns four
things, not one:

| field | meaning |
|---|---|
| `safe_at_entry` | would a planner checking only `t_in` accept this? |
| `safe_throughout` | is every instant of `[t_in, t_out]` safe? |
| `safety_lost_at` | the last safe instant, when safety is lost during the traversal |
| `margin` | spare minutes between clearing the element and losing it |

Implementation is one query against the timeline:

```
safe_throughout  ⟺  safety_horizon(t_in) ≥ t_out
```

where `safety_horizon(t)` is the end of the safe window containing `t`
(`None` if already unsafe, `∞` if the window never closes).

## What happens when a road becomes unsafe halfway across

**The vehicle is caught.** The mission ends at `safety_lost_at`, on the segment,
with the responder — and on the egress leg, the resident — still aboard. The
failure reason is `CAUGHT_MID_EDGE` and the record names the segment, the entry
time, the instant safety was lost, and the exit time that never happened.

There is **no** modelled reverse, no half-edge retreat, no shelter-in-place.
That is a decision (D-003), not an omission: a U-turn would need a partial-edge
travel time, an unmodelled turnaround duration, and a behavioural claim about
driving in smoke that no synthetic fixture can support. Modelling it as "the
vehicle escapes" would make the kernel optimistic in exactly the situation where
optimism is lethal.

### Two admission policies make the consequence visible

`MissionPolicy.admission`:

- **`FULL_INTERVAL`** (default). The planner may only commit to a traversal it
  can provably clear. Catches are impossible by construction; the mission fails
  earlier and honestly, with `NO_SAFE_ROUTE_INGRESS` / `NO_SAFE_ROUTE_EGRESS`.
- **`ENTRY_ONLY`** (red team). The planner admits any traversal that is safe at
  the entry instant — the classic "check the hazard layer when you turn onto the
  road" error — and prefers it when it promises an earlier arrival.

**The audit is always full-interval, whatever the admission policy.** Under
`ENTRY_ONLY`, the planner produces a plan, and then the audit reports what
actually happens to it. Nothing in this package ever reports success for a plan
that spends an instant on an unsafe element; the
`success.{ingress,egress}_is_safe` invariant enforces that independently.

Fixture G measures the difference on one five-node network:

| policy | feasible dispatch set | what happens at t ∈ [5, 14] |
|---|---|---|
| `FULL_INTERVAL` | `[0, 20]` | declines the fast road, takes the long way, succeeds |
| `ENTRY_ONLY` | `[0, 4] ∪ [15, 20]` | takes the fast road, is caught mid-segment at t = 20 |

Ten dispatch minutes, lost by driving into the fire rather than by declining the
mission. The hole in the entry-only feasible set is manufactured entirely by the
wrong semantics.

## Closure semantics

- **Windows are closed.** `closes_at(T)` means safe at exactly `T`, unsafe for
  every instant after. See `TIME_SEMANTICS.md` for why (D-002).
- **Reopening is supported and is not an edge case.** It is the mechanism behind
  the only *intrinsic* non-monotonicity in the model (fixture F).
- **Node closure** applies at every instant the node is occupied. Passing through
  a junction is instantaneous; standing at an address for a pickup is not.
- **Destination dwell**: arriving at `z` requires the destination node to be safe
  throughout `[z, z + min_safe_dwell]`. A refuge that is reachable but does not
  hold is not a completed mission (D-009).

## Probabilistic interpretation

A **coherent scenario** is one deterministic, internally consistent story about
the fire: a full assignment of timelines to corridors and nodes. Deterministic
work comes first; uncertainty is represented by a small, hand-authored
**ensemble** of such scenarios with weights summing to one.

```
P_success(t) = Σ_i w_i · S(t, m_i)
```

where `S(t, m_i) ∈ {0, 1}` is whole-mission success in scenario `i`.

### Why this package refuses to multiply edge probabilities

Giving each edge an independent survival probability and multiplying along a
route is the obvious alternative. It is wrong here, for three reasons:

1. **Hazard is correlated.** The wind shift that closes one corridor closes its
   neighbours minutes later. Independence understates joint failure — and joint
   failure is precisely the case that kills a responder mid-mission.
2. **Missions reuse elements.** Fixture C traverses the same corridor twice, at
   different times. Under an independent-edge product the two traversals would
   be treated as two separate coin flips of the same road. They are not.
3. **The quantity would not mean anything.** `S(t, m)` is a property of the whole
   mission under one fire. A product of edge terms is not the probability of
   anything an operator could act on.

Fixture `b_ensemble` demonstrates the correct calculation on numbers anyone can
check:

```
nominal     (w=0.5): succeeds for t ≤ 30
wind_shift  (w=0.3): succeeds for t ≤ 30
south_flank (w=0.2): succeeds for t ≤ 15

P_success(t) = 1.0   for t ≤ 15
             = 0.8   for 16 ≤ t ≤ 30
             = 0.0   for t ≥ 31
```

`T(q=1.0) = [0, 15]`; `T(q=0.8) = [0, 30]`. The threshold is the operator's risk
appetite, made explicit.

### What the weights are not

Hand-authored sensitivity dials (A-006). They are not calibrated, not
frequencies, and not forecasts. An ensemble of three scenarios says "here are
three coherent futures worth considering and roughly how much we weight them",
and `P_success = 0.8` means "the mission works in the scenarios carrying 80% of
our weight" — nothing more.
