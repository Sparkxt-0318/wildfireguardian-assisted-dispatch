# The oracle-foresight limitation

> **One sentence.** Every feasible dispatch set in this repository is computed
> by a planner that already knows the whole future of the fire, so it is an
> **oracle feasibility envelope** — a *physical feasibility upper bound* — and
> not an operating envelope.

This document expands assumption **A-008** into the form it needs before other
repositories (observation-system simulation, forecast value) can connect to
this one.

---

## 1. What the solver is actually given

A coherent scenario `m` is a *complete* description of the hazard over all
time: every corridor's closure, every reopening, every node's overrun, out to
the horizon. The search is handed that object in full and may plan against any
part of it, including parts that lie in the future of the dispatch instant.

So `S(t, m) = 1` means:

> There exists a plan which, **had it been chosen at time `t` by someone who
> already knew `m`**, would have completed the mission.

It does not mean, and must never be reported as meaning:

> A responder dispatched at `t` will complete the mission.
> A dispatcher should send someone at `t`.
> `t` is inside the operating envelope.

## 2. Why this makes the result an upper bound

Any real planner acts on information available at the moment of the decision.
Formally, a realisable policy must be *measurable with respect to the
information filtration* — it may condition only on what is known by then.
The oracle planner has no such restriction. Since the oracle can reproduce any
realisable policy's plan and additionally use future information,

```
𝒯_q^{forecast}  ⊆  𝒯_q^{oracle}
```

for any forecast, always. The gap between them is exactly the quantity a
forecast-value study would try to measure. **This repository computes only the
right-hand side.**

## 3. Fixture F, worked through

Fixture F is a two-road network whose egress corridor is safe on
`[0, 12] ∪ [18, 25]` — a flare front crosses it between 12 and 18, then it is
lost for good at 25.

```
base --5-- home --5-- shelter          pickup = 2 min

dispatch at t:  reach home at t+5, pickup ends t+7, egress occupies [t+7, t+12]

  [t+7, t+12] ⊆ [0, 12]    ⟺  t ≤ 0
  [t+7, t+12] ⊆ [18, 25]   ⟺  11 ≤ t ≤ 13

𝒯_1 = {0} ∪ [11, 13]
```

The second component is **physically real**. A responder dispatched at t = 12
drives continuously, waits nowhere, and delivers the resident at t = 24 on a
corridor that is genuinely safe for the whole traversal. Nothing about that
mission is a modelling artefact.

And yet:

> **To use the window `[11, 13]`, the dispatcher must know at t = 11 that the
> corridor will reopen at t = 18.**

Consider what the decision looks like without that knowledge. At t = 11 the
corridor is shut. Everything observable says the route is gone. Dispatching now
means committing a responder to drive towards a closed road on the expectation
that it will clear in seven minutes — a bet on the future behaviour of a fire
front. If the front is slower than expected and the corridor reopens at 20
rather than 18, the egress leg `[18, 23]` becomes `[18, 23]` against a window
starting at 20, and the mission fails with the responder and the resident at
the address, inside the perimeter, with less time left than when they started.

So the window is:

- **physically feasible** — an oracle can use it;
- **operationally unusable without predictive information** — no realisable
  policy can use it from observation alone;
- **worth quantifying** — how much forecast skill would be needed to convert it
  into a usable window is a well-posed question, and it is precisely the
  question this repository is *not* answering.

The isolated first component, `{0}`, makes the same point more sharply: a
measure-zero set of dispatch times. Physically feasible, operationally
meaningless, and only visible at all because the exact solver does not sample.

## 4. Approved vocabulary

| use | instead of |
|---|---|
| oracle feasibility envelope | operating envelope |
| physical feasibility upper bound | achievable dispatch window |
| oracle-conditioned feasible dispatch set | recommended dispatch times |
| "physically feasible under scenario `m`" | "safe to dispatch" |
| "an upper bound on what any forecast could support" | "the dispatch window" |

The prohibition list in `CLAIMS.md` is binding on all outputs of this
repository, including plots, tables, commit messages and this document.

## 5. What would close the gap

Not in this repository (see `SCOPE.md`), but stated so the interface can be
designed for it:

1. **A forecast object** `F_s` distinct from the truth `D_s`, with a defined
   information-availability time.
2. **A realisability constraint** on plans: measurable with respect to `F_s`,
   with re-planning at defined decision epochs.
3. **A decision rule** under scenario uncertainty — the threshold `q` is
   currently applied to an oracle quantity, which is not the same as a risk
   appetite applied to a forecast.
4. **A regret metric**: `𝒯_q^{oracle} \ 𝒯_q^{forecast}` is the set of dispatch
   times that were physically available and were not taken. That difference is
   the natural output of a forecast-value study, and this repository's job in
   such a study is to supply the first term — exactly, and with its assumptions
   attached.

## 6. Standing instruction

Any result exported from this repository carries the qualifier. A plot title
says *oracle feasibility*; a table caption says *physical feasibility upper
bound*; a number quoted in prose says *under full knowledge of scenario `m`*.
A result that has lost its qualifier has lost its meaning, and at that point it
is a claim about operations that nothing here supports.
