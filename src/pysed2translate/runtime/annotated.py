"""AnnotatedData: an n-dimensional array with optional labels and a name for each dimension.

Modeled on xarray.DataArray as the SED2 specification describes it (core/Types).  Numbers are float64;
strings are held in an object array.  Booleans are numbers (1 and 0).  The strings 'nan', 'inf' and '-inf'
(any capitalization) are the special values when they appear among numbers.

Index chains follow the reference grammar: each bracket index applies to the CORRESPONDING original dimension
(the first index to the first dimension, the second to the second, ...).  A positional or label index drops its
dimension; a range keeps it.  Positions are zero-based with Python conventions (negative from the end, end-exclusive).
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Optional

import numpy as np

_SPECIAL = {"nan": math.nan, "inf": math.inf, "+inf": math.inf, "-inf": -math.inf}


class DataError(ValueError):
    """The data cannot be represented as, or indexed as, AnnotatedData."""


def special_value(text: Any) -> Optional[float]:
    """The float for 'nan' / 'inf' / '-inf' (any case), else None."""
    if isinstance(text, str):
        return _SPECIAL.get(text.strip().lower())
    return None


class AnnotatedData:
    def __init__(self, values, labels: Optional[list] = None, dims: Optional[list] = None):
        arr = np.asarray(values)
        if arr.dtype == object or arr.dtype.kind in "US":
            arr = np.asarray(arr, dtype=object)
        else:
            arr = arr.astype(np.float64)
        self.values = arr
        n = arr.ndim
        self.labels = list(labels) if labels else [None] * n
        self.dims = list(dims) if dims else [""] * n
        if len(self.labels) != n or len(self.dims) != n:
            raise DataError("labels and dims must have one entry per dimension")
        for i, lab in enumerate(self.labels):
            if lab is not None and len(lab) != arr.shape[i]:
                raise DataError(f"dimension {i} has {arr.shape[i]} entries but {len(lab)} labels")

    # ------------------------------------------------------------------ basics

    @property
    def ndim(self) -> int:
        return self.values.ndim

    @property
    def shape(self) -> tuple:
        return self.values.shape

    @property
    def is_string(self) -> bool:
        return self.values.dtype == object

    def copy(self) -> "AnnotatedData":
        return AnnotatedData(self.values.copy(), [None if l is None else list(l) for l in self.labels], list(self.dims))

    def __repr__(self) -> str:
        return f"AnnotatedData(shape={self.shape}, labels={self.labels}, values={self.values.tolist()})"

    # ------------------------------------------------------------------ from literals

    @classmethod
    def from_constant(cls, value: Any) -> "AnnotatedData":
        """Interpret a JSON value (a document constant, or any literal) as AnnotatedData.

        * a number or boolean -> 0-D numbers;  a string -> 0-D string
        * a list -> a new first dimension of that length, unlabeled, over its (equal-shaped) entries
        * a dictionary -> a new first dimension labeled by the keys, over its (equal-shaped) values
        * a list or scalar made only of 'nan'/'inf'/'-inf' strings and numbers is numeric.
        A mix of numbers and other strings, ragged lists, or null are errors.
        """
        return _build(value, "constant")

    # ------------------------------------------------------------------ indexing

    def index(self, brackets: Iterable) -> "AnnotatedData":
        """Apply bracket indices (Types, "Indexing").  `brackets` is a list of brackets, each a list of indices
        written between one pair of square brackets (`[a:b, n]`: two indices in one bracket).  The indices of a
        bracket apply to the first, second, ... dimension of the data; the next bracket applies to what the
        previous ones selected (an integer or label removes its dimension, a range keeps it, narrowed).  A single
        bracket may also be given as a flat list of indices."""
        brackets = list(brackets)
        if brackets and not isinstance(brackets[0], list):
            brackets = [brackets]
        out = self
        for group in brackets:
            out = out._index_bracket(group)
        return out

    def _index_bracket(self, accessors: Iterable[tuple]) -> "AnnotatedData":
        """One bracket.  Each accessor is ('int', n), ('label', text) or ('range', (a, b)) with a or b possibly
        None."""
        accessors = list(accessors)
        if len(accessors) > self.ndim:
            raise DataError(f"{len(accessors)} indices applied to {self.ndim}-dimensional data")
        key = []
        new_labels: list = []
        new_dims: list = []
        for d in range(self.ndim):
            if d >= len(accessors):
                key.append(slice(None))
                new_labels.append(self.labels[d])
                new_dims.append(self.dims[d])
                continue
            kind, val = accessors[d]
            size = self.shape[d]
            if kind == "int":
                if val < -size or val >= size:
                    raise DataError(f"index {val} is outside dimension {d} of size {size}")
                key.append(val % size if size else val)
            elif kind == "label":
                labs = self.labels[d]
                if labs is None:
                    raise DataError(f"dimension {d} has no labels, so [{val!r}] cannot be applied")
                matches = [i for i, l in enumerate(labs) if _label_equal(l, val)]
                if not matches:
                    raise DataError(f"label {val!r} is not one of the labels of dimension {d}: {labs}")
                key.append(matches[0])
            elif kind == "range":
                a, b = val
                start, stop, _ = slice(a, b).indices(size)
                if stop <= start:
                    raise DataError(f"the range [{'' if a is None else a}:{'' if b is None else b}] selects no "
                                    f"entry of dimension {d} (size {size})")
                key.append(slice(start, stop))
                labs = self.labels[d]
                new_labels.append(None if labs is None else list(labs[start:stop]))
                new_dims.append(self.dims[d])
            else:
                raise DataError(f"unknown index kind {kind!r}")
        out = self.values[tuple(key)]
        return AnnotatedData(out, new_labels, new_dims)


def _label_equal(label: Any, wanted: Any) -> bool:
    if isinstance(label, (int, float)) and not isinstance(label, bool) and isinstance(wanted, str):
        try:
            return float(wanted) == float(label)
        except ValueError:
            return False
    return label == wanted


# --------------------------------------------------------------------------- building from literals

def _kinds(value: Any, what: str, out: set) -> None:
    """Collect the kinds of scalar found: 'num', 'str' (a string that is not nan/inf/-inf), 'special'."""
    if isinstance(value, dict):
        for k, v in value.items():
            _kinds(v, f"{what}[{k!r}]", out)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _kinds(v, f"{what}[{i}]", out)
    elif isinstance(value, bool) or isinstance(value, (int, float)):
        out.add("num")
    elif isinstance(value, str):
        out.add("special" if special_value(value) is not None else "str")
    else:
        raise DataError(f"{what}: cannot use {value!r} as data")


def _build(value: Any, what: str) -> AnnotatedData:
    kinds: set = set()
    _kinds(value, what, kinds)
    if "str" in kinds and "num" in kinds:
        raise DataError(f"{what}: numbers and strings cannot be mixed in one block of data")
    return _make(value, what, string_mode="str" in kinds)


def _make(value: Any, what: str, string_mode: bool) -> AnnotatedData:
    if isinstance(value, dict):
        keys = list(value.keys())
        return _stack([_make(value[k], f"{what}[{k!r}]", string_mode) for k in keys], keys, what, string_mode)
    if isinstance(value, list):
        return _stack([_make(v, f"{what}[{i}]", string_mode) for i, v in enumerate(value)], None, what, string_mode)
    if string_mode:
        return AnnotatedData(np.asarray(value, dtype=object))
    if isinstance(value, str):
        return AnnotatedData(np.asarray(special_value(value)))
    return AnnotatedData(np.asarray(float(value)))


def _stack(parts: list, keys: Optional[list], what: str, string_mode: bool) -> AnnotatedData:
    if not parts:
        empty = np.zeros(0, dtype=object) if string_mode else np.zeros(0)
        return AnnotatedData(empty, [keys] if keys is not None else None)
    first = parts[0]
    for p in parts[1:]:
        if p.shape != first.shape:
            raise DataError(f"{what}: entries have different shapes ({first.shape} and {p.shape})")
        if p.labels != first.labels:
            raise DataError(f"{what}: entries have different labels")
    return AnnotatedData(np.stack([p.values for p in parts]), [keys] + first.labels, [""] + first.dims)
