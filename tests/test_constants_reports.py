"""Milestone M1: documents with constants and reports translate into scripts that run and write correct files.

Each generated script is run in a subprocess.  The result files are read back with sed2-test-suite's reader
(tools/sed2suite/results_io.py), which was written independently of the runtime's writers.
"""
import json
import math
import os
import subprocess
import sys

import numpy as np
import pytest

pytest.importorskip("libsed2")
results_io = pytest.importorskip("sed2suite.results_io")

from pysed2translate.backends import BACKENDS  # noqa: E402
from pysed2translate.translate import translate_file  # noqa: E402

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")

CONSTANTS = {
    "num": 1.3,
    "int": 5,
    "bool": True,
    "str": "hello",
    "vec": [1.2, 2, 6.6],
    "strs": ["how", "are", "you?"],
    "obj": {"a": 1, "b": 2},
    "table": {"S1": [1, 2, 3], "S2": [4, 5, 6]},
    "grid": [[1, 2, 3], [4, 5, 6]],
    "cube": [[[1, 2], [3, 4]], [[5, 6], [7, 8]]],
    "special": [1, "nan", "inf", "-inf"],
    "alias": "#constants:vec",
    "alias2": "#constants:alias",
    "alias3": "#constants:grid[0:1]",
    "alias4": "#constants:grid[1][2]",
    "alias5": "#constants:alias4",
    "alias_idx": "#constants:table['S2']",      # an alias whose target is indexed
    "alias_idx2": "#constants:alias_idx",       # an alias of that alias
}


def make(tmp_path, reports, constants=None, name="doc"):
    doc = {"version": "v1.0.0", "constants": CONSTANTS if constants is None else constants,
           "outputs": {rid: {"_type": "report", "data": ref} for rid, ref in reports.items()}}
    path = tmp_path / f"{name}.sed2.json"
    path.write_text(json.dumps(doc))
    return str(path)


def run_script(tmp_path, doc_path, backend="roadrunner"):
    script = tmp_path / "run.py"
    script.write_text(translate_file(doc_path, backend))
    out = tmp_path / "out"
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [SRC, os.environ.get("PYTHONPATH", "")])))
    r = subprocess.run([sys.executable, str(script), "--output-dir", str(out)], capture_output=True, text=True,
                       env=env)
    return r, out


def read(out, prefix, rid, ndim, rows=False, cols=False, dtype="number"):
    return results_io.read_csv(str(out / f"{prefix}.{rid}.csv"), ndim=ndim, row_labels=rows, column_labels=cols,
                               dtype=dtype)


@pytest.mark.parametrize("backend", BACKENDS)
def test_empty_document_runs(tmp_path, backend):
    path = tmp_path / "e.sed2.json"
    path.write_text(json.dumps({"version": "v1.0.0"}))
    r, out = run_script(tmp_path, str(path), backend)
    assert r.returncode == 0, r.stderr
    assert not out.exists() or not list(out.iterdir())


@pytest.mark.parametrize("backend", BACKENDS)
def test_constants_only_document_runs(tmp_path, backend):
    path = tmp_path / "c.sed2.json"
    path.write_text(json.dumps({"version": "v1.0.0", "constants": CONSTANTS}))
    r, _ = run_script(tmp_path, str(path), backend)
    assert r.returncode == 0, r.stderr


def test_scalars(tmp_path):
    p = make(tmp_path, {"n": "#constants:num", "i": "#constants:int", "b": "#constants:bool", "s": "#constants:str"})
    r, out = run_script(tmp_path, p)
    assert r.returncode == 0, r.stderr
    assert read(out, "doc", "n", 0).values[()] == 1.3
    assert read(out, "doc", "i", 0).values[()] == 5.0
    assert read(out, "doc", "b", 0).values[()] == 1.0
    assert read(out, "doc", "s", 0, dtype="string").values[()] == "hello"


def test_vectors_and_labels(tmp_path):
    p = make(tmp_path, {"v": "#constants:vec", "t": "#constants:strs", "sp": "#constants:special"})
    r, out = run_script(tmp_path, p)
    assert r.returncode == 0, r.stderr
    assert read(out, "doc", "v", 1).values.tolist() == [1.2, 2.0, 6.6]
    assert read(out, "doc", "t", 1, dtype="string").values.tolist() == ["how", "are", "you?"]
    sp = read(out, "doc", "sp", 1).values
    assert sp[0] == 1.0 and math.isnan(sp[1]) and sp[2] == math.inf and sp[3] == -math.inf


def test_two_and_three_dimensional(tmp_path):
    p = make(tmp_path, {"g": "#constants:grid", "c": "#constants:cube"})
    r, out = run_script(tmp_path, p)
    assert r.returncode == 0, r.stderr
    assert read(out, "doc", "g", 2).values.tolist() == [[1, 2, 3], [4, 5, 6]]
    assert not (out / "doc.c.csv").exists()
    cube = results_io.read_h5(str(out / "doc.c.h5"))
    assert cube.shape == (2, 2, 2) and cube.values.ravel().tolist() == list(range(1, 9))


def test_indexing_follows_the_spec(tmp_path):
    refs = {
        "lab": "#constants:table['S2']",         # label drops dimension 0
        "pos": "#constants:grid[1]",             # row 1
        "neg": "#constants:vec[-1]",
        "rng": "#constants:vec[1:3]",
        "both": "#constants:grid[1][0:2]",
        "open": "#constants:vec[:2]",
        "scalar": "#constants:grid[1][2]",
        "chain": "#constants:grid[0:2][1]",       # the second bracket indexes the result of the first
        "comma": "#constants:grid[0:2, 1]",       # the comma form indexes the dimensions in order
        "mix": "#constants:grid[-1, 0:2]",
    }
    p = make(tmp_path, refs)
    r, out = run_script(tmp_path, p)
    assert r.returncode == 0, r.stderr
    assert read(out, "doc", "lab", 1).values.tolist() == [4, 5, 6]
    assert read(out, "doc", "pos", 1).values.tolist() == [4, 5, 6]
    assert read(out, "doc", "neg", 0).values[()] == 6.6
    assert read(out, "doc", "rng", 1).values.tolist() == [2.0, 6.6]
    assert read(out, "doc", "both", 1).values.tolist() == [4, 5]
    assert read(out, "doc", "open", 1).values.tolist() == [1.2, 2.0]
    assert read(out, "doc", "scalar", 0).values[()] == 6.0
    assert read(out, "doc", "chain", 1).values.tolist() == [4, 5, 6]
    assert read(out, "doc", "comma", 1).values.tolist() == [2, 5]
    assert read(out, "doc", "mix", 1).values.tolist() == [4, 5]


def test_aliases_are_followed(tmp_path):
    p = make(tmp_path, {"a": "#constants:alias", "a2": "#constants:alias2", "a3": "#constants:alias[1]",
                        "a4": "#constants:alias3", "a5": "#constants:alias4", "a6": "#constants:alias5"})
    r, out = run_script(tmp_path, p)
    assert r.returncode == 0, r.stderr
    assert read(out, "doc", "a", 1).values.tolist() == [1.2, 2.0, 6.6]
    assert read(out, "doc", "a2", 1).values.tolist() == [1.2, 2.0, 6.6]
    assert read(out, "doc", "a3", 0).values[()] == 2.0
    assert read(out, "doc", "a4", 2).values.tolist() == [[1, 2, 3]]
    assert read(out, "doc", "a5", 0).values[()] == 6.0
    assert read(out, "doc", "a6", 0).values[()] == 6.0


def test_aliases_of_indexed_targets_are_followed(tmp_path):
    p = make(tmp_path, {"b1": "#constants:alias_idx", "b2": "#constants:alias_idx[0]", "b3": "#constants:alias_idx2[1]",
                        "b4": "#constants:alias_idx2"})
    r, out = run_script(tmp_path, p)
    assert r.returncode == 0, r.stderr
    assert read(out, "doc", "b1", 1).values.tolist() == [4, 5, 6]
    assert read(out, "doc", "b2", 0).values[()] == 4.0
    assert read(out, "doc", "b3", 0).values[()] == 5.0
    assert read(out, "doc", "b4", 1).values.tolist() == [4, 5, 6]


def test_prefix_and_output_names(tmp_path):
    p = make(tmp_path, {"r": "#constants:num"}, name="00042")
    r, out = run_script(tmp_path, p)
    assert r.returncode == 0, r.stderr
    assert [f.name for f in out.iterdir()] == ["00042.r.csv"]


def test_script_text_is_deterministic_and_has_no_paths(tmp_path):
    p = make(tmp_path, {"r": "#constants:grid[1]", "q": "#constants:alias2"})
    a, b = translate_file(p, "copasi"), translate_file(p, "copasi")
    assert a == b and str(tmp_path) not in a
    compile(a, "<generated>", "exec")


def test_all_backends_produce_the_same_constants_script_body(tmp_path):
    p = make(tmp_path, {"r": "#constants:table['S1']"})
    bodies = []
    for backend in BACKENDS:
        text = translate_file(p, backend)
        bodies.append("\n".join(l for l in text.splitlines() if "backend:" not in l and not l.startswith("BACKEND =")))
    assert len(set(bodies)) == 1


def test_writers_agree_with_the_suite_reader_for_special_values(tmp_path):
    p = make(tmp_path, {"sp": "#constants:special"}, constants={"special": [0.1, "nan", "inf", "-inf", 1e300, 1e-300]})
    r, out = run_script(tmp_path, p)
    assert r.returncode == 0, r.stderr
    v = read(out, "doc", "sp", 1).values
    assert v[0] == 0.1 and math.isnan(v[1]) and v[2] == math.inf and v[3] == -math.inf
    assert v[4] == 1e300 and v[5] == 1e-300


def test_null_constant_that_nothing_uses_is_fine(tmp_path):
    p = make(tmp_path, {"r": "#constants:vec"}, constants={"vec": [1, 2], "nothing": None})
    r, out = run_script(tmp_path, p)
    assert r.returncode == 0, r.stderr
    assert read(out, "doc", "r", 1).values.tolist() == [1, 2]


def test_a_failing_step_is_reported_and_does_not_stop_the_others(tmp_path, capsys):
    from pysed2translate import runtime as rt

    ctx = rt.Context(str(tmp_path), str(tmp_path / "o"), "p")
    with ctx.step("good1"):
        pass
    with ctx.step("bad"):
        rt.AnnotatedData.from_constant([1, "a"])
    with ctx.step("good2"):
        pass
    assert ctx.exit_status() == 1
    assert [f[0] for f in ctx.failures] == ["bad"]
    assert "error in bad" in capsys.readouterr().err
    assert rt.Context(str(tmp_path), str(tmp_path), "p").exit_status() == 0


@pytest.mark.parametrize("constants", [
    {"a": 5, "b": ["#constants:a", 6]},
    {"a": 5, "b": {"k": "#constants:a"}},
    {"a": 5, "b": [[1, 2], ["#constants:a", 3]]},
])
def test_reference_inside_a_list_or_dictionary_constant_is_refused(tmp_path, constants):
    """The specification does not say whether such an entry is replaced by the value it refers to (SED2/TODO.md), so
    the translator refuses instead of reporting the text of the reference as a string."""
    from pysed2translate import errors

    p = make(tmp_path, {"r": "#constants:a"}, constants=constants)
    with pytest.raises(errors.TranslationError, match="inside a list or dictionary.*SED2/TODO.md"):
        translate_file(p, "roadrunner")


def test_a_literal_string_that_only_looks_like_text_is_not_refused(tmp_path):
    p = make(tmp_path, {"r": "#constants:b"}, constants={"b": ["a#b", "c"]})
    r, out = run_script(tmp_path, p, "roadrunner")
    assert r.returncode == 0, r.stderr
