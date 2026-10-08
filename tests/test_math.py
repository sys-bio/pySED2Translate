"""Tests for the math runtime (runtime/mathfn.py) and the AST-to-Python translator (mathgen.py)."""
import math

import numpy as np
import pytest

import libsed2._predefined_functions as registry

from pysed2translate import mathgen
from pysed2translate.errors import TranslationError
from pysed2translate.runtime import Context  # noqa: F401  (import check)
from pysed2translate.runtime import mathfn as m
from pysed2translate.runtime.annotated import AnnotatedData, DataError


class _Rt:
    """The `rt` namespace seen by generated code, reduced to what the math needs."""
    m = m


def ev(text, **names):
    """Translate `text` and evaluate the Python it produces."""
    code = mathgen.math_to_python(
        text, resolve_reference=lambda r: f"REFS[{r!r}]",
        resolve_name=lambda n: f"NAMES[{n!r}]" if n in names else None)
    return eval(code, {"rt": _Rt, "REFS": {}, "NAMES": names})  # noqa: S307 - our own generated code


def val(x):
    return x.values if isinstance(x, AnnotatedData) else np.asarray(x)


def close(actual, expected, tol=1e-12):
    a, e = val(actual), np.asarray(expected, dtype=float)
    assert a.shape == e.shape, (a.shape, e.shape)
    np.testing.assert_allclose(a, e, rtol=tol, atol=tol, equal_nan=True)


# --------------------------------------------------------------------------- registry coverage

def _arities(spec):
    kind = spec[0]
    if kind == "set":
        return sorted(spec[1])
    lo, hi = spec[1], spec[2]
    return list(range(lo, (hi if hi is not None else lo + 3) + 1))


def test_every_registry_function_is_implemented():
    missing = sorted(set(registry.FUNCTIONS) - set(m.FUNCTIONS))
    assert not missing, f"libsed2 predefined functions with no runtime implementation: {missing}"


def test_every_registry_constant_is_implemented():
    assert set(registry.CONSTANTS) == set(m.CONSTANTS)


def test_runtime_has_no_unknown_functions():
    assert sorted(set(m.FUNCTIONS) - set(registry.FUNCTIONS)) == []


# arguments that are inside every function's domain, by name
_SAMPLE = {
    "arccosh": 1.5, "arcsech": 0.5, "arctanh": 0.5, "arccoth": 2.0, "arcsec": 2.0, "arccsc": 2.0, "arcsin": 0.5,
    "arccos": 0.5, "factorial": 5, "ln": 2.0, "log": 10.0,
}


def _call_args(name, n):
    base = _SAMPLE.get(name, 0.75)
    if name in ("uniform",):
        return [0.0, 1.0]
    if name in ("normal", "lognormal"):
        return [0.0, 1.0][:2] + ([-100.0, 100.0] if n == 4 else [])
    if name == "binomial":
        return [10, 0.5] + ([0, 10] if n == 4 else [])
    if name == "bernoulli":
        return [0.5]
    if name in ("cauchy", "laplace"):
        full = {1: [1.0], 2: [0.0, 1.0], 4: [0.0, 1.0, -1000.0, 1000.0]}
        return full[n]
    if name == "gamma":
        return [2.0, 1.0] + ([0.0, 100.0] if n == 4 else [])
    if name in ("chisquare", "exponential", "poisson", "rayleigh"):
        return [2.0] + ([0.0, 100.0] if n == 3 else [])
    if name == "piecewise":
        return [base] * n
    return [base] * n


def test_every_registry_function_runs_for_every_allowed_arity():
    for name, spec in registry.FUNCTIONS.items():
        for n in _arities(spec):
            if name in ("and", "or", "xor") and n == 0:
                args = []
            else:
                args = _call_args(name, n)
            if name in ("eq", "lt", "gt", "leq", "geq", "neq", "implies", "min", "max", "and", "or", "xor", "sum"):
                args = [1.0] * n
            if name == "sum":
                args = [AnnotatedData(np.array([1.0, 2.0]))]
            result = m.FUNCTIONS[name](*args)
            arr = val(result)
            assert arr.dtype.kind == "f", (name, n)
            assert arr.shape == () or name == "sum", (name, n, arr.shape)


def test_generated_names_use_trailing_underscore_for_keywords():
    assert m.python_name("and") == "and_" and m.python_name("or") == "or_" and m.python_name("not") == "not_"
    assert m.python_name("sin") == "sin"
    for name in m.FUNCTIONS:
        assert callable(getattr(m, m.python_name(name))), name


# --------------------------------------------------------------------------- operators and precedence

@pytest.mark.parametrize("text,expected", [
    ("1 + 2 * 3", 7.0),
    ("(1 + 2) * 3", 9.0),
    ("10 - 4 - 3", 3.0),
    ("100 / 10 / 5", 2.0),
    ("2 ^ 3", 8.0),
    ("2 ^ 3 ^ 2", 512.0),
    ("-2 ^ 2", -4.0),
    ("+5", 5.0),
    ("- - 3", 3.0),
    ("7 % 3", 1.0),
    ("-7 % 3", -1.0),
    ("7 % -3", 1.0),
    ("1 / 0", math.inf),
    ("-1 / 0", -math.inf),
    ("0 / 0", math.nan),
    ("2 * pi", 2 * math.pi),
    ("exponentiale", math.e),
    ("infinity", math.inf),
    ("notanumber", math.nan),
    ("true + true", 2.0),
    ("false", 0.0),
    ("1.5e3", 1500.0),
])
def test_operators(text, expected):
    close(ev(text), expected)


# --------------------------------------------------------------------------- function values

@pytest.mark.parametrize("text,expected", [
    ("abs(-3)", 3.0), ("exp(1)", math.e), ("ln(exponentiale)", 1.0), ("log(1000)", 3.0), ("log(2, 8)", 3.0),
    ("floor(-1.5)", -2.0), ("ceiling(-1.5)", -1.0), ("root(9)", 3.0), ("root(3, 27)", 3.0),
    ("quotient(7, 2)", 3.0), ("quotient(-7, 2)", -3.0), ("rem(7, 3)", 1.0), ("rem(-7, 3)", -1.0),
    ("factorial(5)", 120.0), ("factorial(0)", 1.0), ("factorial(-1)", math.nan), ("factorial(2.5)", math.nan),
    ("min(3, 1, 2)", 1.0), ("max(3, 1, 2)", 3.0), ("min(4)", 4.0),
    ("sin(1)", math.sin(1)), ("cos(1)", math.cos(1)), ("tan(1)", math.tan(1)),
    ("sec(1)", 1 / math.cos(1)), ("csc(1)", 1 / math.sin(1)), ("cot(1)", 1 / math.tan(1)),
    ("sinh(1)", math.sinh(1)), ("cosh(1)", math.cosh(1)), ("tanh(1)", math.tanh(1)),
    ("sech(1)", 1 / math.cosh(1)), ("csch(1)", 1 / math.sinh(1)), ("coth(1)", 1 / math.tanh(1)),
    ("arcsin(0.5)", math.asin(0.5)), ("arccos(0.5)", math.acos(0.5)), ("arctan(2)", math.atan(2)),
    ("arcsec(2)", math.acos(0.5)), ("arccsc(2)", math.asin(0.5)), ("arccot(2)", math.atan(0.5)),
    ("arcsinh(1)", math.asinh(1)), ("arccosh(2)", math.acosh(2)), ("arctanh(0.5)", math.atanh(0.5)),
    ("arcsech(0.5)", math.acosh(2)), ("arccsch(2)", math.asinh(0.5)), ("arccoth(2)", math.atanh(0.5)),
])
def test_function_values(text, expected):
    close(ev(text), expected)


def test_domain_errors_give_nan_not_exceptions():
    close(ev("ln(-1)"), math.nan)
    close(ev("arcsin(2)"), math.nan)
    close(ev("root(-4)"), math.nan)


# --------------------------------------------------------------------------- relational and logical

@pytest.mark.parametrize("text,expected", [
    ("1 < 2", 1.0), ("2 < 1", 0.0), ("1 <= 1", 1.0), ("2 > 1", 1.0), ("1 >= 2", 0.0),
    ("1 == 1", 1.0), ("1 != 1", 0.0), ("1 != 2", 1.0),
    ("1 < 2 <= 2", 1.0), ("1 < 3 <= 2", 0.0), ("eq(2, 2, 2)", 1.0), ("eq(2, 2, 3)", 0.0),
    ("and(1, 1, 0)", 0.0), ("and(1, 2)", 1.0), ("and()", 1.0),
    ("or(0, 0, 1)", 1.0), ("or(0, 0)", 0.0), ("or()", 0.0),
    ("xor(1, 1)", 0.0), ("xor(1, 0)", 1.0), ("xor(1, 1, 1)", 1.0), ("xor()", 0.0),
    ("not(0)", 1.0), ("not(5)", 0.0), ("implies(1, 0)", 0.0), ("implies(0, 0)", 1.0), ("implies(1, 1)", 1.0),
    ("true && false", 0.0), ("true || false", 1.0), ("!true", 0.0),
    ("notanumber == notanumber", 0.0), ("not(notanumber)", 1.0),
])
def test_relational_and_logical(text, expected):
    close(ev(text), expected)


@pytest.mark.parametrize("text,expected", [
    ("piecewise(1, 2 > 3, 5)", 5.0),
    ("piecewise(1, 2 < 3, 5)", 1.0),
    ("piecewise(1, 0, 2, 1, 3)", 2.0),
    ("piecewise(1, 0, 2, 0)", math.nan),
    ("piecewise(1, 1)", 1.0),
    ("piecewise(7)", 7.0),
])
def test_piecewise(text, expected):
    close(ev(text), expected)


# --------------------------------------------------------------------------- arrays, broadcasting, labels

def test_array_literal_and_scalar_broadcast():
    r = ev("5 + [1, 2, 3]")
    assert isinstance(r, AnnotatedData)
    close(r, [6, 7, 8])


def test_array_of_arrays_is_two_dimensional():
    r = ev("[[1, 2], [3, 4]]")
    assert r.shape == (2, 2)
    close(r, [[1, 2], [3, 4]])


def test_lower_dim_operand_broadcasts_over_trailing_dims():
    a = AnnotatedData(np.array([10.0, 20.0, 30.0]))  # (3,)
    b = AnnotatedData(np.arange(6.0).reshape(2, 3))  # (2, 3)
    close(m.mul(a, b), [[0, 20, 60], [30, 80, 150]])
    close(m.mul(b, a), [[0, 20, 60], [30, 80, 150]])


def test_equal_dim_size_mismatch_is_an_error():
    with pytest.raises(DataError):
        m.add(AnnotatedData(np.ones(3)), AnnotatedData(np.ones(4)))
    with pytest.raises(DataError):
        m.add(AnnotatedData(np.ones((2, 3))), AnnotatedData(np.ones(2)))


def test_label_mismatch_is_an_error_and_labels_propagate():
    a = AnnotatedData(np.array([1.0, 2.0]), [["x", "y"]], ["species"])
    b = AnnotatedData(np.array([3.0, 4.0]), [["x", "z"]], ["species"])
    with pytest.raises(DataError):
        m.add(a, b)
    c = AnnotatedData(np.array([3.0, 4.0]))  # unlabelled operand adopts the labels
    r = m.add(a, c)
    assert r.labels[0] == ["x", "y"] and r.dims[0] == "species"
    close(r, [4, 6])


def test_labels_survive_unary_functions():
    a = AnnotatedData(np.array([1.0, 4.0]), [["x", "y"]], ["species"])
    r = m.root(a)
    assert r.labels[0] == ["x", "y"]
    close(r, [1, 2])


def test_strings_are_rejected():
    s = AnnotatedData(np.array(["a", "b"], dtype=object))
    with pytest.raises(DataError):
        m.add(s, 1.0)
    with pytest.raises(DataError):
        m.sin("text")


def test_sum_reduces_first_dimension():
    two_d = AnnotatedData(np.array([[1.0, 2.0], [3.0, 4.0]]), [["r1", "r2"], ["a", "b"]], ["row", "col"])
    r = m.sum(two_d)
    close(r, [4, 6])
    assert r.labels == [["a", "b"]] and r.dims == ["col"]
    assert val(m.sum(ev("[1, 2, 3]"))).shape == ()
    close(m.sum(ev("[1, 2, 3]")), 6.0)
    assert m.sum(2.5) == 2.5


def test_min_max_are_elementwise_over_arguments():
    close(ev("min([1, 5, 3], 2)"), [1, 2, 2])
    close(ev("max([1, 5, 3], [4, 4, 4])"), [4, 5, 4])


def test_array_entries_must_match_in_shape():
    with pytest.raises(DataError):
        m.array(AnnotatedData(np.ones(2)), AnnotatedData(np.ones(3)))


def test_to_data():
    assert m.to_data(3).shape == ()
    d = AnnotatedData(np.ones(2))
    assert m.to_data(d) is d


def test_scalar_in_scalar_out():
    assert isinstance(ev("1 + 2"), float)
    assert isinstance(ev("sin(1)"), float)


# --------------------------------------------------------------------------- distributions

N = 20000


def _draws(text, n=N):
    m.seed(1)
    return val(ev(f"{text}")) if n == 1 else None


def _sample(fn, *args, n=N):
    m.seed(123)
    ones = AnnotatedData(np.ones(n))
    # scalar parameters are broadcast against a length-n array to get n independent draws
    return val(fn(*[m.mul(ones, a) for a in args]))


def test_distribution_statistics():
    s = _sample(m.normal, 3.0, 2.0)
    assert abs(s.mean() - 3.0) < 0.1 and abs(s.std() - 2.0) < 0.1
    u = _sample(m.uniform, 2.0, 4.0)
    assert u.min() >= 2.0 and u.max() <= 4.0 and abs(u.mean() - 3.0) < 0.05
    assert abs(_sample(m.exponential, 2.0).mean() - 0.5) < 0.02
    assert abs(_sample(m.poisson, 4.0).mean() - 4.0) < 0.1
    assert abs(_sample(m.bernoulli, 0.3).mean() - 0.3) < 0.02
    assert abs(_sample(m.binomial, 10.0, 0.5).mean() - 5.0) < 0.1
    assert abs(_sample(m.gamma, 2.0, 3.0).mean() - 6.0) < 0.2
    assert abs(_sample(m.chisquare, 4.0).mean() - 4.0) < 0.15
    assert abs(_sample(m.rayleigh, 2.0).mean() - 2.0 * math.sqrt(math.pi / 2)) < 0.05
    assert abs(np.median(_sample(m.cauchy, 5.0, 1.0)) - 5.0) < 0.1
    assert abs(_sample(m.laplace, 1.0, 2.0).mean() - 1.0) < 0.1
    assert np.all(_sample(m.lognormal, 0.0, 0.5) > 0)


def test_cauchy_and_laplace_single_argument_means_scale_with_location_zero():
    assert abs(np.median(_sample(m.cauchy, 1.0))) < 0.1
    assert abs(_sample(m.laplace, 1.0).mean()) < 0.1


def test_distribution_truncation_by_min_max():
    s = _sample(m.normal, 0.0, 1.0, 0.5, 1.0)
    assert s.min() >= 0.5 and s.max() <= 1.0
    p = _sample(m.poisson, 4.0, 2.0, 3.0)
    assert set(np.unique(p)) <= {2.0, 3.0}


def test_seed_makes_draws_repeatable_and_default_seed_is_zero():
    m.seed(7)
    a = val(m.normal(0.0, 1.0))
    m.seed(7)
    b = val(m.normal(0.0, 1.0))
    assert float(a) == float(b)
    m.seed(0)
    first = float(val(m.uniform(0.0, 1.0)))
    assert first == float(np.random.default_rng(0).uniform(0.0, 1.0))


def test_distribution_with_scalar_parameters_gives_scalar():
    assert isinstance(m.normal(0.0, 1.0), float)


def test_distribution_wrong_arity_is_an_error():
    with pytest.raises(DataError):
        m.normal(1.0)
    with pytest.raises(DataError):
        m.cauchy(1.0, 2.0, 3.0)
    with pytest.raises(DataError):
        m.log()
    with pytest.raises(DataError):
        m.min()


def test_impossible_truncation_is_an_error():
    with pytest.raises(DataError):
        m.normal(0.0, 1.0, 1000.0, 1001.0)


# --------------------------------------------------------------------------- mathgen

def test_mathgen_resolves_references_and_names():
    code = mathgen.math_to_python("2 * #constants:x + y", lambda r: f"<{r}>", lambda n: f"<{n}>")
    assert "<#constants:x>" in code and "<y>" in code and "rt.m.mul" in code and "rt.m.add" in code


def test_mathgen_is_deterministic():
    f = lambda r: "X"  # noqa: E731
    assert mathgen.math_to_python("sin(1) + 2 ^ 3", f) == mathgen.math_to_python("sin(1) + 2 ^ 3", f)


def test_mathgen_keyword_function_names():
    code = mathgen.math_to_python("and(1, 0) || not(1)", lambda r: "X")
    compile(code, "<gen>", "eval")
    assert "rt.m.and_(" in code and "rt.m.not_(" in code and "rt.m.or_(" in code


def test_mathgen_syntax_error():
    with pytest.raises(TranslationError):
        mathgen.math_to_python("1 +", lambda r: "X")


def test_mathgen_unknown_name_and_function():
    with pytest.raises(TranslationError):
        mathgen.math_to_python("foo + 1", lambda r: "X")
    with pytest.raises(TranslationError):
        mathgen.math_to_python("nosuchfunction(1)", lambda r: "X")


def test_mathgen_numbers_are_floats_in_output():
    assert "1.0" in mathgen.math_to_python("1", lambda r: "X")
    code = mathgen.math_to_python("[1, 2]", lambda r: "X")
    assert code.startswith("rt.m.array(")
