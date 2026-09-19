# The research question

## Informal

> For a mobility-limited resident, at what dispatch times can a responder
> complete the entire base → resident → pickup → safe destination mission under
> time-varying hazards?

## Formal

Let

- `G = (V, E)` be a directed road network, with `τ(e) > 0` the traversal time of
  edge `e` in minutes;
- `m` be a **coherent hazard scenario**: a deterministic assignment of a safety
  timeline to every corridor and every node;
- `b ∈ V` the responder base, `r ∈ V` the resident's address, `D ⊆ V` the set of
  declared safe destinations;
- `p ≥ 0` the pickup (on-scene service) duration;
- `t` the **dispatch time** — the instant the responder leaves the base.

For a traversal of edge `e` entered at `t_in` and left at `t_out = t_in + τ(e)`,
define the availability operator

```
A_e([t_in, t_out], m)
```

which reports whether `e` is safe **at every instant of the closed interval**
`[t_in, t_out]` under `m` — not merely at `t_in`. `HAZARD_SEMANTICS.md` gives its
full definition and its consequences.

A **mission plan** dispatched at `t` is a pair of routes
`(π_in, π_out)` with:

```
π_in  : b → r     entered at t,           arriving at  a = t + Σ τ(e)
service           occupying r over        [a, a + p]
π_out : r → d∈D   entered at a + p,       arriving at  z = a + p + Σ τ(e)
```

with **no idle time anywhere** (`TIME_SEMANTICS.md`, D-004). The plan
**succeeds** under `m` when

1. `b` is safe at `t`;
2. `A_e([·, ·], m)` holds for every edge of `π_in`, and every intermediate node
   is safe at the instant it is passed;
3. `r` is safe throughout the whole service interval `[a, a + p]`;
4. `A_e([·, ·], m)` holds for every edge of `π_out`, likewise for its nodes;
5. `d` accepts an arrival at `z`, and `d` remains safe throughout
   `[z, z + dwell(d)]`.

Define the **deterministic feasibility predicate**

```
S(t, m) = 1  if some plan dispatched at t succeeds under m
          0  otherwise
```

Given a **scenario ensemble** `M = {(m_i, w_i)}` with `Σ w_i = 1`, define

```
P_success(t) = Σ_i  w_i · S(t, m_i)
```

— a weighted count over whole coherent scenarios. **Not** a product over edges
(D-001).

The object this project computes is the **feasible dispatch set**

```
T(q) = { t : P_success(t) ≥ q }
```

for a stated threshold `q ∈ (0, 1]`.

## Why the answer is a set

It is tempting to collapse `T` to

```
t† = sup T
```

and report "dispatch before `t†`". That summary is valid **only when `T` is
downward closed** on the studied range — i.e. when feasibility, once lost, is
never regained.

It is not, in general. Two independent mechanisms break monotonicity:

- **Reopening hazard.** A corridor blocked by a passing flare front becomes safe
  again. A mission dispatched later meets the corridor in its second safe
  window. Fixture F: `T = {0} ∪ [11, 13]`.
- **Expiring destinations.** A refuge that stops qualifying forces a longer
  egress, which can interact with a later closure in either direction
  (fixture E).

A third, avoidable mechanism is **bad hazard semantics**: fixture `g_myopic`
shows entry-time-only admission manufacturing a hole in `T` that full-interval
admission does not have.

Accordingly, `FeasibleDispatchSet.latest_dispatch()` raises
`NonMonotonicFeasibilityError` unless the set is monotone on the studied grid.
`sup T` remains available as `.supremum`, labelled as what it is: a true
statement about the supremum and a false statement about the set (D-006).

## What a positive answer does and does not mean

`t ∈ T(q)` means: **under the stated scenarios, with full foresight of each
scenario's hazard timeline, a plan exists that completes the mission.**

It does not mean an online dispatcher could find that plan. The planner here
knows each scenario's entire future (A-008). That makes every feasibility result
in this repository an **optimistic upper bound** on what is achievable with real
forecasting. Narrowing that gap is future work, not a completed claim.
