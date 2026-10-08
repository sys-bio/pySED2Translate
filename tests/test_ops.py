"""Hand-computed expectations for the runtime operations in runtime/ops.py."""
import math

import numpy as np
import pytest

from pysed2translate.runtime import AnnotatedData, DataError, ops


def vals(x):
    return x.values.tolist()


# --------------------------------------------------------------------------- numeric_range

def test_explicit_values():
    assert vals(ops.numeric_range(values=[0, 1, 5])) == [0, 1, 5]
    with pytest.raises(DataError):
        ops.numeric_range(values=[1], start=0)


def test_number_of_steps_alone_runs_from_zero_to_n():
    assert vals(ops.numeric_range(number_of_steps=4)) == [0, 1, 2, 3, 4]


def test_start_end_steps_linear():
    assert vals(ops.numeric_range(start=0, end=10, number_of_steps=5)) == [0, 2, 4, 6, 8, 10]
    assert vals(ops.numeric_range(start=1, end=2, number_of_steps=2, scale="linear")) == [1, 1.5, 2]


def test_start_end_steps_log10():
    r = vals(ops.numeric_range(start=1, end=1000, number_of_steps=3, scale="log10"))
    np.testing.assert_allclose(r, [1, 10, 100, 1000], rtol=1e-12)
    assert r[0] == 1 and r[-1] == 1000  # endpoints are exact
    with pytest.raises(DataError):
        ops.numeric_range(start=0, end=10, number_of_steps=2, scale="log10")


def test_start_steps_interval_and_end_steps_interval():
    assert vals(ops.numeric_range(start=2, number_of_steps=3, interval=0.5)) == [2, 2.5, 3, 3.5]
    assert vals(ops.numeric_range(end=10, number_of_steps=3, interval=2)) == [4, 6, 8, 10]


def test_start_interval_end_follow_the_spec_examples():
    assert vals(ops.numeric_range(start=0, end=10, interval=3)) == [0, 3, 6, 9, 10]
    r = vals(ops.numeric_range(start=0, end=10, interval=3.333))
    np.testing.assert_allclose(r, [0, 3.333, 6.666, 9.999, 10], rtol=1e-12)
    r = vals(ops.numeric_range(start=0, end=10, interval=3.333333))
    np.testing.assert_allclose(r, [0, 3.333333, 6.666666, 10], rtol=1e-12)
    assert vals(ops.numeric_range(start=0, end=9, interval=3)) == [0, 3, 6, 9]  # end on a boundary appears once


def test_invalid_range_combinations():
    for kwargs in ({}, {"start": 0}, {"start": 0, "end": 1}, {"scale": "linear"}, {"number_of_steps": 3, "scale": "linear"},
                   {"number_of_steps": 0}, {"number_of_steps": 2.5}, {"start": 0, "end": 1, "number_of_steps": 2, "scale": "sqrt"}):
        with pytest.raises(DataError):
            ops.numeric_range(**kwargs)


# --------------------------------------------------------------------------- scalars and lists

def test_scalar_and_lists():
    assert ops.scalar(AnnotatedData(np.asarray(2.5))) == 2.5
    assert ops.scalar(True) == 1.0 and ops.scalar(3) == 3.0
    with pytest.raises(DataError):
        ops.scalar(AnnotatedData(np.ones(2)))
    with pytest.raises(DataError):
        ops.scalar("x")
    assert ops.numbers_from(AnnotatedData(np.array([1.0, 2.0]))) == [1.0, 2.0]
    with pytest.raises(DataError):
        ops.numbers_from(AnnotatedData(np.ones((2, 2))))
    assert ops.strings_from(AnnotatedData.from_constant(["a", "b"])) == ["a", "b"]
    assert ops.string_scalar(AnnotatedData.from_constant("hi")) == "hi"


# --------------------------------------------------------------------------- block and relabel

def test_block_of_scalars_labels_the_dimension():
    b = ops.block(["x", "y"], [AnnotatedData(np.asarray(1.0)), 2])
    assert b.labels == [["x", "y"]] and vals(b) == [1.0, 2.0]


def test_block_of_vectors_makes_a_matrix():
    b = ops.block(["a", "b"], [[1, 2, 3], [4, 5, 6]])
    assert b.shape == (2, 3) and b.labels == [["a", "b"], None] and vals(b) == [[1, 2, 3], [4, 5, 6]]


def test_block_errors():
    with pytest.raises(DataError):
        ops.block(["a", "b"], [[1, 2], [1, 2, 3]])
    with pytest.raises(DataError):
        ops.block(["a", "b"], [1, "s"])
    with pytest.raises(DataError):
        ops.block(["a"], [1, 2])
    assert ops.block([], []).shape == (0,)


def test_relabel_replaces_only_the_first_dimension():
    d = AnnotatedData(np.arange(6.0).reshape(2, 3), [["a", "b"], ["x", "y", "z"]], ["rows", "cols"])
    r = ops.relabel(d, ["P", "Q"])
    assert r.labels == [["P", "Q"], ["x", "y", "z"]] and r.dims == ["rows", "cols"] and vals(r) == vals(d)
    assert d.labels[0] == ["a", "b"]  # the input is not changed
    assert ops.relabel(AnnotatedData(np.ones(2)), ["u", "v"]).labels == [["u", "v"]]
    with pytest.raises(DataError):
        ops.relabel(d, ["only one"])
    with pytest.raises(DataError):
        ops.relabel(AnnotatedData(np.asarray(1.0)), [])


# --------------------------------------------------------------------------- string formation

def test_scalar_pieces():
    r = ops.string_formation(["a", 1, "-", 2.5, True])
    assert r.ndim == 0 and r.values[()] == "a1-2.5true"


def test_spec_example_list_expands_to_strings():
    r = ops.string_formation(["n = ", AnnotatedData.from_constant([1, 2, 3])])
    assert r.shape == (3,) and vals(r) == ["n = 1", "n = 2", "n = 3"]


def test_lists_combine_pairwise_and_keep_labels():
    a = AnnotatedData(np.array([1.0, 2.0]), [["u", "v"]], ["d"])
    b = AnnotatedData.from_constant(["x", "y"])
    r = ops.string_formation([a, "_", b])
    assert vals(r) == ["1_x", "2_y"] and r.labels == [["u", "v"]] and r.dims == ["d"]


def test_two_dimensional_strings():
    m = AnnotatedData.from_constant([[1, 2], [3, 4]])
    r = ops.string_formation(["<", m, ">"])
    assert r.shape == (2, 2) and vals(r) == [["<1>", "<2>"], ["<3>", "<4>"]]


def test_lists_of_different_shape_are_an_error():
    with pytest.raises(DataError):
        ops.string_formation([AnnotatedData.from_constant([1, 2]), AnnotatedData.from_constant([1, 2, 3])])


@pytest.mark.parametrize("x,text", [(3.0, "3"), (-4.0, "-4"), (0.0, "0"), (2.5, "2.5"), (1e20, "1e+20"),
                                    (math.nan, "nan"), (math.inf, "inf"), (-math.inf, "-inf"), (0.1, "0.1")])
def test_number_text(x, text):
    assert ops.number_text(x) == text
