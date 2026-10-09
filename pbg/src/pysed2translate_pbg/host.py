"""The seam to the host (pysed2translate).  The ONLY module of this package that imports it (rule M2).

Everything an engine or a command needs from the host is re-exported here under a stable name.  If the host changes,
this file changes.  `check_seams()` verifies at once that every name exists (phase 0 of the plan; also a test).
"""
from __future__ import annotations

import libsed2  # noqa: F401  (the SED2 object model; engines reach it as host.libsed2)

from pysed2translate import runtime as rt                       # AnnotatedData, SbmlModel, ops, m, backends, Context, plots, writers
from pysed2translate import errors                               # exception classes and exit statuses
from pysed2translate import kisao                                # setting names
from pysed2translate import __version__ as HOST_VERSION
from pysed2translate.backends import (ALL_BACKENDS, BACKENDS, FBA_BACKENDS, KINDS, backend_problem,  # dynamic simulators, FBA tools,
                                      parse_backend_args, split_backend)                              # kinds, name[:variant] parsing
from pysed2translate.capabilities import load_table              # the capability table
from pysed2translate.translate import default_prefix, load_document  # validated libsed2 document from a file
from pysed2translate.errors import (EXIT_INVALID, EXIT_OK, EXIT_TRANSLATION, EXIT_UNSUPPORTED, EXIT_USAGE,
                                    InvalidDocumentError, PySED2TranslateError, TranslationError, UnsupportedTaskError)
from pysed2translate.runtime import BackendCannotRun, EXIT_CANNOT_RUN
from pysed2translate import suite_runner as _suite_runner        # suite location and comparison, used by the contract tests

AnnotatedData = rt.AnnotatedData
SbmlModel = rt.SbmlModel
DataError = rt.DataError
Context = rt.Context

# the suite helpers (only tests/contract and the `suite` command use these)
locate_suite = _suite_runner.locate_suite
list_cases = _suite_runner.list_cases
document_path = _suite_runner.document_path
PASS, FAIL, SKIP, ERROR = _suite_runner.PASS, _suite_runner.FAIL, _suite_runner.SKIP, _suite_runner.ERROR
RunResult = _suite_runner.RunResult
script_run_case = _suite_runner.run_case           # the Python-script target (`pysed2translate`), for --script
format_report = _suite_runner.format_report
disagreements_with_expected = _suite_runner.disagreements_with_expected
crosscheck = _suite_runner.crosscheck
draft_entries = _suite_runner.draft_entries
suite_tail = _suite_runner._tail


def check_document(backend: str, document, overrides=None) -> None:
    """Raise UnsupportedTaskError if the backend that would perform a task cannot do it (capability table).  `overrides`
    maps a kind of work to its backend."""
    load_table().check_document(backend, document.to_json_value(), overrides or {})


def kinds_in(document) -> set:
    """The kinds of work ('ode', 'steady', 'jacobian', 'fba') the document needs a simulator for."""
    return _suite_runner.kinds_in(document.to_json_value())


def result_columns(results: list) -> list:
    """The backends that appear in a list of results, in the order of the host's table."""
    return _suite_runner.columns(results)


def default_backends(case_dir: str) -> list:
    """The backends the host runs a case on when none are named."""
    return _suite_runner.default_backends(case_dir)


def capability_table():
    return load_table()


def math_functions():
    """Names of the predefined math functions the runtime implements, for the engine's own validation."""
    return rt.m.FUNCTIONS


def check_seams() -> list:
    """Names this package expects from the host that are missing (an empty list when all is well)."""
    expected = ["rt.AnnotatedData", "rt.SbmlModel", "rt.ops", "rt.m", "rt.backends", "rt.Context", "rt.plots",
                "rt.write_report", "rt.BackendCannotRun", "rt.backends.TimeCourse", "rt.backends.SteadyState",
                "rt.backends.get", "rt.backends.FbaRequest", "rt.ops.repeat_table", "rt.ops.scan_table", "rt.ops.numeric_range", "rt.ops.block",
                "rt.ops.relabel", "rt.ops.string_formation", "rt.ops.string_data", "rt.ops.csv_import",
                "rt.ops.scalar", "rt.ops.string_scalar", "rt.ops.numbers_from", "rt.ops.strings_from",
                "rt.ops.mapping_from", "rt.ops.grid", "rt.ops.labeled_vector", "rt.m.to_data", "rt.m.array",
                "rt.m.neg", "rt.m.python_name", "rt.m.FUNCTIONS", "rt.m.CONSTANTS", "rt.plots.plot2d",
                "rt.plots.plot3d", "kisao.ALL_SETTINGS", "errors.EXIT_UNSUPPORTED"]
    missing = []
    g = globals()
    for dotted in expected:
        obj = g
        try:
            head, *rest = dotted.split(".")
            obj = g[head]
            for part in rest:
                obj = getattr(obj, part)
        except (KeyError, AttributeError):
            missing.append(dotted)
    return missing
