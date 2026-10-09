"""Rules M2-M6, M9 of process-bigraph.md section 3.11 as tests.  (M1 is a test in the host's own tests/; M7, M8 are review/CI rules.)"""
import ast
import os
import subprocess
import sys

import pytest

from pysed2translate_pbg import engines

PKG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src", "pysed2translate_pbg")
ROOT = os.path.abspath(os.path.join(PKG, "..", ".."))


def _py_files(base):
    for r, _d, fs in os.walk(base):
        if "__pycache__" in r:
            continue
        for f in fs:
            if f.endswith(".py"):
                yield os.path.join(r, f)


def _imports(path):
    tree = ast.parse(open(path, encoding="utf-8").read(), path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom):
            yield ("." * node.level) + (node.module or ""), node


def _names(path):
    out = []
    for item in _imports(path):
        if isinstance(item, str):
            out.append(item)
        else:
            out.append(item[0])
    return out


def test_m2_only_host_py_imports_the_host():
    for path in _py_files(PKG):
        bad = [n for n in _names(path) if n == "pysed2translate" or n.startswith("pysed2translate.")]
        if os.path.basename(path) != "host.py":
            assert not bad, f"{path} imports the host directly: {bad}"
    assert any(n.startswith("pysed2translate") for n in _names(os.path.join(PKG, "host.py")))


def test_m2_engines_reach_libsed2_through_the_host():
    for path in _py_files(os.path.join(PKG, "engines")):
        bad = [n for n in _names(path) if n == "libsed2" or n.startswith("libsed2.")]
        assert not bad, f"{path} imports libsed2 directly: {bad}"


def test_m3_engines_are_independent():
    names = engines.names()
    for a in names:
        for path in _py_files(os.path.join(PKG, "engines", a)):
            for n in _names(path):
                for b in names:
                    if b != a:
                        assert f"engines.{b}" not in n and n != b, f"{path} reaches engine {b}: {n}"


def test_m4_discovery_finds_exactly_the_folders_present():
    folders = sorted(d for d in os.listdir(os.path.join(PKG, "engines"))
                     if os.path.exists(os.path.join(PKG, "engines", d, "__init__.py")))
    assert engines.names() == folders


def test_m4_engine_command_still_runs_without_v1(tmp_path):
    import shutil

    copy = tmp_path / "pysed2translate_pbg"
    shutil.copytree(PKG, copy, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.rmtree(copy / "engines" / "v1")
    r = subprocess.run([sys.executable, "-c", "import pysed2translate_pbg.engines as e; print(e.names())"], cwd=tmp_path,
                       capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(tmp_path)})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "[]"


def test_m5_contract_tests_do_not_know_engine_internals():
    for path in _py_files(os.path.dirname(os.path.abspath(__file__))):
        for n in _names(path):
            assert not n.startswith("pysed2translate_pbg.engines.") and n != "pysed2translate_pbg.engines.v1", f"{path}: {n}"


def test_m8_dependencies_are_the_targets_own():
    text = open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8").read()
    assert "process-bigraph" in text and "bigraph-schema" in text
    host_root = os.path.abspath(os.path.join(ROOT, ".."))
    for name in ("pyproject.toml", "requirements.txt", "requirements-lock.txt"):
        p = os.path.join(host_root, name)
        if os.path.exists(p):
            body = open(p, encoding="utf-8").read().lower()
            assert "process-bigraph" not in body and "bigraph-schema" not in body, p


def test_m9_one_default_in_one_place():
    from pysed2translate_pbg import cli

    assert cli.DEFAULT_ENGINE == "v1"
    hits = [p for p in _py_files(PKG) if 'DEFAULT_ENGINE = "' in open(p, encoding="utf-8").read()]
    assert [os.path.basename(h) for h in hits] == ["cli.py"]
