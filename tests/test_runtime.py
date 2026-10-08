import math
import random

import numpy as np
import pytest

from pysed2translate import runtime as rt
from pysed2translate.runtime import AnnotatedData, DataError


# ---------------------------------------------------------------- from_constant

def test_scalars():
    a = AnnotatedData.from_constant(1.5)
    assert a.ndim == 0 and a.values[()] == 1.5 and not a.is_string
    assert AnnotatedData.from_constant(True).values[()] == 1.0
    assert AnnotatedData.from_constant(7).values[()] == 7.0
    s = AnnotatedData.from_constant("hello")
    assert s.ndim == 0 and s.is_string and s.values[()] == "hello"


def test_lists_and_matrices():
    a = AnnotatedData.from_constant([10, 20, 30])
    assert a.shape == (3,) and a.labels == [None] and a.values.tolist() == [10.0, 20.0, 30.0]
    m = AnnotatedData.from_constant([[1, 2, 3], [4, 5, 6]])
    assert m.shape == (2, 3) and m.labels == [None, None]
    t = AnnotatedData.from_constant([[[1, 2], [3, 4]], [[5, 6], [7, 8]]])
    assert t.shape == (2, 2, 2)
    e = AnnotatedData.from_constant([])
    assert e.shape == (0,)


def test_dictionaries_label_the_first_dimension():
    d = AnnotatedData.from_constant({"a": 1, "b": 2})
    assert d.shape == (2,) and d.labels == [["a", "b"]] and d.values.tolist() == [1.0, 2.0]
    ds = AnnotatedData.from_constant({"a": "x", "b": "y"})
    assert ds.is_string and ds.labels == [["a", "b"]]
    dl = AnnotatedData.from_constant({"S1": [1, 2, 3], "S2": [4, 5, 6]})
    assert dl.shape == (2, 3) and dl.labels == [["S1", "S2"], None]
    dd = AnnotatedData.from_constant({"r1": {"c1": 1, "c2": 2}, "r2": {"c1": 3, "c2": 4}})
    assert dd.shape == (2, 2) and dd.labels == [["r1", "r2"], ["c1", "c2"]]


def test_special_values():
    a = AnnotatedData.from_constant([1, "nan", "INF", "-inf"])
    assert not a.is_string
    assert a.values[0] == 1.0 and math.isnan(a.values[1]) and a.values[2] == math.inf and a.values[3] == -math.inf
    assert math.isnan(AnnotatedData.from_constant("nan").values[()])
    # in a list that has real strings, 'nan' is just text
    s = AnnotatedData.from_constant(["a", "nan"])
    assert s.is_string and s.values.tolist() == ["a", "nan"]


@pytest.mark.parametrize("bad", [[1, "a"], [[1, 2], [3]], None, [1, None], {"a": [1], "b": [1, 2]},
                                 {"a": {"x": 1}, "b": {"y": 1}}, [{"a": 1}, {"b": 1}]])
def test_bad_constants(bad):
    with pytest.raises(DataError):
        AnnotatedData.from_constant(bad)


# ---------------------------------------------------------------- indexing

def test_index_int_and_negative():
    a = AnnotatedData.from_constant([[1, 2, 3], [4, 5, 6]])
    assert a.index([("int", 1)]).values.tolist() == [4.0, 5.0, 6.0]
    assert a.index([("int", -1), ("int", 2)]).values[()] == 6.0
    assert a.index([("int", 0), ("int", -3)]).values[()] == 1.0
    with pytest.raises(DataError):
        a.index([("int", 2)])
    with pytest.raises(DataError):
        a.index([("int", -3)])


def test_index_label():
    a = AnnotatedData.from_constant({"S1": [1, 2], "S2": [3, 4]})
    r = a.index([("label", "S2")])
    assert r.values.tolist() == [3.0, 4.0] and r.labels == [None]
    assert a.index([("label", "S1"), ("int", 1)]).values[()] == 2.0
    with pytest.raises(DataError):
        a.index([("label", "S3")])
    with pytest.raises(DataError):
        AnnotatedData.from_constant([1, 2]).index([("label", "x")])


def test_index_range_keeps_dimension():
    a = AnnotatedData.from_constant({"a": 1, "b": 2, "c": 3, "d": 4})
    r = a.index([("range", (1, 3))])
    assert r.values.tolist() == [2.0, 3.0] and r.labels == [["b", "c"]]
    assert a.index([("range", (-3, -1))]).labels == [["b", "c"]]
    assert a.index([("range", (None, 2))]).labels == [["a", "b"]]
    assert a.index([("range", (2, None))]).labels == [["c", "d"]]
    assert a.index([("range", (3, 100))]).labels == [["d"]]
    for empty in ((3, 1), (2, 2), (10, None)):      # "Any indexing must select at least one entry"
        with pytest.raises(DataError, match="selects no entry"):
            a.index([("range", empty)])


def test_comma_indices_apply_to_the_dimensions_in_order():
    m = AnnotatedData.from_constant([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
    r = m.index([[("range", (0, 2)), ("int", 1)]])          # [0:2, 1]: column 1 of rows 0 and 1
    assert r.shape == (2,) and r.values.tolist() == [2.0, 5.0]
    r = m.index([[("range", (1, 3)), ("range", (0, 2))]])   # [1:3, 0:2]
    assert r.shape == (2, 2) and r.values.tolist() == [[4.0, 5.0], [7.0, 8.0]]
    assert m.index([[("int", -1), ("int", -1)]]).values[()] == 9.0


def test_a_second_bracket_applies_to_the_result_of_the_first():
    m = AnnotatedData.from_constant([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
    # [0:2][1] : a range keeps its dimension, so [1] is row 1 of the two selected rows
    r = m.index([[("range", (0, 2))], [("int", 1)]])
    assert r.shape == (3,) and r.values.tolist() == [4.0, 5.0, 6.0]
    # [2:3][0] is the same as [2]
    assert m.index([[("range", (2, 3))], [("int", 0)]]).values.tolist() == m.index([[("int", 2)]]).values.tolist()
    # [3][5]-style: an integer removes its dimension, so the second bracket indexes the next one
    assert m.index([[("int", 1)], [("int", 2)]]).values[()] == 6.0
    assert m.index([[("int", 1)], [("range", (0, 2))]]).values.tolist() == [4.0, 5.0]
    # the brackets after a range index the narrowed data (negative values count from its end)
    assert m.index([[("range", (1, 3))], [("int", -1)]]).values.tolist() == [7.0, 8.0, 9.0]
    with pytest.raises(DataError):
        m.index([[("range", (0, 1))], [("int", 1)]])        # only one row was selected


def test_too_many_indices():
    with pytest.raises(DataError):
        AnnotatedData.from_constant([1, 2]).index([("int", 0), ("int", 0)])


def test_numeric_label_lookup():
    a = AnnotatedData(np.array([10.0, 20.0]), [[0.0, 0.5]])
    assert a.index([("label", "0.5")]).values[()] == 20.0


def test_constructor_checks():
    with pytest.raises(DataError):
        AnnotatedData(np.zeros(3), [["a", "b"]])
    with pytest.raises(DataError):
        AnnotatedData(np.zeros((2, 2)), [None])


# ---------------------------------------------------------------- CSV text

def test_csv_exact_text():
    assert rt.csv_text(AnnotatedData(np.array(1.5))) == "1.5\n"
    assert rt.csv_text(AnnotatedData(np.array([1.0, 2.0, 3.0]))) == "1.0\n2.0\n3.0\n"
    assert rt.csv_text(AnnotatedData(np.array([1.0, 2.0]), [["a", "b"]])) == "a,1.0\nb,2.0\n"
    m = AnnotatedData(np.array([[1.0, 2.0], [3.0, 4.0]]), [None, ["x", "y"]])
    assert rt.csv_text(m) == "x,y\n1.0,2.0\n3.0,4.0\n"
    both = AnnotatedData(np.array([[1.0, 2.0], [3.0, 4.0]]), [["r1", "r2"], ["x", "y"]])
    assert rt.csv_text(both) == ",x,y\nr1,1.0,2.0\nr2,3.0,4.0\n"
    rows = AnnotatedData(np.array([[1.0, 2.0]]), [["r1"], None])
    assert rt.csv_text(rows) == "r1,1.0,2.0\n"


def test_csv_special_values_and_quoting():
    a = AnnotatedData(np.array([math.nan, math.inf, -math.inf, 0.1, -0.0, 1e-5, 1e22]))
    assert rt.csv_text(a) == "nan\ninf\n-inf\n0.1\n-0.0\n1e-05\n1e+22\n"
    s = AnnotatedData(np.array(['a,b', 'say "hi"', "plain", "two\nlines"], dtype=object))
    assert rt.csv_text(s) == '"a,b"\n"say ""hi"""\nplain\n"two\nlines"\n'


def test_csv_rejects_3d():
    with pytest.raises(DataError):
        rt.csv_text(AnnotatedData(np.zeros((2, 2, 2))))


def test_format_number():
    assert rt.format_number(3) == "3.0"
    assert rt.format_number(np.float64(0.5)) == "0.5"
    assert rt.format_number(True) == "1.0"


# ---------------------------------------------------------------- files

def test_write_report_chooses_format(tmp_path):
    ctx = rt.Context(str(tmp_path), str(tmp_path / "out"), "00001")
    p2 = rt.write_report(ctx, "r2", AnnotatedData(np.zeros((2, 2))))
    assert p2.endswith("00001.r2.csv") and open(p2, encoding="utf-8").read() == "0.0,0.0\n0.0,0.0\n"
    pytest.importorskip("h5py")
    p3 = rt.write_report(ctx, "r3", AnnotatedData(np.zeros((2, 2, 2))))
    assert p3.endswith("00001.r3.h5")


def test_context_paths(tmp_path):
    ctx = rt.Context(str(tmp_path), str(tmp_path / "o"), "T")
    assert ctx.input_path("m.xml") == str(tmp_path / "m.xml")
    assert ctx.input_path("sub/../m.xml") == str(tmp_path / "m.xml")
    assert ctx.input_path(str(tmp_path / "abs.xml")) == str(tmp_path / "abs.xml")
    assert ctx.output_path("rep.csv") == str(tmp_path / "o" / "T.rep.csv")
    assert (tmp_path / "o").is_dir()


# ---------------------------------------------------------------- cross-check against the suite's independent reader

suite = pytest.importorskip("sed2suite.results_io", reason="sed2-test-suite tools not found")


def random_data(rng, ndim, string=False):
    shape = tuple(rng.randint(1, 4) for _ in range(ndim))
    if string:
        words = ["a", "b,c", 'q"uote', "x y", "z"]
        vals = np.array([rng.choice(words) for _ in range(int(np.prod(shape)) or 1)], dtype=object)[: int(np.prod(shape))]
        vals = vals.reshape(shape) if ndim else np.asarray(rng.choice(words), dtype=object)
    else:
        specials = [math.nan, math.inf, -math.inf, 0.1, -2.5, 1e-9, 12345.678, 1.0 / 3.0]
        vals = np.array([rng.choice(specials) for _ in range(int(np.prod(shape)))]).reshape(shape) if ndim else np.asarray(0.25)
    labels = []
    for n in shape:
        labels.append(None if rng.random() < 0.5 else [f"L{rng.randint(0, 9)}_{i}" for i in range(n)])
    return AnnotatedData(vals, labels)


@pytest.mark.parametrize("ndim", [0, 1, 2])
@pytest.mark.parametrize("string", [False, True])
def test_csv_round_trip_with_suite_reader(tmp_path, ndim, string):
    rng = random.Random(1234 + ndim + 10 * string)
    for k in range(25):
        d = random_data(rng, ndim, string)
        path = str(tmp_path / f"r{k}.csv")
        rt.write_csv(path, d)
        got = suite.read_csv(path, ndim=ndim, row_labels=ndim >= 1 and d.labels[0] is not None,
                             column_labels=ndim == 2 and d.labels[1] is not None,
                             dtype="string" if string else "number")
        assert got.shape == d.shape
        assert [None if l is None else list(l) for l in got.labels] == d.labels
        if string:
            assert got.values.tolist() == d.values.tolist()
        else:
            a, b = got.values.astype(float), d.values.astype(float)
            assert np.array_equal(np.isnan(a), np.isnan(b))
            assert np.array_equal(a[~np.isnan(a)], b[~np.isnan(b)])


@pytest.mark.parametrize("string", [False, True])
def test_h5_round_trip_with_suite_reader(tmp_path, string):
    pytest.importorskip("h5py")
    rng = random.Random(99)
    for k in range(10):
        d = random_data(rng, 3, string)
        d.dims = ["x", "", "z"]
        path = str(tmp_path / f"r{k}.h5")
        rt.write_h5(path, d)
        got = suite.read_h5(path)
        assert got.shape == d.shape and list(got.dims) == d.dims
        assert [None if l is None else list(l) for l in got.labels] == d.labels
        if string:
            assert got.values.tolist() == d.values.tolist()
        else:
            a, b = got.values.astype(float), d.values.astype(float)
            assert np.array_equal(np.isnan(a), np.isnan(b)) and np.array_equal(a[~np.isnan(a)], b[~np.isnan(b)])
