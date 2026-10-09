"""Flux balance analysis: the cobra backend, the table entries and the generated scripts."""
import io
import json
import os
import subprocess
import sys

import numpy as np
import pytest

pytest.importorskip("libsed2")
cobra = pytest.importorskip("cobra")
pytest.importorskip("libsbml")

from pysed2translate import runtime as rt  # noqa: E402
from pysed2translate.runtime.backends import FbaRequest  # noqa: E402

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")


def toy_text(glucose_lb=-10.0, objective="BIOMASS", unique_bounds=True):
    """glucose -> respiration (capacity 6) or fermentation (acetate overflow) -> biomass, and a maintenance drain that
    must carry 0.5: with 10 glucose the unique optimum is respiration 6, fermentation 3.5, biomass 0.165."""
    from cobra import Metabolite, Model, Reaction

    m = Model("toy")

    def rxn(rid, mets, lb, ub):
        r = Reaction(rid)
        r.lower_bound, r.upper_bound = lb, ub
        r.add_metabolites(mets)
        return r

    glc, ac, g, a, bm = (Metabolite(n, compartment="c") for n in ("glc_e", "ac_e", "glc_c", "ac_c", "bm"))
    m.add_reactions([rxn("EX_glc", {glc: -1}, glucose_lb, 1000), rxn("EX_ac", {ac: -1}, 0, 1000),
                     rxn("GLCt", {glc: -1, g: 1}, 0, 1000), rxn("RESP", {g: -1, bm: 0.024}, 0, 6),
                     rxn("FERM", {g: -1, a: 2, bm: 0.006}, 0, 1000), rxn("ACX", {a: -1, ac: 1}, 0, 1000),
                     rxn("BIOMASS", {bm: -1}, 0, 1000), rxn("ATPM", {g: -1}, 0.5, 1000)])
    m.objective = objective
    buf = io.StringIO()
    cobra.io.write_sbml_model(m, buf)
    return buf.getvalue()


def model(**kw):
    return rt.SbmlModel(toy_text(**kw), "toy")


@pytest.mark.parametrize("variant", ["", "glpk", "scipy"])
def test_optimum_and_fluxes_by_sbml_id(variant):
    be = rt.backends.get("cobra:" + variant if variant else "cobra")
    data, out = be.fba(model(), FbaRequest(output_variables=["R_BIOMASS", "R_RESP", "R_FERM", "R_EX_glc"]))
    assert data.labels == [["R_BIOMASS", "R_RESP", "R_FERM", "R_EX_glc"]]
    assert np.allclose(data.values, [0.165, 6.0, 3.5, -10.0], atol=1e-9)


def test_the_model_is_handed_on_unchanged():
    m = model()
    _data, out = rt.backends.get("cobra").fba(m, FbaRequest(output_variables=["R_BIOMASS"]))
    assert out is m


def test_a_bound_changed_with_a_model_change_changes_the_optimum():
    m = model().with_values({"R_EX_glc_lower_bound": -5.0})
    data, _ = rt.backends.get("cobra").fba(m, FbaRequest(output_variables=["R_BIOMASS"]))
    assert data.values[0] == pytest.approx(0.108)


def test_parameters_report_their_value():
    data, _ = rt.backends.get("cobra").fba(model(), FbaRequest(output_variables=["R_EX_glc_lower_bound", "R_BIOMASS"]))
    assert data.values.tolist()[0] == -10.0


def test_infeasible_is_a_data_error_not_zeros():
    m = model().with_values({"R_EX_glc_lower_bound": 0.0})   # no glucose, but the maintenance drain must carry 0.5
    with pytest.raises(rt.DataError, match="no optimum.*infeasible"):
        rt.backends.get("cobra").fba(m, FbaRequest(output_variables=["R_BIOMASS"]))


def test_unknown_variable():
    with pytest.raises(rt.DataError, match="no reaction, parameter, compartment or species 'nope'"):
        rt.backends.get("cobra").fba(model(), FbaRequest(output_variables=["nope"]))


def test_a_model_without_fbc_cannot_be_run():
    plain = rt.SbmlModel('<?xml version="1.0"?><sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1">'
                         '<model id="p"><listOfCompartments><compartment id="c" constant="true" size="1"/></listOfCompartments>'
                         '</model></sbml>')
    with pytest.raises(rt.BackendCannotRun, match="FBC") as ei:
        rt.backends.get("cobra").fba(plain, FbaRequest(output_variables=["x"]))
    assert ei.value.backend == "cobra"


def test_algorithm_other_than_fba_is_refused():
    with pytest.raises(rt.DataError, match="KISAO:0000019 is not available for flux balance analysis"):
        rt.backends.get("cobra").fba(model(), FbaRequest(output_variables=["R_BIOMASS"], algorithm="KISAO:0000019"))
    data, _ = rt.backends.get("cobra").fba(model(), FbaRequest(output_variables=["R_BIOMASS"], algorithm="KISAO:0000437"))
    assert data.values[0] == pytest.approx(0.165)


def test_variants():
    with pytest.raises(rt.DataError, match="no variants"):
        rt.backends.get("roadrunner:x")
    assert rt.backends.get("cobra:scipy") is rt.backends.get("cobra:scipy")
    assert rt.backends.get("cobra:scipy") is not rt.backends.get("cobra:glpk")


# ------------------------------------------------------------------------------ scripts

def run_script(tmp_path, doc, *backend_args):
    (tmp_path / "toy.xml").write_text(toy_text())
    p = tmp_path / "00001.sed2.json"
    p.write_text(json.dumps(doc))
    env = dict(os.environ, PYTHONPATH=SRC)
    t = subprocess.run([sys.executable, "-m", "pysed2translate", str(p), *backend_args, "-o", str(tmp_path / "s.py")],
                       capture_output=True, text=True, env=env)
    assert t.returncode == 0, t.stderr
    return subprocess.run([sys.executable, str(tmp_path / "s.py"), "--input-dir", str(tmp_path), "--output-dir", str(tmp_path),
                           "--no-png"], capture_output=True, text=True, env=env)


DOC = {
    "version": "v1.0.0",
    "tasks": {
        "m": {"_type": "modelImport", "location": "toy.xml", "language": "urn:sedml:language:sbml"},
        "f": {"_type": "fluxBalanceAnalysis", "model": "#tasks:m.model", "outputVariables": ["R_BIOMASS", "R_RESP"]},
    },
    "outputs": {"r": {"_type": "report", "data": "#tasks:f"}},
}


@pytest.mark.parametrize("args", [("-b", "cobra"), ("-b", "roadrunner"), ("-b", "copasi", "-b", "fba=cobra:scipy")])
def test_script_writes_the_fluxes(tmp_path, args):
    r = run_script(tmp_path, DOC, *args)
    assert r.returncode == 0, r.stderr
    rows = [ln.split(",") for ln in (tmp_path / "00001.r.csv").read_text().split()]
    assert rows[0][0] == "R_BIOMASS" and float(rows[0][1]) == pytest.approx(0.165)
    assert rows[1][0] == "R_RESP" and float(rows[1][1]) == pytest.approx(6.0)


def test_script_infeasible_fails_the_task(tmp_path):
    doc = json.loads(json.dumps(DOC))
    f = doc["tasks"].pop("f")
    f["model"] = "#tasks:c.model"
    doc["tasks"]["c"] = {"_type": "modelChange", "inputModel": "#tasks:m.model", "setValues": {"R_EX_glc_lower_bound": 0.0}}
    doc["tasks"]["f"] = f
    r = run_script(tmp_path, doc, "-b", "cobra")
    assert r.returncode == 1 and "no optimum" in r.stderr and not (tmp_path / "00001.r.csv").exists()


def test_script_skips_a_model_without_fbc(tmp_path):
    (tmp_path / "plain.xml").write_text('<?xml version="1.0"?><sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1">'
                                        '<model id="p"><listOfCompartments><compartment id="c" constant="true" size="1"/></listOfCompartments></model></sbml>')
    doc = json.loads(json.dumps(DOC))
    doc["tasks"]["m"]["location"] = "plain.xml"
    r = run_script(tmp_path, doc, "-b", "roadrunner")
    assert r.returncode == 11 and r.stderr.startswith("skip: cobra cannot run the model")
