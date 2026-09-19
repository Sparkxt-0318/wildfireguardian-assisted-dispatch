# wildfireguardian-assisted-dispatch

Mathematics and computational foundation for **assisted wildfire evacuation
missions**: the case where a resident cannot self-evacuate and a responder has
to go and get them.

> **Synthetic phase.** Everything in this repository is synthetic. Synthetic
> road graphs, synthetic hazard-time fields, synthetic timings. There is no
> real wildfire model here, no real Korean road network, and no integration
> with WildfireGuardian routing. See [docs/SCOPE.md](docs/SCOPE.md).

## The research question

> For a mobility-limited resident, **at what dispatch times** can a responder
> complete the entire mission
>
> ```
> responder base  ->  resident  ->  (pickup)  ->  safe destination
> ```
>
> under time-varying hazards?

This is not ordinary evacuation routing. Ordinary routing asks "can this person
get out?". This asks whether a *round trip with a service stop in the middle*
survives a hazard field that is moving while the trip is happening — and it
answers with a **set of dispatch times**, not a single deadline.

## Three results this project exists to make unavoidable

**1. A hazard check at the entry instant is not a hazard check.**
The availability operator `A_e([t_in, t_out], m)` is evaluated over the *whole*
traversal interval. A segment that is safe when you turn onto it and unsafe
before you come off it is a segment that kills the mission. Fixture G measures
exactly what the entry-only shortcut costs: ten dispatch minutes that look
feasible and are not.

**2. Later is sometimes better.**
Feasibility is **not** monotone in dispatch time. Fixture F is a two-road
network whose feasible dispatch set is `{0} ∪ [11, 13]` — dispatch at t = 5 and
the mission fails; dispatch at t = 12, seven minutes later, and it succeeds,
with no waiting anywhere. Any summary of the form "leave before t†" is a false
statement about that set, so `latest_dispatch()` raises rather than produce one.

**3. Uncertainty is a set of coherent fires, not a product of edge
probabilities.**
`P_success(t)` is the total weight of the hazard scenarios in which the whole
mission completes. Nothing in this package ever multiplies per-edge survival
probabilities: wildfire hazard is correlated in space and time, and that
product systematically understates joint failure.

## Install and run

```bash
pip install -e ".[dev]"      # pyarrow + matplotlib are optional extras
pytest                       # 153 tests, all of them arithmetic you can check
```

```bash
wg-dispatch fixtures --list           # the seven synthetic fixtures, A-G
wg-dispatch fixtures --check          # re-derive every hand calculation
wg-dispatch fixtures --show c         # one fixture's arithmetic, in full

wg-dispatch evaluate a --dispatch-time 0      # one mission, minute by minute
wg-dispatch sweep f                           # the feasible dispatch set
wg-dispatch sweep f --out results.parquet     # ...and the table behind it
wg-dispatch pickup-sweep d                    # sensitivity to on-scene time
wg-dispatch plot-feasibility results.parquet --out feasibility.png
```

Any command that takes a config file also takes a fixture key, so nothing needs
a YAML file to be reproducible.

```console
$ wg-dispatch sweep f
feasible dispatch set - fixture-f  (threshold q = 1, grid step 1 min)

  ---------------------
  #..........###.......
  t = 0          t = 20

  legend: '#' feasible   '.' infeasible
  windows : [[0, 0], [11, 13]]
  monotone: False
  sup T   : 13 (NOT a valid latest-dispatch summary)
  warning : feasibility is NOT monotone in dispatch time: it is regained after
            being lost (1 gap(s): [(0, 11)]). A single latest-dispatch summary
            is invalid here.
```

## A mission record

Evaluation never returns a bare boolean. Every dispatch time produces a full
record — `dispatch_time`, `ingress_route`, `resident_arrival_time`,
`pickup_start`, `pickup_end`, `egress_route`, `destination_arrival`,
`mission_success`, `failure_reason`, `hazard_conflict` — plus a minute-by-minute
log in which *every* minute is either travel or declared service:

```console
$ wg-dispatch evaluate g_myopic --dispatch-time 6
mission G-mid-edge-entry-only | scenario coherent | dispatch t=6 | FAILED (caught_mid_edge)
  policy: admission=entry_only, waiting=prohibited, revisits=prohibited, horizon=120 min
     6.00 -    6.00  dispatch base           responder dispatched from base
     6.00 -   10.00  travel   base->home     clear
    10.00 -   10.00  arrival  home           responder reaches the resident
    10.00 -   12.00  service  home           pickup, 2 min (p02)
    12.00 -   20.00  travel_aborted home->shelter  segment safety lost at t=20, 2 min short of the far end
    20.00 -   20.00  abort    home->shelter  mission ends here: the segment became unsafe mid-traversal and there is no modelled escape
  hazard conflict: [egress] responder and resident caught on home->shelter at t=20: entered at 12, would have cleared at 22
```

## Repository map

| Path | What lives there |
|---|---|
| `src/.../network/` | synthetic directed road graphs, corridors, travel model |
| `src/.../hazards/` | timelines, coherent scenarios, ensembles, `A_e([t_in,t_out],m)` |
| `src/.../missions/` | mission spec, policies, evaluator, mission records |
| `src/.../service/` | the pickup model and its four scenario durations |
| `src/.../search/` | complete time-expanded state search |
| `src/.../feasibility/` | `P_success(t)`, the set `T`, monotonicity, sensitivity |
| `src/.../scenarios/` | declarative YAML/JSON configs, parquet/CSV output |
| `src/.../fixtures/` | the synthetic fixtures A-G, each with its hand calculation |
| `src/.../validation/` | invariants and hand-calculation checking |
| `src/.../cli/` | `wg-dispatch` |
| `docs/` | the context system — read `PROJECT_CONTEXT.md` first |
| `tasks/` | roadmap, current work, completed work |
| `experiments/` | runnable studies and their configs |

## Documentation

Read in this order:

1. [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md) — what this is and why
2. [`docs/RESEARCH_QUESTION.md`](docs/RESEARCH_QUESTION.md) — the question, formally
3. [`docs/SCOPE.md`](docs/SCOPE.md) — what is deliberately not here
4. [`docs/MISSION_MODEL.md`](docs/MISSION_MODEL.md) — the timeline, leg by leg
5. [`docs/HAZARD_SEMANTICS.md`](docs/HAZARD_SEMANTICS.md) — `A_e`, closures, ensembles
6. [`docs/TIME_SEMANTICS.md`](docs/TIME_SEMANTICS.md) — units, boundaries, waiting
7. [`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md) — every assumption, numbered
8. [`docs/DECISIONS.md`](docs/DECISIONS.md) — every modelling decision, numbered
9. [`docs/VALIDATION.md`](docs/VALIDATION.md) — how any of this is known to be right
10. [`docs/FAILURE_MODES.md`](docs/FAILURE_MODES.md) — how missions fail, and how *this project* could
11. [`docs/GLOSSARY.md`](docs/GLOSSARY.md) — terms

## Status

Phase 1 (deterministic kernel + small ensembles) is complete: see
[`tasks/COMPLETED.md`](tasks/COMPLETED.md) for what is done,
[`tasks/CURRENT.md`](tasks/CURRENT.md) for what is being worked on, and
[`tasks/ROADMAP.md`](tasks/ROADMAP.md) for what comes next.

**Do not integrate real WildfireGuardian routing yet.**
