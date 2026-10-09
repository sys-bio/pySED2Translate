"""Tier C: process-bigraph documents whose behaviour is pinned by scripts translated from them (pbg/tools/pbg2py.py).

For each case: the rows process-bigraph produces (expected_framework) must equal the rows of the script under the `start` reading
(except where the case says otherwise), and the committed script must be what the exporter writes now.  C5 compares the report
files of the engine and of the exported script."""
import glob
import json
import os
import subprocess
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.abspath(os.path.join(HERE, "..", "..", "tools"))
if not os.path.isdir(TOOLS):
    pytest.skip("pbg/tools is absent", allow_module_level=True)
sys.path.insert(0, TOOLS)
import pbg2py  # noqa: E402

pytest.importorskip("process_bigraph")
CASES = sorted(os.path.basename(p)[: -len(".case.json")] for p in glob.glob(os.path.join(HERE, "*.case.json")))
ENV = {**os.environ, "PYTHONPATH": HERE + os.pathsep + os.environ.get("PYTHONPATH", "")}
# the event reading differs from the framework where intervals differ (pbg/upstream/P-3.md)
EVENT_DIFFERS = {"c2_unequal_intervals"}


def load(name, suffix):
    with open(os.path.join(HERE, f"{name}.{suffix}"), encoding="utf-8") as f:
        return json.load(f)


def run_script(path, *args):
    r = subprocess.run([sys.executable, path, *args], capture_output=True, text=True, env=ENV)
    assert r.returncode == 0, r.stderr
    return r.stdout


def rounded(rows):
    return [[row[0]] + [round(v, 6) for v in row[1:]] for row in rows]


@pytest.mark.parametrize("name", CASES)
@pytest.mark.parametrize("mode", ["start", "event"])
def test_script_rows(name, mode):
    if name.startswith("c3") and not os.environ.get("PBG_RUN_C3"):
        pytest.skip("C3 runs roadrunner and cobra; set PBG_RUN_C3=1 (the committed rows are checked in test_committed_scripts)")
    rows = rounded(json.loads(run_script(os.path.join(HERE, f"{name}.script_{mode}.py")).strip().splitlines()[-1]))
    assert rows == load(name, f"expected_{mode}.json")
    framework = load(name, "expected_framework.json")
    if mode == "start" or name not in EVENT_DIFFERS:
        assert rows == framework
    else:
        assert rows != framework


@pytest.mark.parametrize("name", CASES)
@pytest.mark.parametrize("mode", ["start", "event"])
def test_committed_scripts_are_what_the_exporter_writes(name, mode):
    case = load(name, "case.json")
    state = load(name, "pbg.composite.json")["state"]
    with open(os.path.join(HERE, f"{name}.script_{mode}.py"), encoding="utf-8") as f:
        assert f.read() == pbg2py.export(state, case["end"], mode, case["watch"])


def test_c3_differs_from_the_sequential_loop_in_the_stated_way():
    """The process-coupled culture (equal intervals, both processes read the state at the start of the interval) uses the FBA result
    one interval later than the Loop of suite case 00282, so growth runs ahead of the Loop's; the first interval is the same."""
    rows = load("c3_ode_fba_processes", "expected_framework.json")
    seq = [[1.0, 9.896621, 0.030338], [8.0, 4.99417, 0.520583]]      # the Loop (suite case 00282): t, S, B
    assert rows[1][1:3] == seq[0][1:3]
    assert rows[8][1] < seq[1][1] and rows[8][2] > seq[1][2]


def test_c5_engine_and_exported_script_write_the_same_report(tmp_path):
    h5py = pytest.importorskip("h5py")
    pytest.importorskip("cobra")
    a, b = tmp_path / "engine", tmp_path / "script"
    a.mkdir(), b.mkdir()
    data = os.path.join(HERE, "data")
    from pysed2translate_pbg.engines import v1

    assert v1.run(os.path.join(HERE, "c5_cosimulation_clock.pbg.composite.json"), data, str(a), png=False) == 0
    run_script(os.path.join(HERE, "c5_cosimulation_clock.script.py"), data, str(b))
    with h5py.File(a / "00282.cosim_output.h5") as fa, h5py.File(b / "00282.cosim_output.h5") as fb:
        assert np.array_equal(fa["data"][()], fb["data"][()])
        assert fa["data"].shape == (8, 5, 4)
