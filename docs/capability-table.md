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
| `deferred` | True when the task is out of scope for now (flux balance analysis, stochastic tasks), not impossible. |
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
* the flux balance and stochastic tasks are listed as deferred.

The test suite records which backends produced each test's canonical results (`backends` in `settings.json`).
If this table says a backend cannot run a test it previously produced results for, that is a failure of the
table, not a skip.  Every implemented task has been run against analytic results on each backend that claims it (tests/test_backends.py,
test_steady_state.py, test_repeats.py, ...), so no entry is marked `verified: false` now; use that flag again for any
expectation added without a run.  The checks in `checks.py` are: `ode_simulation` (algorithm and solver settings),
`steady_state`, `jacobian`, `model_change` (no addElements/replaceElements), `repeat` (no aggregates), `csv_import`.

Outputs (`report`, `plot2D`, `plot3D`) are written by generated Python and are not backend dependent, so they
have no entries.
