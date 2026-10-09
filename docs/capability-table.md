# Backend capability table

`src/pysed2translate/capabilities/capabilities.json` records what each backend can do, keyed by task `_type`
and then backend.  `capabilities.schema.json` describes the format, and `load_table()` validates the file.

```json
"jacobianFull": {
  "roadrunner": { "supported": true, "check": "jacobian" },
  "copasi":     { "supported": true, "check": "jacobian" },
  "opencor":    { "supported": false, "reason": "libopencor does not expose a Jacobian" }
}
```

| Field | Meaning |
|---|---|
| `supported` | Default verdict. |
| `reason` | Required when `supported` is false; shown to the user. |
| `deferred` | True when the task is out of scope for now (stochastic tasks), not impossible. |
| `verified` | False while the entry is an expectation not yet confirmed by running the backend.  Absent means verified. |
| `note` | Free text. |
| `conditions` | List of `{"when": {"path": [values]}, "supported": bool, "reason": str}`, checked in order; the first whose paths all match (dotted paths into the task's JSON; a missing attribute is null) decides. |
| `check` | Name of a function in `capabilities/checks.py` (`f(task_json, backend) -> reason or None`) for cases `conditions` cannot express.  Called only if no condition matched and `supported` is true. |

When a backend cannot perform a task, the translator raises `UnsupportedTaskError(backend, task, reason)` and the
command line exits with status 11, which test runners report as a skip with that reason.  Nested tasks
(`subTasks` of a Loop, Scatter or ParameterScan) are checked too.

Rules kept by the unit tests:

* every concrete task class in libsed2 has an entry for every backend, so adding a task type to libsed2 fails
  the tests until each backend's support is recorded;
* the table has no entries for task types libsed2 does not know;
* the stochastic tasks are listed as deferred.

The test suite records which backends produced each test's canonical results (`backends` in `settings.json`).
If this table says a backend cannot run a test it previously produced results for, that is a failure of the
table, not a skip.  Every implemented task has been run against analytic results on each backend that claims it (tests/test_backends.py,
test_steady_state.py, test_repeats.py, ...), so no entry is marked `verified: false` now; use that flag again for any
expectation added without a run.  The checks in `checks.py` are: `ode_simulation` (algorithm and solver settings),
`steady_state`, `jacobian`, `model_change` (no addElements/replaceElements), `repeat` (no aggregates), `csv_import`.

Outputs (`report`, `plot2D`, `plot3D`) are written by generated Python and are not backend dependent, so they
have no entries.

## Backends for kinds of work (flux balance analysis)

The table lists four backends: the dynamic simulators roadrunner, COPASI and OpenCOR, and `cobra` (COBRApy), which does
flux balance analysis only.  Two optional top-level maps connect them:

* `kinds`: task `_type` -> kind of work (`ode`, `steady`, `jacobian`, `fba`);
* `serves`: kind -> the backends that belong to it (`fba` -> `cobra`; the other kinds -> the three simulators).

A task is checked against the backend that performs it, found by `CapabilityTable.backend_for(type, default, overrides)`: the
backend named for its kind (`-b fba=cobra:scipy`), else the default backend if it serves the kind, else the only backend that does
(so `-b roadrunner` on a document with a FluxBalanceAnalysis runs that task on cobra), else the default, which the table then
refuses with its reason (`-b cobra` on an ODE task: "cobra ... does not integrate differential equations").

A backend name may carry a variant after a colon: `cobra:glpk` or `cobra:scipy` choose the LP solver.  On the command line:

```
pysed2translate X.sed2.json -b roadrunner                     # ODE on roadrunner, FBA on cobra
pysed2translate X.sed2.json -b copasi -b fba=cobra:scipy      # a different solver for one kind
pysed2translate X.sed2.json -b cobra:glpk                     # a document with FBA only
```

The generated script names the backend of such a task where it is called (`rt.backends.get('cobra:scipy').fba(...)`); scripts
that use one backend are unchanged.  The suite runner runs a case whose only simulation work is FBA on `cobra` by default.

The FBA model must use the SBML FBC package (an objective and flux bounds); otherwise the script exits with status 11 and
"the model does not use the SBML FBC package".  Bounds are parameters, so ModelChange can set them
(`R_EX_glc__D_e_lower_bound`); give each reaction its own bound parameters if one is to change without the others, as COBRApy
does for non-default bounds.
