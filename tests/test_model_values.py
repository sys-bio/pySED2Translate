"""The value of a model element by label, `#tasks:id.model['S1']` (Types, "Elements of models"; the labels are those
of model_formats/SBML/labels.md).  The value is read from the model's state with libroadrunner, whichever simulator
produced the state."""
import json
import os
import subprocess
import sys

import numpy as np
import pytest

antimony = pytest.importorskip("antimony")
pytest.importorskip("libsed2")
results_io = pytest.importorskip("sed2suite.results_io")
pytest.importorskip("roadrunner")

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
from pysed2translate.errors import TranslationError  # noqa: E402
from pysed2translate.runtime import DataError, backends  # noqa: E402
from pysed2translate.runtime.model import SbmlModel  # noqa: E402
from pysed2translate.translate import translate_file  # noqa: E402

ANT = """
model m
  compartment C = 2
  species S1 in C = 3, S2 in C = 0
  substanceOnly species S4 in C = 5
  J0: S1 -> S2; k1*S1*C
  J2: S4 -> ; k2*S4
  k1 = 0.5
  k2 = 0.1
  A := S1 + S2
  B := 2*time + k1
end
"""
IMPORT = {"_type": "modelImport", "location": "m.xml", "language": "urn:sedml:language:sbml"}
BACKENDS = ("roadrunner", "copasi", "opencor")


@pytest.fixture(scope="module")
def sbml():
    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString(ANT) >= 0
    return antimony.getSBMLString("m")


def run_doc(tmp_path, sbml, backend, tasks, reports):
    (tmp_path / "m.xml").write_text(sbml)
    doc = {"version": "v1.0.0", "tasks": tasks,
           "outputs": {k: {"_type": "report", "data": v} for k, v in reports.items()}}
    path = tmp_path / "doc.sed2.json"
    path.write_text(json.dumps(doc))
    script = tmp_path / "run.py"
    script.write_text(translate_file(str(path), backend))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [SRC, os.environ.get("PYTHONPATH", "")])))
    r = subprocess.run([sys.executable, str(script), "--output-dir", str(tmp_path / "out")], capture_output=True,
                       text=True, env=env)
    assert r.returncode == 0, r.stderr
    return lambda name: float(results_io.read_csv(str(tmp_path / "out" / f"doc.{name}.csv"), ndim=0).values[()])


def usable(backend):
    try:
        backends.get(backend)
    except DataError as e:
        pytest.skip(str(e))


def test_values_of_a_model_that_was_not_run(sbml):
    m = SbmlModel(sbml)
    value = lambda label: m.index([[("label", label)]]).values[()]
    assert value("S1") == pytest.approx(3.0)        # a concentration (the amount would be 6, in a compartment of size 2)
    assert value("S4") == pytest.approx(5.0)        # hasOnlySubstanceUnits: the amount
    assert value("C") == 2.0 and value("k1") == 0.5
    assert value("A") == pytest.approx(3.0)         # set by an assignment rule
    assert value("B") == pytest.approx(0.5)
    assert value("J0") == pytest.approx(3.0)        # a reaction: its flux, k1 * S1 * C / C with C = 2
    assert value("J2") == pytest.approx(0.5)


@pytest.mark.parametrize("backend", BACKENDS)
def test_values_after_a_time_course(tmp_path, sbml, backend):
    usable(backend)
    tasks = {"m1": IMPORT,
             "s": {"_type": "oneStepODESimulation", "model": "#tasks:m1.model", "independentVariable": "time",
                   "outputVariables": ["S1"], "independentStep": 2}}
    reports = {"s1": "#tasks:s.model['S1']", "s4": "#tasks:s.model['S4']", "a": "#tasks:s.model['A']",
               "b": "#tasks:s.model['B']", "j0": "#tasks:s.model['J0']", "j2": "#tasks:s.model['J2']",
               "c": "#tasks:s.model['C']", "out": "#tasks:s['S1']"}
    got = run_doc(tmp_path, sbml, backend, tasks, reports)
    s1 = 3.0 * np.exp(-0.5 * 2)
    assert got("s1") == pytest.approx(s1, rel=1e-6)
    assert got("out") == pytest.approx(s1, rel=1e-6)       # the same number as the simulation's own output
    assert got("s4") == pytest.approx(5 * np.exp(-0.1 * 2), rel=1e-6)
    assert got("a") == pytest.approx(3.0, rel=1e-6)         # S1 + S2 is conserved
    assert got("b") == pytest.approx(2 * 2 + 0.5, rel=1e-6)  # the model's time is where the run ended
    assert got("j0") == pytest.approx(s1, rel=1e-6)
    assert got("j2") == pytest.approx(0.1 * 5 * np.exp(-0.2), rel=1e-6)
    assert got("c") == 2.0


def test_values_in_math_and_after_a_model_change(tmp_path, sbml):
    tasks = {"m1": IMPORT,
             "c": {"_type": "modelChange", "inputModel": "#tasks:m1.model", "setValues": {"S1": 4, "k1": 0.25}},
             "calc": {"_type": "calculation", "math": "#tasks:c.model['S1'] * 2 + #tasks:c.model[\"k1\"]"}}
    got = run_doc(tmp_path, sbml, "roadrunner", tasks, {"calc": "#tasks:calc", "a": "#tasks:c.model['A']"})
    assert got("calc") == pytest.approx(8.25)
    assert got("a") == pytest.approx(4.0)


def test_values_inside_a_parameter_scan(tmp_path, sbml):
    tasks = {"m1": IMPORT,
             "ps": {"_type": "parameterScan", "model": "#tasks:m1.model",
                    "parameterRanges": [{"_type": "parameterRange", "modelElement": "k1", "values": [1, 2]}],
                    "subTasks": {"v": {"_type": "calculation", "math": "#tasks:ps.model['B'] * 10"}},
                    "outputVariableMap": {"v": "#tasks:ps:subTasks:v"}}}
    (tmp_path / "m.xml").write_text(sbml)
    doc = {"version": "v1.0.0", "tasks": tasks, "outputs": {"r": {"_type": "report", "data": "#tasks:ps"}}}
    (tmp_path / "doc.sed2.json").write_text(json.dumps(doc))
    script = tmp_path / "run.py"
    script.write_text(translate_file(str(tmp_path / "doc.sed2.json"), "roadrunner"))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [SRC, os.environ.get("PYTHONPATH", "")])))
    r = subprocess.run([sys.executable, str(script), "--output-dir", str(tmp_path / "out")], capture_output=True,
                       text=True, env=env)
    assert r.returncode == 0, r.stderr
    got = results_io.read_csv(str(tmp_path / "out" / "doc.r.csv"), ndim=2, row_labels=True, column_labels=True)
    np.testing.assert_allclose(got.values, [[10], [20]])        # B = 2*time + k1 at time 0


def test_stoichiometries_and_their_ids(sbml):
    import libsbml

    doc = libsbml.readSBMLFromString(sbml)
    reaction = doc.getModel().getReaction("J0")
    reaction.getReactant(0).setId("st1")
    reaction.getReactant(0).setStoichiometry(2.0)
    reaction.getProduct(0).setId("st2")
    reaction.getProduct(0).setConstant(False)
    assignment = doc.getModel().createInitialAssignment()
    assignment.setSymbol("st2")
    assignment.setMath(libsbml.parseL3Formula("3 * 0.5"))
    m = SbmlModel(libsbml.writeSBMLToString(doc))
    assert m.kind_of("st1") == "stoichiometry"
    assert m.index([[("label", "st1")]]).values[()] == 2.0
    assert m.index([[("label", "st2")]]).values[()] == 1.5


def test_labels_that_are_not_values_are_errors(sbml):
    m = SbmlModel(sbml)
    with pytest.raises(DataError, match="no species, compartment, global parameter or reaction"):
        m.index([[("label", "nope")]])
    with pytest.raises(DataError, match="numerically"):
        m.index([[("int", 0)]])
    with pytest.raises(DataError, match="one label only"):
        m.index([[("label", "S1"), ("label", "S2")]])
    with pytest.raises(DataError, match="one label only"):
        m.index([[("label", "S1")], [("label", "S2")]])


def test_time_travels_with_the_model(sbml):
    m = SbmlModel(sbml).with_values({"k1": 0.25})
    assert m.time == 0.0
    later = m.with_state({"S1": 1.0}, time=3.0).with_values({"k2": 0.2})
    assert later.time == 3.0
    assert later.index([[("label", "B")]]).values[()] == pytest.approx(6.25)
