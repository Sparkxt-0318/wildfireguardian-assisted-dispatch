# Validation

## The strategy

There is no ground truth to compare against — the networks and hazards are
invented. So validation here rests on **five** independent legs, three of which
were added by the v0.1 scientific audit:

1. **Arithmetic.** Every fixture carries a hand calculation that a reviewer can
   check with a pencil, and the suite re-derives the fixture's feasible windows
   and compares them against that arithmetic.
2. **Invariants.** Every mission record is re-checked from scratch against the
   network, the pickup model and the hazard scenario, by code that does not
   share a line with the evaluator.
3. **An independent implementation.** `validation/brute_force.py` re-derives
   every answer by enumerating plans with its own DFS, its own timing
   arithmetic and its own window scanning. It shares no search, timing or
   hazard-assessment code with the main solver, on purpose (D-020).
4. **An exact solver.** `feasibility/exact.py` computes the feasible dispatch
   set in closed form. Where the grid sweep samples, this does not, so the two
   disagreeing is informative rather than mysterious (D-018).
5. **Properties and mutations.** Property-based tests assert *relationships*
   across families of random worlds; mutation testing introduces each defect the
   project claims to defend against and checks the suite rejects it (D-021,
   D-022).

No leg alone is sufficient. Arithmetic catches wrong answers; invariants catch
right answers reached by a route the model does not admit; the oracle catches
answers that are only self-consistent; the exact solver catches answers that are
artefacts of sampling; mutation testing catches tests that assert nothing.

> **Rule.** A fixture's expected windows must be derived from arithmetic, never
> copied from a previous run. Expected values recorded from output validate
> nothing except that the code still does what it did — which is precisely what
> a regression is. `test_fixtures.py` asserts that every fixture carries a
> non-empty hand calculation.

## Running it

```bash
pytest                              # the whole suite
wg-dispatch fixtures --check        # hand calculation + exact solver + oracle
wg-dispatch fixtures --show c       # one fixture's arithmetic in full
python tools/mutation_test.py       # break it on purpose; see what survives
python tools/build_benchmark.py     # regenerate reports/BENCHMARK_V0_1.md
```

`wg-dispatch fixtures --check` performs all three comparisons per fixture: the
sampled sweep against the hand-derived grid windows, the exact solver against
the hand-derived components, and the reference oracle against the main solver
point by point.

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
| `h_north` | staging comparison, near base | nearer is not wider | `[0, 12]` |
| `h_south` | staging comparison, far base | the binding constraint moves | `[0, 15]` |
| `n` | narrow window | a grid sweep can miss a feasible set entirely | exact `[11.3, 11.4]`, **sampled: empty** |
| `n_resolved` | the same, finely sampled | resolution below the feature size | `[11.3, 11.4]` |

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

## Property-based tests

`tests/test_properties.py` generates small random worlds and asserts
relationships rather than values:

- a longer pickup, slower roads, or uniformly earlier hazard can only **shrink**
  the feasible set;
- `p = 0` dominates every positive pickup duration;
- removing all hazard can only enlarge it;
- a hazard-free world reduces to ordinary travel-time arithmetic, checked
  against an independently computed shortest mission duration;
- a disconnected resident or destination is infeasible under **any** hazard;
- adding a positive-weight failing scenario cannot raise `P_success`;
- weights normalise, `0 ≤ P_success ≤ 1`, and it equals the hand-summed weight
  of the succeeding scenarios;
- `sup 𝒯_q` is attained — dispatching at exactly that instant succeeds, and an
  instant later it does not;
- the main solver, the exact solver and the reference oracle agree pointwise.

**Scope discipline.** The monotonicity properties hold only in *closure-only*
worlds and are generated that way. Two tests assert that they genuinely fail
outside that scope — on fixture F, a later dispatch and a *longer* pickup each
turn failure into success. Without those, the property tests would be encoding
the exact error this project exists to refute (D-021, `FAILURE_MODES.md` F-14).

## Boundary semantics

`tests/test_boundary_semantics.py` walks every exact-equality case — closure at
the entry instant, closure at the exit instant, reopening at the entry instant,
a window exactly as long as the traversal, a degenerate window, a pickup ending
exactly as the address is lost, a refuge lost exactly on arrival, availability
endpoints, and dispatch exactly at the feasible-set boundary — and checks each
against the main evaluator **and** the independent oracle, so a convention
implemented inconsistently in the two places cannot pass. Each expectation is
derived from the stated convention, and the consequences are tabulated in
`TIME_SEMANTICS.md` rather than discovered later.

## Mutation testing

`tools/mutation_test.py` introduces, one at a time, the eight defects the
project claims to defend against: entry-only edge safety, product-style
probability aggregation, ignored pickup duration, implicit waiting through
cycles, a deadline emitted from a non-monotone set, silent search-budget
truncation, travel continuing after a mid-edge failure, and an unsafe refuge
accepted as a destination. Results are in `reports/MUTATION_TESTING.md`. A
surviving mutant is a release blocker.

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
  within a scenario and are oracle-conditioned upper bounds (A-008, F-11, F-13).
- That non-monotonicity is common in reality. The fixtures show it is
  *possible*, which is enough to make a single-deadline summary unsound in
  general, and is not enough to say anything about frequency (F-12).
- That the exact solver is exact outside its stated conditions. It refuses
  there, which is a different and weaker guarantee than being right there.
- That the reference oracle is correct. It is *independent*, not authoritative.
  Agreement between two implementations raises confidence; it does not prove
  either one. The hand calculations remain the only external anchor.
