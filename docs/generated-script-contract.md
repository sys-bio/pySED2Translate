# Generated-script contract

What a script produced by `pysed2translate` promises, and what it expects.

## Command line of the translator

```
pysed2translate FILE --backend {roadrunner,copasi,opencor} [-o OUT.py] [--prefix P]
                [--input-dir DIR] [--output-dir DIR] [-v|-q]
```

Without `-o` the script goes to standard output.  Exit status:

| Code | Meaning |
|---|---|
| 0 | Script written. |
| 2 | Bad command line. |
| 10 | The SED2 document is unreadable or invalid.  Each libsed2 error is listed with its rule id and location. |
| 11 | The chosen backend cannot perform a task in the document.  The message names the backend, the task and the reason.  A test runner reports this as a skip, not a failure. |
| 12 | Any other translation error. |

Warnings from libsed2 validation are logged but do not stop translation.

## The script

* Needs Python 3.13, numpy, the `pysed2translate` package (for `pysed2translate.runtime`), and the chosen
  simulator.  It does not need libsed2.
* **Inputs.** `location` values in the document are resolved against `--input-dir`.  The default is the
  directory containing the script, unless the translator was given `--input-dir`, which becomes the default.
* **Outputs.** Result files are written to `--output-dir` (default: the current directory, unless the translator
  was given `--output-dir`), created if needed.  Names are `<prefix>.<id>.<ext>`:
  * `<prefix>.<report_id>.csv`, or `.h5` for data with three or more dimensions
  * `<prefix>.<plot_id>_as_data.csv` (Plot2D) or `.h5` (Plot3D)
  * `<prefix>.<plot_id>.png` when matplotlib is available and pictures are enabled (`--no-png` turns them off; the
    `_as_data` files are always written).  A picture that cannot be drawn is reported on stderr and does not fail the plot.

  The prefix is the document's file name up to `.sed2.json` (`00001.sed2.json` gives `00001`), or `--prefix`.
  The formats are those of sed2-test-suite's `docs/FORMATS.md`.
* **Manifest.** `--manifest FILE` also writes a JSON file `{"reports": {id: {file, format, ndim, dtype, labels}},
  "plots": {id: {file, format, type}}}` describing what the script wrote, in the shape of a case's `settings.json`
  entries.  The suite runner uses it to record first results (`--promote`).
* **Determinism.** The script text depends only on the document, the backend and the options.  It contains no
  timestamps, no translator version and no absolute paths unless `--input-dir`/`--output-dir` were given.
  Two runs of the translator on the same input give identical text.  Random draws use a fixed seed unless the
  document says otherwise.
* **Exit status of the script.** 0 on success; non-zero if a simulation or an output failed.
