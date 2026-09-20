# Temporal resolution

> **Finding of the v0.1 audit.** The dispatch-grid sweep can miss feasible
> windows entirely. It is not a rounding error: a feasible set of positive
> width can be reported as empty. The repository now ships an exact,
> discretization-free solver, and every sampled result carries its resolution.

---

## 1. Where discretization enters — and where it does not

It is worth being precise, because only one of these is sampled:

| step | discretized? |
|---|---|
| evaluating one mission at one dispatch time `t` | **No.** Arrival times are exact sums; hazard checks are exact interval comparisons at `EPS = 1e-9` min. |
| the state search over `(node, time)` | **No.** Reachable times are exact sums of travel times; see `ENUMERATION_COMPLETENESS.md`. |
| `P_success(t)` at a given `t` | **No.** A weighted sum of exact booleans. |
| **sweeping `t` over a grid** | **Yes.** This is the only sampling in the pipeline, and it is where the defect lives. |
| `exact_feasible_set` | **No.** Closed-form interval arithmetic. |

So the mission model is exact and the *scan over dispatch times* was not.

## 2. The counterexample: fixture N

```
base --5-- home --5-- shelter,  pickup 2 min
egress corridor passable only on [18.3, 23.4]

egress occupies [t+7, t+12]:
    t + 7  ≥ 18.3  ⟹  t ≥ 11.3
    t + 12 ≤ 23.4  ⟹  t ≤ 11.4

TRUE feasible set:  [11.3, 11.4]   — 0.1 min wide, six seconds
```

A one-minute sweep samples `t = 11` and `t = 12`. Neither is feasible. The
sweep reports **empty**, and it reports it with no transition anywhere on the
grid — so `refine_transitions` has nothing to bisect and cannot help. The
window is not narrowly missed; it is invisible.

```console
$ wg-dispatch sweep n
sampled feasible dispatch set - fixture-n  (threshold q = 1, grid step 1 min)
  .....................
  windows : []
  warning : these windows are SAMPLED at 1 min; a feasible window narrower than
            the step and lying between two samples is invisible to this method
  warning : no sampled dispatch time meets the threshold - which is NOT the same
            as the feasible set being empty

exact feasible dispatch set T_q, q = 1 (no temporal discretization)
  T_q           : [11.3, 11.4]
  components    : 1
  note: the grid found NO feasible dispatch time, but the exact set is
        non-empty - the window is narrower than the grid step
```

A weaker version of the same defect is already present in fixture F, which the
original release shipped: its feasible set is `{0} ∪ [11, 13]`, and the first
component is a **single instant**. The default grid found it only because the
grid happened to start at exactly `t = 0`. A sweep over `[0.5, 20]` would have
reported one component instead of two — and the headline non-monotonicity claim
would have been quietly weakened by an arbitrary choice of grid offset.

## 3. What the repository does about it

Both remedies the audit called for, not one:

**A — detect and refine reliably.** `feasibility/exact.py` computes `𝒯_q` in
closed form, with no sampling, under conditions it checks rather than assumes
(constant travel times, no waiting, simple paths, full-interval admission,
bounded plan and scenario counts). When a condition fails it raises
`ExactSolverUnavailable` and says which one — it never silently degrades to
sampling. `wg-dispatch sweep` runs it by default alongside the grid and
cross-checks the two, reporting any disagreement.

**B — report the resolution and refuse to imply exactness beyond it.** Every
`FeasibleDispatchSet` carries its `resolution` and emits an *unconditional*
warning naming it. The renderer labels the result `SAMPLED`. An empty sampled
result says in as many words that it is not evidence of an empty feasible set.

## 4. Rules for quoting a result

1. **Never quote a grid-derived boundary at finer precision than the grid step.**
   A sweep at 2-minute resolution that says the last feasible instant is 14 has
   established `14 ∈ 𝒯` and nothing about 15. (The exact solver says 15.)
2. **An empty sampled set is not an empty feasible set.** Say "no feasible
   dispatch time was found at 1-minute resolution", or run the exact solver.
3. **`refine_transitions` refines; it does not discover.** Its tolerance
   applies to boundaries the grid already bracketed.
4. **If the exact solver refused, say why.** "Exact solver not applicable
   (entry-only admission)" is a result. "The feasible set is `[0, 4] ∪ [15, 20]`"
   without that qualifier is not.
5. **Choose the grid from the feature size you care about** — and note that in
   general you do not know the feature size in advance, which is the entire
   argument for the exact solver.

## 5. Residual limitation

The exact solver's conditions are not universal. Under entry-time-only
admission, or if node revisits or waiting are ever enabled, `𝒯_q` is no longer
a union of per-plan interval constraints and the solver correctly refuses. In
those cases the only available answers are the sampled sweep and the
brute-force oracle, both of which are pointwise. **Any future feature that
breaks the solver's conditions must ship with an explicit statement that the
feasible set is once again resolution-limited.**
