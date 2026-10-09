# Tier C: process-bigraph documents with translated scripts

Each case has: `NAME.pbg.composite.json` (the document), `NAME.case.json` (end time, watched stores, modules to import),
`NAME.script_start.py` / `NAME.script_event.py` (plain Python translated from the document by the prototype exporter
`../../research/pbg2py.py`; two readings of the scheduling rule), `NAME.expected_framework.json` (rows from process-bigraph 1.8.5),
`NAME.expected_start.json`, `NAME.expected_event.json` (rows from the scripts).  Regenerate with `research/make_tier_c.py`.
The documents refer to `loopsteps2.P1/P2`; put `research/` on `PYTHONPATH` to run them.

| Case | Result |
|---|---|
| `c1_equal_intervals` | framework = `start` = `event` |
| `c2_unequal_intervals` | framework = `start`; `event` differs (see `upstream/P-3.md`) |
