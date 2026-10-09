# Tier C: process-bigraph documents with translated scripts

Each case has: `NAME.pbg.composite.json` (the document), `NAME.case.json` (end time, watched stores, modules to import),
`NAME.script_start.py` / `NAME.script_event.py` (plain Python translated from the document by the scheduler exporter
`../../tools/pbg2py.py`, never written by hand; two readings of the scheduling rule), `NAME.expected_framework.json` (rows from
process-bigraph 1.8.5), `NAME.expected_start.json`, `NAME.expected_event.json` (rows from the scripts).  The process classes are
in `procs.py` (next to the documents; the documents refer to `procs.P1` and so on).  Regenerate everything with
`python ../../tools/make_tier_c.py` (needs process-bigraph 1.8.5; roadrunner and cobra for C3 and C5).  `test_tier_c.py` also checks
that the committed scripts are what the exporter writes now.

| Case | What it pins down | Result |
|---|---|---|
| `c1_equal_intervals` | Jacobi coupling: both processes read the start-of-interval state | framework = `start` = `event` |
| `c2_unequal_intervals` | stale read of the slower process | framework = `start`; `event` differs (see `upstream/P-3.md`) |
| `c3_ode_fba_processes` | an ODE process and an FBA process, equal intervals (the Spatio-Flux pattern) | framework = `start`; compared with the sequential Loop, which differs in the stated way |
| `c4_step_reads_process` | a Step reading a process output | framework = `start` |
| `c5_cosimulation_clock` | the clock-form document the engine writes for suite case 00282, exported with its Steps only | report files of the engine and of the exported script agree |

The exporter's `start` reading is the framework's behaviour; `event` is the reading of the specification text.
