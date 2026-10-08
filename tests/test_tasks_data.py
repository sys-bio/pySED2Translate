"""End-to-end tests of the tasks that need no simulator: the generated script is run and its reports are read back
with sed2-test-suite's reader.  Expected values are computed by hand."""
import json
import math
import os
import subprocess
import sys

import pytest

pytest.importorskip("libsed2")
results_io = pytest.importorskip("sed2suite.results_io")

from pysed2translate.translate import translate_file  # noqa: E402

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")


def run_doc(tmp_path, constants=None, tasks=None, reports=None, backend="roadrunner"):
    doc = {"version": "v1.0.0", "tasks": tasks or {},
           "outputs": {rid: {"_type": "report", "data": ref} for rid, ref in (reports or {}).items()}}
    if constants:
        doc["constants"] = constants
    path = tmp_path / "doc.sed2.json"
    path.write_text(json.dumps(doc))
    script = tmp_path / "run.py"
    script.write_text(translate_file(str(path), backend))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [SRC, os.environ.get("PYTHONPATH", "")])))
    out = tmp_path / "out"
    r = subprocess.run([sys.executable, str(script), "--output-dir", str(out)], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return out


def rd(out, rid, ndim, **kw):
    return results_io.read_csv(str(out / f"doc.{rid}.csv"), ndim=ndim, **kw)


def calc(math_text):
    return {"_type": "calculation", "math": math_text}


# --------------------------------------------------------------------------- Calculation

def test_calculation_scalar_arithmetic(tmp_path):
    out = run_doc(tmp_path, constants={"x": 3, "v": [1, 2, 3], "m": [[1, 2], [3, 4]]},
                  tasks={"a": calc("2 * #constants:x + 1"),
                         "b": calc("1 + #constants:v * 2"),
                         "c": calc("1 * #constants:m * #constants:v[0:2]"),
                         "d": calc("sin(pi / 2) + #tasks:a"),
                         "e": calc("piecewise(1, #constants:x > 5, 0)"),
                         "f": calc("sum(#constants:m)")},
                  reports={"a": "#tasks:a", "b": "#tasks:b", "c": "#tasks:c", "d": "#tasks:d", "e": "#tasks:e",
                           "f": "#tasks:f"})
    assert rd(out, "a", 0).values[()] == 7.0
    assert rd(out, "b", 1).values.tolist() == [3, 5, 7]
    assert rd(out, "c", 2).values.tolist() == [[1, 4], [3, 8]]  # [1D] * [2D] multiplies each row
    assert rd(out, "d", 0).values[()] == pytest.approx(8.0)
    assert rd(out, "e", 0).values[()] == 0.0
    assert rd(out, "f", 1).values.tolist() == [4, 6]


def test_math_is_always_an_expression_even_when_it_starts_with_a_reference(tmp_path):
    """Calculation: a `math` of just `#constants:v` is that value, and `#constants:v * 2` is an expression."""
    out = run_doc(tmp_path, constants={"v": [1, 2, 3], "n": 4},
                  tasks={"a": calc("#constants:v"), "b": calc("#constants:v * 2"), "c": calc("#constants:n ^ 2"),
                         "d": calc("#constants:v[0:2] + #constants:n")},
                  reports={"a": "#tasks:a", "b": "#tasks:b", "c": "#tasks:c", "d": "#tasks:d"})
    assert rd(out, "a", 1).values.tolist() == [1, 2, 3]
    assert rd(out, "b", 1).values.tolist() == [2, 4, 6]
    assert rd(out, "c", 0).values[()] == 16.0
    assert rd(out, "d", 1).values.tolist() == [5, 6]


def test_math_accepts_the_full_index_syntax(tmp_path):
    """Comma indices, open ranges, whitespace in brackets and double-quoted labels all work inside math."""
    out = run_doc(tmp_path, constants={"v": [1, 2, 3, 4], "grid": [[1, 2, 3], [4, 5, 6]], "t": {"a": 7, "b": 8}},
                  tasks={"a": calc("sum(#constants:v[2:])"), "b": calc("#constants:grid[1, 2] * 10"),
                         "c": calc('#constants:t["b"] + 0'), "d": calc("sum(#constants:grid[0:2, 1])"),
                         "e": calc("#constants:v[ 1 : 3 ] * 1"), "f": calc("sum(#constants:v[:2])")},
                  reports={k: f"#tasks:{k}" for k in "abcdef"})
    assert rd(out, "a", 0).values[()] == 7.0
    assert rd(out, "b", 0).values[()] == 60.0
    assert rd(out, "c", 0).values[()] == 8.0
    assert rd(out, "d", 0).values[()] == 7.0
    assert rd(out, "e", 1).values.tolist() == [2, 3]
    assert rd(out, "f", 0).values[()] == 3.0


def test_calculation_uses_earlier_tasks_and_index(tmp_path):
    out = run_doc(tmp_path, constants={"v": [10, 20, 30]},
                  tasks={"a": calc("1 * #constants:v / 10"), "b": calc("0.5 + #tasks:a[1]")},
                  reports={"b": "#tasks:b"})
    assert rd(out, "b", 0).values[()] == 2.5


# --------------------------------------------------------------------------- ranges

def test_ranges(tmp_path):
    out = run_doc(
        tmp_path, constants={"n": 4, "lo": 0.0},
        tasks={
            "r1": {"_type": "numericRange", "values": [5, 6, 7]},
            "r2": {"_type": "numericRange", "numberOfSteps": 3},
            "r3": {"_type": "numericRange", "start": 0, "end": 1, "numberOfSteps": 4, "scale": "linear"},
            "r4": {"_type": "numericRange", "start": 1, "end": 100, "numberOfSteps": 2, "scale": "log10"},
            "r5": {"_type": "numericRange", "start": 0, "end": 10, "interval": 3},
            "r6": {"_type": "numericRange", "start": "#constants:lo", "interval": 2, "numberOfSteps": "#constants:n"},
            "r7": {"_type": "parameterRange", "modelElement": "k1", "values": [1, "#constants:n"]},
            "r8": {"_type": "range", "values": ["a", "b"]},
        },
        reports={f"r{i}": f"#tasks:r{i}" for i in range(1, 9)})
    assert rd(out, "r1", 1).values.tolist() == [5, 6, 7]
    assert rd(out, "r2", 1).values.tolist() == [0, 1, 2, 3]
    assert rd(out, "r3", 1).values.tolist() == [0, 0.25, 0.5, 0.75, 1]
    assert rd(out, "r4", 1).values.tolist() == pytest.approx([1, 10, 100])
    assert rd(out, "r5", 1).values.tolist() == [0, 3, 6, 9, 10]
    assert rd(out, "r6", 1).values.tolist() == [0, 2, 4, 6, 8]
    assert rd(out, "r7", 1).values.tolist() == [1, 4]
    assert rd(out, "r8", 1, dtype="string").values.tolist() == ["a", "b"]


# --------------------------------------------------------------------------- CreateDataBlock, RelabelData

def test_a_data_block_of_vectors_is_a_matrix(tmp_path):
    out = run_doc(tmp_path, constants={"v": [1, 2, 3]},
                  tasks={"blk": {"_type": "createDataBlock", "data": {"r1": "#constants:v", "r2": [4, 5, 6]}},
                         "x": calc("#tasks:blk['r2'][1] * 1"), "y": calc("#tasks:blk['r2', 1] * 1")},
                  reports={"x": "#tasks:x", "y": "#tasks:y", "row": "#tasks:blk['r2']"})
    assert rd(out, "x", 0).values[()] == 5.0 and rd(out, "y", 0).values[()] == 5.0
    assert rd(out, "row", 1).values.tolist() == [4, 5, 6]


def test_create_data_block(tmp_path):
    out = run_doc(tmp_path, constants={"v": [1, 2, 3], "k": 7, "spec": {"p": 1, "q": 2}},
                  tasks={"blk": {"_type": "createDataBlock", "data": {"a": "#constants:k", "b": 2.5}},
                         "mat": {"_type": "createDataBlock", "data": {"r1": "#constants:v", "r2": [4, 5, 6]}},
                         "viaref": {"_type": "createDataBlock", "data": "#constants:spec"}},
                  reports={"blk": "#tasks:blk", "mat": "#tasks:mat", "viaref": "#tasks:viaref"})
    b = rd(out, "blk", 1, row_labels=True)
    assert b.labels[0] == ["a", "b"] and b.values.tolist() == [7.0, 2.5]
    m = rd(out, "mat", 2, row_labels=True)
    assert m.labels[0] == ["r1", "r2"] and m.values.tolist() == [[1, 2, 3], [4, 5, 6]]
    assert rd(out, "viaref", 1, row_labels=True).values.tolist() == [1, 2]


def test_block_label_lookup_after_creation(tmp_path):
    out = run_doc(tmp_path, constants={"v": [1, 2, 3]},
                  tasks={"mat": {"_type": "createDataBlock", "data": {"r1": "#constants:v", "r2": [4, 5, 6]}}},
                  reports={"row": "#tasks:mat['r2']"})
    assert rd(out, "row", 1).values.tolist() == [4, 5, 6]


def test_relabel_data(tmp_path):
    out = run_doc(tmp_path, constants={"names": ["x", "y", "z"], "v": [10, 20, 30]},
                  tasks={"blk": {"_type": "createDataBlock", "data": {"a": 1, "b": 2, "c": 3}},
                         "rel": {"_type": "relabelData", "input": "#tasks:blk", "labels": ["P", "Q", "R"]},
                         "rel2": {"_type": "relabelData", "input": "#tasks:blk", "labels": "#constants:names"}},
                  reports={"rel": "#tasks:rel", "rel2": "#tasks:rel2", "orig": "#tasks:blk"})
    assert rd(out, "rel", 1, row_labels=True).labels[0] == ["P", "Q", "R"]
    assert rd(out, "rel2", 1, row_labels=True).labels[0] == ["x", "y", "z"]
    assert rd(out, "orig", 1, row_labels=True).labels[0] == ["a", "b", "c"]
    assert rd(out, "rel", 1, row_labels=True).values.tolist() == [1, 2, 3]


# --------------------------------------------------------------------------- StringFormation

def test_string_formation(tmp_path):
    out = run_doc(tmp_path, constants={"v": [1, 2, 3], "s": ["a", "b", "c"], "k": 2.5, "name": "S"},
                  tasks={"one": {"_type": "stringFormation", "concatenate": ["x = ", "#constants:k", " units"]},
                         "many": {"_type": "stringFormation", "concatenate": ["n = ", "#constants:v"]},
                         "pair": {"_type": "stringFormation", "concatenate": ["#constants:name", "#constants:v", "_",
                                                                              "#constants:s"]},
                         "lit": {"_type": "stringFormation", "concatenate": ["n=", [4, 5]]}},
                  reports={"one": "#tasks:one", "many": "#tasks:many", "pair": "#tasks:pair", "lit": "#tasks:lit"})
    assert rd(out, "one", 0, dtype="string").values[()] == "x = 2.5 units"
    assert rd(out, "many", 1, dtype="string").values.tolist() == ["n = 1", "n = 2", "n = 3"]
    assert rd(out, "pair", 1, dtype="string").values.tolist() == ["S1_a", "S2_b", "S3_c"]
    assert rd(out, "lit", 1, dtype="string").values.tolist() == ["n=4", "n=5"]


def test_string_formation_strings_accessor(tmp_path):
    out = run_doc(tmp_path, constants={"v": [1, 2]},
                  tasks={"s": {"_type": "stringFormation", "concatenate": ["id", "#constants:v"]}},
                  reports={"a": "#tasks:s.strings"})
    assert rd(out, "a", 1, dtype="string").values.tolist() == ["id1", "id2"]


# --------------------------------------------------------------------------- determinism and backends

def test_data_tasks_translate_identically_for_every_backend(tmp_path):
    doc = {"version": "v1.0.0", "constants": {"v": [1, 2]},
           "tasks": {"a": calc("1 + #constants:v"), "r": {"_type": "numericRange", "numberOfSteps": 2}},
           "outputs": {"o": {"_type": "report", "data": "#tasks:a"}}}
    path = tmp_path / "d.sed2.json"
    path.write_text(json.dumps(doc))
    texts = {b: "\n".join(l for l in translate_file(str(path), b).splitlines() if "backend:" not in l and not l.startswith("BACKEND ="))
             for b in ("roadrunner", "copasi", "opencor")}
    assert len(set(texts.values())) == 1
    assert translate_file(str(path), "copasi") == translate_file(str(path), "copasi")


def test_aggregation_calculation_is_skipped_for_every_backend(tmp_path):
    from pysed2translate.errors import UnsupportedTaskError

    doc = {"version": "v1.0.0", "constants": {"v": [1, 2, 3]},
           "tasks": {"agg": {"_type": "aggregationCalculation", "input": "#constants:v"}}}
    path = tmp_path / "agg.sed2.json"
    path.write_text(json.dumps(doc))
    for backend in ("roadrunner", "copasi", "opencor"):
        with pytest.raises(UnsupportedTaskError, match="aggregation function"):
            translate_file(str(path), backend)
