# Project context

## What this repository is

A research kernel for one question: **when can a responder be sent to collect a
resident who cannot self-evacuate, and still complete the whole mission before
the fire closes the route?**

It is deliberately small. It contains a synthetic road-graph model, a
synthetic time-varying hazard model, a mission evaluator, a dispatch-time
feasibility calculator, seven hand-checkable fixtures, and a command line tool.
It contains no fire physics, no real geography, and no operational system
integration.

## Why it exists separately from evacuation routing

Standard evacuation routing answers: *given a hazard field, what is the safest
or fastest way out for the people who can move?* It is a one-directional,
one-shot problem, and its answer degrades gracefully — leave earlier, do better.

Assisted dispatch is a different problem:

1. **It is a round trip with a service stop in the middle.** The responder goes
   *towards* the hazard, stops for a measurable period, and comes back out. The
   same corridor often carries both directions, at different times, with the
   pickup duration sitting between them. Fixture C shows the inbound-only answer
   being wrong by thirteen minutes on a trivial network.

2. **Its timing is the decision, not an input.** For self-evacuation the
   question is "which way?". Here it is "at what time may we start?" — the
   route follows from the dispatch time, not the other way round.

3. **Its answer is not a deadline.** Because hazard fields reopen and refuges
   expire, the set of workable dispatch times can have holes in it. Fixture F
   is a two-edge network whose feasible set is `{0} ∪ [11, 13]`. Every
   single-number summary of that set is a false statement about part of it.

4. **Failure is not graceful.** A self-evacuee who leaves late arrives late. A
   responder who enters a segment that closes mid-traversal is on a burning road
   with a mobility-limited passenger. The model must therefore be pessimistic
   about commitment, and explicit about it.

## What "synthetic phase" means

Every number in this repository was chosen so that a reader can check it by
hand. Travel times are round minutes. Closures are single instants. Fixtures
have five nodes, not five thousand. This is not a stepping stone towards a
"realistic" version of the same code — it is the stage at which the *semantics*
get settled, so that when real data eventually arrives, the questions "what does
this model do when a road closes halfway across?" and "what does `P_success`
mean?" already have written answers.

Concretely, the phase-1 exit criteria were: a working deterministic evaluator,
explicit time-dependent edge behaviour, a computed dispatch-time set, at least
one non-monotonic example, working scenario ensembles, working pickup
sensitivity, passing hand-calculable fixtures, detailed failure reasons, and
complete documentation. All of them are met; see `tasks/COMPLETED.md`.

The kernel was then put through an adversarial scientific audit before being
frozen as `v0.1.0`. The audit found three defects — a grid sweep that could
miss feasible windows entirely, a wrong predicate for "dispatch by X", and a
silent truncation in arrival branching — all fixed, each with a test that would
fail if the fix were reverted. `reports/V0_1_SCIENTIFIC_AUDIT.md` has the full
account, including what survived and under what assumptions.

## How the pieces fit

```
                     ┌──────────────┐
  synthetic graph ──►│              │
                     │  evaluator   │──► MissionResult  (full timeline,
  hazard scenario ──►│              │                    failure reason,
                     └──────┬───────┘                    hazard conflict)
                            │
                            ▼ once per dispatch time, per scenario
                     ┌──────────────┐
                     │  P_success   │──► T = { t : P_success(t) ≥ q }
                     └──────┬───────┘
                            │
                            ▼
                    monotone?  ── yes ──► t† = sup T is meaningful
                        │
                        no ──► report the windows; refuse the single deadline
```

## Who reads what

- **Someone new**: `README.md`, then `RESEARCH_QUESTION.md`, then
  `MISSION_MODEL.md`.
- **Someone who needs the formal object**: `MATHEMATICAL_SPECIFICATION.md`.
- **Someone implementing**: `HAZARD_SEMANTICS.md` and `TIME_SEMANTICS.md`, then
  `DECISIONS.md` for anything that looks arbitrary — it probably is not, and
  `ENUMERATION_COMPLETENESS.md` for what the search does and does not promise.
- **Someone reviewing a result**: `CLAIMS.md` first, then `ASSUMPTIONS.md`,
  `ORACLE_FEASIBILITY_LIMIT.md`, `TEMPORAL_RESOLUTION.md` and
  `FAILURE_MODES.md`. The second half of `FAILURE_MODES.md` is a list of ways
  this project itself could mislead you.
- **Someone about to quote a number**: `CLAIMS.md` and
  `ORACLE_FEASIBILITY_LIMIT.md`, without exception.
- **Someone extending it**: `AGENTS.md` and `tasks/ROADMAP.md`.
- **Someone auditing it**: `reports/V0_1_SCIENTIFIC_AUDIT.md`, then
  `reports/BENCHMARK_V0_1.md` and `reports/MUTATION_TESTING.md`.
