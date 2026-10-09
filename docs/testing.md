# Testing

## Unit tests, golden scripts, coverage

```
python -m pytest                                  # all tests (about 10 minutes; roadrunner, COPASI and OpenCOR are used)
python -m pytest tests/test_golden.py             # only the golden scripts (a few seconds)
python -m pytest --cov --cov-report=term-missing  # with a coverage report
```

* Needs `libsed2` (wheel), `sed2-test-suite` next to this folder (or `SED2SUITE_TOOLS` pointing at its `tools`
  folder) and, for the simulator tests, roadrunner, basico and libopencor (see `docs/environment-notes.md`).
  A test whose simulator is not installed is skipped.
* The generated scripts run in subprocesses.  `[tool.coverage.run] patch = ["subprocess"]` makes coverage measure
  the runtime code they execute as well, so the figures cover `runtime/` properly.  Coverage writes one data file per
  process and combines them at the end, which deletes files; on a folder where deleting is not allowed, point
  `COVERAGE_FILE` at another directory.  Splitting the run into several `--cov-append` runs works the same way.
* Figures at the time of writing: 599 tests (the coverage figures below were measured at 584 tests and not repeated), 95% line and branch coverage (`tasks_sim.py` 97%, `core.py` 92%,
  `runtime/ops.py` 91%).  What is not covered is mostly defensive error branches.

## Golden scripts

`tests/golden/docs/*.sed2.json` are documents chosen so that every task and output type the translator handles
appears in at least one (a test checks that).  `tests/golden/scripts/` holds the exact script generated for each
document and backend, or `NAME.BACKEND.skip.txt` with the translator's reason when the backend cannot run it.
`tests/test_golden.py` fails with a diff when the output changes.  When the change is intended:

```
python scripts/update_golden.py --check     # what is out of date
python scripts/update_golden.py             # rewrite the files, then review the diff
```

## The suite runner

`pysed2translate.suite_runner` translates each case of `sed2-test-suite`, runs the script, and compares the files it
writes with the case's expected results.

```
python -m pysed2translate.suite_runner                         # every semantic case, every backend
python -m pysed2translate.suite_runner 00003 -b copasi         # chosen cases and backends
python -m pysed2translate.suite_runner --crosscheck            # also compare the backends with one another
python -m pysed2translate.suite_runner --log-draft             # print draft entries for disagreements.json
python -m pysed2translate.suite_runner 00007 --promote roadrunner    # first results of a new case, from a backend
```

Each cell of the matrix is PASS, FAIL, SKIP (the translator says the backend cannot do it) or ERROR; a star marks a
backend that the case's `settings.json` records as having produced canonical results.  The rule for those: the
translator must support them, so "unsupported" there is a FAIL.  The exit status is 1 if anything is FAIL or ERROR.

`--promote BACKEND` writes the results of the run into the case folder (refusing to replace existing result files
without `--force`), creates `NNNNN.settings.json` if the case has none, and records the backend and its version
in it.  A case whose results are worked out by hand should have them checked against the promoted ones and then
be marked `"source": "analytical"` in `provenance`.

Differences between backends, or between a backend and the expected results, that are not obvious from the output
go into `sed2-test-suite/disagreements.json` (format in that repository's `docs/FORMATS.md`): test, backends, size,
diagnosis (solver setting, translator bug, simulator bug, spec ambiguity), resolution.
