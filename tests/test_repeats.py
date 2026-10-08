"""Loop, Scatter and ParameterScan, end to end through translated scripts.

Model: compartment C = 2; S1 (concentration 3) -> S2 with rate k1*S1*C, k1 = 0.5, so [S1](t) = 3 exp(-k1 t).
"""
import json
import os
import subprocess
import sys

import numpy as np
import pytest

antimony = pytest.importorskip("antimony")
pytest.importorskip("libsed2")

from pysed2translate.capabilities import load_table  # noqa: E402
from pysed2translate.errors import InvalidDocumentError, TranslationError  # noqa: E402
from pysed2translate.runtime import DataError, backends  # noqa: E402
from pysed2translate.translate import Options, emit_script, load_document, translate_file  # noqa: E402

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
ANT = """
model m
  compartment C = 2
  species S1 in C = 3, S2 in C = 0
  J0: S1 -> S2; k1*S1*C
  k1 = 0.5
end
"""
IMPORT = {"_type": "modelImport", "location": "m.xml", "language": "urn:sedml:language:sbml"}
BACKENDS = ("roadrunner", "copasi", "opencor")


@pytest.fixture(scope="module")
def sbml():
    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString(ANT) >= 0
    return antimony.getSBMLString("m")


def write(tmp_path, sbml, doc):
    (tmp_path / "m.xml").write_text(sbml)
    path = tmp_path / "doc.sed2.json"
    path.write_text(json.dumps(doc))
    return path


def run_script(tmp_path, text):
    script = tmp_path / "run.py"
    script.write_text(text)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [SRC, os.environ.get("PYTHONPATH", "")])))
    r = subprocess.run([sys.executable, str(script), "--output-dir", str(tmp_path / "out")], capture_output=True,
                       text=True, env=env)
    assert r.returncode == 0, r.stderr


def run(tmp_path, sbml, backend, doc):
    results_io = pytest.importorskip("sed2suite.results_io")
    path = write(tmp_path, sbml, doc)
    run_script(tmp_path, translate_file(str(path), backend))

    def read(name, **kw):
        if kw.get("ndim") == 2:
            kw.setdefault("row_labels", True)
            kw.setdefault("column_labels", True)
        return results_io.read_csv(str(tmp_path / "out" / f"doc.{name}.csv"), **kw)
    return read


def usable(backend):
    try:
        backends.get(backend)
    except DataError as e:
        pytest.skip(str(e))


def numeric(start, steps, interval):
    return {"_type": "numericRange", "start": start, "numberOfSteps": steps, "interval": interval}


def one_step(model, step):
    return {"_type": "oneStepODESimulation", "model": model, "independentVariable": "time",
            "outputVariables": ["S1"], "independentStep": step}


# --------------------------------------------------------------------------- Scatter

def test_scatter_with_per_iteration_range_and_index(tmp_path, sbml):
    doc = {"version": "v1.0.0",
           "tasks": {"sc": {"_type": "scatter", "range": numeric(0, 3, 1),
                            "subTasks": {"x": {"_type": "calculation", "math": "1 * #tasks:sc.range * 2 + #tasks:sc.index * 10"},
                                         "y": {"_type": "calculation", "math": "1 * #tasks:sc:subTasks:x + 1"}},
                            "outputVariableMap": {"X": "#tasks:sc:subTasks:x", "Y": "#tasks:sc:subTasks:y"}}},
           "outputs": {"r": {"_type": "report", "data": "#tasks:sc"}}}
    got = run(tmp_path, sbml, "roadrunner", doc)("r", ndim=2)
    np.testing.assert_allclose(got.values, [[0, 1], [12, 13], [24, 25], [36, 37]])
    assert got.labels[0] == ["0", "1", "2", "3"]      # the range values label the iterations
    assert got.labels[1] == ["X", "Y"]                 # the outputVariableMap keys label the entries


def test_scatter_without_outputs_has_no_entries(tmp_path, sbml):
    """The range values are the labels of dimension 0; with no outputVariableMap there are no entries."""
    doc = {"version": "v1.0.0",
           "tasks": {"sc": {"_type": "scatter", "range": numeric(1, 2, 0.5), "outputVariableMap": {},
                            "subTasks": {"x": {"_type": "calculation", "math": "1"}}}},
           "outputs": {"r": {"_type": "report", "data": "#tasks:sc"}}}
    got = run(tmp_path, sbml, "roadrunner", doc)("r", ndim=2)
    assert got.values.shape == (3, 0)
    assert got.labels[0] == ["1", "1.5", "2"]


@pytest.mark.parametrize("backend", BACKENDS)
def test_scatter_parameter_sweep_runs_simulations(tmp_path, sbml, backend):
    usable(backend)
    doc = {"version": "v1.0.0",
           "tasks": {"m1": IMPORT,
                     "sc": {"_type": "scatter", "range": numeric(0.25, 3, 0.25),
                            "subTasks": {"c": {"_type": "modelChange", "inputModel": "#tasks:m1.model",
                                               "setValues": {"k1": "#tasks:sc.range"}},
                                         "s": one_step("#tasks:sc:subTasks:c.model", 2)},
                            "outputVariableMap": {"S1": "#tasks:sc:subTasks:s['S1']"}}},
           "outputs": {"r": {"_type": "report", "data": "#tasks:sc"}}}
    got = run(tmp_path, sbml, backend, doc)("r", ndim=2)
    k = np.array([0.25, 0.5, 0.75, 1.0])
    assert got.labels[0] == ["0.25", "0.5", "0.75", "1"]
    np.testing.assert_allclose(got.values[:, 0], 3 * np.exp(-2 * k), rtol=1e-6)


# --------------------------------------------------------------------------- Loop

def test_loop_carries_a_number(tmp_path, sbml):
    doc = {"version": "v1.0.0",
           "tasks": {"lp": {"_type": "loop", "range": numeric(1, 3, 1),
                            "loopVariables": {"acc": {"initialValue": 1.0, "subsequentValues": "#tasks:lp:subTasks:d"}},
                            "subTasks": {"d": {"_type": "calculation", "math": "1 * #tasks:lp:loopVariables:acc * 2"}},
                            "outputVariableMap": {"D": "#tasks:lp:subTasks:d"}}},
           "outputs": {"r": {"_type": "report", "data": "#tasks:lp"}}}
    got = run(tmp_path, sbml, "roadrunner", doc)("r", ndim=2)
    np.testing.assert_allclose(got.values[:, 0], [2, 4, 8, 16])
    assert got.labels[0] == ["1", "2", "3", "4"] and got.labels[1] == ["D"]


@pytest.mark.parametrize("backend", BACKENDS)
def test_loop_carries_the_model_state(tmp_path, sbml, backend):
    usable(backend)
    doc = {"version": "v1.0.0",
           "tasks": {"m1": IMPORT,
                     "lp": {"_type": "loop", "range": numeric(1, 3, 1),
                            "loopVariables": {"m": {"initialValue": "#tasks:m1.model",
                                                    "subsequentValues": "#tasks:lp:subTasks:s.model"}},
                            "subTasks": {"s": one_step("#tasks:lp:loopVariables:m", 1)},
                            "outputVariableMap": {"S1": "#tasks:lp:subTasks:s['S1']"}}},
           "outputs": {"r": {"_type": "report", "data": "#tasks:lp"}}}
    got = run(tmp_path, sbml, backend, doc)("r", ndim=2)
    assert got.labels[0] == ["1", "2", "3", "4"]
    np.testing.assert_allclose(got.values[:, 0], 3 * np.exp(-0.5 * np.array([1, 2, 3, 4])), rtol=1e-6)


def test_loop_with_two_variables_updates_them_together(tmp_path, sbml):
    # (a, b) -> (b, a + b): Fibonacci
    doc = {"version": "v1.0.0",
           "tasks": {"lp": {"_type": "loop", "range": numeric(0, 5, 1),
                            "loopVariables": {"a": {"initialValue": 0, "subsequentValues": "#tasks:lp:subTasks:nb"},
                                              "b": {"initialValue": 1, "subsequentValues": "#tasks:lp:subTasks:nsum"}},
                            "subTasks": {"nb": {"_type": "calculation", "math": "1 * #tasks:lp:loopVariables:b"},
                                         "nsum": {"_type": "calculation",
                                                  "math": "1 * #tasks:lp:loopVariables:a + #tasks:lp:loopVariables:b"}},
                            "outputVariableMap": {"A": "#tasks:lp:subTasks:nb"}}},
           "outputs": {"r": {"_type": "report", "data": "#tasks:lp"}}}
    got = run(tmp_path, sbml, "roadrunner", doc)("r", ndim=2).values
    np.testing.assert_allclose(got[:, 0], [1, 1, 2, 3, 5, 8])


def test_nested_repeats(tmp_path, sbml):
    doc = {"version": "v1.0.0",
           "tasks": {"outer": {"_type": "scatter", "range": numeric(1, 2, 1),
                               "subTasks": {"inner": {"_type": "scatter", "range": numeric(10, 1, 10),
                                                      "subTasks": {"p": {"_type": "calculation",
                                                                         "math": "1 * #tasks:outer.range * #tasks:outer:subTasks:inner.range"}},
                                                      "outputVariableMap": {"P": "#tasks:outer:subTasks:inner:subTasks:p"}},
                                            "last": {"_type": "calculation", "math": "1 * #tasks:outer:subTasks:inner[1]['P']"}},
                               "outputVariableMap": {"L": "#tasks:outer:subTasks:last"}}},
           "outputs": {"r": {"_type": "report", "data": "#tasks:outer"}}}
    got = run(tmp_path, sbml, "roadrunner", doc)("r", ndim=2).values
    np.testing.assert_allclose(got, [[20], [40], [60]])


# --------------------------------------------------------------------------- ParameterScan

def scan_doc(model_ref, scan_model_ref=None):
    """A scan of k1 and S1.  Normally a ModelChange applies the current values (`.ranges`); with `scan_model_ref` the
    sub-task takes the scan's own `.model`, which already has them."""
    sub = {"c": {"_type": "modelChange", "inputModel": model_ref,
                 "setValues": {} if scan_model_ref else {"k1": "#tasks:ps.ranges['k1']", "S1": "#tasks:ps.ranges['S1']"}},
           "s": one_step("#tasks:ps:subTasks:c.model", 2),
           "idx": {"_type": "calculation", "math": "1 * #tasks:ps.indexes['k1'] * 10 + #tasks:ps.indexes['S1']"}}
    return {"version": "v1.0.0",
            "tasks": {"m1": IMPORT,
                      "ps": {"_type": "parameterScan", "model": "#tasks:m1.model",
                             "parameterRanges": [{"_type": "parameterRange", "modelElement": "k1", "start": 0.25,
                                                  "numberOfSteps": 2, "interval": 0.25},
                                                 {"_type": "parameterRange", "modelElement": "S1", "values": [1, 2]}],
                             "subTasks": sub,
                             "outputVariableMap": {"S1": "#tasks:ps:subTasks:s['S1']", "idx": "#tasks:ps:subTasks:idx"}}},
            "outputs": {"r": {"_type": "report", "data": "#tasks:ps"},
                        "slice": {"_type": "report", "data": "#tasks:ps[1]"}}}


def check_scan(tmp_path):
    results_io = pytest.importorskip("sed2suite.results_io")
    pytest.importorskip("h5py")
    got = results_io.read_h5(str(tmp_path / "out" / "doc.r.h5"))
    data = got.values
    assert data.shape == (3, 2, 2)
    # one dimension per parameterRange in order, named by its model element and labeled by its values;
    # then the outputVariableMap entries labeled by their keys
    assert got.dims == ["k1", "S1", ""]
    assert got.labels == [["0.25", "0.5", "0.75"], ["1", "2"], ["S1", "idx"]]
    k = np.array([0.25, 0.5, 0.75])[:, None]
    s0 = np.array([1.0, 2.0])[None, :]
    np.testing.assert_allclose(data[:, :, 0], s0 * np.exp(-2 * k), rtol=1e-6)
    np.testing.assert_allclose(data[:, :, 1], np.array([[0, 1], [10, 11], [20, 21]]))


@pytest.mark.parametrize("backend", BACKENDS)
def test_parameter_scan(tmp_path, sbml, backend):
    usable(backend)
    path = write(tmp_path, sbml, scan_doc("#tasks:m1.model"))
    run_script(tmp_path, translate_file(str(path), backend))
    check_scan(tmp_path)


@pytest.mark.parametrize("backend", BACKENDS)
def test_scan_model_output_is_the_model_with_the_current_values(tmp_path, sbml, backend):
    """`#tasks:scan.model`, inside the scan, is the scanned model initialized with the current value of every range."""
    usable(backend)
    path = write(tmp_path, sbml, scan_doc("#tasks:ps.model", scan_model_ref=True))
    run_script(tmp_path, translate_file(str(path), backend))
    check_scan(tmp_path)


# --------------------------------------------------------------------------- limits

def test_aggregates_and_task_parameters_are_skipped():
    table = load_table()
    for b in table.backends:
        for t in ("loop", "scatter", "parameterScan"):
            assert table.verdict(b, t, {"_type": t, "outputVariableMap": {"a": "#tasks:x"}}) is None
            assert "S-006" in table.verdict(b, t, {"aggregateOutputVariables": {"a": {}}})
            assert "S-011" in table.verdict(b, t, {"taskParameters": [{"id": "p"}]})


def test_subtasks_are_checked_by_the_capability_table():
    table = load_table()
    doc = {"tasks": {"sc": {"_type": "scatter", "subTasks": {"c": {"_type": "modelChange", "addElements": ["x"]}}}}}
    with pytest.raises(Exception, match="addElements"):
        table.check_document("roadrunner", doc)


def test_the_inside_of_a_repeat_is_not_visible_outside(tmp_path, sbml):
    doc = {"version": "v1.0.0",
           "tasks": {"sc": {"_type": "scatter", "range": numeric(0, 1, 1),
                            "subTasks": {"x": {"_type": "calculation", "math": "1"}}, "outputVariableMap": {"X": "#tasks:sc:subTasks:x"}},
                     "after": {"_type": "calculation", "math": "1 * #tasks:sc:subTasks:x"}},
           "outputs": {}}
    path = write(tmp_path, sbml, doc)
    with pytest.raises((TranslationError, InvalidDocumentError)):
        translate_file(str(path), "roadrunner")


# --------------------------------------------------------------------------- the shape of [id] (Loop, Scatter and ParameterScan descriptions)

def test_vector_entries_extend_the_result_with_their_own_dimensions(tmp_path, sbml):
    """A sub-task output that is not a single number adds its dimensions after the entries; the iteration stays
    dimension 0, labeled by the range values, and the entry's own labels are kept."""
    results_io = pytest.importorskip("sed2suite.results_io")
    pytest.importorskip("h5py")
    doc = {"version": "v1.0.0",
           "tasks": {"m1": IMPORT,
                     "sc": {"_type": "scatter", "range": numeric(1, 2, 1),
                            "subTasks": {"c": {"_type": "modelChange", "inputModel": "#tasks:m1.model",
                                               "setValues": {"k1": "#tasks:sc.range"}},
                                         "t": {"_type": "explicitODESimulation", "model": "#tasks:sc:subTasks:c.model",
                                               "independentVariable": "time", "outputVariables": ["S1", "S2"],
                                               "independentVariableRange": {"_type": "numericRange", "start": 0,
                                                                            "end": 1, "numberOfSteps": 4}}},
                            "outputVariableMap": {"tc": "#tasks:sc:subTasks:t"}}},
           "outputs": {"r": {"_type": "report", "data": "#tasks:sc"}}}
    path = write(tmp_path, sbml, doc)
    run_script(tmp_path, translate_file(str(path), "roadrunner"))
    got = results_io.read_h5(str(tmp_path / "out" / "doc.r.h5"))
    assert got.values.shape[:2] == (3, 1) and got.values.ndim == 4
    assert got.labels[0] == ["1", "2", "3"] and got.labels[1] == ["tc"]


def test_string_entries_are_allowed(tmp_path, sbml):
    doc = {"version": "v1.0.0",
           "tasks": {"sc": {"_type": "scatter", "range": numeric(0, 1, 1),
                            "subTasks": {"x": {"_type": "stringFormation", "concatenate": ["n=", "#tasks:sc.index"]}},
                            "outputVariableMap": {"X": "#tasks:sc:subTasks:x"}}},
           "outputs": {"r": {"_type": "report", "data": "#tasks:sc"}}}
    got = run(tmp_path, sbml, "roadrunner", doc)("r", ndim=2, dtype="string")
    assert got.values.tolist() == [["n=0"], ["n=1"]]
    assert got.labels == [["0", "1"], ["X"]]



def test_repeat_results_can_be_indexed_by_iteration_and_key(tmp_path, sbml):
    doc = {"version": "v1.0.0",
           "tasks": {"sc": {"_type": "scatter", "range": numeric(0, 3, 1),
                            "subTasks": {"x": {"_type": "calculation", "math": "#tasks:sc.range * 2 + #tasks:sc.index * 10"},
                                         "y": {"_type": "calculation", "math": "#tasks:sc:subTasks:x + 1"}},
                            "outputVariableMap": {"X": "#tasks:sc:subTasks:x", "Y": "#tasks:sc:subTasks:y"}}},
           "outputs": {"one": {"_type": "report", "data": "#tasks:sc[2, 'Y']"},
                       "col": {"_type": "report", "data": "#tasks:sc[1:3, 'X']"},
                       "row": {"_type": "report", "data": "#tasks:sc['3']"},
                       "last": {"_type": "report", "data": "#tasks:sc[-1][0]"}}}
    got = run(tmp_path, sbml, "roadrunner", doc)
    assert got("one", ndim=0).values[()] == 25.0
    col = got("col", ndim=1, row_labels=True)
    np.testing.assert_allclose(col.values, [12, 24])
    assert col.labels[0] == ["1", "2"]                  # a range keeps the iteration labels
    row = got("row", ndim=1, row_labels=True)
    np.testing.assert_allclose(row.values, [36, 37])
    assert row.labels[0] == ["X", "Y"]
    assert got("last", ndim=0).values[()] == 36.0
