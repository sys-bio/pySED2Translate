# pbg/research

Environment of the recorded results: Python 3.13, process-bigraph 1.8.5, bigraph-schema 1.7.0, numpy 2.2.6, tellurium 2.2.13.1
(libroadrunner 2.10.0), copasi-basico 0.87, cobra 0.32.1, viva-tellurium 0.1.2, viva-copasi 0.1.2; Linux x86_64; run 2026-10-09.
Run each from this folder.

| Script | Run | Result recorded |
|---|---|---|
| `wrap1.py` | `pip install viva-tellurium==0.1.2` then `python wrap1.py` | `TelluriumUTCStep` requested tolerances 1e-3 / 1e-2, integrator has 1e-12 / 1e-06; `TelluriumProcess` applies them; Gillespie selected but the seed is not applied (W-1) |
| `wrap2.py` | `pip install viva-copasi==0.1.2` then `python wrap2.py` | `start_time`, `relative_tolerance`, `method` accepted and ignored (W-2, W-3); SBML text refused (W-4); two successive updates give different end values (W-10) |
| `pbg2py.py` | library: the prototype scheduler exporter (process-bigraph document -> plain Python script, reading `start` or `event`) | see `exp9.py` |
| `exp9.py` | `PYTHONPATH=. python exp9.py` | Intervals 1/1: export agrees with process-bigraph under both readings.  Intervals 1/2: agrees under `start`, differs under `event` (t = 4: x 0.15625, y 0.140625 against 0.25, 0.25) |
| `make_tier_c.py` | `PYTHONPATH=. python make_tier_c.py` | Writes `../tests/native/` (cases C1, C2) |
| `loopsteps.py`, `loopsteps2.py` | imported by the above | Stand-in steps and processes (Double, Carry, LoopHost, P1, P2) used in the clock-form experiments and the tier C documents |
| `realfba.py` | `python realfba.py PATH/iAF1260.xml ...` | Loads and solves each SBML-FBC model.  iAF1260: 2382 reactions, growth 0.7367, 0.3 s first solve |

`decay.xml` is the one-species model used by `wrap2.py`.
