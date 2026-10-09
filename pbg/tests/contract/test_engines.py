"""Engine-agnostic acceptance tests (rule M5): every engine found is run through translate -> run -> compare on a spread of
suite cases.  Only the engine interface and the suite helpers are used.  The whole suite is `pysed2translate-pbg suite`."""
import os

import pytest

from pysed2translate_pbg import engines, host, suite as pbg_suite
from conftest import simulator_available

# spread over the suite's series: constants/reports, calculations, ranges, ODE kinds, ModelChange, steady state, Jacobian,
# Loop, Scatter, ParameterScan, CsvImport, plots (found by looking at the case descriptions; see the README of this folder)
CASES = ["00001", "00020", "00040", "00060", "00080", "00100", "00120", "00140", "00160", "00180", "00200", "00220", "00240", "00260"]
SIMULATORS = ["roadrunner", "copasi", "opencor"]


def _case_dir(suite, case):
    return os.path.join(suite.cases_dir, case)


@pytest.mark.parametrize("engine", engines.names())
@pytest.mark.parametrize("backend", SIMULATORS)
@pytest.mark.parametrize("case", CASES)
def test_case_agrees_with_canonical_data(engine, backend, case, suite, tmp_path):
    if not simulator_available(backend):
        pytest.skip(f"{backend} is not installed")
    if not os.path.isdir(_case_dir(suite, case)):
        pytest.skip(f"no case {case}")
    r = pbg_suite.run_case(suite, engine, _case_dir(suite, case), {"*": backend}, str(tmp_path), engine_options={"wrappers": "off"})
    assert r.status in (host.PASS, host.SKIP), f"{case} {backend}: {r.status} {r.reason}"


@pytest.mark.parametrize("engine", engines.names())
def test_engine_interface(engine):
    mod = engines.load(engine)
    assert mod.NAME == engine
    assert callable(mod.translate) and callable(mod.run) and callable(mod.add_arguments)
    assert isinstance(mod.VERSION, str)
