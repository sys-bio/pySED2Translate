"""Conformance tests for the simulator backends: each implemented backend must reproduce analytic solutions.

Model: compartment C = 2; species S1 (concentration 3, in C), A (substanceOnly, amount 4); k1 = 0.5;
J0: S1 -> S2 with rate k1*S1*C; A' = -k1*A.  Concentrations satisfy [S1](t) = 3 exp(-k1 t) and A(t) = 4 exp(-k1 t);
J0 = k1*[S1]*C.  The model has no explicit time dependence, so a run that starts at t0 evolves as if from 0.
"""
import json
import math
import os
import subprocess
import sys

import numpy as np
import pytest

antimony = pytest.importorskip("antimony")

from pysed2translate.runtime import DataError, SbmlModel  # noqa: E402
from pysed2translate.runtime import backends  # noqa: E402
from pysed2translate.runtime.backends import TimeCourse  # noqa: E402

BACKENDS = ("roadrunner", "copasi", "opencor")
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
ABS, REL = 1e-9, 1e-6
K1, S10, A0, C = 0.5, 3.0, 4.0, 2.0

ANT = f"""
model m
  compartment C = {C}
  species S1 in C = {S10}, S2 in C = 0
  substanceOnly species A in C = {A0}
  k1 = {K1}
  J0: S1 -> S2; k1*S1*C
  A' = -k1*A
end
"""


@pytest.fixture(scope="module")
def sbml():
    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString(ANT) >= 0, antimony.getLastError()
    return antimony.getSBMLString("m")


@pytest.fixture
def model(sbml):
    return SbmlModel(sbml, "m.xml")


@pytest.fixture(params=BACKENDS)
def backend(request):
    try:
        return backends.get(request.param)
    except DataError as e:
        if "not implemented" in str(e):
            pytest.skip(str(e))
        raise


def close(actual, expected):
    expected = np.asarray(expected, dtype=float)
    np.testing.assert_allclose(actual, expected, rtol=REL, atol=ABS)


def s1(t):
    return S10 * np.exp(-K1 * np.asarray(t, dtype=float))


def a(t):
    return A0 * np.exp(-K1 * np.asarray(t, dtype=float))


# --------------------------------------------------------------------------- explicit points

def test_explicit_points(backend, model):
    pts = [0.0, 0.5, 1.0, 2.5, 4.0]
    data, _ = backend.time_course(model, TimeCourse(independent_variable="time", output_variables=["S1", "A", "J0", "C", "k1"],
                                                    points=pts))
    assert data.shape == (5, 6)
    assert data.labels[1] == ["time", "S1", "A", "J0", "C", "k1"]
    v = data.values
    close(v[:, 0], pts)
    close(v[:, 1], s1(pts))
    close(v[:, 2], a(pts))
    close(v[:, 3], K1 * s1(pts) * C)
    close(v[:, 4], C)
    close(v[:, 5], K1)


def test_amount_and_concentration_follow_sbml_id_semantics(backend, model):
    data, _ = backend.time_course(model, TimeCourse(independent_variable="time", output_variables=["S1", "S2"], points=[0.0, 1.0]))
    close(data.values[0, 1:], [S10, 0.0])  # S1 and S2 are concentrations
    close(data.values[1, 1], s1(1.0))
    close(data.values[1, 2], S10 - s1(1.0))  # mass conservation in a constant compartment


def test_start_before_first_point(backend, model):
    data, _ = backend.time_course(model, TimeCourse(independent_variable="time", output_variables=["S1"], start=0.0,
                                                    points=[2.0, 3.0]))
    close(data.values[:, 0], [2.0, 3.0])
    close(data.values[:, 1], s1([2.0, 3.0]))


def test_nonzero_start_time(backend, model):
    data, _ = backend.time_course(model, TimeCourse(independent_variable="time", output_variables=["S1"], start=1.0,
                                                    points=[1.0, 2.0]))
    close(data.values[:, 0], [1.0, 2.0])
    close(data.values[:, 1], s1([0.0, 1.0]))  # evolves from the initial state at t = 1


def test_irregular_points_after_a_later_start(backend, model):
    pts = [1.0, 1.5, 4.0, 4.25]
    data, _ = backend.time_course(model, TimeCourse(independent_variable="time", output_variables=["S1", "A"], start=0.0,
                                                    points=pts))
    close(data.values[:, 0], pts)
    close(data.values[:, 1], s1(pts))
    close(data.values[:, 2], a(pts))


def test_single_point(backend, model):
    data, _ = backend.time_course(model, TimeCourse(independent_variable="time", output_variables=["S1"], points=[0.0]))
    assert data.shape == (1, 2)
    close(data.values, [[0.0, S10]])


def test_bad_points(backend, model):
    with pytest.raises(DataError):
        backend.time_course(model, TimeCourse(independent_variable="time", output_variables=["S1"], points=[2.0, 1.0]))
    with pytest.raises(DataError):
        backend.time_course(model, TimeCourse(independent_variable="time", output_variables=["S1"], start=5.0, points=[1.0, 2.0]))


# --------------------------------------------------------------------------- one step, span

def test_one_step(backend, model):
    data, end = backend.time_course(model, TimeCourse(independent_variable="time", output_variables=["S1", "A"], step=2.0))
    assert data.shape == (2,) and data.labels == [["S1", "A"]]
    close(data.values, [s1(2.0), a(2.0)])


def test_span_chooses_its_own_points(backend, model):
    if backend.name == "opencor":  # libopencor has only uniform time courses; the capability table skips such tasks
        with pytest.raises(DataError, match="uniform"):
            backend.time_course(model, TimeCourse(independent_variable="time", output_variables=["S1"], span=(0.0, 3.0)))
        return
    data, _ = backend.time_course(model, TimeCourse(independent_variable="time", output_variables=["S1"], span=(0.0, 3.0)))
    t, y = data.values[:, 0], data.values[:, 1]
    assert t[0] == 0.0 and t[-1] == pytest.approx(3.0) and np.all(np.diff(t) > 0)
    close(y, s1(t))
    assert len(t) >= 3


# --------------------------------------------------------------------------- the model at the end of a run

def test_end_of_run_model_continues_the_simulation(backend, model):
    _, mid = backend.time_course(model, TimeCourse(independent_variable="time", output_variables=["S1"], points=[0.0, 2.0]))
    data, _ = backend.time_course(mid, TimeCourse(independent_variable="time", output_variables=["S1", "A"], points=[0.0, 1.0]))
    close(data.values[:, 1], s1([2.0, 3.0]))
    close(data.values[:, 2], a([2.0, 3.0]))


def test_the_input_model_is_not_changed(backend, model):
    before = model.text
    backend.time_course(model, TimeCourse(independent_variable="time", output_variables=["S1"], points=[0.0, 1.0]))
    assert model.text == before


def test_changed_value_is_used(backend, model):
    changed = model.with_values({"k1": 1.0, "S1": 5.0})
    data, _ = backend.time_course(changed, TimeCourse(independent_variable="time", output_variables=["S1"], points=[0.0, 1.5]))
    close(data.values[:, 1], 5.0 * np.exp(-1.0 * np.array([0.0, 1.5])))


# --------------------------------------------------------------------------- settings and errors

def test_tolerances_can_be_given(backend, model):
    tc = TimeCourse(independent_variable="time", output_variables=["S1"], points=[0.0, 1.0, 2.0],
                    settings={"relativeTolerance": 1e-11, "absoluteTolerance": 1e-13})
    data, _ = backend.time_course(model, tc)
    close(data.values[:, 1], s1([0.0, 1.0, 2.0]))


def test_unknown_variable_and_independent_variable(backend, model):
    with pytest.raises(DataError):
        backend.time_course(model, TimeCourse(independent_variable="time", output_variables=["nope"], points=[0.0, 1.0]))
    with pytest.raises(DataError):
        backend.time_course(model, TimeCourse(independent_variable="x", output_variables=["S1"], points=[0.0, 1.0]))


def test_unsupported_setting_is_an_error_not_ignored(backend, model):
    with pytest.raises(DataError):
        backend.time_course(model, TimeCourse(independent_variable="time", output_variables=["S1"], points=[0.0, 1.0],
                                              settings={"toleranceForRootFinder": 1e-3}))


# --------------------------------------------------------------------------- translated documents

@pytest.mark.parametrize("name", BACKENDS)
@pytest.mark.parametrize("spelling", ["time", "urn:sedml:symbol:time"])
def test_translated_document_runs_end_to_end(tmp_path, sbml, name, spelling):
    results_io = pytest.importorskip("sed2suite.results_io")
    pytest.importorskip("libsed2")
    try:
        backends.get(name)
    except DataError as e:
        pytest.skip(str(e))
    from pysed2translate.translate import translate_file

    (tmp_path / "m.xml").write_text(sbml)
    doc = {"version": "v1.0.0",
           "tasks": {"m1": {"_type": "modelImport", "location": "m.xml", "language": "urn:sedml:language:sbml"},
                     "s": {"_type": "explicitODESimulation", "model": "#tasks:m1.model", "independentVariable": spelling,
                           "outputVariables": ["S1", "A"],
                           "independentVariableRange": {"_type": "numericRange", "start": 0, "end": 4, "numberOfSteps": 4}}},
           "outputs": {"r": {"_type": "report", "data": "#tasks:s"},
                       "col": {"_type": "report", "data": "#tasks:s[0:5, 'S1']"}}}
    path = tmp_path / "doc.sed2.json"
    path.write_text(json.dumps(doc))
    script = tmp_path / "run.py"
    script.write_text(translate_file(str(path), name))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [SRC, os.environ.get("PYTHONPATH", "")])))
    r = subprocess.run([sys.executable, str(script), "--output-dir", str(tmp_path / "out")], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    t = [0, 1, 2, 3, 4]
    got = results_io.read_csv(str(tmp_path / "out" / "doc.r.csv"), ndim=2, column_labels=True)
    # the first column is labelled with the independentVariable attribute as written (outputs.json: labels are
    # `[independentVariable] + outputVariables`)
    assert got.labels[1] == [spelling, "S1", "A"]
    close(got.values[:, 1], s1(t))
    close(got.values[:, 2], a(t))
    col = results_io.read_csv(str(tmp_path / "out" / "doc.col.csv"), ndim=1)
    close(col.values, s1(t))


# --------------------------------------------------------------------------- algorithms (KiSAO)

def _alg_course(model, name, algorithm, points, **settings):
    tc = TimeCourse(independent_variable="time", output_variables=["S1"], points=points, algorithm=algorithm,
                    settings=settings)
    return backends.get(name).time_course(model, tc)[0]


@pytest.mark.parametrize("algorithm", ["KISAO:0000019", "KISAO:0000288", "KISAO:0000280", "KISAO:0000694"])
def test_roadrunner_algorithms(model, algorithm):
    pts = [0.0, 1.0, 2.0, 3.0]
    data = _alg_course(model, "roadrunner", algorithm, pts)
    np.testing.assert_allclose(data.values[:, 1], s1(pts), rtol=1e-5, atol=1e-8)


def test_roadrunner_rk4_is_accurate_with_fine_output(model):
    pts = list(np.linspace(0.0, 2.0, 401))
    data = _alg_course(model, "roadrunner", "KISAO:0000032", pts)
    np.testing.assert_allclose(data.values[:, 1], s1(pts), rtol=1e-6, atol=1e-8)


def test_roadrunner_rejects_algorithms_it_does_not_have(model):
    for algorithm in ("KISAO:0000030", "KISAO:0000088", "KISAO:0000086", "nonsense"):
        with pytest.raises(DataError):
            _alg_course(model, "roadrunner", algorithm, [0.0, 1.0])


def test_roadrunner_cvode_settings_are_applied(model):
    data = _alg_course(model, "roadrunner", None, [0.0, 1.0, 2.0], useStiffSolver=True, maxBDForder=3,
                       maxNumberOfSteps=100000, initialStepSize=1e-6, maxInternalStepSize=0.5, minInternalStepSize=1e-14)
    np.testing.assert_allclose(data.values[:, 1], s1([0.0, 1.0, 2.0]), rtol=1e-6, atol=1e-8)


@pytest.mark.parametrize("algorithm", ["KISAO:0000088", "KISAO:0000304", "KISAO:0000694", None])
def test_copasi_algorithms(model, algorithm):
    pts = [0.0, 1.0, 2.0, 3.0]
    data = _alg_course(model, "copasi", algorithm, pts)
    np.testing.assert_allclose(data.values[:, 1], s1(pts), rtol=1e-5, atol=1e-8)


def test_copasi_rejects_algorithms_it_does_not_have(model):
    for algorithm in ("KISAO:0000019", "KISAO:0000032", "KISAO:0000030", "nonsense"):
        with pytest.raises(DataError):
            _alg_course(model, "copasi", algorithm, [0.0, 1.0])


def test_copasi_uses_ids_not_names():
    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString('model n\n species X = 2, Y = 0\n X is "Ex"\n Y is "Why"\n k = 1\n R: X -> Y; k*X\nend') >= 0
    named = SbmlModel(antimony.getSBMLString("n"))
    data, _ = backends.get("copasi").time_course(named, TimeCourse(independent_variable="time", output_variables=["X", "Y"],
                                                                   points=[0.0, 1.0]))
    close(data.values[1, 1:], [2 * np.exp(-1.0), 2 - 2 * np.exp(-1.0)])


@pytest.mark.parametrize("algorithm,kwargs,rtol", [
    ("KISAO:0000019", {}, 1e-6), ("KISAO:0000694", {}, 1e-6), ("KISAO:0000433", {}, 1e-6),
    ("KISAO:0000288", {}, 1e-6), ("KISAO:0000280", {}, 1e-6),
    ("KISAO:0000032", {"initialStepSize": 1e-3}, 1e-6),
    ("KISAO:0000301", {"initialStepSize": 1e-3}, 1e-3), ("KISAO:0000381", {"initialStepSize": 1e-3}, 1e-3),
    ("KISAO:0000030", {"initialStepSize": 1e-5}, 1e-3),
])
def test_opencor_algorithms(model, algorithm, kwargs, rtol):
    pts = [0.0, 1.0, 2.0, 3.0]
    data = _alg_course(model, "opencor", algorithm, pts, **kwargs)
    np.testing.assert_allclose(data.values[:, 1], s1(pts), rtol=rtol, atol=1e-8)


def test_opencor_fixed_step_default_step_is_fine_enough(model):
    pts = [0.0, 1.0, 2.0]
    data = _alg_course(model, "opencor", "KISAO:0000032", pts)  # rk4, step = spacing / 100
    np.testing.assert_allclose(data.values[:, 1], s1(pts), rtol=1e-6, atol=1e-8)


def test_opencor_rejects_algorithms_and_settings_it_lacks(model):
    for algorithm in ("KISAO:0000088", "nonsense"):
        with pytest.raises(DataError):
            _alg_course(model, "opencor", algorithm, [0.0, 1.0])
    with pytest.raises(DataError):
        _alg_course(model, "opencor", None, [0.0, 1.0], maxBDForder=3)
    with pytest.raises(DataError):
        _alg_course(model, "opencor", "KISAO:0000032", [0.0, 1.0], relativeTolerance=1e-6)


def test_opencor_cvode_settings(model):
    data = _alg_course(model, "opencor", None, [0.0, 1.0, 2.0], useStiffSolver=False, maxNumberOfSteps=100000,
                       maxInternalStepSize=0.1, relativeTolerance=1e-9, absoluteTolerance=1e-12)
    np.testing.assert_allclose(data.values[:, 1], s1([0.0, 1.0, 2.0]), rtol=1e-5, atol=1e-8)


# --------------------------------------------------------------------------- models a simulator cannot run

EVENT_MODEL = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="ev">
    <listOfParameters><parameter id="x" value="1" constant="false"/></listOfParameters>
    <listOfRules>
      <rateRule variable="x"><math xmlns="http://www.w3.org/1998/Math/MathML"><apply><minus/><ci>x</ci></apply></math></rateRule>
    </listOfRules>
    <listOfEvents>
      <event id="e" useValuesFromTriggerTime="true">
        <trigger initialValue="false" persistent="true"><math xmlns="http://www.w3.org/1998/Math/MathML"><apply><gt/><csymbol encoding="text" definitionURL="http://www.sbml.org/sbml/symbols/time">t</csymbol><cn>1</cn></apply></math></trigger>
        <listOfEventAssignments><eventAssignment variable="x"><math xmlns="http://www.w3.org/1998/Math/MathML"><cn>5</cn></math></eventAssignment></listOfEventAssignments>
      </event>
    </listOfEvents>
  </model>
</sbml>
"""


def test_opencor_refuses_a_model_with_events_instead_of_leaving_them_out(tmp_path):
    """sbml2cellml converts events away without a warning; the backend must say so, not return a wrong time course."""
    pytest.importorskip("libopencor")
    pytest.importorskip("sbml2cellml")
    from pysed2translate.runtime import BackendCannotRun

    (tmp_path / "ev.xml").write_text(EVENT_MODEL)
    model = SbmlModel.load(str(tmp_path / "ev.xml"), "urn:sedml:language:sbml")
    assert model.has_events()
    with pytest.raises(BackendCannotRun, match="events"):
        backends.get("opencor").time_course(model, TimeCourse(independent_variable="time", output_variables=["x"],
                                                              points=[0.0, 1.0, 2.0]))


@pytest.mark.parametrize("name", ["roadrunner", "copasi"])
def test_other_backends_run_a_model_with_events(tmp_path, name):
    try:
        backend = backends.get(name)
    except DataError as e:
        pytest.skip(str(e))
    (tmp_path / "ev.xml").write_text(EVENT_MODEL)
    model = SbmlModel.load(str(tmp_path / "ev.xml"), "urn:sedml:language:sbml")
    data, _ = backend.time_course(model, TimeCourse(independent_variable="time", output_variables=["x"],
                                                    points=[0.0, 0.5, 1.5, 2.5]))
    # x' = -x from 1; at t = 1 the event sets x = 5, so x(1.5) = 5 exp(-0.5) and x(2.5) = 5 exp(-1.5)
    assert data.values[1, 1] == pytest.approx(math.exp(-0.5), rel=1e-5)
    assert data.values[2, 1] == pytest.approx(5 * math.exp(-0.5), rel=1e-5)
    assert data.values[3, 1] == pytest.approx(5 * math.exp(-1.5), rel=1e-5)


def test_a_script_exits_with_the_skip_status_when_the_backend_cannot_run_the_model(tmp_path):
    pytest.importorskip("libsed2")
    pytest.importorskip("libopencor")
    pytest.importorskip("sbml2cellml")
    from pysed2translate.errors import EXIT_UNSUPPORTED
    from pysed2translate.runtime import EXIT_CANNOT_RUN
    from pysed2translate.translate import translate_file

    assert EXIT_CANNOT_RUN == EXIT_UNSUPPORTED
    (tmp_path / "ev.xml").write_text(EVENT_MODEL)
    doc = {"version": "v1.0.0",
           "tasks": {"m": {"_type": "modelImport", "location": "ev.xml", "language": "urn:sedml:language:sbml"},
                     "s": {"_type": "explicitODESimulation", "model": "#tasks:m.model", "independentVariable": "time",
                           "outputVariables": ["x"],
                           "independentVariableRange": {"_type": "numericRange", "start": 0, "end": 2, "numberOfSteps": 2}}},
           "outputs": {"r": {"_type": "report", "data": "#tasks:s"}}}
    path = tmp_path / "doc.sed2.json"
    path.write_text(json.dumps(doc))
    script = tmp_path / "run.py"
    script.write_text(translate_file(str(path), "opencor"))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [SRC, os.environ.get("PYTHONPATH", "")])))
    r = subprocess.run([sys.executable, str(script), "--output-dir", str(tmp_path / "out")], capture_output=True, text=True,
                       env=env)
    assert r.returncode == EXIT_UNSUPPORTED, r.stderr
    assert "skip: opencor cannot run the model" in r.stderr and "events" in r.stderr
    assert not (tmp_path / "out").exists() or not list((tmp_path / "out").glob("*.csv"))
