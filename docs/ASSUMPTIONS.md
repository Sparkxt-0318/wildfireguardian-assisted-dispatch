# Assumptions

Every assumption that could change a result, numbered so it can be cited.
An assumption is something we accept without evidence; a *decision* is something
we chose among alternatives — those live in `DECISIONS.md`.

---

### A-001 — Everything is synthetic
The networks, the hazard timelines, the travel times and the pickup durations
are invented to be hand-checkable. No result here describes any real place.
*If violated:* nothing; this is a scope statement. *Related:* `SCOPE.md`, D-016.

### A-002 — One responder, always available at the base
A single responder vehicle, present at the base and ready to depart at any
dispatch time. No crewing, no queueing, no competing calls.
*If violated:* `T` is an upper bound — a real dispatcher cannot take every `t`
in it, because the responder may be elsewhere.

### A-003 — One resident, one pickup
A single mobility-limited resident at a known address, evacuated in one trip.
No capacity constraint, no multi-stop routing.
*If violated:* the problem becomes assignment + scheduling, which is a different
model (`SCOPE.md`).

### A-004 — Pickup durations are scenario parameters, not medical categories
The four durations (2, 5, 10, 15 min) are sensitivity values. They are not
derived from EMS data, are not validated triage categories, and carry no
clinical meaning. Profile names (`p02`…`p15`) are deliberately content-free.
*If violated:* reporting a `p10` result as "a category-3 patient" would be a
fabricated clinical claim.

### A-005 — Hazard is exogenous and deterministic within a scenario
The fire does not respond to the mission, and within one coherent scenario every
timeline is known exactly. Uncertainty lives *between* scenarios, not inside
one.
*If violated:* `S(t, m)` stops being well defined and the ensemble sum loses its
meaning.

### A-006 — Ensemble weights are hand-authored, not calibrated
Weights are sensitivity dials expressing "how much do we weight this future",
not empirical frequencies.
*If violated:* `P_success = 0.8` would be read as a calibrated probability. It is
not. *Related:* `HAZARD_SEMANTICS.md`.

### A-007 — Travel times are constant and FIFO
`τ(e)` depends on the edge alone. No congestion, no evacuation traffic, no
speed reduction in smoke.
*If violated:* mission durations are optimistic, and non-FIFO travel times would
introduce a *second* source of "leave later, arrive earlier" that would confound
the hazard-driven non-monotonicity this project is isolating. *Related:* D-007.

### A-008 — The planner has full foresight within a scenario ⚠
The search knows each scenario's entire hazard timeline in advance, including
reopenings that have not happened yet.

**This is the most consequential assumption in the repository.** It makes every
feasibility result an *optimistic upper bound*: no online dispatcher, working
from a forecast, can do better, and most would do considerably worse. In
particular, the second feasible window of fixture F (`[11, 13]`) is only
exploitable by someone who knows in advance that the corridor will reopen at
t = 18.
*If violated (i.e. in reality):* `T` shrinks, possibly a lot. *Related:*
roadmap R-3.

### A-009 — Dispatch and communication are instantaneous
The responder departs at exactly `t`. No alerting delay, no acknowledgement, no
turnout time.
*If violated:* shift every result later by the omitted delay; the shape of `T` is
unchanged only if the delay is constant.

### A-010 — The resident is present and ready when service starts
The service interval begins at the arrival instant and lasts exactly `p`. The
resident is home, awake, and does not need to be located.
*If violated:* `p` absorbs the difference, which is what the sensitivity sweep
is for.

### A-011 — No fuel, range, or crew-hour constraints
The vehicle can execute any route within the horizon.
*If violated:* long detours (fixture B's valley road, fixture G's long way
round) may not actually be available.

### A-012 — Destinations have unlimited capacity
A qualifying destination always accepts the arrival. `available_from` /
`available_until` model administrative windows, not occupancy.
*If violated:* a destination could be reachable, safe, and still full.

### A-013 — Nodes are points with no transit time
Passing through a junction is instantaneous; there are no turn penalties and no
intersection delay. Occupying a node for a *service* is the only case where node
duration is non-zero.
*If violated:* every route gains time proportional to its junction count.

### A-014 — A caught vehicle is a lost mission, with no partial credit
Being on a segment when its safety is lost ends the mission. The model makes no
claim about survival, injury, or what happens next — only that the mission did
not complete.
*If violated:* nothing in the arithmetic; but do not read `CAUGHT_MID_EDGE` as a
casualty prediction. *Related:* D-003.

### A-015 — One safe destination is as good as another
Destinations are alternatives, distinguished only by arrival time, dwell
requirement, availability window and an explicit tie-break priority. There is no
modelled quality, distance-to-hospital, or suitability.
*If violated:* selection by earliest arrival may pick the wrong place.
