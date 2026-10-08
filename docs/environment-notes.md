# Environment notes

* The `libroadrunner` wheel links `libpython3.13.so` dynamically.  On Linux with a uv-managed Python, set
  `LD_LIBRARY_PATH` to Python's lib directory (`scripts/setup_env.sh` writes `<venv>/env.sh` to do this; source it
  after activating the environment).  Windows is not affected.
* OpenCOR (`libopencor`) default solver tolerances are too loose for suite comparisons.  Set them explicitly in
  generated scripts (CVODE absolute 1e-12, relative 1e-10; see `scripts/smoke_test.py`).  Every backend's solver
  tolerances are set explicitly, never left at defaults.
* The libsed2 wheel is not on PyPI.  Put `libsed2-<version>-py3-none-any.whl` in this directory (it is
  git-ignored); `scripts/setup_env.sh` installs the newest one.  Current: 0.1.1 (rebuilt 2026-10-08; the version number did not change, so
  reinstall with `--force-reinstall`).
* roadrunner 2.10: the `rk45` integrator returns wrong values at fixed output points, and there is no Euler
  integrator; the variable-step last row (BoundedODESimulation) is interpolated and less accurate, so the backend
  recomputes the end point on its own.
* roadrunner reports `steadyState()` as a residual and raises `RuntimeError` when it fails; the backend also
  rejects a residual above 1e-6.  Its Jacobians are concentration-based.
* COPASI (basico): `get_jacobian_matrix` labels the full Jacobian in the model's species order but the matrix is in
  COPASI's state order (independent species, then dependent ones), so the labels can be wrong; the backend names the
  rows from the state template.  The Jacobian uses relative steps: basico's factor 1e-12 loses about 5e-5, so the
  backend uses 1e-6, and a variable whose value is exactly 0 gets a derivative of 0 (the backend refuses instead).
  COPASI's Jacobian is amount-based; the backend converts to SBML-id units.  The steady-state task is run with
  Resolution 1e-12 and negative concentrations accepted (as roadrunner does).
* libopencor 0.20261006.1: `SedSteadyState` cannot be used from Python.  Without an ODE solver, running it reports
  "requires an ODE solver"; with one set (any), `SedDocument.instantiate()` segfaults the interpreter, even for a
  one-variable hand-written CellML model.  The capability table marks steadyState unsupported for opencor.  Reported upstream: https://github.com/opencor/libopencor/issues/604.
  libopencor exposes no Jacobian.
* The value of a model element by label (`#tasks:m1.model['S1']`) is read with libroadrunner for every backend: the
  model travels between tasks as SBML text carrying its state (the end state of the last simulation, and the time it
  ended), and that text is loaded into roadrunner to read one element.  A script for COPASI or OpenCOR therefore
  needs libroadrunner when it uses such a reference.  COPASI could answer natively after a run (basico `get_value`),
  but cannot be given a time; libopencor can only report values of a run that integrated for a positive time (a
  zero-length run returns zeros), so it cannot answer for a model that was never simulated.  Species are read as
  `[id]` (concentration) unless they have `hasOnlySubstanceUnits`, and every other element (compartment, parameter,
  reaction, stoichiometry) by its plain id.  A pending event or a delay in the model is not carried in the state.
