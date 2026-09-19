# Validation

## The strategy

There is no ground truth to compare against — the networks and hazards are
invented. So validation here rests on two independent legs:

1. **Arithmetic.** Every fixture carries a hand calculation that a reviewer can
   check with a pencil, and the test suite re-derives the fixture's feasible
   windows and compares them against that arithmetic.
2. **Invariants.** Every mission record is re-checked from scratch against the
   network, the pickup model and the hazard scenario, by code that does not
   share a line with the evaluator.

Neither leg alone is sufficient. Arithmetic catches wrong answers; invariants
catch right answers reached by a route the model does not admit.

> **Rule.** A fixture's expected windows must be derived from arithmetic, never
> copied from a previous run. Expected values recorded from output validate
> nothing except that the code still does what it did — which is precisely what
> a regression is. `test_fixtures.py` asserts that every fixture carries a
> non-empty hand calculation.

## Running it

```bash
pytest                          # 153 tests
wg-dispatch fixtures --check    # every hand calculation, re-derived
wg-dispatch fixtures --show c   # one fixture's arithmetic in full
```

## The fixtures

| Key | Fixture | What it pins down | Expected `T` |
|---|---|---|---|
| `a` | single road | the basic deadline subtraction | `[0, 15]` |
| `b` | two routes, one closes earlier | feasibility follows the *surviving* route | `[0, 30]` |
| `b_ensemble` | three coherent scenarios | `P_success` as a weight sum | `[0, 15]` at q=1, `[0, 30]` at q=0.8 |
| `c` | inbound vs outbound conflict | the outbound traversal binds | `[0, 14]` |
| `d` | pickup sensitivity | on-scene time comes off one-for-one | `[0, 30 − p]` |
| `e` | temporary refuge | reached ≠ evacuated | `[0, 39]` |
| `f` | non-monotonic feasibility | the set has a hole | `{0} ∪ [11, 13]` |
| `g` | mid-edge closure | an unclearable segment is never entered | `[0, 20]` |
| `g_myopic` | entry-time-only admission | what the wrong semantics costs | `[0, 4] ∪ [15, 20]` |

### Worked example — fixture C

```
approach  : [t,     t+10]   base -> junction
spur in   : [t+10,  t+18]   junction -> home      (corridor 'spur')
pickup    : [t+18,  t+23]
spur out  : [t+23,  t+31]   home -> junction      (corridor 'spur', reversed)
exit      : [t+31,  t+37]   junction -> shelter

the spur is lost at t = 45; the binding traversal is the OUTBOUND one:
    t + 31 ≤ 45   ⟹   t ≤ 14

t† = 45 − (10 + 8 + 5 + 8) = 14
```

The inbound-only answer would be `t + 18 ≤ 45`, i.e. `t ≤ 27`. Thirteen minutes
of fiction, every one of which strands the responder and the resident on a
dead-end spur. The test asserts both the correct answer and that the computed
supremum is below the naive one.

## The invariants

Run by `validation/invariants.py` over every dispatch time of every fixture, in
both `test_invariants.py` and `wg-dispatch fixtures --check`.

**Time accounting**
- the first log entry starts exactly at the dispatch time;
- consecutive entries abut exactly — no gap, no overlap;
- no entry runs backwards.

**No implicit waiting**
- each `travel` entry lasts exactly its edge's travel time;
- each `service` entry lasts exactly the pickup duration;
- `dispatch`, `arrival` and `abort` entries are instantaneous;
- a `travel_aborted` entry is truncated at the instant safety was lost, and is
  never longer than the edge;
- no `wait` entry exists at all.

**Route chaining**
- every recorded traversal's endpoints match the network's;
- each traversal starts where the previous one ended, and when it ended;
- no node is visited twice on a leg (unless the policy allows it).

**Full-interval coverage**
- every recorded traversal is re-assessed against the scenario from scratch, and
  its recorded `safe_throughout` must match;
- a *successful* mission must have all-safe ingress and egress routes and a safe
  service window. This is the check that would catch full-interval auditing
  being bypassed anywhere.

**Record consistency**
- a success carries no failure reason, no hazard conflict, and every field
  filled in, with a pickup window matching the model and a destination that
  accepts the arrival;
- a failure carries a reason and no destination arrival.

### Negative tests

Invariants that never fail are decorative. `test_invariants.py` tampers with
genuine results and asserts the checks catch it:

- shifting the second half of a log by five minutes → `gap or overlap`;
- stretching a service entry by three minutes → `pickup model` mismatch;
- inserting a `wait` entry → `prohibits waiting`;
- re-auditing a real success against a harsher scenario → `safe_throughout`
  mismatch.

## Boundary refinement

Grid sweeps locate a transition only to within one grid step.
`refine_transitions` bisects each observed flip to any tolerance; fixture F's
three boundaries are confirmed at 0, 11 and 13 to within 0.01 min.

This assumes feasibility flips at most once per grid cell — a statement about
grid resolution, not about monotonicity. If that is in doubt, sweep finer
(`F-8` in `FAILURE_MODES.md`).

## What validation here does *not* establish

- That the model resembles any real road network or fire (A-001).
- That the feasible sets are achievable in practice — they assume full foresight
  within a scenario and are upper bounds (A-008, F-11).
- That non-monotonicity is common in reality. The fixtures show it is
  *possible*, which is enough to make a single-deadline summary unsound in
  general, and is not enough to say anything about frequency (F-12).
