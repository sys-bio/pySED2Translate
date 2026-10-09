import copy
import json
import os
import subprocess
import sys

import pytest

from pysed2translate import capabilities as cap
from pysed2translate import errors
from pysed2translate.backends import ALL_BACKENDS, BACKENDS

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")

DEFERRED = ["boundedStochasticSimulation", "explicitStochasticSimulation", "oneStepStochasticSimulation",
            "drawFromDistribution"]


def entry(**kw):
    return {"supported": True, **kw}


def table(tasks, backends=("a", "b")):
    return {"schemaVersion": 1, "backends": list(backends), "tasks": tasks}


def test_shipped_table_is_valid():
    t = cap.load_table()
    assert t.backends == list(ALL_BACKENDS)


def libsed2_task_types():
    libsed2 = pytest.importorskip("libsed2")
    import libsed2.model as M
    out = []
    for name in dir(M):
        c = getattr(M, name)
        if isinstance(c, type) and getattr(c, "_TYPE_CONST", None) and M._dispatch_AbstractTask(c._TYPE_CONST) is c:
            out.append(c._TYPE_CONST)
    return sorted(out)


def test_every_libsed2_task_class_has_an_entry_for_every_backend():
    t = cap.load_table()
    types = libsed2_task_types()
    assert len(types) >= 25  # sanity: the discovery found the task classes
    missing = [(ty, b) for ty in types for b in ALL_BACKENDS if t.entry(b, ty) is None]
    assert missing == []


def test_table_has_no_entries_for_unknown_task_types():
    t = cap.load_table()
    assert set(t.task_types) <= set(libsed2_task_types())


@pytest.mark.parametrize("task", DEFERRED)
@pytest.mark.parametrize("backend", ALL_BACKENDS)
def test_deferred_tasks(task, backend):
    t = cap.load_table()
    e = t.entry(backend, task)
    assert e["supported"] is False and e["deferred"] is True and e["reason"]
    with pytest.raises(errors.UnsupportedTaskError) as ei:
        t.check_task(backend, "x", task)
    assert ei.value.backend == backend and task in ei.value.task and "deferred" in ei.value.reason


def test_known_expectations():
    t = cap.load_table()
    for b in BACKENDS:
        assert t.verdict(b, "explicitODESimulation") is None
        assert t.verdict(b, "calculation") is None
    assert t.verdict("opencor", "jacobianFull") is not None
    assert t.verdict("opencor", "jacobianReduced") is not None
    assert t.verdict("roadrunner", "jacobianFull") is None


def test_unknown_task_type_and_backend():
    t = cap.load_table()
    assert "no entry" in t.verdict("roadrunner", "foo@bar")
    with pytest.raises(errors.TranslationError):
        t.verdict("tellurium", "calculation")


# ---------------------------------------------------------------- semantics on synthetic tables

def test_conditions_first_match_wins_and_default_applies():
    data = table({"sim": {
        "a": {"supported": True, "conditions": [
            {"when": {"algorithm": ["KISAO:1", "KISAO:2"]}, "supported": False, "reason": "no stiff solver"},
            {"when": {"algorithm": ["KISAO:2"]}, "supported": True}]},
        "b": {"supported": False, "reason": "never", "conditions": [
            {"when": {"settings.stepSize": [0.1]}, "supported": True}]}}})
    assert cap.validate_table(data) == []
    t = cap.CapabilityTable(data)
    assert t.verdict("a", "sim", {"algorithm": "KISAO:1"}) == "no stiff solver"
    assert t.verdict("a", "sim", {"algorithm": "KISAO:2"}) == "no stiff solver"  # first match wins
    assert t.verdict("a", "sim", {"algorithm": "KISAO:3"}) is None
    assert t.verdict("a", "sim", {}) is None
    assert t.verdict("b", "sim", {"settings": {"stepSize": 0.1}}) is None
    assert t.verdict("b", "sim", {"settings": {"stepSize": 0.2}}) == "never"
    assert t.verdict("b", "sim", {}) == "never"


def test_all_when_paths_must_match():
    data = table({"sim": {b: {"supported": True, "conditions": [
        {"when": {"x": [1], "y": [2]}, "supported": False, "reason": "both"}]} for b in "ab"}})
    t = cap.CapabilityTable(data)
    assert t.verdict("a", "sim", {"x": 1, "y": 2}) == "both"
    assert t.verdict("a", "sim", {"x": 1, "y": 3}) is None


def test_python_check(monkeypatch):
    monkeypatch.setitem(cap.CHECKS, "no_events", lambda task, backend: "events" if task.get("events") else None)
    data = table({"sim": {"a": {"supported": True, "check": "no_events"}, "b": {"supported": True}}})
    assert cap.validate_table(data) == []
    t = cap.CapabilityTable(data)
    assert t.verdict("a", "sim", {"events": True}) == "events"
    assert t.verdict("a", "sim", {}) is None
    assert t.verdict("b", "sim", {"events": True}) is None


def test_validate_table_problems():
    good = table({"sim": {"a": entry(), "b": entry()}})
    assert cap.validate_table(good) == []
    bad = copy.deepcopy(good)
    bad["tasks"]["sim"]["a"] = {"supported": False}  # no reason
    assert cap.validate_table(bad)
    bad = copy.deepcopy(good)
    del bad["tasks"]["sim"]["b"]
    assert any("no entry for backend 'b'" in p for p in cap.validate_table(bad))
    bad = copy.deepcopy(good)
    bad["tasks"]["sim"]["c"] = entry()
    assert any("not a listed backend" in p for p in cap.validate_table(bad))
    bad = copy.deepcopy(good)
    bad["tasks"]["sim"]["a"]["check"] = "not_registered"
    assert any("not registered" in p for p in cap.validate_table(bad))
    bad = copy.deepcopy(good)
    bad["tasks"]["sim"]["a"]["conditions"] = [{"when": {"x": [1]}, "supported": False}]
    assert cap.validate_table(bad)
    bad = copy.deepcopy(good)
    bad["tasks"]["sim"]["a"]["extra"] = 1
    assert cap.validate_table(bad)


def test_load_table_rejects_invalid_file(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps(table({"sim": {"a": {"supported": False}, "b": entry()}})))
    with pytest.raises(errors.TranslationError):
        cap.load_table(str(p))


def test_check_document_walks_nested_subtasks():
    data = table({"loop": {b: entry() for b in "ab"}, "inner": {"a": entry(), "b": {"supported": False, "reason": "no"}}})
    t = cap.CapabilityTable(data)
    doc = {"tasks": {"l": {"_type": "loop", "subTasks": {"s": {"_type": "inner"}}}}}
    t.check_document("a", doc)
    with pytest.raises(errors.UnsupportedTaskError) as ei:
        t.check_document("b", doc)
    assert "task 's' (inner)" in ei.value.task


# ---------------------------------------------------------------- command line

def run_cli(*args):
    env = dict(os.environ, PYTHONPATH=SRC)
    return subprocess.run([sys.executable, "-m", "pysed2translate", *args], capture_output=True, text=True, env=env)


FBA_DOC = {
    "version": "v1.0.0",
    "tasks": {
        "m": {"_type": "modelImport", "location": "m.sbml", "language": "urn:sedml:language:sbml"},
        "f": {"_type": "fluxBalanceAnalysis", "model": "#tasks:m.model", "outputVariables": ["r1"]},
    },
}
STOCHASTIC_DOC = {
    "version": "v1.0.0",
    "tasks": {
        "m": {"_type": "modelImport", "location": "m.sbml", "language": "urn:sedml:language:sbml"},
        "t": {"_type": "oneStepStochasticSimulation", "model": "#tasks:m.model", "independentVariable": "time",
              "outputVariables": ["S1"], "independentStep": 1},
    },
}


def test_cli_skips_unsupported_task_with_exit_11(tmp_path):
    pytest.importorskip("libsed2")
    p = tmp_path / "00009.sed2.json"
    p.write_text(json.dumps(STOCHASTIC_DOC))
    for b in ALL_BACKENDS:
        r = run_cli(str(p), "-b", b)
        assert r.returncode == errors.EXIT_UNSUPPORTED, r.stderr
        assert b in r.stderr and "oneStepStochasticSimulation" in r.stderr and "deferred" in r.stderr


def test_flux_balance_analysis_goes_to_cobra_whatever_the_default_backend_is(tmp_path):
    pytest.importorskip("libsed2")
    p = tmp_path / "00009.sed2.json"
    p.write_text(json.dumps(FBA_DOC))
    for b in BACKENDS:
        r = run_cli(str(p), "-b", b)
        assert r.returncode == 0, r.stderr
        assert f"backend: {b}; fba: cobra" in r.stdout and "rt.backends.get('cobra').fba(" in r.stdout
    r = run_cli(str(p), "-b", "cobra")
    assert r.returncode == 0 and "rt.backends.get(BACKEND).fba(" in r.stdout and "fba:" not in r.stdout.splitlines()[1]


def test_a_dynamic_task_on_cobra_is_a_skip_with_the_reason(tmp_path):
    pytest.importorskip("libsed2")
    doc = {"version": "v1.0.0", "tasks": {"m": _MODEL, "s": {"_type": "explicitODESimulation", **_SIM,
           "independentVariableRange": {"_type": "numericRange", "start": 0, "end": 1, "numberOfSteps": 2}}}}
    p = tmp_path / "00009.sed2.json"
    p.write_text(json.dumps(doc))
    r = run_cli(str(p), "-b", "cobra")
    assert r.returncode == errors.EXIT_UNSUPPORTED and "does not integrate differential equations" in r.stderr


def test_backend_options_for_one_kind(tmp_path):
    pytest.importorskip("libsed2")
    p = tmp_path / "00009.sed2.json"
    p.write_text(json.dumps(FBA_DOC))
    r = run_cli(str(p), "-b", "roadrunner", "-b", "fba=cobra:scipy")
    assert r.returncode == 0 and "rt.backends.get('cobra:scipy').fba(" in r.stdout
    r = run_cli(str(p), "-b", "cobra:glpk")
    assert r.returncode == 0 and "BACKEND = 'cobra:glpk'" in r.stdout
    for bad in (["-b", "cobra:nosuch"], ["-b", "fba=cobra"], ["-b", "roadrunner", "-b", "copasi"],
                ["-b", "roadrunner", "-b", "nokind=cobra"], ["-b", "roadrunner", "-b", "fba=cobra", "-b", "fba=cobra:glpk"],
                ["-b", "roadrunner:x"]):
        r = run_cli(str(p), *bad)
        assert r.returncode == errors.EXIT_USAGE or r.returncode == errors.EXIT_TRANSLATION, (bad, r.stderr)
        assert r.stderr.startswith("error:"), (bad, r.stderr)


def test_backend_for_resolution():
    t = cap.load_table()
    assert t.backend_for("calculation", "roadrunner") == "roadrunner"
    assert t.backend_for("explicitODESimulation", "copasi") == "copasi"
    assert t.backend_for("explicitODESimulation", "cobra") == "cobra"                  # refused later, with the reason
    assert t.backend_for("fluxBalanceAnalysis", "opencor") == "cobra"                  # the only one that serves fba
    assert t.backend_for("fluxBalanceAnalysis", "cobra:scipy") == "cobra:scipy"
    assert t.backend_for("fluxBalanceAnalysis", "copasi", {"fba": "cobra:glpk"}) == "cobra:glpk"
    assert t.backend_for("steadyState", "copasi", {"steady": "roadrunner"}) == "roadrunner"
    assert t.backend_for("steadyState", "copasi", {"fba": "cobra"}) == "copasi"


_MODEL = {"_type": "modelImport", "location": "m.sbml", "language": "urn:sedml:language:sbml"}
_SIM = {"model": "#tasks:m.model", "independentVariable": "time", "outputVariables": ["S1"]}
DEFERRED_TASKS = {
    "explicitStochasticSimulation": {"_type": "explicitStochasticSimulation", **_SIM,
                                     "independentVariableRange": {"_type": "numericRange", "start": 0, "end": 1,
                                                                  "numberOfSteps": 2}},
    "boundedStochasticSimulation": {"_type": "boundedStochasticSimulation", **_SIM,
                                    "independentVariableSpan": {"start": 0, "end": 1}},
    "oneStepStochasticSimulation": {"_type": "oneStepStochasticSimulation", **_SIM, "independentStep": 1},
    "drawFromDistribution": {"_type": "drawFromDistribution", "distribution": "http://www.sbml.org/sbml/symbols/distrib/normal",
                             "arguments": [0, 1]},
}


@pytest.mark.parametrize("task", sorted(DEFERRED_TASKS))
@pytest.mark.parametrize("backend", ALL_BACKENDS)
def test_cli_skips_every_deferred_task_type(tmp_path, task, backend):
    pytest.importorskip("libsed2")
    doc = {"version": "v1.0.0", "tasks": {"m": _MODEL, "t": DEFERRED_TASKS[task]}}
    p = tmp_path / "00010.sed2.json"
    p.write_text(json.dumps(doc))
    r = run_cli(str(p), "-b", backend)
    assert r.returncode == errors.EXIT_UNSUPPORTED, r.stderr
    assert backend in r.stderr and task in r.stderr and "deferred" in r.stderr


def test_every_task_type_is_either_supported_or_has_a_reason():
    t = cap.load_table()
    for ty in t.task_types:
        for b in ALL_BACKENDS:
            e = t.entry(b, ty)
            assert e["supported"] or e.get("reason"), (ty, b)
