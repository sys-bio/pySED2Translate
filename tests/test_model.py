"""SbmlModel (runtime/model.py) and the ModelImport / ModelElementList translation."""
import json
import os
import subprocess
import sys

import pytest

pytest.importorskip("libsed2")
libsbml = pytest.importorskip("libsbml")
antimony = pytest.importorskip("antimony")
results_io = pytest.importorskip("sed2suite.results_io")

from pysed2translate.runtime import DataError, SbmlModel  # noqa: E402
from pysed2translate.translate import translate_file  # noqa: E402

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")

ANT = """
function twice(x)
  x*2
end
model m
  compartment C = 2
  species S1 in C = 3, S2 in C = 0, S3 in C = 1
  substanceOnly species A in C = 5
  k1 = 0.5
  k2 := 2*k1
  J0: S1 -> S2; k1*S1*C
  J1: S2 -> S3; k1*S2*C
  E1: at time > 5: k1 = 1
end
"""


@pytest.fixture(scope="module")
def sbml_text():
    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString(ANT) >= 0, antimony.getLastError()
    return antimony.getSBMLString("m")


@pytest.fixture
def model(sbml_text):
    return SbmlModel(sbml_text, "m.xml")


def model_of(m):
    return libsbml.readSBMLFromString(m.text).getModel()


# --------------------------------------------------------------------------- inspection

def test_element_ids_all_in_model_order(model):
    assert model.element_ids() == ["twice", "C", "S1", "S2", "S3", "A", "k1", "k2", "J0", "J1", "E1"]


def test_element_ids_filters(model):
    assert model.element_ids(include_types=["species"]) == ["S1", "S2", "S3", "A"]
    assert model.element_ids(include_types=["species"], exclude_elements=["S2"]) == ["S1", "S3", "A"]
    assert model.element_ids(include_elements=["J0", "J1"], include_types=["species"], exclude_elements=["S1"]) == \
        ["S2", "S3", "A", "J0", "J1"]
    assert model.element_ids(include_types=["reaction"], exclude_types=["reaction"]) == []
    assert model.element_ids(include_elements=["S1"], exclude_elements=["S1"]) == []  # excluded wins
    assert model.element_ids(exclude_types=["species", "reaction", "event", "functionDefinition"]) == ["C", "k1", "k2"]
    assert model.element_ids(include_elements=[]) == []


def test_element_ids_errors(model):
    with pytest.raises(DataError):
        model.element_ids(include_types=["gene"])
    with pytest.raises(DataError):
        model.element_ids(include_elements=["nope"])


def test_kind_of(model):
    assert model.kind_of("S1") == "species_concentration"
    assert model.kind_of("A") == "species_amount"
    assert model.kind_of("C") == "compartment"
    assert model.kind_of("k1") == "parameter"
    assert model.kind_of("J0") == "reaction"
    assert model.kind_of("zzz") == "unknown"


def test_state_variables_exclude_constants_and_rule_assigned(model):
    # k1 is changed by the event, so it is a state variable; k2 is set by a rule
    assert set(model.state_variables()) == {"S1", "S2", "S3", "A", "k1"}


# --------------------------------------------------------------------------- changes

def test_with_values_changes_a_copy(model):
    new = model.with_values({"S1": 10, "A": 7, "C": 4, "k1": 2})
    d = model_of(new)
    assert d.getSpecies("S1").getInitialConcentration() == 10
    assert d.getSpecies("A").getInitialAmount() == 7
    assert d.getCompartment("C").getSize() == 4
    assert d.getParameter("k1").getValue() == 2
    assert model_of(model).getSpecies("S1").getInitialConcentration() == 3  # the original is untouched


def test_with_values_flags_and_errors(model):
    d = model_of(model.with_values({"S1.boundary": 1}))
    assert d.getSpecies("S1").getBoundaryCondition() is True
    with pytest.raises(DataError):
        model.with_values({"nope": 1})
    with pytest.raises(DataError):
        model.with_values({"S1.color": 1})


def test_setting_a_value_drops_its_initial_assignment():
    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString("model q\n p = 1\n substanceOnly species x in C\n compartment C = 1\n x = 2*p\nend") >= 0, antimony.getLastError()
    text = antimony.getSBMLString("q")
    m = SbmlModel(text)
    ia = libsbml.readSBMLFromString(text).getModel()
    assert ia.getInitialAssignment("x") is not None
    assert model_of(m.with_values({"x": 5})).getInitialAssignment("x") is None


def test_with_state_ignores_unknown_and_assigned(model):
    new = model.with_state({"S1": 1.5, "S2": 2.5, "k2": 99, "ghost": 1})
    d = model_of(new)
    assert d.getSpecies("S1").getInitialConcentration() == 1.5 and d.getSpecies("S2").getInitialConcentration() == 2.5
    assert d.getParameter("k2").getValue() != 99


def test_without_removes_elements(model):
    new = model.without(["J1", "S3"])
    assert new.element_ids(include_types=["reaction", "species"]) == ["S1", "S2", "A", "J0"]
    with pytest.raises(DataError):
        model.without(["nope"])


def test_load_errors(tmp_path):
    with pytest.raises(DataError):
        SbmlModel.load(str(tmp_path / "missing.xml"), "urn:sedml:language:sbml")
    bad = tmp_path / "bad.xml"
    bad.write_text("<not sbml")
    with pytest.raises(DataError):
        SbmlModel.load(str(bad), "urn:sedml:language:sbml")
    ok = tmp_path / "ok.xml"
    ok.write_text("<sbml xmlns='http://www.sbml.org/sbml/level3/version1/core' level='3' version='1'><model id='x'/></sbml>")
    assert SbmlModel.load(str(ok), "urn:sedml:language:sbml.level-3.version-1").element_ids() == []
    with pytest.raises(DataError):
        SbmlModel.load(str(ok), "urn:sedml:language:cellml")


# --------------------------------------------------------------------------- translated documents

def run_doc(tmp_path, sbml_text, tasks, reports):
    (tmp_path / "m.xml").write_text(sbml_text)
    doc = {"version": "v1.0.0",
           "tasks": {"m1": {"_type": "modelImport", "location": "m.xml", "language": "urn:sedml:language:sbml"}, **tasks},
           "outputs": {rid: {"_type": "report", "data": ref} for rid, ref in reports.items()}}
    path = tmp_path / "doc.sed2.json"
    path.write_text(json.dumps(doc))
    script = tmp_path / "run.py"
    script.write_text(translate_file(str(path), "roadrunner"))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [SRC, os.environ.get("PYTHONPATH", "")])))
    out = tmp_path / "out"
    r = subprocess.run([sys.executable, str(script), "--output-dir", str(out)], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return out


def test_model_element_list_end_to_end(tmp_path, sbml_text):
    out = run_doc(tmp_path, sbml_text, {
        "all_species": {"_type": "modelElementList", "model": "#tasks:m1.model", "includeTypes": ["species"]},
        "some": {"_type": "modelElementList", "model": "#tasks:m1.model", "includeElements": ["J0", "J1"],
                 "includeTypes": ["species"], "excludeElements": ["S1"]},
    }, {"a": "#tasks:all_species.strings", "b": "#tasks:some.strings"})
    a = results_io.read_csv(str(out / "doc.a.csv"), ndim=1, dtype="string")
    b = results_io.read_csv(str(out / "doc.b.csv"), ndim=1, dtype="string")
    assert a.values.tolist() == ["S1", "S2", "S3", "A"]
    assert b.values.tolist() == ["S2", "S3", "A", "J0", "J1"]


def test_model_element_list_filters_given_by_constants(tmp_path, sbml_text):
    (tmp_path / "m.xml").write_text(sbml_text)
    doc = {"version": "v1.0.0", "constants": {"skip": ["S1", "S2"], "kinds": ["species"]},
           "tasks": {"m1": {"_type": "modelImport", "location": "m.xml", "language": "urn:sedml:language:sbml"},
                     "l": {"_type": "modelElementList", "model": "#tasks:m1.model", "includeTypes": "#constants:kinds",
                           "excludeElements": "#constants:skip"}},
           "outputs": {"r": {"_type": "report", "data": "#tasks:l.strings"}}}
    path = tmp_path / "doc.sed2.json"
    path.write_text(json.dumps(doc))
    script = tmp_path / "run.py"
    script.write_text(translate_file(str(path), "copasi"))
    env = dict(os.environ, PYTHONPATH=SRC)
    r = subprocess.run([sys.executable, str(script), "--output-dir", str(tmp_path / "o")], capture_output=True,
                       text=True, env=env)
    assert r.returncode == 0, r.stderr
    got = results_io.read_csv(str(tmp_path / "o" / "doc.r.csv"), ndim=1, dtype="string")
    assert got.values.tolist() == ["S3", "A"]


def test_missing_model_file_fails_the_run(tmp_path, sbml_text):
    (tmp_path / "m.xml").write_text(sbml_text)
    doc = {"version": "v1.0.0",
           "tasks": {"m1": {"_type": "modelImport", "location": "nothere.xml", "language": "urn:sedml:language:sbml"}}}
    path = tmp_path / "doc.sed2.json"
    path.write_text(json.dumps(doc))
    script = tmp_path / "run.py"
    script.write_text(translate_file(str(path), "opencor"))
    r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=SRC),
                       cwd=str(tmp_path))
    assert r.returncode == 1 and "nothere.xml" in r.stderr
