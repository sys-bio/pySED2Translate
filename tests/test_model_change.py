"""ModelChange: setValues and removeElements, end to end through translated scripts.

Model: compartment C = 2; $Src -> S1 (rate k0*C); J1: S1 -> S2 (k1*S1*C); J2: S2 -> $Snk (k2*S2*C); S1 = 1, S2 = 0.5;
k0 = 2, k1 = 0.5, k2 = 1.  Steady state [S1] = k0/k1, [S2] = k0/k2.
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
from pysed2translate.errors import UnsupportedTaskError  # noqa: E402
from pysed2translate.runtime import DataError, backends  # noqa: E402
from pysed2translate.translate import translate_file  # noqa: E402

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
ANT = """
model m
  compartment C = 2
  species S1 in C = 1, S2 in C = 0.5
  $Src -> S1; k0*C
  J1: S1 -> S2; k1*S1*C
  J2: S2 -> $Snk; k2*S2*C
  k0 = 2; k1 = 0.5; k2 = 1
end
"""
IMPORT = {"_type": "modelImport", "location": "m.xml", "language": "urn:sedml:language:sbml"}


@pytest.fixture(scope="module")
def sbml():
    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString(ANT) >= 0
    return antimony.getSBMLString("m")


def run(tmp_path, sbml, backend, doc):
    results_io = pytest.importorskip("sed2suite.results_io")
    (tmp_path / "m.xml").write_text(sbml)
    path = tmp_path / "doc.sed2.json"
    path.write_text(json.dumps(doc))
    script = tmp_path / "run.py"
    script.write_text(translate_file(str(path), backend))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [SRC, os.environ.get("PYTHONPATH", "")])))
    r = subprocess.run([sys.executable, str(script), "--output-dir", str(tmp_path / "out")], capture_output=True,
                       text=True, env=env)
    assert r.returncode == 0, r.stderr

    def read(name, **kw):
        return results_io.read_csv(str(tmp_path / "out" / f"doc.{name}.csv"), **kw)
    return read


def course(model):
    return {"_type": "explicitODESimulation", "model": model, "independentVariable": "time",
            "outputVariables": ["S1", "S2", "k1"],
            "independentVariableRange": {"_type": "numericRange", "start": 0, "end": 2, "numberOfSteps": 2}}


def test_set_values_literal_reference_and_chain(tmp_path, sbml):
    doc = {"version": "v1.0.0", "constants": {"v": {"a": 0.25}},
           "tasks": {"m1": IMPORT,
                     "c1": {"_type": "modelChange", "inputModel": "#tasks:m1.model",
                            "setValues": {"S1": 3, "k1": "#constants:v['a']", "S2.boundary": False}},
                     "c2": {"_type": "modelChange", "inputModel": "#tasks:c1.model", "setValues": {"S2": 0.0}},
                     "s0": course("#tasks:m1.model"), "s1": course("#tasks:c1.model"), "s2": course("#tasks:c2.model")},
           "outputs": {"r0": {"_type": "report", "data": "#tasks:s0"}, "r1": {"_type": "report", "data": "#tasks:s1"},
                       "r2": {"_type": "report", "data": "#tasks:s2"}}}
    read = run(tmp_path, sbml, "roadrunner", doc)
    r0 = read("r0", ndim=2, column_labels=True).values
    r1 = read("r1", ndim=2, column_labels=True).values
    r2 = read("r2", ndim=2, column_labels=True).values
    assert r0[0, 1:].tolist() == [1, 0.5, 0.5]            # the input model is untouched
    assert r1[0, 1:].tolist() == [3, 0.5, 0.25]           # S1 and k1 changed
    assert r2[0, 1:].tolist() == [3, 0.0, 0.25]           # the chained change keeps the earlier one


@pytest.mark.parametrize("backend", ("roadrunner", "copasi", "opencor"))
def test_remove_element_changes_the_dynamics(tmp_path, sbml, backend):
    try:
        backends.get(backend)
    except DataError as e:
        pytest.skip(str(e))
    doc = {"version": "v1.0.0",
           "tasks": {"m1": IMPORT,
                     "c1": {"_type": "modelChange", "inputModel": "#tasks:m1.model", "removeElements": ["J1"]},
                     "s": course("#tasks:c1.model")},
           "outputs": {"r": {"_type": "report", "data": "#tasks:s"}}}
    read = run(tmp_path, sbml, backend, doc)
    got = read("r", ndim=2, column_labels=True).values
    t = got[:, 0]
    # without J1: [S1]' = k0 (rate k0*C in a compartment of size C); [S2]' = -k2 [S2]
    np.testing.assert_allclose(got[:, 1], 1 + 2 * t, rtol=1e-6)
    np.testing.assert_allclose(got[:, 2], 0.5 * np.exp(-t), rtol=1e-6)


@pytest.mark.parametrize("backend", ("roadrunner", "copasi"))
def test_changed_model_feeds_a_steady_state(tmp_path, sbml, backend):
    doc = {"version": "v1.0.0", "constants": {"names": ["k1", "k2"]},
           "tasks": {"m1": IMPORT,
                     "c1": {"_type": "modelChange", "inputModel": "#tasks:m1.model", "setValues": {"k1": 1, "k2": 4}},
                     "ss": {"_type": "steadyState", "model": "#tasks:c1.model", "outputVariables": ["S1", "S2"]}},
           "outputs": {"r": {"_type": "report", "data": "#tasks:ss"}}}
    read = run(tmp_path, sbml, backend, doc)
    got = read("r", ndim=1, row_labels=True).values
    np.testing.assert_allclose(got, [2.0, 0.5], rtol=1e-6)   # k0/k1, k0/k2


def test_set_values_by_reference_to_a_block(tmp_path, sbml):
    doc = {"version": "v1.0.0",
           "tasks": {"m1": IMPORT,
                     "blk": {"_type": "createDataBlock", "data": {"k1": 0.1, "S1": 7}},
                     "c1": {"_type": "modelChange", "inputModel": "#tasks:m1.model", "setValues": "#tasks:blk"},
                     "s": course("#tasks:c1.model")},
           "outputs": {"r": {"_type": "report", "data": "#tasks:s"}}}
    read = run(tmp_path, sbml, "roadrunner", doc)
    got = read("r", ndim=2, column_labels=True).values
    assert got[0, 1:].tolist() == [7, 0.5, 0.1]


def test_add_and_replace_elements_are_skipped():
    table = load_table()
    for b in table.backends:
        assert table.verdict(b, "modelChange", {"_type": "modelChange", "setValues": {"k": 1}}) is None
        assert table.verdict(b, "modelChange", {"removeElements": ["J1"]}) is None
        assert "S-010" in table.verdict(b, "modelChange", {"addElements": ["x"]})
        assert "S-010" in table.verdict(b, "modelChange", {"replaceElements": {"a": "b"}})
        with pytest.raises(UnsupportedTaskError):
            table.check_task(b, "c", "modelChange", {"addElements": ["x"]})


def test_non_numeric_value_is_a_translation_error(tmp_path, sbml):
    from pysed2translate.errors import TranslationError

    doc = {"version": "v1.0.0",
           "tasks": {"m1": IMPORT, "c1": {"_type": "modelChange", "inputModel": "#tasks:m1.model", "setValues": {"k1": "fast"}}},
           "outputs": {}}
    path = tmp_path / "doc.sed2.json"
    path.write_text(json.dumps(doc))
    with pytest.raises(TranslationError, match="not a number"):
        translate_file(str(path), "roadrunner")
