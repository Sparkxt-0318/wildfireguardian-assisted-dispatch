# Experiments

Runnable studies. Nothing here is required by the library or the test suite; it
exists so that the headline results can be regenerated in one command and
inspected as tables and figures.

## Layout

```
experiments/
  configs/                  declarative studies (YAML)
    ridge_study.yaml        a fully-specified config, no fixture shortcut
    reopening_corridor.yaml the non-monotonic study, written out
    pickup_pressure.yaml    a fixture shortcut with an override
  run_phase1_study.py       regenerates every phase-1 result
  output/                   generated; not tracked
```

## Regenerating the phase-1 results

```bash
python experiments/run_phase1_study.py
```

Writes into `experiments/output/`:

- `fixture_<key>_sweep.parquet` (or `.csv` without pyarrow) — one row per
  dispatch time per scenario;
- `fixture_<key>_feasibility.png` — the two-panel feasibility figure, when
  matplotlib is installed;
- `pickup_sensitivity.csv` — fixture D across 2/5/10/15 minutes;
- `summary.md` — every fixture's expected and computed feasible windows side by
  side, plus the headline findings.

The script fails loudly if any fixture disagrees with its hand calculation, so
it doubles as an end-to-end check.

## Running a config directly

```bash
wg-dispatch sweep experiments/configs/reopening_corridor.yaml --refine
wg-dispatch evaluate experiments/configs/ridge_study.yaml --dispatch-time 15
wg-dispatch pickup-sweep experiments/configs/pickup_pressure.yaml
```

Any command that accepts a config path also accepts a fixture key
(`wg-dispatch sweep f`), so no file is needed to reproduce a fixture.

## Adding a study

1. Write the arithmetic first — what do you expect, and why?
2. Put the config in `configs/`, with the derivation in a leading comment.
3. If the study establishes a new semantic claim, it belongs in
   `src/.../fixtures/` with a test, not only here (see `AGENTS.md`).
