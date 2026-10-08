import pytest

from pysed2translate import kisao
from pysed2translate.capabilities import load_table
from pysed2translate.errors import UnsupportedTaskError

BACKENDS = ("roadrunner", "copasi", "opencor")


def sim(**extra):
    d = {"_type": "explicitODESimulation", "model": "#tasks:m.model", "independentVariable": "time",
         "outputVariables": ["S1"], "independentVariableRange": {"_type": "numericRange", "numberOfSteps": 3}}
    d.update(extra)
    return d


@pytest.mark.parametrize("text,number", [("KISAO:0000019", 19), ("kisao_0000694", 694), ("KISAO:0000032", 32),
                                         ("KISAO:19", None), ("19", None), ("CVODE", None), ("", None), (None, None)])
def test_term_number(text, number):
    assert kisao.term_number(text) == number


def test_every_backend_has_the_generic_ode_solver():
    for b in BACKENDS:
        assert kisao.ode_solver(b, None) is not None
        assert kisao.ode_solver(b, kisao.GENERIC_ODE_SOLVER) == kisao.ode_solver(b, None)


@pytest.mark.parametrize("backend,algorithm,ok", [
    ("roadrunner", "KISAO:0000019", True), ("roadrunner", "KISAO:0000288", True), ("roadrunner", "KISAO:0000086", False),
    ("roadrunner", "KISAO:0000030", False), ("roadrunner", "KISAO:0000088", False),
    ("copasi", "KISAO:0000088", True), ("copasi", "KISAO:0000304", True), ("copasi", "KISAO:0000019", False),
    ("opencor", "KISAO:0000019", True), ("opencor", "KISAO:0000030", True), ("opencor", "KISAO:0000301", True),
    ("opencor", "KISAO:0000088", False), ("opencor", "nonsense", False),
])
def test_algorithm_support(backend, algorithm, ok):
    problem = kisao.algorithm_problem(backend, algorithm)
    assert (problem is None) == ok, problem
    if not ok:
        assert algorithm.lower() in problem.lower() or "KiSAO" in problem


def test_settings_problem_names_the_unsupported_settings():
    assert kisao.settings_problem("roadrunner", {"relativeTolerance": 1e-8}) is None
    msg = kisao.settings_problem("opencor", {"relativeTolerance": 1e-8, "maxBDForder": 3, "useReducedModel": True})
    assert "maxBDForder" in msg and "useReducedModel" in msg and "relativeTolerance" not in msg
    assert kisao.settings_problem("roadrunner", {"absoluteTolerance": 1e-8}, "rk4") is not None  # rk4 has no settings
    assert kisao.settings_problem("roadrunner", {"absoluteTolerance": 1e-8}, "cvode") is None


def test_bounded_simulations_need_a_variable_step_solver():
    assert kisao.step_problem("roadrunner", {}) is None
    assert "fixed step" in kisao.step_problem("roadrunner", {"workingAlgorithms": [{"algorithm": "KISAO:0000032"}]})
    assert "fixed step" in kisao.step_problem("opencor", {"workingAlgorithms": [{"algorithm": "KISAO:0000030"}]})
    assert kisao.step_problem("opencor", {"workingAlgorithms": [{"algorithm": "KISAO:0000019"}]}) is None
    assert "absoluteToleranceVector" in kisao.settings_problem("roadrunner", {"absoluteToleranceVector": [1]})


def test_tolerance_defaults_are_tight():
    assert kisao.DEFAULT_ABSOLUTE_TOLERANCE <= 1e-10 and kisao.DEFAULT_RELATIVE_TOLERANCE <= 1e-8


# --------------------------------------------------------------------------- capability integration

@pytest.mark.parametrize("task_type", ["explicitODESimulation", "boundedODESimulation", "oneStepODESimulation"])
def test_plain_ode_tasks_are_supported_wherever_the_backend_can_run_them(task_type):
    table = load_table()
    for b in BACKENDS:
        verdict = table.verdict(b, task_type, {"_type": task_type})
        if (b, task_type) == ("opencor", "boundedODESimulation"):  # libopencor has uniform time courses only
            assert "uniform" in verdict
        else:
            assert verdict is None


def test_capability_check_skips_unsupported_algorithms_and_settings():
    table = load_table()
    wa = [{"algorithm": "KISAO:0000019"}]
    assert table.verdict("roadrunner", "explicitODESimulation", sim(workingAlgorithms=wa)) is None
    assert table.verdict("copasi", "explicitODESimulation", sim(workingAlgorithms=wa)) is not None
    with pytest.raises(UnsupportedTaskError, match="COPASI has no CVODE"):
        table.check_task("copasi", "s", "explicitODESimulation", sim(workingAlgorithms=wa))
    assert "maxBDForder" in table.verdict("opencor", "explicitODESimulation", sim(maxBDForder=2))
    assert table.verdict("roadrunner", "explicitODESimulation", sim(maxBDForder=2)) is None
    assert "reference" in table.verdict("roadrunner", "explicitODESimulation", sim(workingAlgorithms=[{"algorithm": "#constants:a"}]))
    assert "more than one" in table.verdict("roadrunner", "explicitODESimulation",
                                            sim(workingAlgorithms=[{"algorithm": "KISAO:0000019"}, {"algorithm": "KISAO:0000032"}]))
    assert "taskParameters" in table.verdict("roadrunner", "explicitODESimulation", sim(taskParameters={"p": {"value": 1}}))


def test_document_check_reaches_the_simulation():
    table = load_table()
    doc = {"tasks": {"s": sim(workingAlgorithms=[{"algorithm": "KISAO:0000088"}])}}
    table.check_document("copasi", doc)
    with pytest.raises(UnsupportedTaskError):
        table.check_document("roadrunner", doc)


# --------------------------------------------------------------------------- tables against the real simulators

def test_opencor_ids_are_those_of_libopencor():
    oc = pytest.importorskip("libopencor")
    solvers = {"cvode": oc.SolverCvode, "forward_euler": oc.SolverForwardEuler, "rk4": oc.SolverFourthOrderRungeKutta,
               "heun": oc.SolverHeun, "rk2": oc.SolverSecondOrderRungeKutta}
    for number, (name, _) in kisao.ODE_ALGORITHMS["opencor"].items():
        if number in (694, 433, 288, 280, 261):  # generic / alias terms
            continue
        assert solvers[name]().id == f"KISAO:{number:07d}", (number, name)


def test_copasi_methods_exist_in_basico():
    basico = pytest.importorskip("basico")
    valid = {m.lower() for m in basico.get_valid_methods(basico.T.TIME_COURSE)}
    for name, _ in kisao.ODE_ALGORITHMS["copasi"].values():
        assert f"deterministic ({name})" in valid, name
