# What "complete enumeration" means here

The v0.1 audit flagged the word *complete* as used without stated conditions.
This document states them. The word is now used only as **"complete under the
conditions in §3"**, and the code says so at the point of use.

---

## 1. Is time continuous or discretized?

**Time is continuous.** `t` is a real number of minutes; hazard windows have
real endpoints; arrival times are real.

What is finite is not time but the set of *reachable* times. The search
enumerates `(node, time)` states, and under the phase-1 conditions only
finitely many such states exist — not because time was sampled, but because
only finitely many times are reachable at all.

This distinction matters. A sampled search would have a resolution; this one
does not. Its limitation is different and is documented in §5–§8.

## 2. What creates candidate time states?

Exactly two operations advance the clock (D-004):

```
edge traversal:   t  ↦  t + τ(e),     τ(e) > 0
pickup service:   t  ↦  t + p
```

so every reachable time at a node is

```
t_start  +  Σ (travel times along the chain used to get there)
```

— a sum of plan constants. **Nothing else creates a candidate time.** In
particular the hazard timelines do *not*: the search never proposes "arrive at
the instant this corridor reopens", because doing so would require waiting.

## 3. Under what conditions is enumeration complete?

Complete — meaning *every reachable `(node, time)` state is generated exactly
once, and no reachable state is pruned* — under all of:

1. **`G` is finite.**
2. **`τ(e) > 0` for every edge**, enforced at construction (`Edge.__post_init__`).
3. **`τ` does not depend on time** (`ConstantTravelModel`, D-007).
4. **No waiting** (`WaitingPolicy.PROHIBITED`, D-004).
5. **Each leg is a simple path** (`allow_node_revisits = False`, D-005) — *or*,
   with revisits allowed, a finite horizon `H`, which bounds chain length by
   `H / min_e τ(e)`.
6. **The state count stays under `max_states`.** Exceeding it raises
   `SearchBudgetExceeded`; it never truncates (D-013).

Under (1)+(5) the number of chains per leg is the number of simple paths, which
is finite (though exponential in the worst case). Under (1)+(2)+(6) with
revisits allowed it is finite but far larger. Either way the reachable state
set is finite and the search visits all of it.

**Sketch.** Each expansion strictly increases the clock by at least
`min_e τ(e) > 0`, so no chain revisits a state and no cycle repeats a time.
De-duplication is keyed on `(node, quantized time)` when revisits are allowed,
and on `(node, quantized time, visited-set)` when they are not — the visited set
is part of the state precisely because two chains reaching the same node at the
same instant admit *different continuations* when node reuse is forbidden.
Dropping it from the key would be a silent incompleteness, and it was a
deliberate design point rather than an optimisation.

## 4. Can infinitely many states arise?

Not under §3. Remove condition (5) *and* the horizon and the answer becomes
yes — a cycle can be traversed unboundedly often, generating an unbounded
increasing sequence of arrival times. This is why the horizon is mandatory
rather than advisory, and why it is documented as a *budget, not a finding*
(`HORIZON_EXCEEDED` ranks below every hazard-based failure reason).

## 5. What happens under reopening hazards?

This is the case that rules out the obvious optimisation. With a reopening
corridor, **earliest arrival is not a dominant label**: arriving at a node
earlier ends the pickup earlier, starts the egress earlier, and can land it
*inside* a closure window that a later arrival would have cleared. So the
classical "settle each node once at its earliest arrival" argument fails, and
using it would silently convert feasible missions into infeasible ones.

The search therefore keeps *every* distinct arrival time, and the mission
evaluator branches over *every* distinct arrival time at the resident's
address, up to `max_resident_arrivals` (default 64). Enumeration is complete;
the branch cap is the one place where a practical bound could in principle bite,
and it is a named policy field rather than a magic number.

Note what completeness here does **not** buy. The search is complete over plans
*given the dispatch time*. Completeness over dispatch times is a separate
question, answered by the exact interval solver rather than by this search —
see `TEMPORAL_RESOLUTION.md`.

## 6. What happens if travel time becomes time-dependent?

Condition (3) fails, and two things change:

- **Reachable times stay finite** if `τ(e, ·)` is deterministic and piecewise
  constant, so the enumeration argument survives in form.
- **The exact interval solver breaks.** Its whole basis is that a plan's
  offsets `c_i, e_k` are constants; with time-dependent `τ` they are functions
  of `t`, the constraints stop being interval translations, and
  `exact_feasible_set` correctly refuses (it checks `isinstance(travel,
  ConstantTravelModel)`).
- **Non-FIFO travel would introduce a second, hazard-free source of "leave
  later, arrive earlier"**, which would confound the non-monotonicity result
  this phase exists to isolate (D-007, A-007).

Any future time-dependent travel model must therefore state its FIFO status and
must re-open the question of what replaces the exact solver.

## 7. What happens if waiting is introduced later?

Condition (4) fails, and the finiteness argument fails with it: a wait may in
principle end at *any* real instant, so `(node, time)` becomes a continuum.

The standard repair is available and should be stated now so it is not
reinvented badly: it suffices to restrict wait-until instants to the **hazard
breakpoints** — the finitely many window endpoints `α_j, β_j` of the elements
the plan will use — since feasibility is piecewise constant between them.
Waiting to any other instant is dominated by waiting to the next breakpoint.
With that restriction the state set is finite again and enumeration is complete
under a restated condition (4′).

Two further consequences, already recorded in D-004: a wait must appear in the
mission log as its own leg with its own node-hazard assessment over the whole
wait interval, and the exact interval solver must be re-derived or retired,
because a plan's offsets would no longer be constants.

## 8. Summary of the honest phrasing

- ✅ "The search enumerates every reachable `(node, time)` state under the
  conditions in `ENUMERATION_COMPLETENESS.md` §3."
- ✅ "Complete over plans for a *given* dispatch time."
- ❌ "Complete search." (Complete over what? under what conditions?)
- ❌ "Exhaustive." (Not over dispatch times — that is the exact solver's job,
  and only within *its* stated conditions.)
