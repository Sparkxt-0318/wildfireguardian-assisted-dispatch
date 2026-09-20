# Time semantics

## Units

The canonical unit is the **minute**, as a `float`, measured from the scenario
epoch `t = 0`. There is no wall-clock, no date, no timezone.

Minutes rather than seconds because hand-checkable fixtures are the primary
validation instrument in this phase, and `40 − 10 − 5 − 10 = 15` is a
calculation a reviewer does in their head (D-008).

All time comparisons go through `units.py` with `EPS = 1e-9` minutes. That
tolerance guards against float dust in sums of fixture constants; it is not a
modelling parameter and nothing in the model varies on that scale.

## The boundary convention

**Safety windows are closed intervals `[start, end]`, and `end` is the last safe
instant.**

- `closes_at(25)` → safe at exactly `t = 25`, unsafe for every `t > 25`.
- `closed_between(12, 18)` → unsafe on the *open* interval `(12, 18)`; safe at
  both endpoints.
- A traversal over `[t_in, t_out]` is admissible under full-interval semantics
  iff some window `W` satisfies `W.start ≤ t_in` and `t_out ≤ W.end`.

Why closed rather than half-open (D-002): fixture deadlines then read as
`arrival ≤ T` instead of `arrival < T`, which keeps the arithmetic in the
fixtures checkable without a footnote on every line. Because these hazards are
synthetic step functions, the difference between the two conventions is a
measure-zero set of instants and carries no physical content — but it must be
stated once and obeyed everywhere, which is what `hazards/timeline.py` is for.

### Consequences, stated rather than discovered

The v0.1 audit tested every exact-equality case
(`tests/test_boundary_semantics.py`) against both the main evaluator and the
independent oracle. These are the consequences of the convention. None of them
was chosen to make a test pass; each follows from "`end` is the last safe
instant".

| case | outcome | why |
|---|---|---|
| edge closes exactly at the **exit** instant | **safe**, margin 0 | `[t_in, t_out] ⊆ [α, β]` holds with `t_out = β` |
| edge closes exactly at the **entry** instant | **caught mid-edge** (degenerate) | safe at entry, unsafe an instant later; under the default policy it is simply never entered |
| corridor **reopens** exactly at the entry instant | usable | `t_in = α` is inside the window |
| safe window exactly as long as the traversal | usable | equality is allowed at both ends |
| **degenerate** window `[α, α]` | cannot carry any positive-duration traversal | and *can* carry a zero-duration occupancy |
| pickup ends exactly as the address is lost | **safe** | the service interval is closed |
| refuge lost exactly on arrival, `min_safe_dwell = 0` | **success** | uncomfortable, and exactly why D-009 exists |
| same refuge with any positive dwell | failure | the dwell interval extends past `β` |
| destination `available_until` exactly equal to arrival | accepted | availability endpoints are inclusive |

Two structural consequences follow, and both are asserted as tests:

- **A mission can succeed with exactly zero margin.** Fixture A at `t = 15`
  clears the corridor at exactly `t = 40`. The record reports `margin = 0`,
  which is honest about how much slack a real operation would have — namely
  none.
- **The feasible dispatch set is closed**, so when it is non-empty and bounded
  its supremum is *attained*: the last feasible dispatch instant is itself
  feasible. This is checked for every fixture and over random generated worlds
  (`tests/test_properties.py`), and it is what makes `last_feasible_instant` a
  usable quantity rather than an open bound.

## Waiting

**Phase 1 prohibits waiting.** `WaitingPolicy.PROHIBITED` is the only
implemented policy; any other value raises `WaitingNotImplementedError` at
construction rather than being silently ignored.

The mission clock therefore advances by exactly two things:

- edge traversal, for `τ(e)` minutes;
- pickup service, for `p` minutes.

Everything else is instantaneous. This is enforced after the fact, not merely
intended: `validation/invariants.py` checks that consecutive log entries abut
exactly, that each `travel` entry lasts exactly its edge's travel time, that
each `service` entry lasts exactly the pickup duration, and that no `wait` entry
exists at all. Those checks run over every dispatch time of every fixture in the
test suite.

### If waiting is ever added

It must be (D-004):

1. **explicit** — a decision the planner makes, never a side effect of a
   scheduling rule;
2. **located at a node from a declared allow-list** — "wait anywhere" is not a
   model, it is an escape hatch;
3. **visible in the mission log** as its own leg, with its own node-hazard
   assessment over the whole wait interval.

Anything less re-introduces implicit waiting through the back door, and every
timestamp in the record stops being a sum the reader can check.

### Waiting by driving

A subtler loophole: if a leg may revisit a node, the responder can drive
`base → home → base → home` purely to burn ten minutes until a corridor reopens.
No instant is idle, so a naive "no waiting" check passes — and the model has
waiting in it anyway.

So each leg is a **simple path** by default
(`MissionPolicy.allow_node_revisits = False`, D-005). The option to allow
revisits exists, and when it is enabled the resulting plans must be read as
hold-by-circulation; the `simple_path` invariant enforces the default.

This is a real constraint with a real cost: it rules out legitimate routes that
must pass one junction twice. On the five-node synthetic networks of this phase
that cost is zero, and the alternative — silently permitting waiting in a model
that advertises no waiting — is not acceptable.

Note that a *loop-free* detour that simply takes longer is still available, and
is a legitimate source of non-monotonicity. The rule forbids revisiting places,
not spending time.

## Horizon

`MissionPolicy.horizon` (default 8 hours, fixtures use 2–3) is the clock time
after which the mission is abandoned. It bounds the time-expanded search, which
would otherwise circulate forever in a cyclic network.

It is a **budget, not a finding**. `HORIZON_EXCEEDED` is ranked below every
hazard-based failure reason when the evaluator decides which failure to report,
so a branch that ran out of clock never outranks a branch that hit an actual
closure.

Similarly, exhausting `max_states` raises `SearchBudgetExceeded` rather than
returning "no route found". A truncated search reporting infeasibility is the
single most dangerous silent failure this package could have (D-013).

## Grid resolution

Dispatch sweeps sample `T` on a grid. `FeasibleDispatchSet.intervals` is
therefore a statement about the *sampled* grid, accurate to `resolution`.

`feasibility/refine.py` bisects each observed feasibility transition to any
tolerance, which is how the fixtures confirm boundaries to 0.01 min. The
bisection assumes only that feasibility does not flip more than once inside a
single grid cell — a statement about grid resolution, not about monotonicity of
the whole set.
