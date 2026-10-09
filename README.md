# pySED2Translate
A translator from SED2 to a python script, using libSED2.

## Usage

```
pysed2translate 00001.sed2.json --backend roadrunner -o 00001.py
python 00001.py --input-dir . --output-dir results/
```

See `docs/generated-script-contract.md` for exit codes and what the generated script reads and writes, and `build.md` for the project plan.  Setup: `scripts/setup_env.sh` (or `.ps1`), then `pip install -e . --no-deps` inside the environment.  The libsed2 wheel is not on PyPI; put it in this directory.

## Status

Backends: roadrunner (tellurium), COPASI (basico) and OpenCOR (libopencor with sbml2cellml); flux balance analysis runs on COBRApy (`cobra`, `cobra:glpk`, `cobra:scipy`).  The translator handles constants, reports, calculations and data manipulation, ModelImport, explicit, one-step and bounded ODE simulations, SteadyState, JacobianFull and JacobianReduced, FluxBalanceAnalysis, ModelChange (`setValues`, `removeElements`), ModelElementList, the repeats (Scatter, Loop, ParameterScan), CsvImport, and the data behind Plot2D and Plot3D (pictures with matplotlib).  A task a backend cannot perform is refused with a reason and exit status 11 (the capability table is in `src/pysed2translate/capabilities`, see `docs/capability-table.md`).  What is waiting for the SED2 specification, and the choices made where it is silent, are in `docs/deferred.md`; simulator problems are logged in `sed2-test-suite/disagreements.json`.

All 273 semantic cases of sed2-test-suite run through the suite runner:

```
python -m pysed2translate.suite_runner --crosscheck      # every case on every backend, and the backends against each other
```

The tests are described in `docs/testing.md`.

