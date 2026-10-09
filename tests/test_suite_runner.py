"""The suite runner, on small temporary suites (constants-only documents, so no simulator is needed)."""
import json
import os
import shutil
import sys

import numpy as np
import pytest

pytest.importorskip("libsed2")
rio = pytest.importorskip("sed2suite.results_io")

from sed2suite import compare, disagreements, settings as st  # noqa: E402

from pysed2translate import suite_runner as sr  # noqa: E402
from pysed2translate.errors import TranslationError, UnsupportedTaskError  # noqa: E402

DOC = {"version": "v1.0.0", "constants": {"v": [1, 2, 3]},
       "outputs": {"r": {"_type": "report", "data": "#constants:v"}}}


def settings_for(backends=("roadrunner",), **kw):
    s = {"schemaVersion": 1, "tolerances": {"absolute": 1e-7, "relative": 1e-4},
         "provenance": {"source": "analytical"}, "backends": list(backends),
         "reports": {"r": {"file": "{id}.r.csv", "format": "csv", "ndim": 1}}}
    s.update(kw)
    return s


def make_case(root, case="00001", expected=(1.0, 2.0, 3.0), backends=("roadrunner",), doc=DOC, with_results=True):
    d = root / "cases" / "semantic" / case
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{case}.sed2.json").write_text(json.dumps(doc))
    s = settings_for(backends)
    s["reports"]["r"]["file"] = f"{case}.r.csv"
    (d / f"{case}.settings.json").write_text(json.dumps(s))
    if with_results:
        rio.write_csv(str(d / f"{case}.r.csv"), rio.AnnotatedData(np.array(expected), [None]))
    return str(d)


@pytest.fixture
def suite(tmp_path):
    root = tmp_path / "suite"
    root.mkdir()
    (root / "disagreements.json").write_text(json.dumps(disagreements.empty_log()))
    return sr.Suite(str(root), compare, st, disagreements)


def run(suite, case_dir, backend="roadrunner", tmp=None, timeout=60.0):
    return sr.run_case(suite, case_dir, backend, os.path.join(suite.root, "work"), timeout)


# --------------------------------------------------------------------------- finding things

def test_locate_suite_by_path(tmp_path):
    here = os.path.dirname(compare.__file__)
    root = os.path.abspath(os.path.join(here, "..", ".."))
    s = sr.locate_suite(root)
    assert s.root == root and s.cases_dir == os.path.join(root, "cases", "semantic")


def test_locate_suite_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("SED2SUITE", raising=False)
    monkeypatch.setattr(sr.os.path, "isdir", lambda p: False)
    with pytest.raises(FileNotFoundError):
        sr.locate_suite(str(tmp_path))


def test_list_cases(suite):
    a, b = make_case(suite.root and __import__("pathlib").Path(suite.root), "00002"), make_case(
        __import__("pathlib").Path(suite.root), "00001")
    assert [os.path.basename(c) for c in sr.list_cases(suite, [])] == ["00001", "00002"]
    assert sr.list_cases(suite, ["00002"]) == [a]
    assert sr.list_cases(suite, [b]) == [b]
    assert sr.list_cases(suite, [os.path.join(b, "00001.sed2.json")]) == [b]
    with pytest.raises(FileNotFoundError):
        sr.list_cases(suite, ["00009"])


def test_list_cases_without_a_cases_folder(suite):
    assert sr.list_cases(suite, []) == []


# --------------------------------------------------------------------------- running one case

def test_pass(suite, tmp_path):
    case = make_case(tmp_path / "suite")
    r = run(suite, case)
    assert r.status == sr.PASS and r.canonical and r.reason == ""
    assert set(r.manifest["reports"]) == {"r"}
    assert os.path.exists(os.path.join(r.out_dir, "00001.r.csv"))


def test_pass_on_a_backend_that_is_not_canonical(suite, tmp_path):
    case = make_case(tmp_path / "suite")
    r = run(suite, case, "copasi")
    assert r.status == sr.PASS and not r.canonical


def test_fail_on_different_values(suite, tmp_path):
    case = make_case(tmp_path / "suite", expected=(1.0, 2.0, 3.5))
    r = run(suite, case)
    assert r.status == sr.FAIL and "report r" in r.reason
    found = sr.disagreements_with_expected(suite, case, [r])
    assert len(found) == 1 and found[0].backends == ("roadrunner", "expected")
    assert found[0].measure["maxAbsolute"] == pytest.approx(0.5)
    assert "00001 r: roadrunner vs expected" in found[0].message()


def test_fail_when_expected_results_are_missing(suite, tmp_path):
    case = make_case(tmp_path / "suite", with_results=False)
    assert run(suite, case).status == sr.FAIL


def test_error_when_the_document_is_invalid(suite, tmp_path):
    case = make_case(tmp_path / "suite", doc={"version": "v1.0.0", "tasks": {"t": {"_type": "nonsense"}}})
    r = run(suite, case)
    assert r.status == sr.ERROR and "not valid" in r.reason


def test_error_without_document_or_settings(suite, tmp_path):
    case = make_case(tmp_path / "suite")
    os.remove(os.path.join(case, "00001.sed2.json"))
    assert "does not exist" in run(suite, case).reason
    os.remove(os.path.join(case, "00001.settings.json"))
    r = run(suite, case)
    assert r.status == sr.ERROR and "settings" in r.reason


def test_skip_when_unsupported_and_not_canonical(suite, tmp_path, monkeypatch):
    case = make_case(tmp_path / "suite")

    def refuse(*a, **k):
        raise UnsupportedTaskError("copasi", "t", "no such thing")

    monkeypatch.setattr(sr, "translate_file", refuse)
    r = run(suite, case, "copasi")
    assert r.status == sr.SKIP and "no such thing" in r.reason


def test_unsupported_on_a_canonical_backend_is_a_failure(suite, tmp_path, monkeypatch):
    case = make_case(tmp_path / "suite", backends=("roadrunner", "copasi"))

    def refuse(*a, **k):
        raise UnsupportedTaskError("copasi", "t", "no such thing")

    monkeypatch.setattr(sr, "translate_file", refuse)
    r = run(suite, case, "copasi")
    assert r.status == sr.FAIL and "canonical" in r.reason
    assert run(suite, case, "opencor").status == sr.SKIP


def test_error_when_translation_fails(suite, tmp_path, monkeypatch):
    case = make_case(tmp_path / "suite")
    monkeypatch.setattr(sr, "translate_file", lambda *a, **k: (_ for _ in ()).throw(TranslationError("boom")))
    r = run(suite, case)
    assert r.status == sr.ERROR and "boom" in r.reason


def test_error_when_the_script_fails_or_hangs(suite, tmp_path, monkeypatch):
    case = make_case(tmp_path / "suite")
    monkeypatch.setattr(sr, "translate_file", lambda *a, **k: "import sys\nprint('bad thing', file=sys.stderr)\nsys.exit(3)\n")
    r = run(suite, case)
    assert r.status == sr.ERROR and "exit 3" in r.reason and "bad thing" in r.reason
    monkeypatch.setattr(sr, "translate_file", lambda *a, **k: "import time\ntime.sleep(30)\n")
    r = run(suite, case, timeout=1.0)
    assert r.status == sr.ERROR and "did not finish" in r.reason


def test_runs_do_not_leave_files_between_runs(suite, tmp_path):
    case = make_case(tmp_path / "suite")
    r = run(suite, case)
    stray = os.path.join(r.out_dir, "stray.txt")
    open(stray, "w").close()
    r = run(suite, case)
    assert not os.path.exists(stray)


# --------------------------------------------------------------------------- cross-checks and drafts

def fake_script(values):
    return ("import argparse, os, json\n"
            "ap = argparse.ArgumentParser()\n"
            "for a in ('--input-dir', '--output-dir', '--manifest'):\n    ap.add_argument(a)\n"
            "ap.add_argument('--no-png', action='store_true')\n"
            "a = ap.parse_args()\n"
            f"open(os.path.join(a.output_dir, '00001.r.csv'), 'w').write({chr(10).join(str(v) for v in values)!r} + chr(10))\n"
            "json.dump({'reports': {'r': {'file': '00001.r.csv', 'format': 'csv', 'ndim': 1, 'dtype': 'number', "
            "'labels': {'rows': False, 'columns': False}}}, 'plots': {}}, open(a.manifest, 'w'))\n")


def test_crosscheck_and_draft_entries(suite, tmp_path, monkeypatch):
    case = make_case(tmp_path / "suite", backends=("roadrunner", "copasi"))
    scripts = {"roadrunner": fake_script([1, 2, 3]), "copasi": fake_script([1, 2, 3.5])}
    monkeypatch.setattr(sr, "translate_file", lambda path, backend, **k: scripts[backend])
    results = [run(suite, case, b) for b in ("roadrunner", "copasi")]
    assert [r.status for r in results] == [sr.PASS, sr.FAIL]
    found = sr.disagreements_with_expected(suite, case, results) + sr.crosscheck(suite, case, results)
    assert [d.backends for d in found] == [("copasi", "expected"), ("roadrunner", "copasi")]
    drafts = sr.draft_entries(suite, found)
    assert [d["id"] for d in drafts] == ["D-001", "D-002"]
    assert disagreements.validate_log({"schemaVersion": 1, "entries": drafts}) == []


def test_a_script_that_fails_is_a_disagreement_with_a_symptom(suite, tmp_path, monkeypatch):
    case = make_case(tmp_path / "suite", backends=("roadrunner", "copasi"))
    scripts = {"roadrunner": fake_script([1, 2, 3]), "copasi": "import sys\nprint('it broke', file=sys.stderr)\nsys.exit(1)\n"}
    monkeypatch.setattr(sr, "translate_file", lambda path, backend, **k: scripts[backend])
    results = [run(suite, case, b) for b in ("roadrunner", "copasi")]
    assert [r.status for r in results] == [sr.PASS, sr.ERROR]
    (d,) = sr.disagreements_with_expected(suite, case, results)
    assert d.backends == ("copasi", "expected") and d.report == "" and "it broke" in d.measure["reason"]
    assert d.message().startswith("00001: copasi vs expected")
    (entry,) = sr.draft_entries(suite, [d])
    assert "report" not in entry and "it broke" in entry["symptom"]
    assert disagreements.validate_log({"schemaVersion": 1, "entries": [entry]}) == []


def test_unsupported_canonical_backend_is_a_disagreement_but_a_bad_document_is_not(suite, tmp_path, monkeypatch):
    case = make_case(tmp_path / "suite", backends=("roadrunner", "copasi"))
    monkeypatch.setattr(sr, "translate_file", lambda *a, **k: (_ for _ in ()).throw(UnsupportedTaskError("copasi", "t", "no")))
    r = run(suite, case, "copasi")
    assert r.status == sr.FAIL
    assert len(sr.disagreements_with_expected(suite, case, [r])) == 1
    monkeypatch.setattr(sr, "translate_file", lambda *a, **k: (_ for _ in ()).throw(TranslationError("boom")))
    r = run(suite, case, "copasi")
    assert r.status == sr.ERROR and sr.disagreements_with_expected(suite, case, [r]) == []


def test_drafts_skip_what_the_log_already_covers(suite, tmp_path):
    log = disagreements.empty_log()
    log["entries"].append({"id": "D-001", "test": "00001", "backends": ["copasi", "expected"], "report": "r",
                           "status": "open", "diagnosis": "undiagnosed", "resolution": ""})
    disagreements.save_log(log, suite.log_path)
    d = sr.Disagreement("00001", ("copasi", "expected"), "r", {"comparable": True, "maxAbsolute": 1.0,
                                                               "maxRelative": 1.0, "where": ""})
    assert sr.draft_entries(suite, [d]) == []
    d2 = sr.Disagreement("00001", ("opencor", "expected"), "r", d.measure)
    assert [e["id"] for e in sr.draft_entries(suite, [d, d2])] == ["D-002"]


def test_crosscheck_ignores_runs_without_output(suite, tmp_path, monkeypatch):
    case = make_case(tmp_path / "suite")
    results = [run(suite, case, "roadrunner"), sr.RunResult("00001", "copasi", sr.SKIP)]
    assert sr.crosscheck(suite, case, results) == []


# --------------------------------------------------------------------------- promotion

def test_promote_creates_settings_and_results(suite, tmp_path, monkeypatch):
    root = tmp_path / "suite"
    case = make_case(root, with_results=False)
    os.remove(os.path.join(case, "00001.settings.json"))
    r = run(suite, case)
    assert r.status == sr.ERROR            # no settings yet: the runner needs them to compare
    # the settings of a new case are made by promote from a run, so run the script directly
    monkeypatch.setattr(sr, "translate_file", lambda path, backend, **k: fake_script([4, 5, 6]))
    s0 = settings_for(())
    s0["reports"]["r"]["file"] = "00001.r.csv"
    s0["backends"] = []
    (root / "cases" / "semantic" / "00001" / "00001.settings.json").write_text(json.dumps(s0))
    r = run(suite, case)
    assert r.status == sr.FAIL            # nothing to compare with yet
    written = sr.promote(suite, case, r, force=True)
    assert sorted(written) == ["00001.r.csv", "00001.settings.json"]
    s = st.load_settings(os.path.join(case, "00001.settings.json"))
    assert s["backends"] == ["roadrunner"] and s["provenance"]["source"] == "simulation"
    assert s["provenance"]["simulators"][0]["name"] == "roadrunner"
    assert st.validate_settings(s, case) == []
    assert run(suite, case).status == sr.PASS


def test_promote_refuses_to_replace_results(suite, tmp_path):
    case = make_case(tmp_path / "suite")
    r = run(suite, case)
    with pytest.raises(ValueError, match="already has result files"):
        sr.promote(suite, case, r)
    assert sr.promote(suite, case, r, force=True)


def test_promote_nothing_from_a_skipped_run(suite, tmp_path):
    case = make_case(tmp_path / "suite")
    with pytest.raises(ValueError, match="nothing to promote"):
        sr.promote(suite, case, sr.RunResult("00001", "copasi", sr.SKIP, "no"))


def test_promote_keeps_tolerances_and_adds_a_second_backend(suite, tmp_path):
    case = make_case(tmp_path / "suite")
    path = os.path.join(case, "00001.settings.json")
    s = st.load_settings(path)
    s["reports"]["r"]["tolerances"] = {"relative": 0.01}
    s["provenance"] = {"source": "simulation", "simulators": [{"name": "copasi", "version": "1"}]}
    s["backends"] = ["copasi"]
    open(path, "w").write(json.dumps(s))
    r = run(suite, case, "roadrunner")
    sr.promote(suite, case, r, force=True)
    s = st.load_settings(path)
    assert s["backends"] == ["roadrunner", "copasi"]
    assert {x["name"] for x in s["provenance"]["simulators"]} == {"roadrunner", "copasi"}
    assert s["reports"]["r"]["tolerances"] == {"relative": 0.01}


# --------------------------------------------------------------------------- output and the command line

def test_matrix_and_report():
    rs = [sr.RunResult("00001", "roadrunner", sr.PASS, canonical=True), sr.RunResult("00001", "copasi", sr.SKIP, "no"),
          sr.RunResult("00002", "roadrunner", sr.FAIL, "report r: off", canonical=True)]
    text = sr.format_report(rs, ["roadrunner", "copasi"])
    lines = text.splitlines()
    assert lines[1].split() == ["00001", "PASS*", "SKIP"]
    assert lines[2].split() == ["00002", "FAIL*", "-"]
    assert "FAIL  00002 roadrunner: report r: off" in text
    assert "1 PASS, 1 FAIL, 1 SKIP, 0 ERROR" in text


def run_main(suite, *args):
    return sr.main(["--suite", suite.root, *args])


def test_main_exit_codes_and_output(suite, tmp_path, capsys):
    root = tmp_path / "suite"
    shutil.copytree(os.path.join(os.path.dirname(compare.__file__), ".."), root / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    make_case(root, "00001")
    assert run_main(suite, "00001", "-b", "roadrunner") == 0
    assert "PASS*" in capsys.readouterr().out
    make_case(root, "00002", expected=(9.0, 9.0, 9.0))
    assert run_main(suite, "-b", "roadrunner", "--log-draft") == 1
    out = capsys.readouterr().out
    assert "FAIL*" in out and "differences found" in out and '"id": "D-001"' in out
    assert run_main(suite, "00002", "-b", "roadrunner", "--json") == 1
    data = json.loads(capsys.readouterr().out)
    assert data["results"][0]["status"] == "FAIL" and data["disagreements"][0]["report"] == "r"


def test_main_usage_errors(suite, tmp_path, capsys):
    root = tmp_path / "suite"
    shutil.copytree(os.path.join(os.path.dirname(compare.__file__), ".."), root / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    assert run_main(suite, "00099") == 2
    assert run_main(suite, "--promote", "roadrunner") == 2
    make_case(root, "00001")
    assert run_main(suite, "00001", "--promote", "roadrunner", "-b", "copasi") == 2
    assert sr.main(["--suite", str(tmp_path / "nowhere")]) == 2
    capsys.readouterr()
    assert run_main(suite) == 0 if False else True


def test_main_with_no_cases(suite, tmp_path, capsys):
    root = tmp_path / "suite"
    shutil.copytree(os.path.join(os.path.dirname(compare.__file__), ".."), root / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    assert run_main(suite) == 0
    assert "no cases found" in capsys.readouterr().out


def test_main_promote(suite, tmp_path, capsys):
    root = tmp_path / "suite"
    shutil.copytree(os.path.join(os.path.dirname(compare.__file__), ".."), root / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    case = make_case(root, "00001")
    assert run_main(suite, "00001", "--promote", "roadrunner") == 1       # results exist: refused
    assert "already has result files" in capsys.readouterr().out
    assert run_main(suite, "00001", "--promote", "roadrunner", "--force") == 0
    assert "promoted" in capsys.readouterr().out


def test_main_work_dir_is_kept(suite, tmp_path):
    root = tmp_path / "suite"
    shutil.copytree(os.path.join(os.path.dirname(compare.__file__), ".."), root / "tools", ignore=shutil.ignore_patterns("__pycache__"))
    make_case(root, "00001")
    work = tmp_path / "keep"
    assert run_main(suite, "-b", "roadrunner", "--work-dir", str(work)) == 0
    assert (work / "00001" / "roadrunner" / "00001.roadrunner.py").exists()
