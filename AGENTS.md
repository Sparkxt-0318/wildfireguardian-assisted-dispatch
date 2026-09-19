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

**Agent C's standing rule:** a new semantic claim ships with a fixture that
would fail if the claim were false. "The tests pass" is not evidence; "this
fixture would break if we reverted the decision" is.

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

## Before you commit

```bash
pytest                      # everything
wg-dispatch fixtures --check   # every hand calculation, re-derived
```

Then check the change against this list:

- [ ] Did this change any answer? If so, which fixture proves the new answer?
- [ ] Did it introduce a choice the docs do not state? Add a `D-###` to
      `docs/DECISIONS.md` (and an `A-###` to `docs/ASSUMPTIONS.md` if it is an
      assumption rather than a decision).
- [ ] Does every new policy knob have a documented default?
- [ ] Does any new failure path emit a `FailureReason` and a `HazardConflict`?
- [ ] Is `tasks/CURRENT.md` still true?

## Style

- Canonical time unit is **minutes**, as a float, from the scenario epoch.
- Module docstrings explain *why*, not *what*: the what is readable from the code.
- Determinism is a feature. Iteration order is sorted, tie-breaks are total, and
  two runs of the same scenario produce byte-identical logs.
