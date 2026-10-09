"""The viva wrapper provider (`--wrappers strict|prefer|off`): the rules, the documents, the ledger, and runs.

The wrappers are community packages; every gap found in them is a ledger entry (pbg/upstream/W-n.md, drafts, never filed by an
assistant).  A test here never loosens a rule to pass: a wrapper that cannot do a task is refused with its ledger id."""
import glob
import json
import os
import re
import subprocess
import sys

import numpy as np
import pytest

from pysed2translate_pbg import host
from pysed2translate_pbg.api import Options
from pysed2translate_pbg.engines import v1
from pysed2translate_pbg.engines.v1 import providers
from pysed2translate_pbg.engines.v1.providers import Request, WrapperRefusal, gaps_for

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
UPSTREAM = os.path.abspath(os.path.join(HERE, "..", "..", "upstream"))
MODEL = {"_type": "modelImport", "location": "decay.xml", "language": "urn:sedml:language:sbml"}
IV = "urn:sedml:symbol:time"


def ode(rng=None, **extra):
    sim = {"_type": "explicitODESimulation", "model": "#tasks:m.model", "independentVariable": IV, "outputVariables": ["S"],
           "independentVariableRange": rng or {"_type": "numericRange", "start": 0, "end": 10, "numberOfSteps": 20}}
    sim.update(extra)
    return sim


def document(tasks, outputs=None):
    return {"version": "v1.0.0", "tasks": {"m": MODEL, **tasks},
            "outputs": outputs or {"r": {"_type": "report", "data": "#tasks:s"}}}


def translate(tmp_path, doc, wrappers="strict", backend=None):
    path = tmp_path / "t.sed2.json"
    path.write_text(json.dumps(doc))
    opts = Options(backend=backend or {"*": "roadrunner"}, prefix="t", source_name="t.sed2.json", input_dir=DATA,
                   engine={"wrappers": wrappers})
    result = v1.translate(host.load_document(str(path)), opts)
    return json.loads(next(iter(result.files.values()))), result


# ------------------------------------------------------------------------------------------------ the rules

def request(**kw):
    base = dict(tid="s", kind="ode", backend="roadrunner", mode="points", model_task="m", location="decay.xml",
                language="urn:sedml:language:sbml", points=[0.0, 1.0, 2.0])
    base.update(kw)
    return Request(**base)


def ids(req, used=None):
    plan, gaps = gaps_for(req, used)
    return plan, sorted(i for i, _ in gaps)


def test_a_plain_uniform_time_course_gets_a_plan_for_each_wrapper():
    plan, gaps = ids(request())
    assert gaps == [] and plan.address == "viva_tellurium.processes.TelluriumUTCStep"
    assert plan.config == {"start_time": 0.0, "end_time": 2.0, "n_points": 3, "model_format": "sbml", "model_file": "decay.xml"}
    plan, gaps = ids(request(backend="copasi"))
    assert gaps == [] and plan.address == "viva_copasi.processes.CopasiUTCStep"
    assert plan.config == {"time": 2.0, "n_points": 3, "model_source": "decay.xml"}


@pytest.mark.parametrize("change,expected", [
    (dict(guarded=True), ["W-10"]),
    (dict(model_task=None), ["W-6"]),
    (dict(mode="span", points=None), ["W-5"]),
    (dict(mode="step", points=None), ["L-1"]),
    (dict(points=[0.0, 1.0, 3.0]), ["W-5"]),
    (dict(points=[0.0]), ["W-5"]),
    (dict(points=None, points_problem="from a task"), ["L-2"]),
    (dict(settings=["relativeTolerance"]), ["W-1"]),
    (dict(algorithm="KISAO:0000032"), ["L-5"]),
    (dict(language="urn:sedml:language:cellml"), ["L-3"]),
    (dict(init=1.0), ["L-4"]),
    (dict(backend="opencor"), ["W-9"]),
    (dict(kind="fba", backend="cobra:glpk"), ["W-11"]),
    (dict(kind="jacobian"), ["W-8"]),
])
def test_tellurium_gaps(change, expected):
    assert ids(request(**change))[1] == expected


@pytest.mark.parametrize("change,expected", [
    (dict(settings=["absoluteTolerance"]), ["W-3"]),
    (dict(algorithm="KISAO:0000019"), ["W-3"]),
    (dict(points=[1.0, 2.0, 3.0]), ["W-2"]),
])
def test_copasi_gaps(change, expected):
    assert ids(request(backend="copasi", **change))[1] == expected


def test_default_cvode_is_accepted_but_a_stated_option_is_not():
    assert ids(request(algorithm="KISAO:0000019"))[1] == []
    assert ids(request(algorithm="KISAO:0000288"))[1] == ["L-5"]       # BDF: options the wrapper cannot take


def test_steady_state_rules():
    assert ids(request(kind="steady", points=None))[1] == []
    assert ids(request(kind="steady", points=None, algorithm="KISAO:0000407"))[1] == ["W-8"]


def test_the_two_wrapper_families_are_not_mixed():
    assert ids(request(backend="copasi"), used="tellurium")[1] == ["W-13"]
    assert ids(request(backend="roadrunner"), used="tellurium")[1] == []


# ------------------------------------------------------------------------------------------------ documents

def test_strict_translates_a_time_course_into_a_wrapper_and_an_adapter(tmp_path):
    pbg, result = translate(tmp_path, document({"s": ode()}))
    nodes = pbg["state"]
    assert nodes["viva_s"]["address"] == "local:!viva_tellurium.processes.TelluriumUTCStep"
    assert nodes["viva_s"]["config"]["model_file"].endswith("decay.xml")
    assert nodes["task_s"]["address"].endswith("steps.SedVivaOde")
    assert pbg["sed2"]["wrappers"]["tasks"] == {"s": "viva_tellurium.processes.TelluriumUTCStep"}
    assert result.manifest["wrappers"] == "strict" and result.manifest["notes"] == []


def test_off_keeps_the_host_runtime(tmp_path):
    pbg, _ = translate(tmp_path, document({"s": ode()}), wrappers="off")
    assert "wrappers" not in pbg["sed2"] and "viva_s" not in pbg["state"]
    assert pbg["state"]["task_s"]["address"].endswith("steps.SedOdeSimulation")


def test_strict_refuses_with_the_ledger_ids(tmp_path):
    doc = document({"s": ode({"_type": "numericRange", "values": [0, 1, 3]})})
    with pytest.raises(WrapperRefusal) as e:
        translate(tmp_path, doc)
    assert e.value.ids() == ["W-5"] and "W-5" in str(e.value)
    assert isinstance(e.value, host.UnsupportedTaskError) and e.value.exit_code == host.EXIT_UNSUPPORTED


def test_prefer_falls_back_with_a_note(tmp_path):
    doc = document({"s": ode({"_type": "numericRange", "values": [0, 1, 3]})})
    pbg, result = translate(tmp_path, doc, wrappers="prefer")
    assert "wrappers" not in pbg["sed2"]
    assert pbg["state"]["task_s"]["address"].endswith("steps.SedOdeSimulation")
    assert any("W-5" in n and "'s'" in n for n in result.manifest["notes"])


def model_use_document():
    return document({"s": ode(), "n": {"_type": "oneStepODESimulation", "model": "#tasks:s.model", "independentVariable": IV,
                                       "outputVariables": ["S"], "independentStep": 1}},
                    {"r": {"_type": "report", "data": "#tasks:n"}})


def test_a_later_use_of_the_model_a_wrapper_cannot_hand_on_is_refused_in_strict_mode(tmp_path):
    with pytest.raises(WrapperRefusal) as e:
        translate(tmp_path, model_use_document())
    assert e.value.ids() == ["W-6"] and list(e.value.gaps) == ["s"]


def test_prefer_runs_a_task_on_the_host_when_a_later_task_needs_its_model(tmp_path):
    pbg, result = translate(tmp_path, model_use_document(), wrappers="prefer")
    assert pbg["state"]["task_s"]["address"].endswith("steps.SedOdeSimulation")
    assert any("'s'" in n and "model" in n for n in result.manifest["notes"])


def test_strict_refuses_the_second_family(tmp_path):
    doc = document({"s": ode(), "u": {"_type": "steadyState", "model": "#tasks:m.model", "outputVariables": ["S"]}},
                   {"r": {"_type": "report", "data": "#tasks:u"}})
    with pytest.raises(WrapperRefusal) as e:
        translate(tmp_path, doc, backend={"ode": "roadrunner", "steady": "copasi"})
    assert e.value.ids() == ["W-13"]


def test_the_default_mode_is_strict():
    assert providers.DEFAULT_MODE == "strict" and set(providers.MODES) == {"strict", "prefer", "off"}


# ------------------------------------------------------------------------------------------------ the ledger

def test_every_ledger_entry_has_its_draft_and_every_draft_its_entry():
    drafts = {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(UPSTREAM, "W-*.md"))}
    assert drafts == {i for i in providers.LEDGER if i.startswith("W-")}
    for i in providers.LEDGER:
        assert re.fullmatch(r"[WL]-\d+", i)


def test_ledger_ids_used_by_the_rules_exist():
    src = open(providers.__file__, encoding="utf-8").read()
    quoted = re.findall(r'"([WL]-\d+)"', src)
    assert set(quoted) <= set(providers.LEDGER)
    used = {i for i in providers.LEDGER if quoted.count(i) > (2 if i in providers.NOTES_ONLY else 1)}   # LEDGER, (NOTES_ONLY,) a rule
    unused = set(providers.LEDGER) - used
    assert unused == set(providers.NOTES_ONLY) | {"W-7"}      # W-7 is found while running (steps.py); the others are observations


# ------------------------------------------------------------------------------------------------ runs

def run_cli(doc_path, out_dir, input_dir=DATA, cwd=None):
    env = {**os.environ, "MPLBACKEND": "Agg"}
    return subprocess.run([sys.executable, "-m", "pysed2translate_pbg.cli", "run", str(doc_path), "--input-dir", str(input_dir),
                           "--output-dir", str(out_dir), "--no-png"], capture_output=True, text=True, env=env, cwd=cwd)


def read_csv(path):
    return np.loadtxt(path, delimiter=",", skiprows=1)


@pytest.mark.parametrize("backend,module", [("roadrunner", "tellurium"), ("copasi", "basico")])
def test_a_wrapped_time_course_matches_the_host_runtime(tmp_path, backend, module):
    pytest.importorskip(module)
    results = {}
    for mode in ("off", "strict"):
        pbg, _ = translate(tmp_path, document({"s": ode()}), wrappers=mode, backend={"*": backend})
        p = tmp_path / f"{mode}.pbg.composite.json"
        p.write_text(json.dumps(pbg))
        out = tmp_path / mode
        out.mkdir()
        r = run_cli(p, out)
        assert r.returncode == 0, r.stderr[-800:]
        results[mode] = read_csv(out / "t.r.csv")
    a, b = results["off"], results["strict"]
    assert a.shape == b.shape == (21, 2)
    # the wrappers cannot set tolerances (W-1, W-3): the agreement is that of the simulators' defaults
    assert np.allclose(a, b, rtol=1e-4, atol=1e-8)


def test_a_variable_the_wrapper_does_not_return_is_a_skip_with_w7(tmp_path):
    pytest.importorskip("tellurium")
    pbg, _ = translate(tmp_path, document({"s": ode(outputVariables=["S", "k"])}))
    p = tmp_path / "t.pbg.composite.json"
    p.write_text(json.dumps(pbg))
    out = tmp_path / "out"
    out.mkdir()
    r = run_cli(p, out)
    assert r.returncode == host.EXIT_CANNOT_RUN and "W-7" in r.stderr


def test_a_run_with_another_input_directory_is_refused(tmp_path):
    pytest.importorskip("tellurium")
    pbg, _ = translate(tmp_path, document({"s": ode()}))
    p = tmp_path / "t.pbg.composite.json"
    p.write_text(json.dumps(pbg))
    out = tmp_path / "out"
    out.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    r = run_cli(p, out, input_dir=other)
    assert r.returncode == 1 and "fixed when the document was translated" in r.stderr
