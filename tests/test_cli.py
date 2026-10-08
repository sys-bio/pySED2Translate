import json
import os
import subprocess
import sys

import pytest

from pysed2translate import errors
from pysed2translate.cli import main
from pysed2translate.codegen import CodeBuilder
from pysed2translate.translate import default_prefix, translate_file

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
EMPTY = {"version": "v1.0.0"}


def write(tmp_path, doc, name="00001.sed2.json"):
    p = tmp_path / name
    p.write_text(json.dumps(doc))
    return str(p)


def run_cli(*args):
    env = dict(os.environ, PYTHONPATH=SRC)
    return subprocess.run([sys.executable, "-m", "pysed2translate", *args], capture_output=True, text=True, env=env)


def test_default_prefix():
    assert default_prefix("a/b/00001.sed2.json") == "00001"
    assert default_prefix("x.json") == "x"
    assert default_prefix("plain") == "plain"


def test_code_builder():
    cb = CodeBuilder()
    with cb.block("def f():"):
        cb.line("x = 1")
        with cb.block("if x:"):
            pass
        cb.line()
    assert cb.text() == "def f():\n    x = 1\n    if x:\n        pass\n\n"


def test_empty_document_prints_runnable_stub(tmp_path):
    p = write(tmp_path, EMPTY)
    r = run_cli(p, "--backend", "roadrunner")
    assert r.returncode == errors.EXIT_OK, r.stderr
    assert "PREFIX = '00001'" in r.stdout
    assert r.stdout.startswith("#!/usr/bin/env python3\n")
    compile(r.stdout, "stub", "exec")
    # and it runs
    script = tmp_path / "out.py"
    r2 = run_cli(p, "-b", "copasi", "-o", str(script), "--prefix", "T")
    assert r2.returncode == 0 and "PREFIX = 'T'" in script.read_text()
    env = dict(os.environ, PYTHONPATH=SRC)
    done = subprocess.run([sys.executable, str(script), "--output-dir", str(tmp_path / "res")],
                          capture_output=True, text=True, env=env)
    assert done.returncode == 0, done.stderr


def test_output_is_deterministic(tmp_path):
    p = write(tmp_path, EMPTY)
    a = run_cli(p, "-b", "opencor").stdout
    assert a == run_cli(p, "-b", "opencor").stdout
    assert str(tmp_path) not in a  # no absolute paths unless asked for
    b = run_cli(p, "-b", "opencor", "--input-dir", "/data/in", "--output-dir", "/data/out").stdout
    assert "DEFAULT_INPUT_DIR = '/data/in'" in b and "DEFAULT_OUTPUT_DIR = '/data/out'" in b


def test_invalid_document_exit_code_and_rule_ids(tmp_path):
    pytest.importorskip("libsed2")
    p = write(tmp_path, {"version": "v1.0.0", "outputs": {"r": {"_type": "report", "data": "#constants:missing"}}})
    r = run_cli(p, "-b", "roadrunner")
    assert r.returncode == errors.EXIT_INVALID
    assert "SEDBase-0006" in r.stderr


def test_unreadable_files(tmp_path):
    assert run_cli(str(tmp_path / "nope.sed2.json"), "-b", "roadrunner").returncode == errors.EXIT_INVALID
    bad = tmp_path / "bad.sed2.json"
    bad.write_text("{not json")
    r = run_cli(str(bad), "-b", "roadrunner")
    assert r.returncode == errors.EXIT_INVALID and "error" in r.stderr


def test_usage_errors(tmp_path):
    p = write(tmp_path, EMPTY)
    assert run_cli(p).returncode == 2  # --backend is required
    assert run_cli(p, "-b", "tellurium").returncode == 2


def test_element_without_a_handler_is_an_error_not_silence(tmp_path, monkeypatch):
    pytest.importorskip("libsed2")
    from pysed2translate import core

    monkeypatch.setattr(core, "TASK_HANDLERS", {})
    doc = {"version": "v1.0.0", "tasks": {"m": {"_type": "modelImport", "location": "m.xml",
                                                "language": "urn:sedml:language:sbml"}}}
    p = write(tmp_path, doc)
    with pytest.raises(errors.TranslationError, match="not implemented"):
        translate_file(p, "roadrunner")


def test_main_maps_unsupported_task_to_skip(monkeypatch, capsys, tmp_path):
    from pysed2translate import cli

    def boom(*a, **k):
        raise errors.UnsupportedTaskError("opencor", "task 's' (jacobianFull)", "no Jacobian in OpenCOR")

    monkeypatch.setattr(cli, "translate_file", boom)
    p = write(tmp_path, EMPTY)
    assert main([p, "-b", "opencor"]) == errors.EXIT_UNSUPPORTED
    err = capsys.readouterr().err
    assert "skip:" in err and "opencor" in err and "jacobianFull" in err and "no Jacobian" in err


def test_exit_codes_are_distinct():
    codes = [errors.EXIT_OK, errors.EXIT_USAGE, errors.EXIT_INVALID, errors.EXIT_UNSUPPORTED, errors.EXIT_TRANSLATION]
    assert len(set(codes)) == len(codes)
