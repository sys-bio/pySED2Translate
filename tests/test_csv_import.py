"""CsvImport (and the DataImport skip)."""
import json
import os
import subprocess
import sys

import numpy as np
import pytest

from pysed2translate.capabilities import load_table
from pysed2translate.runtime import DataError, ops

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")


def csv(tmp_path, text, name="d.csv"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


# --------------------------------------------------------------------------- the reader

def test_plain_numbers(tmp_path):
    d = ops.csv_import(csv(tmp_path, "1,2,3\n4,5,6\n"))
    assert d.shape == (2, 3) and d.labels == [None, None]
    np.testing.assert_array_equal(d.values, [[1, 2, 3], [4, 5, 6]])


def test_header_row_labels_the_columns(tmp_path):
    d = ops.csv_import(csv(tmp_path, "time, S1 ,S2\n0,1,2\n1,3,4\n"), headers=True)
    assert d.labels == [None, ["time", "S1", "S2"]]
    np.testing.assert_array_equal(d.values, [[0, 1, 2], [1, 3, 4]])
    # each bracket index applies to the corresponding dimension: all rows, then the column named S1
    assert d.index([("range", (None, None)), ("label", "S1")]).values.tolist() == [1, 3]


def test_column_names_when_there_is_no_header(tmp_path):
    d = ops.csv_import(csv(tmp_path, "1,2\n3,4\n"), column_names=["a", "b"])
    assert d.labels == [None, ["a", "b"]]
    # the header row wins over columnNames
    d = ops.csv_import(csv(tmp_path, "x,y\n1,2\n"), headers=True, column_names=["a", "b"])
    assert d.labels[1] == ["x", "y"]


def test_separator_blank_lines_bom_and_special_values(tmp_path):
    d = ops.csv_import(csv(tmp_path, "\ufeff1;nan\n\n inf ;-inf\n"), separator=";")
    assert d.shape == (2, 2)
    assert np.isnan(d.values[0, 1]) and d.values[1, 0] == np.inf and d.values[1, 1] == -np.inf
    t = ops.csv_import(csv(tmp_path, "1\t2\n", "t.csv"), separator="\t")
    assert t.values.tolist() == [[1, 2]]


def test_ncols_and_nrows_take_the_first_ones(tmp_path):
    p = csv(tmp_path, "a,b,c\n1,2,3\n4,5,6\n7,8,9\n")
    d = ops.csv_import(p, headers=True, ncols=2, nrows=2)
    assert d.labels[1] == ["a", "b"]
    np.testing.assert_array_equal(d.values, [[1, 2], [4, 5]])
    with pytest.raises(DataError, match="fewer"):
        ops.csv_import(p, headers=True, nrows=4)
    with pytest.raises(DataError, match="fewer"):
        ops.csv_import(p, headers=True, ncols=4)


def test_errors(tmp_path):
    with pytest.raises(DataError, match="not a number"):
        ops.csv_import(csv(tmp_path, "time,S1\n0,1\n"))
    with pytest.raises(DataError, match="expected 2"):
        ops.csv_import(csv(tmp_path, "1,2\n3\n"))
    with pytest.raises(DataError, match="single character"):
        ops.csv_import(csv(tmp_path, "1\n"), separator="ab")
    with pytest.raises(DataError, match="column names"):
        ops.csv_import(csv(tmp_path, "1,2\n"), column_names=["a"])
    with pytest.raises(DataError, match="cannot read"):
        ops.csv_import(str(tmp_path / "missing.csv"))
    with pytest.raises(DataError, match="empty|not a number"):
        ops.csv_import(csv(tmp_path, "1,\n"))


def test_empty_file(tmp_path):
    assert ops.csv_import(csv(tmp_path, "")).shape == (0, 0)
    d = ops.csv_import(csv(tmp_path, "a,b\n"), headers=True)
    assert d.shape == (0, 2) and d.labels[1] == ["a", "b"]


# --------------------------------------------------------------------------- translated documents

def run(tmp_path, doc, files):
    pytest.importorskip("libsed2")
    results_io = pytest.importorskip("sed2suite.results_io")
    from pysed2translate.translate import translate_file

    for name, text in files.items():
        (tmp_path / name).write_text(text)
    path = tmp_path / "doc.sed2.json"
    path.write_text(json.dumps(doc))
    script = tmp_path / "run.py"
    script.write_text(translate_file(str(path), "roadrunner"))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [SRC, os.environ.get("PYTHONPATH", "")])))
    r = subprocess.run([sys.executable, str(script), "--output-dir", str(tmp_path / "out")], capture_output=True,
                       text=True, env=env)
    assert r.returncode == 0, r.stderr
    return lambda name, **kw: results_io.read_csv(str(tmp_path / "out" / f"doc.{name}.csv"), **kw)


def test_csv_import_end_to_end(tmp_path):
    doc = {"version": "v1.0.0", "constants": {"sep": ";", "names": ["u", "v"], "wanted": 2},
           "tasks": {"d": {"_type": "csvImport", "location": "d.csv", "headers": True},
                     "e": {"_type": "csvImport", "location": "e.csv", "separator": "#constants:sep",
                           "columnNames": "#constants:names", "nrows": "#constants:wanted"},
                     "f": {"_type": "calculation", "math": "1 * #tasks:d[1]['S1'] * 2"}},
           "outputs": {"r": {"_type": "report", "data": "#tasks:d"}, "r2": {"_type": "report", "data": "#tasks:e"},
                       "col": {"_type": "report", "data": "#tasks:d[0:3, 1]"},
                       "twice": {"_type": "report", "data": "#tasks:f"}}}
    read = run(tmp_path, doc, {"d.csv": "time,S1\n0,1.5\n1,2.5\n2,3.5\n", "e.csv": "1;2\n3;4\n5;6\n"})
    got = read("r", ndim=2, column_labels=True)
    assert got.labels[1] == ["time", "S1"]
    np.testing.assert_allclose(got.values, [[0, 1.5], [1, 2.5], [2, 3.5]])
    got = read("r2", ndim=2, column_labels=True)
    assert got.labels[1] == ["u", "v"]
    np.testing.assert_allclose(got.values, [[1, 2], [3, 4]])
    np.testing.assert_allclose(read("col", ndim=1).values, [1.5, 2.5, 3.5])
    assert read("twice", ndim=0).values[()] == 5.0


def test_missing_file_fails_the_task(tmp_path):
    from pysed2translate.translate import translate_file

    pytest.importorskip("libsed2")
    doc = {"version": "v1.0.0", "tasks": {"d": {"_type": "csvImport", "location": "nope.csv"}},
           "outputs": {"r": {"_type": "report", "data": "#tasks:d"}}}
    path = tmp_path / "doc.sed2.json"
    path.write_text(json.dumps(doc))
    (tmp_path / "run.py").write_text(translate_file(str(path), "roadrunner"))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [SRC, os.environ.get("PYTHONPATH", "")])))
    r = subprocess.run([sys.executable, str(tmp_path / "run.py"), "--output-dir", str(tmp_path / "out")],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 1 and "cannot read the data file" in r.stderr


def test_capabilities():
    table = load_table()
    for b in table.backends:
        assert table.verdict(b, "csvImport", {"_type": "csvImport", "location": "x.csv"}) is None
        assert table.verdict(b, "csvImport", {"organization": "columns"}) is None
        assert "TODO.md: CsvImport" in table.verdict(b, "csvImport", {"organization": "rows"})
        assert "TODO.md: TaskParameter" in table.verdict(b, "csvImport", {"taskParameters": [{"id": "p"}]})
        assert "TODO.md: CsvImport" in table.verdict(b, "dataImport", {"_type": "dataImport", "location": "x", "format": "y"})
