# Mathematical specification

This document defines the object this repository computes, and — just as
importantly — the two *neighbouring* objects it does **not** compute.

---

## 1. Primitives

| symbol | meaning |
|---|---|
| `G = (V, E)` | a finite directed road network |
| `τ : E → ℝ_{>0}` | traversal time of an edge, in minutes, **independent of time** |
| `b ∈ V` | responder base (staging location) |
| `r ∈ V` | the mobility-limited resident's address |
| `D ⊆ V` | declared safe destinations |
| `p ≥ 0` | pickup / on-scene service duration, in minutes |
| `t ∈ ℝ` | **dispatch time** — the decision variable |
| `H` | planning horizon, in minutes from the scenario epoch |

### Hazard scenarios

A **coherent hazard scenario** `m` assigns to every corridor `c` and every node
`v` a *safety timeline*

```
W(x, m) = ⋃_{j=1..n_x} [α_j, β_j],      α_1 ≤ β_1 < α_2 ≤ β_2 < …
```

a finite union of **closed** intervals during which the element may be
occupied. Closedness is the convention of D-002 and is load-bearing throughout
this document; `β` is the *last safe instant*, not the first unsafe one.

Scenarios are deterministic. All uncertainty lives between scenarios.

### Availability operator

For an occupancy of element `x` over the closed interval `[t_in, t_out]`:

```
A_x([t_in, t_out], m) = 1   ⟺   ∃ j :  α_j ≤ t_in  and  t_out ≤ β_j
```

i.e. the whole occupancy interval lies inside a single safe window. Note that
`A` is **not** `𝟙[t_in ∈ W]`; the difference between those two definitions is
the content of fixture G and costs ten dispatch minutes there.

Two derived quantities the implementation also reports:

```
safe_at_entry(x, t_in, m)  =  𝟙[ t_in ∈ W(x, m) ]
safety_lost_at(x, t_in, m) =  β_j   where  t_in ∈ [α_j, β_j]      (if any)
```

---

## 2. Missions and plans

A **plan** dispatched at `t` is a triple `π = (P, Q, d)` where `P` is a path
`b → r`, `Q` is a path `r → d`, and `d ∈ D`. Under the phase-1 policy set
(no waiting, simple paths per leg) the plan's timing is fully determined by `t`:

```
ingress edge i occupies   [t + c_{i-1},      t + c_i]          c_i = Σ_{k≤i} τ(P_k)
resident reached at       A(π)  = t + c_n
service occupies          [A(π),             A(π) + p]         at node r
egress edge k occupies    [A(π)+p+e_{k-1},   A(π)+p+e_k]       e_k = Σ_{l≤k} τ(Q_l)
destination reached at    Z(π)  = A(π) + p + e_m
```

Every offset `c_i, e_k` is a constant of the plan. There is no scheduling
freedom: the clock advances only by `τ` and by `p` (D-004).

**Plan feasibility** `F(π, t, m) = 1` iff all of the following hold:

1. `b` is safe at `t`;
2. `A_{corridor(P_i)}([t+c_{i-1}, t+c_i], m) = 1` for every ingress edge, and
   every intermediate node is safe at the instant it is passed;
3. `A_r([A(π), A(π)+p], m) = 1` — the address is safe for the *whole* service;
4. the same as (2) for every egress edge and node;
5. `available_from(d) ≤ Z(π) ≤ available_until(d)`;
6. `A_d([Z(π), Z(π) + dwell(d)], m) = 1` — the destination *holds*;
7. `Z(π) ≤ H`.

**Scenario feasibility**

```
S(t, m) = max over plans π of F(π, t, m)        ∈ {0, 1}
```

— "does a feasible plan exist". Under the red-team admission policy
`ENTRY_ONLY` this is replaced by a *selection* rule (choose the
earliest-arriving entry-admissible plan, then audit it fully), which is a
strictly different and strictly worse object; see §6.

---

## 3. The scientific object

Given an ensemble `M = {(m_i, w_i)}` with `w_i > 0`, `Σ w_i = 1`:

```
P_success(t | D_s)  =  Σ_i  w_i · S(t, m_i)
```

where `D_s` denotes the **scenario data** the evaluation is conditioned on —
here, the fully specified hazard timelines of the ensemble members. The
feasible dispatch set at risk threshold `q ∈ (0, 1]` is

```
𝒯_q  =  { t : P_success(t | D_s) ≥ q }
```

### Structure of 𝒯_q

**Proposition.** Under the phase-1 conditions (constant `τ`, no waiting, simple
paths, finitely many closed hazard windows), `𝒯_q` is a *finite union of closed
intervals*:

```
𝒯_q  =  ⋃_{k=1..K} [a_k, b_k],        b_k < a_{k+1}
```

*Proof sketch.* For fixed `π`, each condition (1)–(7) constrains `t` to a
finite union of closed intervals — condition (2), for example, gives
`t ∈ ⋃_j [α_j − c_{i-1}, β_j − c_i]`, which is empty for windows shorter than
`τ`. Intersecting finitely many such sets gives a finite union of closed
intervals; `S(·, m)` is the union over the finitely many simple-path plans,
hence also one. Finally

```
𝒯_q = ⋃_{J ⊆ M : w(J) ≥ q} ⋂_{i ∈ J} S(·, m_i)
```

is a finite union of finite intersections of such sets. ∎

Two consequences are used throughout:

- **`𝒯_q` is closed.** Hence when it is non-empty and bounded, `sup 𝒯_q` is
  *attained*: the last feasible dispatch instant is itself feasible. This is
  asserted as a property test over random worlds and over every fixture.
- **`𝒯_q` is computable exactly**, with no time discretization. That is what
  `feasibility/exact.py` does; `ExactFeasibleSet.components` are the `[a_k, b_k]`
  above.

### Why `sup 𝒯_q` is not a deadline

`t† = sup 𝒯_q` is a true statement about the supremum of the set. The sentence
*"dispatch by t†"* is a different and stronger claim:

```
"dispatch by X"   ⟺   [t_min, X] ⊆ 𝒯_q     (every earlier time also works)
```

which holds **iff `K = 1` and `a_1 ≤ t_min`** for the studied range starting at
`t_min`. Fixture F is the standing counterexample: `𝒯_1 = {0} ∪ [11, 13]`, so
`sup 𝒯_1 = 13` while `5 ∉ 𝒯_1`. Reporting "dispatch by 13" asserts that
dispatching at 5 is fine, and it is not.

Two independent mechanisms break `K = 1`:

- **reopening hazard** — a corridor closed by a passing front becomes usable
  again (fixture F);
- **expiring destinations** — a refuge stops qualifying and forces a different,
  longer egress (fixture E).

A third mechanism is *not* a property of the world at all: entry-time-only
hazard semantics manufactures a gap that correct semantics does not have
(fixture `g_myopic`, `𝒯_1 = [0, 4] ∪ [15, 20]` against `[0, 20]`).

Accordingly the API exposes `last_feasible_instant` unconditionally and
`dispatch_by_deadline()` only when the deadline reading is true, raising
`DispatchByDeadlineUndefined` otherwise. See §10 of the task vocabulary in
`GLOSSARY.md`.

---

## 4. Three feasibility notions — only one is implemented

The formula `{t : P_success(t | D_s) ≥ q}` has the same shape in all three cases
below. What differs is what `D_s` is, and therefore what the answer means.

### (a) Physical / oracle feasibility — **what this repository computes**

`D_s` is the *true, fully specified* hazard scenario. The planner is allowed to
use all of it, including the future. The question answered is:

> Ignoring all information limits, was this mission *physically possible* if
> dispatched at `t`?

This is a **physical feasibility upper bound**. It is the right object for
benchmarking, for semantics research, and as an oracle layer other work can be
compared against. It is not something a dispatcher can execute, because nobody
knows `D_s` in advance.

### (b) Forecast-conditioned feasibility — **not implemented**

`D_s` is replaced by a forecast `F_s` available at time `t`, and the planner
may only condition on `F_s`:

```
P_success^forecast(t | F_s) = Σ_i w_i(F_s) · S(t, m_i)
```

with plans required to be measurable with respect to `F_s` (and, realistically,
re-planned as information arrives). This is strictly smaller than (a) in
general: some physically feasible windows are unusable because nothing in the
forecast tells you they exist. `docs/ORACLE_FEASIBILITY_LIMIT.md` works fixture
F through as a concrete instance.

**This repository does not implement (b) and makes no claim about it.**

### (c) Operational dispatch recommendation — **not implemented**

A recommendation additionally requires responder availability and crewing,
competing calls and prioritisation, communications and turnout delay, vehicle
and route practicality, an accountable decision rule under uncertainty, and
validation against real incidents. None of that is modelled here
(`ASSUMPTIONS.md` A-002, A-009, A-011, A-012).

**This repository does not produce dispatch recommendations.** See
`docs/CLAIMS.md` for the wording that is and is not permitted.

---

## 5. What is exact and what is sampled

| quantity | exactness |
|---|---|
| `A_x([t_in,t_out], m)` | exact interval comparison, tolerance `EPS = 1e-9` min |
| `S(t, m)` at a **given** `t` | exact; the evaluator does not discretize time |
| `P_success(t)` at a given `t` | exact weighted sum |
| `𝒯_q` via `exact_feasible_set` | **exact**; closed-form interval arithmetic |
| `𝒯_q` via a grid sweep | **sampled** at the grid step; see `TEMPORAL_RESOLUTION.md` |
| boundary refinement (`refine_transitions`) | bisection to a stated tolerance, and only for transitions the grid already observed |

Never quote a grid-derived boundary at a precision finer than the grid step.
Fixture N exists to make that failure concrete.

---

## 6. The entry-only variant, stated precisely

Under `TraversalAdmission.ENTRY_ONLY` the planner admits any traversal with
`safe_at_entry = 1`, and selects

```
π*(t) = argmin over entry-admissible plans of Z(π)     (ties broken lexicographically)
```

Success is then `F(π*(t), t, m)` — the *selected* plan audited over full
intervals — rather than `max_π F(π, t, m)`. Because it depends on an argmin,
this object is not a union of per-plan interval constraints, and the exact
solver correctly refuses it (`ExactSolverUnavailable`). It is covered instead by
the brute-force oracle, which implements the selection rule directly.

This is why `𝒯_q` under entry-only admission can be a strict subset of `𝒯_q`
under full-interval admission *with the same world*: the planner walks past a
feasible plan into an infeasible one.
