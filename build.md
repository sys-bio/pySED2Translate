**Goals**

There are several goals of this project:

* To create an independent SED2 test suite, at C:\Users\Lucian\Desktop\sed2-test-suite locally, and https://github.com/sys-bio/sed2-test-suite remotely.
* To create a translation library to translate SED2 documents to Python scripts, using the libsed2 python library, the source code of which is at C:\Users\Lucian\Desktop\SED2 locally, and https://github.com/sys-bio/SED2/ remotely.  The latest python wheel will be uploaded to the pySED2Translate directory for manual installation as a convenience, but won't be added to the github repository; the most recent releases will be available at https://github.com/sys-bio/SED2/releases/
* To discover any gaps in the libsed2 library.
* To use the translation library to populate the SED2 test suite with 'canonical' results.
* To compare different simulators to each other to ensure that the test suite works

The SED2 specification is also present in the SED2 project, and should be consulted when necessary.

**The SED2 Test Suite**

This should be modeled after the SBML Test Suite, at C:\Users\Lucian\Desktop\sbml-test-suite locally and https://github.com/sbmlteam/sbml-test-suite remotely.

At the core, we want cases/semantic/ cases/syntactic/ and cases/stochastic.  The syntactic tests will be filled in from the SED2 project later.  The stochastic tests (for stochastic simulations and the DrawFromDistribution task) will also be filled in later.  For now, we'll focus on the semantic tests.

The root directory will also include:
* README.md : A description of the test suite.
* tags.json : A description of the tags used.  Will be split into two categories: 'component' and 'semantic'.  Component tags will just be a complete list of the elements present in the SED2 file.  Semantic tags will be more conceptual in nature, like the 'test tags' in the SBML test suite.  The semantic tags have not yet been determined, and will be developed with this project as new gaps are seen that need to be filled.
* generate_tags.py : a python script that reads a SED2 file and updates (or creates) a description file including the tags of a particular test.  'python generate_tags.py 00001/00001.sed2.json will produce or update 00001/00001.description.md

Each subfolder of the semantic/ folder will be numbered, starting with 00001/.  Inside each folder will be the following files:
* 00001.sed2.json : The SED2 file being tested
* 00001.description.md : A description of the test, plus a list of the component and semantic tags used in the SED2 file, plus any relevant tags from any of the input files (such as sbml:Events or csv:columnHeaders).  Other than 'the component tags in the SED2 file', all other tags will be created on a case by case basis, when it turns out something can't correctly process a particular input file for a particular reason.
* input file(s) : Any files needed as input to the SED2 file (i.e. 00001.sbml, 00001.csv).  Internally we will use antimony to create any SBML input files.  When we do, the antimony file (00001.ant) will also be present in the directory.
* 00001.[report_id].csv : One or more files from 'report' elements in the SED2 file.  Any report with more than two-dimensional output will be in the HDF5 format instead.  A full description of the report format is below.
* 00001.[plot_id].png : Optional illustrations of 'plot' elements in the SED2 file.  Not compared, and not committed unless a test needs one.
* 00001.[plot_id]_as_data.csv (Plot2D) or 00001.[plot_id]_as_data.h5 (Plot3D) : Zero or more files holding the data behind each 'plot' element, as described under Plot-as-data serialization.
* 00001.settings.json : Similar to the settings.txt file in the sbml test suite, containing absolute and relative tolerances, and a map of report and plot IDs to the corresponding files in the directory (i.e. .csv vs. .h5).  In addition, any rules of how results files need to be compared must be included.  This is particularly important for stochastic input, but also important for bounded input that might not include the same intermediate output lines.  It also records which backends produced the canonical results (see 'Creating everything at once').

Every test must include at least one report that produces the output to be compared, and there must be at least one test for every concrete Task in the SED2 specification, other than flux balance analysis and stochastic tasks (for now).  The first tests should have no tasks at all, and simply have constants, and reports that use those constants.

A test can be officially added to the test suite once it validates, runs on every backend the translator reports as able to run it (see pySED2Translate), and all of those backends produce output that agrees to within the given tolerances (|a-e| <= abs + rel*|e|).

**Report serialization**

A report's `data` is always AnnotatedData, so every expected-results file
represents an n-dimensional array plus optional labels on each dimension.
The suite defines the file format; SED2 itself does not.

*Choosing the format.* Data with 0, 1 or 2 dimensions is written as CSV.
Data with 3 or more dimensions is written as HDF5 (.h5).  A report whose
data is not AnnotatedData (for example a bare model) is not valid in this
suite.  The report-id-to-file mapping, the format, and which dimensions
carry labels are recorded in the test's settings.json, so no reader has to
guess.

*CSV rules.*
* UTF-8, LF line endings, comma separator, RFC 4180 quoting.
* A 2-D array is written as rows by columns.  If the column dimension has
  labels, they are written as a header row.  If the row dimension has
  labels, they are written as the first column.  If both exist, the
  top-left cell is empty.
* A 1-D array is treated as a column vector (n rows, one value column).
  Its labels, if any, are the first column.  There is no header row.
* A 0-D array (a single value) is one line containing one value.
* Numbers are written with 17 significant digits (Python repr
  round-trips).  Special values are written as nan, inf and -inf, as in
  the Types spec.  Booleans are written as 1 and 0.
* String data is written as-is, quoted where RFC 4180 requires.  A single
  array may not mix strings and numbers, except for nan, inf and -inf.
* Dimension names (as in xarray) are not stored in CSV.

*HDF5 rules.*
* The file has a dataset named "data" holding the array in row-major
  (C) order: float64 for numbers, UTF-8 variable-length strings for strings.
* For each dimension i that has labels, a dataset "labels/<i>" holds the
  labels in order.  A dimension with no labels has no such dataset.
* The root attribute "dims" lists the dimension names, or empty strings
  if unnamed.

*Comparison rules.*  Reader code normalizes either format to an array plus
a list of labels per dimension, then checks:
* Same shape, and identical labels in identical order.  String labels
  must match exactly.  Numeric labels (such as time values) use the
  tolerance below.
* Numbers match when |actual - expected| <= absolute + relative * |expected|,
  using the tolerances in settings.json.
* nan matches nan at the same position.  inf matches inf of the same sign.
* Strings must match exactly.
* Row and column order matter; SED2 defines them.

*Shared code.*  The comparison tool's reader is written independently of
the writer used by generated scripts, so a bug in one cannot hide a bug
in the other.

**Plot-as-data serialization**

For each plot, the suite stores the data the plot was drawn from, not the
picture.  The file captures data only: styles, axis scales and limits,
legends, sizes and curve types are not recorded or compared.  The data
written is exactly what the generated script passes to the plotting code.
Nothing is re-resolved separately.  Plot-as-data files use the same number,
string and special-value rules as Report serialization.

*Plot2D: one CSV, named 00001.[plot_id]_as_data.csv.*
* Each curve contributes one column per data field it has, in this order:
  x, y, xErrorLower, xErrorUpper, yErrorLower, yErrorUpper, yFrom, yTo.
  Fields the curve does not define are omitted.
* Column headers are [curve_id].[field], for example "c1.x", "c1.y".
* Curves appear in ascending `order`, ties broken by position in the
  `curves` dictionary.
* There is always a header row, and no index column.
* Every referenced value must resolve to 0-D or 1-D data (0-D counts as
  length 1).  Higher-dimensional data in a curve is an error in the test.
* Curves can have different lengths.  Shorter columns are padded at the
  bottom with empty cells.  An empty cell means "no value"; a real NaN is
  written as nan.

*Plot3D: one HDF5 file, named 00001.[plot_id]_as_data.h5.*
* One group per surface, named for the surface id.
* Each group has datasets "x", "y" and "z", each stored with the shape its
  reference resolves to (for example 1-D x and y with 2-D z, or three
  matching 2-D arrays).
* The group attribute "surfaceType" holds the surface type as a string.
* Surfaces are stored in ascending `order`, ties broken by position in
  the `surfaces` dictionary, and the group attribute "index" records
  that position.

*Comparison rules.*
* CSV: headers must match exactly and in order.  Values compare with the
  report tolerances.  Empty cells must appear in the same positions.
* HDF5: the same group names, dataset names and shapes, values within
  tolerance, and an identical "surfaceType".
* The PNG files are optional illustrations.  They are not compared.

**pySED2Translate**

The pySED2Translate program uses libsed2 to translate SED2 documents to a python script.  It will be configurable with command-line arguments to output python scripts using either tellurium/roadrunner (pip install tellurium), copasi (pip install copasi-basico), or opencor (pip install libopencor).  The Opencor output will use https://github.com/matthiaskoenig/sbml2cellml to translate SBML input to CellML.

*Python environment.*  Use Python 3.13.  All three backends were verified working there.  sbml2cellml requires 3.13 or later, which rules out 3.12, and libroadrunner supports 3.11 through 3.14.  Python 3.14 is probably also fine, but has not been fully tested.  The packages are libroadrunner (via tellurium), python-copasi (via copasi-basico), libopencor, sbml2cellml, antimony, h5py, and the libsed2 wheel.  Pin the tested versions when the environment is created, since libroadrunner requires numpy~=2.2 and libopencor has changed its supported Python range between releases.

Solver tolerances must be set explicitly for every backend and not left at defaults.  With default settings, OpenCOR's result on a simple test model was outside the suite's tolerance.  The tolerances used belong in the test's settings.json.

For any SED2 tasks that are not simulation tasks, python code will be generated directly.  For plot output, matplotlib is used.

For any SED2 simulation tasks that cannot be performed by roadrunner, copasi, or opencor, we will postpone to a later phase of this project (such as flux balance analysis).

For any SED2 simulation tasks that can be performed on a subset of simulators for some models, but not for other models (such as an ODE simulation of a model with events), we will only test the SED2 task with 'universally-simulatable' models for now.  Eventually, it would be nice to have a 'does simulator X support SBML model feature Y', but that's more a test of SBML or the orchestrator than it is a test of SED2 itself.  SED2 tasks that themselves can only be performed on two of the three simulators are acceptable for now.  The translator will need to be able to know when a given task cannot be performed by a particular simulator.

*Backend capabilities.*  The translator stores what each backend can do as a JSON file in its own source, keyed by SED2 task type and then by backend.  Each entry says whether the task is supported and, if not, why.  An entry may carry conditions where support depends on the task's details (such as the KiSAO algorithm, or fixed versus variable step size); the few cases too complex for a condition can use a small Python check instead.  A unit test confirms that every concrete task class in libsed2 has an entry, so adding a task type to libsed2 fails the test until each backend's support is recorded.  When a backend cannot perform a task, the translator raises a specific error naming the backend, the task and the reason, and the command-line program exits with a distinct code, so the test runner reports a skip with a reason and not a failure.

The test suite stays independent of the translator.  It records only which backends produced each test's canonical results, in settings.json.  The translator must support at least those backends for that test.  If the capability table says a backend cannot run a test that backend previously produced canonical results for, that is a failure, so a mistake in the table cannot quietly turn real tests into skips.

Testing pySED2Translate takes sed2-test-suite input files, produces python scripts, and compares them with canonical versions of those scripts.  Smaller tests are also created that are not in the sed2-test-suite, just for testing this program directly.

Finally, the produced python scripts are run, their output is collected, and that output compared against the canonical sed2-test-suite expected outputs. For now, only reports are compared, not plots.

**Creating everything at once**

Because nothing exists at the moment, all of the tests and expected test output will need to be produced with the programs we're testing, and hand-analyzed.  Each test's settings.json file should include information about where the canonical data came from, either 'Analytical' for results that can be calculated by hand, or the simulator(s) that produced those numbers.  All results added for now must produce comparable values across all relevant simulators (ideally all three).

Templates for the tests can be found in the C:\Users\Lucian\Desktop\sed\ directory, particularly the C:\Users\Lucian\Desktop\sed\tests\unit test files\ directory.  However, they are out of date, and will need to be updated to match the current version of the SED2 specification.  The tests must be valid SED2, and pass validation from libsed2.

As gaps are discovered in libsed2, we will edit the libsed2 generator to include the missing functions, and re-create the binaries.  We will not try to find workarounds; finding gaps is one of the principal goals of this project.  Gaps may be collected if desired, but whatever needed the missing function will need to be skipped until the gap is filled.

**Status and decisions (written during the build; the text above is the original plan)**

*State.*  sed2-test-suite has 273 semantic cases (00001-00273), all with hand-derived expected results
(`provenance.source` is `analytical` throughout) and all admitted: each lists in `settings.json` the backends that
reproduce its results.  pySED2Translate translates and runs them on roadrunner, COPASI and OpenCOR.  Series, in the order
the numbers were handed out: constants, calculations and data manipulation, ODE time courses, steady states and
Jacobians, ranges and repeats, ModelChange and the labels of `.model`, CsvImport and the data behind plots,
ModelElementList and the SEDBase fields.  `docs/COVERAGE.md` in the suite shows every SED2 element with its case count,
and the elements deliberately without cases (stochastic simulation, flux balance analysis, DataImport,
AggregationCalculation, task and output parameters, styles).  Not done by design: syntactic and stochastic cases.

*Decisions that go beyond the plan.*
* Case numbers are assigned in order of addition and never reused; the topic of a case lives in its tags.  Cases are
  written by scripts in `sed2-test-suite/authoring/`, which compute the expected tables from formulas; a rebuild keeps a
  case (and its admission) untouched when nothing about it changed.
* "Canonical" means: derived by hand first, then reproduced by every backend that can run the case.  The sign-off in each
  description (how the results were obtained, the tolerances, the admitted backends and date) is checked by the
  validator, and the checklist is `sed2-test-suite/docs/PROMOTION.md`.
* Plot-as-data files are compared as well as reports (the plan said reports only "for now"); the comparison needed
  nothing beyond the formats already described.  Pictures are never compared.
* A backend that cannot run a case is a skip with a reason (translator exit status 11, or, when the simulator only finds
  out at run time, the script exits 11 too).  A skip for a backend that the case lists as canonical is a failure.
* Problems are never hidden: simulator bugs and disagreements go to `sed2-test-suite/disagreements.json` (D-001: COPASI's
  Jacobian is wrong for a species whose value is 0, so the translator refuses it; D-002: sbml2cellml drops SBML events
  without a warning, so the OpenCOR backend refuses models with events); gaps and open questions in libsed2 or the
  specification go to the end of `SED2/TODO.md` and are never worked around.  `docs/deferred.md` lists what the translator
  skips and the choices it made where the specification is silent.
* Time courses are 2-D tables whose first column label is the `independentVariable` attribute exactly as written.
* Simulator limits found: COPASI has no CVODE and no bounded Euler or Runge-Kutta, and cannot honor `useStiffSolver`,
  `initialStepSize` or `maxInternalStepSize`; OpenCOR has neither a steady-state solver (libopencor issue 604) nor a
  Jacobian, cannot give non-uniform (bounded) output, and ignores `initialStepSize` for CVODE.  Species with no initial
  value are undefined in SBML and the simulators disagree (roadrunner 0, COPASI and OpenCOR 1), so every case sets every
  value.

*Open items for the SED2 author* (all in `SED2/TODO.md`): ModelChange `addElements`/`replaceElements` and the order of
changes; AggregationCalculation as one class per function; the CsvImport attributes and DataImport formats; TaskParameter;
references inside list and dictionary constants; RelabelData with the new labels; reporting a dictionary constant or a
model; results of math the text does not state; time-course, steady-state and Jacobian details; the SBML rules for
`setValues` and `removeElements`; ModelElementList order and type vocabulary; plot details (`order` default, shape of
`z`).
