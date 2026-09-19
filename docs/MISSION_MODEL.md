# The mission model

```
   responder base  ──ingress──►  resident  ──[pickup]──►  ──egress──►  safe destination
        t                            a         a → a+p                       z
```

Every instant between `t` and `z` belongs to exactly one leg, and every leg's
duration is a quantity taken from the model rather than chosen by the scheduler.
That is what makes the record auditable (`validation/invariants.py`).

## The timeline, leg by leg

| # | Leg | Interval | Duration comes from | Hazard check |
|---|---|---|---|---|
| 0 | **Dispatch** | `[t, t]` | instantaneous | base node safe at `t` |
| 1 | **Ingress** | `[t, a]` | `Σ τ(e)` over `π_in` | `A_e` over each edge's full interval; each intermediate node safe at the instant it is passed |
| 2 | **Arrival at resident** | `[a, a]` | instantaneous | resident node safe at `a` |
| 3 | **Pickup / service** | `[a, a+p]` | the pickup model | resident node safe **throughout** `[a, a+p]` |
| 4 | **Egress** | `[a+p, z]` | `Σ τ(e)` over `π_out` | as leg 1 |
| 5 | **Destination arrival** | `[z, z]` | instantaneous | destination accepts arrival at `z` |
| 6 | **Required dwell** | `[z, z + dwell]` | the destination | destination node safe **throughout** |

There is no leg 7. There is also no gap between any two legs: consecutive log
entries abut exactly, which the `log.contiguous` invariant enforces.

## Service starts on arrival

`PickupModel.window(a) == (a, a + p)`. The service does not start "when
convenient" — it starts at the arrival instant. Any other rule is waiting, and
waiting is prohibited in phase 1 (D-004).

This is the leg where node hazard actually bites: the responder and the resident
are both stationary at the address for `p` minutes. A node closure that a
passing vehicle would never notice is fatal here, and it gets its own failure
reason, `SERVICE_WINDOW_UNSAFE`.

## Pickup durations

Four scenario values: **2, 5, 10, 15 minutes**, exposed as profiles `p02`,
`p05`, `p10`, `p15`.

> These are scenario parameters. They are **not** validated medical or triage
> categories, they are not derived from any EMS dataset, and they must never be
> reported as if they were (A-004). The profile names are deliberately
> content-free for that reason.

Their effect is exactly one-for-one on the dispatch envelope when the binding
constraint is on the egress leg — fixture D pins that: `t ≤ 30 − p`.

## Destinations

A `Destination` is more than a node id:

- `min_safe_dwell` — how long the place must **remain** safe after arrival.
  This is the difference between a shelter and a temporary refuge. With
  `min_safe_dwell = 0`, a model will happily report success for a mission that
  ends with the resident parked in front of the fire (fixture E).
- `available_from` / `available_until` — administrative availability, independent
  of hazard. Both constraints apply.
- `priority` — a tie-break only; it never overrides arrival time.

A mission may declare several destinations. They are alternatives, not a
preference ordering: the mission succeeds if **any** of them qualifies.

## Route selection

Among all qualifying plans, the evaluator takes:

1. earliest destination arrival `z`;
2. then higher destination `priority`;
3. then destination node id, then the edge sequences, lexicographically.

Steps 3 exist for determinism, not for realism: two runs of the same scenario
must produce byte-identical logs, or the fixtures prove nothing (D-011).

Note what selection does **not** optimise: hazard margin. Fixture E shows the
consequence — the near refuge is chosen while it qualifies, even though the
durable shelter would leave more slack. Margin-aware selection is roadmap item
R-4; it would change answers, so it is not a silent improvement.

## Branching over arrival times

The evaluator does **not** take the earliest arrival at the resident and move
on. It enumerates every distinct arrival time at the resident's address and
evaluates the rest of the mission from each.

This is not caution — it is correctness. With reopening hazards an earlier
arrival does not dominate a later one: the pickup ends earlier, so the egress
leg starts earlier, so it may land *inside* a closure window instead of after
it. The number of branches is capped by
`MissionPolicy.max_resident_arrivals` (default 64).

## What is recorded

Every evaluation returns a `MissionResult` carrying at minimum:

```
dispatch_time  ingress_route  resident_arrival_time  pickup_start  pickup_end
egress_route   destination_arrival  mission_success  failure_reason
hazard_conflict
```

plus the destination node, the mission duration, the tightest hazard margin on
the whole mission, the policy it was produced under, and the minute-by-minute
log. A failing mission fills in everything it got to before it failed —
`SERVICE_WINDOW_UNSAFE` still reports the ingress route and the arrival time,
because that is what makes the failure diagnosable.
