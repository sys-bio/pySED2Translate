"""The real CRM-FBA model (iAF1260) through the PBG engine.  The model is NOT stored in this repository: it is read from
$CRM_FBA_MODEL_DIR (a folder holding iAF1260.xml) or downloaded from the pinned commit of vivarium-collective/CRM-FBA into
a temporary cache.  The test is skipped when the file cannot be had or its checksum differs.

The expected numbers are a regression record (glpk, cobra 0.32.1), not canonical results: nobody has derived them by hand.
"""
import hashlib
import json
import os
import sys
import tempfile
import urllib.request

import numpy as np
import pytest

pytest.importorskip("cobra")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "v1"))   # helpers.py

COMMIT = "4eba24cda40ed16cd217c74ecb0377e4b867186c"
SHA256 = "621ca0ac9d2d49931f8a3d22d03256f80b1f6df562160d23a9f7e9a727c24fcb"
URL = f"https://raw.githubusercontent.com/vivarium-collective/CRM-FBA/{COMMIT}/crm_dfba/models/iAF1260.xml"
BIOMASS = "R_BIOMASS_Ec_iAF1260_core_59p81M"


def _checked(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest() == SHA256


@pytest.fixture(scope="module")
def model_dir():
    given = os.environ.get("CRM_FBA_MODEL_DIR")
    if given and _checked(os.path.join(given, "iAF1260.xml")):
        return given
    cache = os.path.join(tempfile.gettempdir(), "pysed2translate-pbg-crmfba")
    path = os.path.join(cache, "iAF1260.xml")
    if not os.path.exists(path) or not _checked(path):
        try:
            os.makedirs(cache, exist_ok=True)
            urllib.request.urlretrieve(URL, path)
        except OSError as e:
            pytest.skip(f"cannot download the CRM-FBA model: {e}")
    if not _checked(path):
        pytest.skip("the downloaded iAF1260.xml does not have the pinned checksum")
    return cache


def test_glucose_uptake_scan_on_the_real_model(model_dir, tmp_path):
    from pysed2translate_pbg.api import Options
    from pysed2translate_pbg import host
    from pysed2translate_pbg.engines import v1
    from helpers import run_in_process, data_of

    doc = {"version": "v1.0.0", "tasks": {
        "m": {"_type": "modelImport", "location": "iAF1260.xml", "language": "urn:sedml:language:sbml"},
        "sc": {"_type": "scatter", "range": {"_type": "range", "values": [-10, -5, -1]},
               "subTasks": {
                   "c": {"_type": "modelChange", "inputModel": "#tasks:m.model",
                         "setValues": {"R_EX_glc__D_e_lower_bound": "#tasks:sc.range"}},
                   "f": {"_type": "fluxBalanceAnalysis", "model": "#tasks:sc:subTasks:c.model",
                         "outputVariables": [BIOMASS, "R_EX_glc__D_e", "R_EX_o2_e"]}},
               "outputVariableMap": {"F": "#tasks:sc:subTasks:f"}}}}
    p = tmp_path / "real.sed2.json"
    p.write_text(json.dumps(doc))
    pbg = json.loads(next(iter(v1.translate(host.load_document(str(p)), Options(
        backend={"fba": "cobra:glpk"}, prefix="real", source_name="real.sed2.json", engine={"wrappers": "off"})).files.values())))
    state = run_in_process(pbg, input_dir=model_dir, tmp_path=tmp_path)
    d = data_of(state, "sc")
    assert d.shape == (3, 1, 3)
    assert np.allclose(d.values[:, 0, 0], [0.885571, 0.447814, 0.062485], atol=1e-5)
    assert np.allclose(d.values[:, 0, 1], [-10, -5, -1])
