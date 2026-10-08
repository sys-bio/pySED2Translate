"""Math for generated scripts: the SED2 predefined functions, operators and constants.

Every value is a Python float, a numpy scalar, or an AnnotatedData.  Functions apply element by element.  A lower
dimension operand is broadcast across the trailing dimensions of a higher one (`5 + [list]`, `[1D] * [2D]` multiplies
each row).  Operands of the same dimension must have equal sizes and, where both carry labels, equal labels.  The
result is an AnnotatedData (labels and dimension names taken from the operands) if any operand was one, else a float.
Booleans are 1.0 and 0.0.  Arithmetic follows IEEE rules (1/0 is inf, 0/0 is nan).  `x % y` is `rem`, which takes
the dividend's sign (math.fmod), unlike Python's `%`.

The names registered here are the SED2 names (see SED2/schema/predefined-functions.json).  The Python spelling of a
name that is a Python keyword gets a trailing underscore: and_, or_, not_.  FUNCTIONS maps a SED2 function name to
its implementation.
"""
from __future__ import annotations

import builtins
import keyword
import math
from typing import Any, Callable

import numpy as np

from .annotated import AnnotatedData, DataError

FUNCTIONS: dict[str, Callable] = {}
CONSTANTS: dict[str, float] = {
    "pi": math.pi,
    "exponentiale": math.e,
    "true": 1.0,
    "false": 0.0,
    "notanumber": math.nan,
    "infinity": math.inf,
}


globals().update(CONSTANTS)  # rt.m.pi, rt.m.true, ...


def python_name(sed2_name: str) -> str:
    """The attribute of this module that implements a SED2 function or operator name."""
    return sed2_name + "_" if keyword.iskeyword(sed2_name) else sed2_name


# --------------------------------------------------------------------------- operand handling

def _values(x: Any) -> np.ndarray:
    if isinstance(x, AnnotatedData):
        if x.is_string:
            raise DataError("strings cannot be used in arithmetic")
        return x.values
    if isinstance(x, str):
        raise DataError("strings cannot be used in arithmetic")
    return np.asarray(x, dtype=np.float64)


def _check_alignment(operands: list) -> None:
    """Only a lower dimension operand may be stretched: aligned (trailing) dimensions must match in size."""
    ads = [o for o in operands if isinstance(o, AnnotatedData) and o.ndim > 0]
    if len(ads) < 2:
        return
    top = builtins.max(a.ndim for a in ads)
    for r in range(top):
        sizes = set()
        labels = None
        for a in ads:
            j = r - (top - a.ndim)
            if j < 0:
                continue
            sizes.add(a.shape[j])
            lab = a.labels[j]
            if lab is not None:
                if labels is not None and [str(x) for x in labels] != [str(x) for x in lab]:
                    raise DataError(f"operands have different labels in dimension {r}: {labels} and {lab}")
                labels = lab
        if len(sizes) > 1:
            raise DataError(f"operands have different sizes in dimension {r}: {sorted(sizes)}")


def _result_labels(operands: list, ndim: int) -> tuple:
    labels = [None] * ndim
    dims = [""] * ndim
    for o in operands:
        if isinstance(o, AnnotatedData):
            for j in range(o.ndim):
                r = ndim - o.ndim + j
                if labels[r] is None and o.labels[j] is not None:
                    labels[r] = list(o.labels[j])
                if not dims[r] and o.dims[j]:
                    dims[r] = o.dims[j]
    return labels, dims


def _wrap(result: np.ndarray, operands: list, boolean: bool = False):
    result = np.asarray(result)
    if boolean:
        result = result.astype(np.float64)
    if not any(isinstance(o, AnnotatedData) for o in operands):
        return float(result) if result.ndim == 0 else AnnotatedData(result)
    labels, dims = _result_labels(operands, result.ndim)
    return AnnotatedData(result, labels, dims)


def apply(func: Callable, *operands: Any, boolean: bool = False):
    """Apply a numpy function element by element with broadcasting; see the module docstring."""
    _check_alignment(list(operands))
    arrays = [_values(o) for o in operands]
    with np.errstate(all="ignore"):
        try:
            result = func(*arrays)
        except ValueError as e:
            raise DataError(f"cannot combine operands: {e}") from e
    return _wrap(result, list(operands), boolean)


def _register(name: str):
    def deco(fn: Callable) -> Callable:
        FUNCTIONS[name] = fn
        globals()[python_name(name)] = fn
        return fn
    return deco


def _unary(name: str, func: Callable, boolean: bool = False) -> None:
    _register(name)(lambda x, _f=func, _b=boolean: apply(_f, x, boolean=_b))


def _truthy(a: np.ndarray) -> np.ndarray:
    return (a != 0) & ~np.isnan(a)


# --------------------------------------------------------------------------- operators

def add(a, b):
    return apply(np.add, a, b)


def sub(a, b):
    return apply(np.subtract, a, b)


def mul(a, b):
    return apply(np.multiply, a, b)


def div(a, b):
    return apply(np.divide, a, b)


def power(a, b):
    return apply(np.power, a, b)


def neg(a):
    return apply(np.negative, a)


def pos(a):
    return a


# --------------------------------------------------------------------------- arithmetic functions

_unary("abs", np.abs)
_unary("exp", np.exp)
_unary("ln", np.log)
_unary("floor", np.floor)
_unary("ceiling", np.ceil)


@_register("log")
def log(*args):
    if len(args) == 1:
        return apply(np.log10, args[0])
    if len(args) == 2:  # log(base, x)
        return apply(lambda b, x: np.log(x) / np.log(b), args[0], args[1])
    raise DataError("log takes 1 or 2 arguments")


@_register("root")
def root(*args):
    if len(args) == 1:
        return apply(np.sqrt, args[0])
    if len(args) == 2:  # root(degree, x)
        return apply(lambda d, x: np.power(x, 1.0 / d), args[0], args[1])
    raise DataError("root takes 1 or 2 arguments")


@_register("rem")
def rem(a, b):
    return apply(np.fmod, a, b)


@_register("quotient")
def quotient(a, b):
    return apply(lambda x, y: np.trunc(np.divide(x, y)), a, b)


def _factorial(x: np.ndarray) -> np.ndarray:
    out = np.full(x.shape, np.nan)
    for idx, v in np.ndenumerate(x):
        if np.isnan(v) or v < 0 or v != np.floor(v):
            continue
        out[idx] = math.inf if v > 170 else float(math.factorial(int(v)))
    return out


_unary("factorial", _factorial)


@_register("min")
def min(*args):  # noqa: A001 - the SED2 name
    if not args:
        raise DataError("min needs at least one argument")
    return apply(lambda *a: np.minimum.reduce(np.broadcast_arrays(*a)), *args)


@_register("max")
def max(*args):  # noqa: A001
    if not args:
        raise DataError("max needs at least one argument")
    return apply(lambda *a: np.maximum.reduce(np.broadcast_arrays(*a)), *args)


@_register("sum")
def sum(x):  # noqa: A001
    """Reduce the outermost (first) dimension.  A scalar is returned unchanged."""
    if not isinstance(x, AnnotatedData) or x.ndim == 0:
        return x
    if x.is_string:
        raise DataError("strings cannot be summed")
    return AnnotatedData(np.sum(x.values, axis=0), x.labels[1:], x.dims[1:])


# --------------------------------------------------------------------------- trigonometric

def _inv(f: Callable) -> Callable:
    return lambda x: f(1.0 / x)


for _n, _f in {
    "sin": np.sin, "cos": np.cos, "tan": np.tan,
    "sec": lambda x: 1.0 / np.cos(x), "csc": lambda x: 1.0 / np.sin(x), "cot": lambda x: 1.0 / np.tan(x),
    "sinh": np.sinh, "cosh": np.cosh, "tanh": np.tanh,
    "sech": lambda x: 1.0 / np.cosh(x), "csch": lambda x: 1.0 / np.sinh(x), "coth": lambda x: 1.0 / np.tanh(x),
    "arcsin": np.arcsin, "arccos": np.arccos, "arctan": np.arctan,
    "arcsec": _inv(np.arccos), "arccsc": _inv(np.arcsin), "arccot": _inv(np.arctan),
    "arcsinh": np.arcsinh, "arccosh": np.arccosh, "arctanh": np.arctanh,
    "arcsech": _inv(np.arccosh), "arccsch": _inv(np.arcsinh), "arccoth": _inv(np.arctanh),
}.items():
    _unary(_n, _f)


# --------------------------------------------------------------------------- relational and logical

def _chain(name: str, op: Callable, minimum: int = 2) -> None:
    @_register(name)
    def fn(*args):
        if len(args) < minimum:
            raise DataError(f"{name} needs at least {minimum} arguments")
        return apply(lambda *a: np.logical_and.reduce([op(a[i], a[i + 1]) for i in range(len(a) - 1)]),
                     *args, boolean=True)


_chain("eq", np.equal)
_chain("lt", np.less)
_chain("gt", np.greater)
_chain("leq", np.less_equal)
_chain("geq", np.greater_equal)


@_register("neq")
def neq(a, b):
    return apply(np.not_equal, a, b, boolean=True)


@_register("and")
def and_(*args):
    if not args:
        return 1.0
    return apply(lambda *a: np.logical_and.reduce([_truthy(x) for x in np.broadcast_arrays(*a)]), *args, boolean=True)


@_register("or")
def or_(*args):
    if not args:
        return 0.0
    return apply(lambda *a: np.logical_or.reduce([_truthy(x) for x in np.broadcast_arrays(*a)]), *args, boolean=True)


@_register("xor")
def xor(*args):
    if not args:
        return 0.0
    return apply(lambda *a: np.logical_xor.reduce([_truthy(x) for x in np.broadcast_arrays(*a)]), *args, boolean=True)


@_register("not")
def not_(x):
    return apply(lambda a: ~_truthy(a), x, boolean=True)


@_register("implies")
def implies(a, b):
    return apply(lambda x, y: ~_truthy(x) | _truthy(y), a, b, boolean=True)


@_register("piecewise")
def piecewise(*args):
    """piecewise(value1, condition1, value2, condition2, ..., otherwise): the first true condition wins; with no
    otherwise and no true condition the result is nan."""
    if not args:
        raise DataError("piecewise needs at least one argument")
    has_otherwise = len(args) % 2 == 1
    pairs = [(args[i], args[i + 1]) for i in range(0, len(args) - (1 if has_otherwise else 0), 2)]
    otherwise = args[-1] if has_otherwise else math.nan
    flat = [v for p in pairs for v in p] + [otherwise]

    def pick(*a):
        arrs = np.broadcast_arrays(*a)
        n = len(pairs)
        conds = [_truthy(arrs[2 * i + 1]) for i in range(n)]
        vals = [arrs[2 * i] for i in range(n)]
        return np.select(conds, vals, default=arrs[-1]) if n else arrs[-1]

    return apply(pick, *flat)


# --------------------------------------------------------------------------- array literals

def array(*items):
    """[a, b, c]: a new first dimension over the items, which must have equal shapes."""
    if not items:
        return AnnotatedData(np.zeros(0))
    parts = [i if isinstance(i, AnnotatedData) else AnnotatedData(np.asarray(_values(i))) for i in items]
    first = parts[0]
    for p in parts[1:]:
        if p.shape != first.shape:
            raise DataError(f"array entries have different shapes ({first.shape} and {p.shape})")
    return AnnotatedData(np.stack([p.values for p in parts]), [None] + first.labels, [""] + first.dims)


def to_data(x) -> AnnotatedData:
    """A calculation's result as AnnotatedData."""
    return x if isinstance(x, AnnotatedData) else AnnotatedData(np.asarray(float(x)))


# --------------------------------------------------------------------------- random draws (distrib)

_rng = np.random.default_rng(0)


def seed(value: int) -> None:
    """Reseed the generator used by the distrib functions (the default seed is 0)."""
    global _rng
    _rng = np.random.default_rng(value)


def _truncated(draw: Callable, shape: tuple, lo, hi, limit: int = 10000) -> np.ndarray:
    out = draw()
    if lo is None:
        return out
    lo = np.broadcast_to(lo, out.shape)
    hi = np.broadcast_to(hi, out.shape)
    for _ in range(limit):
        bad = (out < lo) | (out > hi)
        if not bad.any():
            return out
        again = draw()
        out = np.where(bad, again, out)
    raise DataError("could not draw a value inside [min, max] after many attempts")


def _dist(name: str, variants: list, sampler: Callable) -> None:
    """Register a distribution.  `variants` lists the allowed argument lists; `sampler(rng, **named)` draws once
    with the named parameters (missing optional ones are absent); min and max truncate by rejection."""
    @_register(name)
    def fn(*args):
        names = None
        for v in variants:
            if len(v) == len(args):
                names = v
                break
        if names is None:
            raise DataError(f"{name} takes {' or '.join(str(len(v)) for v in variants)} arguments, not {len(args)}")

        def run(*arrays):
            params = dict(zip(names, arrays))
            lo, hi = params.pop("min", None), params.pop("max", None)
            shape = np.broadcast_shapes(*[a.shape for a in arrays]) if arrays else ()
            return _truncated(lambda: np.asarray(sampler(_rng, shape, **params), dtype=np.float64), shape, lo, hi)

        return apply(run, *args)


def _b(p, shape):
    return np.broadcast_to(p, shape)


_dist("normal", [["mean", "stdev"], ["mean", "stdev", "min", "max"]],
      lambda r, s, mean, stdev: r.normal(_b(mean, s), _b(stdev, s)))
_dist("bernoulli", [["prob"]], lambda r, s, prob: (r.random(s) < _b(prob, s)))
_dist("binomial", [["nTrials", "probabilityOfSuccess"], ["nTrials", "probabilityOfSuccess", "min", "max"]],
      lambda r, s, nTrials, probabilityOfSuccess: r.binomial(_b(nTrials, s).astype(np.int64), _b(probabilityOfSuccess, s)))
_dist("cauchy", [["scale"], ["location", "scale"], ["location", "scale", "min", "max"]],
      lambda r, s, scale, location=0.0: _b(location, s) + _b(scale, s) * r.standard_cauchy(s))
_dist("chisquare", [["degreesOfFreedom"], ["degreesOfFreedom", "min", "max"]],
      lambda r, s, degreesOfFreedom: r.chisquare(_b(degreesOfFreedom, s)))
_dist("exponential", [["rate"], ["rate", "min", "max"]],
      lambda r, s, rate: r.exponential(1.0 / _b(rate, s)))
_dist("gamma", [["shape", "scale"], ["shape", "scale", "min", "max"]],
      lambda r, s, shape, scale: r.gamma(_b(shape, s), _b(scale, s)))
_dist("laplace", [["scale"], ["location", "scale"], ["location", "scale", "min", "max"]],
      lambda r, s, scale, location=0.0: r.laplace(_b(location, s), _b(scale, s)))
_dist("lognormal", [["mean", "stdev"], ["mean", "stdev", "min", "max"]],
      lambda r, s, mean, stdev: r.lognormal(_b(mean, s), _b(stdev, s)))
_dist("poisson", [["rate"], ["rate", "min", "max"]], lambda r, s, rate: r.poisson(_b(rate, s)))
_dist("rayleigh", [["scale"], ["scale", "min", "max"]], lambda r, s, scale: r.rayleigh(_b(scale, s)))


@_register("uniform")
def uniform(lo, hi):
    return apply(lambda a, b: _rng.uniform(a, b, np.broadcast_shapes(a.shape, b.shape)), lo, hi)
