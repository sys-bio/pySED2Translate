"""Conformance tests for SteadyState, JacobianFull and JacobianReduced: the backends must reproduce analytic results.

OPEN:   compartment C=2; $Src -> S1 (rate k0*C); S1 -> S2 (k1*S1*C); S2 -> $Snk (k2*S2*C); k0=2, k1=0.5, k2=1.
        d[S1]/dt = k0 - k1 [S1]; d[S2]/dt = k1 [S1] - k2 [S2].  Steady state [S1] = 4, [S2] = 2; J1 = k1*[S1]*C = 4.
        Jacobian [[-k1, 0], [k1, -k2]].
MIXED:  A is substanceOnly (an amount), B a concentration, compartment size 2: dA/dt = 1 - 0.5 A,
        d[B]/dt = 0.25 A - 0.25 [B].  Steady state A = B = 2.  Jacobian (A amount, B concentration)
        [[-0.5, 0], [0.25, -0.25]].
SIZES:  P in C1 = 1, Q in C2 = 4: d[P]/dt = 3 - 1.5 [P]; d[Q]/dt = (1.5 [P] - 2 [Q]) / 4.  Steady [P] = 2, [Q] = 1.5.
        Jacobian [[-1.5, 0], [0.375, -0.5]].
CLOSED: A <-> B with k1 = 2, k2 = 1 and A + B = 4: steady state A = 4/3, B = 8/3; full Jacobian [[-2, 1], [2, -1]];
        reduced Jacobian [[-3]] (for whichever species is independent).
BIMOL:  A + B -> C with rate k*A*B, k = 0.7, A = 2, B = 3, C = 1: Jacobian [[-kB, -kA, 0], [-kB, -kA, 0], [kB, kA, 0]].
"""
import json
import os
import subprocess
import sys

import numpy as np
import pytest

antimony = pytest.importorskip("antimony")

from pysed2translate import kisao  # noqa: E402
from pysed2translate.capabilities import load_table  # noqa: E402
from pysed2translate.runtime import DataError, SbmlModel  # noqa: E402
from pysed2translate.runtime import backends  # noqa: E402
from pysed2translate.runtime.backends import SteadyState, TimeCourse  # noqa: E402

BACKENDS = ("roadrunner", "copasi")   # OpenCOR has no steady state or Jacobian (capabilities.json)
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
ABS, REL = 1e-9, 1e-6

ANT = """
model open
  compartment C = 2
  species S1 in C = 1, S2 in C = 0.5
  $Src -> S1; k0*C
  J1: S1 -> S2; k1*S1*C
  S2 -> $Snk; k2*S2*C
  k0 = 2; k1 = 0.5; k2 = 1
end
model open0
  compartment C = 2
  species S1 in C = 1, S2 in C = 0
  $Src -> S1; k0*C
  J1: S1 -> S2; k1*S1*C
  S2 -> $Snk; k2*S2*C
  k0 = 2; k1 = 0.5; k2 = 1
end
model mixed
  compartment C = 2
  substanceOnly species A in C = 4
  species B in C = 1
  $Src -> A; 1
  A -> B; 0.5*A
  B -> $Snk; 0.25*B*C
end
model sizes
  compartment C1 = 1, C2 = 4
  species P in C1 = 2, Q in C2 = 1
  $Src -> P; 3*C1
  J1: P -> Q; k1*P*C1
  Q -> $Snk; k2*Q*C2
  k1 = 1.5; k2 = 0.5
end
model closed
  compartment C = 1
  species A in C = 3, B in C = 1
  J1: A -> B; k1*A
  J2: B -> A; k2*B
  k1 = 2; k2 = 1
end
model bimol
  compartment C = 1
  species A in C = 2, B in C = 3, Cc in C = 1
  J1: A + B -> Cc; k*A*B
  k = 0.7
end
model growth
  species S = 1
  S' = 1
end
model reordered
  compartment C = 1
  species Z in C = 1, Y in C = 2, X in C = 3
  $Src -> Z; 1
  Z -> Y; 2*Z
  Y -> X; 1*Y
  X -> $Snk; 0.5*X
end
"""


@pytest.fixture(scope="module")
def sbml():
    antimony.clearPreviousLoads()
    assert antimony.loadAntimonyString(ANT) >= 0, antimony.getLastError()
    return {n: antimony.getSBMLString(n) for n in
            ("open", "open0", "mixed", "sizes", "closed", "bimol", "growth", "reordered")}


@pytest.fixture
def models(sbml):
    return {n: SbmlModel(t, n + ".xml") for n, t in sbml.items()}


@pytest.fixture(params=BACKENDS)
def backend(request):
    try:
        return backends.get(request.param)
    except DataError as e:
        if "not implemented" in str(e):
            pytest.skip(str(e))
        raise


def close(actual, expected):
    np.testing.assert_allclose(np.asarray(actual, dtype=float), np.asarray(expected, dtype=float), rtol=REL, atol=ABS)


def ss(variables, **kw):
    return SteadyState(independent_variable="time", output_variables=variables, **kw)


# --------------------------------------------------------------------------- steady state

def test_steady_state_values(backend, models):
    data, _ = backend.steady_state(models["open"], ss(["S1", "S2", "C", "k1", "J1"]))
    assert data.shape == (5,)
    assert data.labels[0] == ["S1", "S2", "C", "k1", "J1"]
    close(data.values, [4, 2, 2, 0.5, 4])


def test_steady_state_amount_species_and_other_sizes(backend, models):
    data, _ = backend.steady_state(models["mixed"], ss(["A", "B"]))
    close(data.values, [2, 2])
    data, _ = backend.steady_state(models["sizes"], ss(["P", "Q"]))
    close(data.values, [2, 1.5])


def test_steady_state_of_a_conserved_system(backend, models):
    data, _ = backend.steady_state(models["closed"], ss(["A", "B"]))
    close(data.values, [4 / 3, 8 / 3])


def test_steady_state_model_is_at_steady_state(backend, models):
    _, end = backend.steady_state(models["open"], ss(["S1"]))
    # a time course from the steady-state model does not move
    for name in BACKENDS:
        out, _ = backends.get(name).time_course(end, TimeCourse(independent_variable="time", output_variables=["S1", "S2"],
                                                                points=[0.0, 3.0]))
        close(out.values[:, 1:], [[4, 2], [4, 2]])


def test_the_input_model_is_not_changed(backend, models):
    before = models["open"].text
    backend.steady_state(models["open"], ss(["S1"]))
    assert models["open"].text == before


def test_no_steady_state_is_an_error(backend, models):
    with pytest.raises(DataError):
        backend.steady_state(models["growth"], ss(["S"]))


def test_time_and_other_independent_variables_are_errors(backend, models):
    with pytest.raises(DataError, match="time"):
        backend.steady_state(models["open"], ss(["time"]))
    with pytest.raises(DataError, match="independent variable"):
        backend.steady_state(models["open"], SteadyState(independent_variable="x", output_variables=["S1"]))


def test_unknown_output_variable(backend, models):
    with pytest.raises(DataError):
        backend.steady_state(models["open"], ss(["nope"]))


def test_generic_steady_state_algorithm_only(backend, models):
    data, _ = backend.steady_state(models["open"], ss(["S1"], algorithm="KISAO:0000407"))
    close(data.values, [4])
    with pytest.raises(DataError, match="KISAO"):
        backend.steady_state(models["open"], ss(["S1"], algorithm="KISAO:0000019"))
    with pytest.raises(DataError, match="KiSAO"):
        backend.steady_state(models["open"], ss(["S1"], algorithm="newton"))


# --------------------------------------------------------------------------- Jacobians

def test_full_jacobian(backend, models):
    j = backend.jacobian(models["open"])
    assert j.labels == [["S1", "S2"], ["S1", "S2"]]
    close(j.values, [[-0.5, 0], [0.5, -1]])


def test_jacobian_uses_sbml_id_semantics(backend, models):
    j = backend.jacobian(models["mixed"])
    assert j.labels[0] == ["A", "B"]
    close(j.values, [[-0.5, 0], [0.25, -0.25]])
    j = backend.jacobian(models["sizes"])
    close(j.values, [[-1.5, 0], [0.375, -0.5]])


def test_jacobian_of_a_nonlinear_model(backend, models):
    k = 0.7
    j = backend.jacobian(models["bimol"])
    close(j.values, [[-k * 3, -k * 2, 0], [-k * 3, -k * 2, 0], [k * 3, k * 2, 0]])


def test_jacobian_rows_and_columns_follow_the_models_species_order(backend, models):
    j = backend.jacobian(models["reordered"])
    assert j.labels == [["Z", "Y", "X"], ["Z", "Y", "X"]]
    close(j.values, [[-2, 0, 0], [2, -1, 0], [0, 1, -0.5]])


def test_jacobian_is_at_the_models_current_state(backend, models):
    # this Jacobian depends on the state
    changed = models["bimol"].with_values({"A": 5.0, "B": 1.0})
    j = backend.jacobian(changed)
    close(j.values, [[-0.7, -3.5, 0], [-0.7, -3.5, 0], [0.7, 3.5, 0]])


def test_full_jacobian_of_a_conserved_system(backend, models):
    close(backend.jacobian(models["closed"]).values, [[-2, 1], [2, -1]])


def test_reduced_jacobian_keeps_the_independent_species(backend, models):
    j = backend.jacobian(models["closed"], reduced=True)
    assert j.shape == (1, 1)
    assert j.labels[0] == j.labels[1] and j.labels[0][0] in ("A", "B")
    close(j.values, [[-3]])


def test_reduced_jacobian_without_conservation_is_the_full_one(backend, models):
    j = backend.jacobian(models["open"], reduced=True)
    assert j.labels[0] == ["S1", "S2"]
    close(j.values, [[-0.5, 0], [0.5, -1]])


def test_roadrunner_jacobian_at_zero_values(models):
    close(backends.get("roadrunner").jacobian(models["open0"]).values, [[-0.5, 0], [0.5, -1]])


def test_copasi_refuses_to_differentiate_at_zero(models):
    with pytest.raises(DataError, match="value is 0"):
        backends.get("copasi").jacobian(models["open0"])


def test_opencor_has_neither(models):
    pytest.importorskip("libopencor")
    b = backends.get("opencor")
    with pytest.raises(DataError):
        b.steady_state(models["open"], ss(["S1"]))
    with pytest.raises(DataError):
        b.jacobian(models["open"])


# --------------------------------------------------------------------------- capability table

def test_capabilities():
    table = load_table()
    for task in ("steadyState", "jacobianFull", "jacobianReduced"):
        assert table.verdict("roadrunner", task, {"_type": task}) is None
        assert table.verdict("copasi", task, {"_type": task}) is None
        assert table.verdict("opencor", task, {"_type": task}) is not None
    ok = {"_type": "steadyState", "workingAlgorithms": [{"algorithm": "KISAO:0000407"}]}
    assert table.verdict("roadrunner", "steadyState", ok) is None
    bad = {"_type": "steadyState", "workingAlgorithms": [{"algorithm": "KISAO:0000019"}]}
    assert "KISAO:0000019" in table.verdict("copasi", "steadyState", bad)
    assert "reference" in table.verdict("copasi", "steadyState", {"workingAlgorithms": [{"algorithm": "#constants:a"}]})
    assert "taskParameters" in table.verdict("copasi", "jacobianFull", {"taskParameters": [{"id": "p"}]})
    assert kisao.steady_state_problem("roadrunner", None) is None


# --------------------------------------------------------------------------- translated documents

@pytest.mark.parametrize("name", BACKENDS)
def test_translated_document_runs_end_to_end(tmp_path, sbml, name):
    results_io = pytest.importorskip("sed2suite.results_io")
    pytest.importorskip("libsed2")
    from pysed2translate.translate import translate_file

    (tmp_path / "m.xml").write_text(sbml["open"])
    doc = {"version": "v1.0.0",
           "tasks": {"m1": {"_type": "modelImport", "location": "m.xml", "language": "urn:sedml:language:sbml"},
                     "ss": {"_type": "steadyState", "model": "#tasks:m1.model", "outputVariables": ["S1", "S2", "J1"]},
                     "jf": {"_type": "jacobianFull", "model": "#tasks:ss.model"},
                     "jr": {"_type": "jacobianReduced", "model": "#tasks:m1.model"}},
           "outputs": {"r": {"_type": "report", "data": "#tasks:ss"},
                       "s1": {"_type": "report", "data": "#tasks:ss['S1']"},
                       "jf": {"_type": "report", "data": "#tasks:jf"},
                       "jr": {"_type": "report", "data": "#tasks:jr"}}}
    path = tmp_path / "doc.sed2.json"
    path.write_text(json.dumps(doc))
    script = tmp_path / "run.py"
    script.write_text(translate_file(str(path), name))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [SRC, os.environ.get("PYTHONPATH", "")])))
    r = subprocess.run([sys.executable, str(script), "--output-dir", str(tmp_path / "out")], capture_output=True,
                       text=True, env=env)
    assert r.returncode == 0, r.stderr
    got = results_io.read_csv(str(tmp_path / "out" / "doc.r.csv"), ndim=1, row_labels=True)
    assert got.labels[0] == ["S1", "S2", "J1"]
    close(got.values, [4, 2, 4])
    close(results_io.read_csv(str(tmp_path / "out" / "doc.s1.csv"), ndim=0).values, 4)
    for out in ("jf", "jr"):
        j = results_io.read_csv(str(tmp_path / "out" / f"doc.{out}.csv"), ndim=2, row_labels=True, column_labels=True)
        assert j.labels[1] == ["S1", "S2"]
        close(j.values, [[-0.5, 0], [0.5, -1]])
