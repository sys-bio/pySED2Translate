"""Translation-only tests (no simulator, nothing is run): the text generated for settings and algorithms, the
errors for documents the translator cannot handle, and the command line's error paths."""
import json
import logging

import pytest

pytest.importorskip("libsed2")

from pysed2translate import cli, errors  # noqa: E402
from pysed2translate.errors import InvalidDocumentError, TranslationError  # noqa: E402
from pysed2translate.translate import load_document, translate_file  # noqa: E402

IMP = {"_type": "modelImport", "location": "m.xml", "language": "urn:sedml:language:sbml"}


def write(tmp_path, doc, name="doc.sed2.json"):
    p = tmp_path / name
    p.write_text(json.dumps(doc))
    return str(p)


def sim(**kw):
    d = {"_type": "explicitODESimulation", "model": "#tasks:m.model", "independentVariable": "time",
         "outputVariables": ["S1"], "independentVariableRange": {"_type": "numericRange", "start": 0, "end": 1, "numberOfSteps": 2}}
    d.update(kw)
    return d


def translate(tmp_path, doc, backend="roadrunner"):
    return translate_file(write(tmp_path, doc), backend)


# --------------------------------------------------------------------------- settings and algorithms

def test_settings_as_values_and_as_references(tmp_path):
    doc = {"version": "v1.0.0", "constants": {"tol": 1e-9, "steps": 400, "stiff": True},
           "tasks": {"m": IMP,
                     "a": sim(relativeTolerance=1e-8, maxNumberOfSteps=100, useStiffSolver=False),
                     "b": sim(relativeTolerance="#constants:tol", maxNumberOfSteps="#constants:steps",
                              useStiffSolver="#constants:stiff")}}
    text = translate(tmp_path, doc)
    assert "'relativeTolerance': 1e-08" in text and "'maxNumberOfSteps': 100" in text and "'useStiffSolver': False" in text
    assert "'relativeTolerance': rt.ops.scalar(" in text
    assert "int(rt.ops.scalar(" in text and "bool(rt.ops.scalar(" in text


def test_an_algorithm_given_by_reference_is_refused_up_front(tmp_path):
    """The capability check needs the algorithm while translating, so a reference there is a skip, not an error."""
    doc = {"version": "v1.0.0", "constants": {"alg": "KISAO:0000019"},
           "tasks": {"m": IMP, "s": sim(workingAlgorithms=[{"algorithm": "#constants:alg"}])}}
    with pytest.raises(errors.UnsupportedTaskError, match="reference"):
        translate(tmp_path, doc)


def test_absolute_tolerance_vector_is_not_supported(tmp_path):
    doc = {"version": "v1.0.0", "tasks": {"m": IMP, "s": sim(absoluteToleranceVector=[1e-9])}}
    with pytest.raises((TranslationError, errors.UnsupportedTaskError, InvalidDocumentError)):
        translate(tmp_path, doc)


def test_output_variables_and_start_by_reference(tmp_path):
    doc = {"version": "v1.0.0", "constants": {"vars": ["S1", "S2"], "t0": 1.5},
           "tasks": {"m": IMP, "s": sim(outputVariables="#constants:vars", independentVariableInit="#constants:t0")}}
    text = translate(tmp_path, doc)
    assert "rt.ops.strings_from(" in text and "start=rt.ops.scalar(" in text


# --------------------------------------------------------------------------- errors

def test_unknown_backend(tmp_path):
    with pytest.raises(TranslationError, match="unknown backend"):
        translate(tmp_path, {"version": "v1.0.0"}, backend="nonesuch")


def test_unreadable_documents(tmp_path):
    p = tmp_path / "bad.sed2.json"
    p.write_text("{not json")
    with pytest.raises(InvalidDocumentError):
        load_document(str(p))
    with pytest.raises(InvalidDocumentError):
        load_document(str(tmp_path / "missing.sed2.json"))


def test_a_reference_to_a_constant_that_must_be_known_at_translation(tmp_path):
    doc = {"version": "v1.0.0", "constants": {"loc": "m.xml"},
           "tasks": {"m": {"_type": "modelImport", "location": "#constants:loc", "language": "urn:sedml:language:sbml"}}}
    assert "ctx.input_path('m.xml')" in translate(tmp_path, doc)


def test_parameter_ranges_must_scan_distinct_elements(tmp_path):
    pr = {"_type": "parameterRange", "modelElement": "k1", "values": [1, 2]}
    doc = {"version": "v1.0.0",
           "tasks": {"m": IMP,
                     "ps": {"_type": "parameterScan", "model": "#tasks:m.model", "parameterRanges": [pr, dict(pr)],
                            "subTasks": {"c": {"_type": "calculation", "math": "1"}},
                            "outputVariableMap": {"c": "#tasks:ps:subTasks:c"}}}}
    with pytest.raises((TranslationError, InvalidDocumentError), match="distinct|k1|ParameterScan|parameter"):
        translate(tmp_path, doc)


def test_output_variable_map_values_must_be_references(tmp_path):
    doc = {"version": "v1.0.0",
           "tasks": {"sc": {"_type": "scatter", "range": {"_type": "range", "values": [1]},
                            "subTasks": {"c": {"_type": "calculation", "math": "1"}},
                            "outputVariableMap": {"c": "not a reference"}}}}
    with pytest.raises((TranslationError, InvalidDocumentError)):
        translate(tmp_path, doc)


def test_constants_that_refer_to_each_other(tmp_path):
    doc = {"version": "v1.0.0", "constants": {"a": "#constants:b", "b": "#constants:a"},
           "outputs": {"r": {"_type": "report", "data": "#constants:a"}}}
    with pytest.raises((TranslationError, InvalidDocumentError), match="cycle|circular|constants"):
        translate(tmp_path, doc)


def test_a_reference_to_a_missing_task_output(tmp_path):
    doc = {"version": "v1.0.0",
           "tasks": {"m": IMP, "c": {"_type": "calculation", "math": "1"}},
           "outputs": {"r": {"_type": "report", "data": "#tasks:c.model"}}}
    with pytest.raises((TranslationError, InvalidDocumentError)):
        translate(tmp_path, doc)


# --------------------------------------------------------------------------- command line

def run_cli(tmp_path, *args, doc=None):
    path = write(tmp_path, doc if doc is not None else {"version": "v1.0.0"})
    return cli.main([path, "--backend", "roadrunner", *args])


def test_cli_output_file_and_verbosity(tmp_path, capsys):
    out = tmp_path / "out.py"
    for flags in ([], ["-q"], ["-v"], ["-vv"]):
        assert run_cli(tmp_path, "-o", str(out), *flags) == errors.EXIT_OK
        assert out.read_text().startswith("#!/usr/bin/env python3")
    assert capsys.readouterr().out == ""


def test_cli_invalid_document(tmp_path, capsys):
    path = write(tmp_path, {"version": "v1.0.0", "tasks": {"t": {"_type": "nonsense"}}})
    assert cli.main([path, "-b", "roadrunner"]) == errors.EXIT_INVALID
    assert "not a valid SED2 document" in capsys.readouterr().err


def test_cli_unsupported_translation_and_missing_package(tmp_path, capsys, monkeypatch):
    def refuse(*a, **k):
        raise errors.UnsupportedTaskError("copasi", "t", "cannot")

    monkeypatch.setattr(cli, "translate_file", refuse)
    assert run_cli(tmp_path) == errors.EXIT_UNSUPPORTED
    assert "skip:" in capsys.readouterr().err
    monkeypatch.setattr(cli, "translate_file", lambda *a, **k: (_ for _ in ()).throw(TranslationError("boom")))
    assert run_cli(tmp_path) == errors.EXIT_TRANSLATION
    assert "error: boom" in capsys.readouterr().err
    monkeypatch.setattr(cli, "translate_file", lambda *a, **k: (_ for _ in ()).throw(ImportError("no module named x")))
    assert run_cli(tmp_path) == errors.EXIT_TRANSLATION
    assert "required package is missing" in capsys.readouterr().err


def test_validation_warnings_are_logged_not_fatal(tmp_path, caplog, monkeypatch):
    import libsed2

    class Problem:
        severity, rule_id, location, message = "warning", "Rule-1", "/x", "just so you know"

    real = libsed2.read_from_file

    def read(path):
        doc = real(path)
        doc.validate = lambda: [Problem()]
        return doc

    monkeypatch.setattr(libsed2, "read_from_file", read)
    with caplog.at_level(logging.WARNING, logger="pysed2translate"):
        load_document(write(tmp_path, {"version": "v1.0.0"}))
    assert "just so you know" in caplog.text
