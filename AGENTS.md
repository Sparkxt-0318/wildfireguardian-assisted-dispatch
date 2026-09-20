# Working agreement for agents on this repository

This project is a research kernel whose only product is *trustworthy claims
about dispatch feasibility*. A fast implementation that quietly hides a
modelling decision is worth less than no implementation at all. Everything
below follows from that.

## The three roles

Work on this repository is organised as three roles. One person or agent may
play several of them, but **not in the same commit**: the whole point is that
the specification, the implementation and the attack are written by different
mindsets.

### Agent A — Mission / Hazard Auditor

Owns the semantics. Produces and maintains:

- the **mission timeline** — every leg, every instant that belongs to it, and
  which quantity accounts for it (`docs/MISSION_MODEL.md`);
- **edge hazard semantics** — the operator `A_e([t_in, t_out], m)`, evaluated
  over the whole traversal interval, and what happens when safety is lost
  mid-traversal (`docs/HAZARD_SEMANTICS.md`);
- **waiting semantics** — whether the responder may hold, where, and how it
  must appear in the log (`docs/TIME_SEMANTICS.md`, D-004, D-005);
- **closure semantics** — closed-interval convention, reopening, node closure,
  refuge dwell (`docs/TIME_SEMANTICS.md`, D-002, D-009);
- the **probabilistic interpretation** — coherent scenarios, weights, what
  `P_success` does and does not mean (`docs/HAZARD_SEMANTICS.md`, D-001).

Agent A's deliverable is prose plus numbered decisions and assumptions. Agent A
does not need the code to compile; Agent A needs the semantics to be stated
before anyone implements them.

**Agent A's standing rule:** if the implementation had to *choose* something the
docs do not state, that is an Agent A bug, not an implementation detail.

### Agent B — Implementation Engineer

Owns routing, evaluation and search. Implements exactly what Agent A specified,
and surfaces anything the specification did not cover rather than inventing it.

- Every policy that changes an answer is a named field on `MissionPolicy` with
  a default and a docstring saying why that default.
- Every result carries the policy it was produced under.
- Search is **complete**, not greedy: a later arrival can be the only feasible
  one (see `search/time_expanded.py`), and running out of budget raises rather
  than returning "infeasible".
- No silent fallbacks anywhere. A missing optional dependency says so; a
  truncated search says so; an unknown config key is an error.

### Agent C — Red Team

Owns the attack. Constructs networks with known answers and adversarial timing,
and tries to make the kernel lie. Current red-team fixtures:

- `c` — a corridor used in reverse, where the inbound check gives a comfortable
  and completely wrong answer;
- `f` — a reopening corridor that makes feasibility non-monotone, so that any
  single-deadline summary is false;
- `g_myopic` — entry-time-only admission, which reports a plan right up until
  the audit and then reveals a responder caught mid-segment;
- `e` — a refuge that is reachable but does not hold, so "arrived" and
  "evacuated" come apart.

- `n` / `n_resolved` — a feasible window narrower than the sweep step, which the
  grid reports as no window at all;
- `h_north` / `h_south` — the nearer staging point with the *smaller* feasible
  dispatch set.

**Agent C's standing rule:** a new semantic claim ships with a fixture that
would fail if the claim were false. "The tests pass" is not evidence; "this
fixture would break if we reverted the decision" is.

Agent C also owns `tools/mutation_test.py`. A defect the project claims to
defend against, that no test rejects, is a hole in the suite and a release
blocker — not a note for later.

## Non-negotiables

1. **Nothing real.** No real wildfire model, no real road network, no
   WildfireGuardian routing integration in this phase (D-016, `docs/SCOPE.md`).
2. **Full traversal intervals.** Hazard is never evaluated only at the entry
   instant (D-003).
3. **No implicit waiting.** Time advances only by travel and by declared
   service. Driving in circles counts as waiting and is prohibited by default
   (D-004, D-005).
4. **The answer is a set.** `T = {t : P_success(t) ≥ q}`. A single `t†` is a
   summary that is only emitted when the set is monotone (D-006).
5. **Scenario by scenario.** Never multiply independent per-edge probabilities
   (D-001).
6. **Hand-checkable fixtures.** Every fixture carries arithmetic a reviewer can
   verify with a pencil. Expected values copied from a previous run are
   forbidden (`docs/VALIDATION.md`).
7. **Detailed failures.** "Infeasible" alone is never an acceptable output. A
   failing mission reports where, when, and against which hazard.
8. **Claim discipline.** `docs/CLAIMS.md` is binding on every output — code,
   plots, reports, commit messages, conversation. The prohibited list ("safe
   route", "guaranteed rescue", "operational dispatch recommendation",
   "validated Korean rescue deadline", "lives saved", "real-world probability
   of survival") is not negotiable (D-023).
9. **The oracle qualifier travels with the result.** Every feasible set here is
   an *oracle feasibility envelope* / *physical feasibility upper bound*, never
   an operating envelope (A-008, `docs/ORACLE_FEASIBILITY_LIMIT.md`).
10. **Nothing is "complete" without its conditions.** Use "complete under the
    conditions in `ENUMERATION_COMPLETENESS.md` §3", or do not use the word
    (D-024).
11. **No silent truncation, anywhere.** Every budget raises. The v0.1 audit
    found one that did not — arrival branching — and it now raises too.

## Before you commit

```bash
pytest                             # everything
wg-dispatch fixtures --check       # hand calculation + exact solver + oracle
python tools/mutation_test.py      # a surviving mutant is a release blocker
python tools/build_benchmark.py --write   # if any fixture or answer changed
```

Then check the change against this list:

- [ ] Did this change any answer? If so, which fixture proves the new answer?
- [ ] Did it introduce a choice the docs do not state? Add a `D-###` to
      `docs/DECISIONS.md` (and an `A-###` to `docs/ASSUMPTIONS.md` if it is an
      assumption rather than a decision).
- [ ] Does every new policy knob have a documented default?
- [ ] Does any new failure path emit a `FailureReason` and a `HazardConflict`?
- [ ] Is `tasks/CURRENT.md` still true?
- [ ] Does any new answer agree with the **independent oracle** and the
      **exact solver**, or is there a stated reason one does not apply?
- [ ] Does any new claim appear in `docs/CLAIMS.md`, or is it prohibited there?
- [ ] If the change touches a budget or a cap: does it raise rather than
      truncate?
- [ ] If the change breaks a condition of the exact solver, does the code refuse
      rather than fall back to sampling, and does the documentation say the
      result is resolution-limited again?

## Style

- Canonical time unit is **minutes**, as a float, from the scenario epoch.
- Module docstrings explain *why*, not *what*: the what is readable from the code.
- Determinism is a feature. Iteration order is sorted, tie-breaks are total, and
  two runs of the same scenario produce byte-identical logs.
