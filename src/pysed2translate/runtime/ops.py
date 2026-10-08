"""Operations used by generated task code: ranges, data blocks, relabelling, string formation.

All values are AnnotatedData (or Python floats/strings where noted).
"""
from __future__ import annotations

import itertools
import math
from typing import Any, Optional, Sequence

import numpy as np

from .annotated import AnnotatedData, DataError, special_value


# --------------------------------------------------------------------------- scalars and lists from data

def scalar(x: Any) -> float:
    """A number from a 0-D numeric AnnotatedData (or a plain number)."""
    if isinstance(x, AnnotatedData):
        if x.is_string:
            raise DataError("a number was expected, found a string")
        if x.ndim != 0:
            raise DataError(f"a single number was expected, found {x.ndim}-dimensional data")
        return float(x.values[()])
    if isinstance(x, bool):
        return 1.0 if x else 0.0
    if isinstance(x, (int, float)):
        return float(x)
    raise DataError(f"a number was expected, found {x!r}")


def string_scalar(x: Any) -> str:
    if isinstance(x, AnnotatedData):
        if not x.is_string or x.ndim != 0:
            raise DataError("a single string was expected")
        return str(x.values[()])
    if isinstance(x, str):
        return x
    raise DataError(f"a string was expected, found {x!r}")


def number_list(items: Sequence[Any]) -> list:
    """Entries given as numbers or 0-D data -> list of floats."""
    return [scalar(i) for i in items]


def numbers_from(x: Any) -> list:
    """A list of floats from 1-D numeric data."""
    if isinstance(x, AnnotatedData):
        if x.is_string or x.ndim != 1:
            raise DataError("a list of numbers (1-D numeric data) was expected")
        return [float(v) for v in x.values]
    return number_list(list(x))


def strings_from(x: Any) -> list:
    """A list of str from 1-D string data (or a Python list of strings / 0-D strings)."""
    if isinstance(x, AnnotatedData):
        if not x.is_string or x.ndim != 1:
            raise DataError("a list of strings (1-D string data) was expected")
        return [str(v) for v in x.values]
    return [string_scalar(i) for i in x]


def mapping_from(x: Any) -> dict:
    """A dict of label -> float from 1-D numeric data that has labels (a data block of numbers)."""
    if isinstance(x, AnnotatedData):
        if x.is_string or x.ndim != 1 or x.labels[0] is None:
            raise DataError("an object of numbers (labeled 1-D numeric data) was expected")
        return {str(k): float(v) for k, v in zip(x.labels[0], x.values)}
    raise DataError("an object of numbers was expected")


# --------------------------------------------------------------------------- repeats

def grid(sizes: Sequence[int]):
    """The index tuples of a scan in the order of the dimensions of the result: the first range is the first
    dimension, the last range is the last."""
    return itertools.product(*[range(n) for n in sizes])


def labeled_vector(names: Sequence[str], values: Sequence[float]) -> AnnotatedData:
    """The 1-D numbers of a ParameterScan's `.ranges` / `.indexes`, labeled by the scanned model elements."""
    return AnnotatedData(np.asarray(values, dtype=float), [list(names)])


def _entries(rows: Sequence[Sequence[Any]], ncols: int):
    """Stack the entries a repeat collected (one list of AnnotatedData per iteration) into an array of shape
    (iterations, ncols, *entry shape).  Every entry must have the same shape and kind.  Returns the array, the
    entry shape, whether the entries are strings, and the first entry's (labels, dims) for its own dimensions."""
    shape, strings, parts, first = None, None, [], None
    for row in rows:
        if len(row) != ncols:
            raise DataError(f"expected {ncols} output entries per iteration, found {len(row)}")
        for e in row:
            e = e if isinstance(e, AnnotatedData) else _literal(e)
            if shape is None:
                shape, strings, first = e.shape, e.is_string, (list(e.labels), list(e.dims))
            elif e.shape != shape:
                raise DataError(f"the outputs of a repeat differ in shape: {e.shape} and {shape}")
            elif e.is_string != strings:
                raise DataError("numbers and strings cannot be mixed in the outputs of a repeat")
            parts.append(e.values)
    if shape is None:
        return np.zeros((len(rows), ncols)), (), False, ([], [])
    arr = np.stack(parts) if parts else np.zeros(0)
    return arr.reshape((len(rows), ncols) + shape), shape, bool(strings), first


def _range_labels(points: Sequence[float]) -> list:
    return [number_text(float(p)) for p in points]


def repeat_table(points: Sequence[float], rows: Sequence[Sequence[Any]], keys: Sequence[str]) -> AnnotatedData:
    """The `[id]` of a Loop or Scatter (Loop and Scatter descriptions): dimension 0 is the iteration, labeled by the range values;
    dimension 1 the entries of outputVariableMap, labeled by their keys; then the dimensions of the entries
    themselves (with their labels).  Scalar entries give a plain iterations x entries table."""
    keys = list(keys)
    arr, shape, strings, (elabels, edims) = _entries(rows, len(keys))
    labels = [_range_labels(points), keys] + (elabels or [None] * len(shape))
    dims = ["", ""] + (edims or [""] * len(shape))
    return AnnotatedData(arr, labels, dims)


def scan_table(rows: Sequence[Sequence[Any]], ranges: Sequence[Sequence[float]], names: Sequence[str],
               keys: Sequence[str]) -> AnnotatedData:
    """The `[id]` of a ParameterScan (ParameterScan description): one dimension per scanned range, in the order of the
    parameterRanges, named by its model element and labeled by its values; then the entries of outputVariableMap,
    labeled by their keys; then the dimensions of the entries themselves (with their labels)."""
    keys = list(keys)
    sizes = [len(r) for r in ranges]
    arr, shape, strings, (elabels, edims) = _entries(rows, len(keys))
    arr = arr.reshape(tuple(sizes) + (len(keys),) + shape)
    labels = [_range_labels(r) for r in ranges] + [keys] + (elabels or [None] * len(shape))
    dims = list(names) + [""] + (edims or [""] * len(shape))
    return AnnotatedData(arr, labels, dims)


# --------------------------------------------------------------------------- data files

def csv_import(path: str, separator: Optional[str] = None, headers: Optional[bool] = None,
               column_names: Optional[Sequence[str]] = None, ncols: Optional[int] = None,
               nrows: Optional[int] = None) -> AnnotatedData:
    """CsvImport: a delimiter-separated file of numbers -> 2-D data (rows x columns).

    separator    one character, default ","
    headers      True: the first row holds the column names (they become the labels of the column dimension);
                 default False: every row is data
    column_names the column labels when there is no header row
    ncols/nrows  use only the first `ncols` columns / `nrows` data rows (the file must have at least that many)
    Blank lines are skipped; a cell is a number, or one of nan, inf, -inf.  A cell that is not a number is an error."""
    import csv

    sep = "," if separator is None else separator
    if len(sep) != 1:
        raise DataError(f"the separator must be a single character, not {sep!r}")
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            rows = [[c.strip() for c in row] for row in csv.reader(f, delimiter=sep) if any(c.strip() for c in row)]
    except OSError as e:
        raise DataError(f"cannot read the data file {path}: {e}") from e
    labels = None
    if headers:
        if not rows:
            raise DataError(f"{path} has no header row")
        labels, rows = rows[0], rows[1:]
    if nrows is not None:
        if len(rows) < nrows:
            raise DataError(f"{path} has {len(rows)} data rows, fewer than the requested {nrows}")
        rows = rows[:nrows]
    width = len(rows[0]) if rows else (len(labels) if labels else 0)
    for n, row in enumerate(rows):
        if len(row) != width:
            raise DataError(f"{path}: data row {n + 1} has {len(row)} cells, expected {width}")
    if ncols is not None:
        if width < ncols:
            raise DataError(f"{path} has {width} columns, fewer than the requested {ncols}")
        width = ncols
        rows = [r[:ncols] for r in rows]
        labels = labels[:ncols] if labels else labels
    if labels is not None and len(labels) != width:
        raise DataError(f"{path}: the header has {len(labels)} names for {width} columns")
    if labels is None and column_names is not None:
        labels = [str(c) for c in column_names]
        if len(labels) != width:
            raise DataError(f"{len(labels)} column names were given for {width} columns")
    values = np.empty((len(rows), width), dtype=float)
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            special = special_value(cell)
            if special is not None:
                values[i, j] = special
                continue
            try:
                values[i, j] = float(cell)
            except ValueError:
                raise DataError(f"{path}: row {i + 1}, column {j + 1}: {cell!r} is not a number "
                                "(if the first row holds names, set headers)") from None
    return AnnotatedData(values, [None, labels])


# --------------------------------------------------------------------------- numeric ranges

def numeric_range(start=None, end=None, number_of_steps=None, interval=None, scale=None, values=None) -> AnnotatedData:
    """The points of a NumericRange (see tasks/NumericRange): explicit values; numberOfSteps alone (0..N);
    start/end/numberOfSteps (+ scale 'linear' or 'log10'); start/numberOfSteps/interval; end/numberOfSteps/interval;
    start/interval/end (end always included, a computed point within interval*1e-6 of end is dropped).
    A range with N steps has N+1 points."""
    if values is not None:
        if any(v is not None for v in (start, end, number_of_steps, interval, scale)):
            raise DataError("a range with explicit values cannot also set start, end, numberOfSteps, interval or scale")
        return AnnotatedData(np.asarray(values, dtype=float))
    n = None if number_of_steps is None else int(number_of_steps)
    if n is not None and (n != number_of_steps or n < 1):
        raise DataError(f"numberOfSteps must be a positive integer, not {number_of_steps}")
    if scale is not None and not (start is not None and end is not None and n is not None):
        raise DataError("scale is only allowed with start, end and numberOfSteps")
    if n is not None and start is None and end is None and interval is None:
        return AnnotatedData(np.arange(n + 1, dtype=float))
    if start is not None and end is not None and n is not None and interval is None:
        scale = scale or "linear"
        if scale == "linear":
            pts = np.linspace(start, end, n + 1)
        elif scale == "log10":
            if start <= 0 or end <= 0:
                raise DataError("a log10 range needs positive start and end")
            pts = np.logspace(math.log10(start), math.log10(end), n + 1)
            pts[0], pts[-1] = start, end
        else:
            raise DataError(f"unknown scale {scale!r}")
        return AnnotatedData(pts)
    if start is not None and n is not None and interval is not None and end is None:
        return AnnotatedData(start + interval * np.arange(n + 1))
    if end is not None and n is not None and interval is not None and start is None:
        return AnnotatedData(end - interval * np.arange(n, -1, -1))
    if start is not None and end is not None and interval is not None and n is None:
        if interval <= 0:
            raise DataError("interval must be positive")
        tol = interval * 1e-6
        pts, k = [], 0
        while True:
            p = start + k * interval
            if p > end + tol:
                break
            if abs(p - end) > tol:
                pts.append(p)
            k += 1
        pts.append(end)
        return AnnotatedData(np.asarray(pts, dtype=float))
    raise DataError("this combination of start, end, numberOfSteps, interval and scale does not define a range")


# --------------------------------------------------------------------------- data blocks and labels

def block(keys: Sequence[str], items: Sequence[Any]) -> AnnotatedData:
    """CreateDataBlock: a new first dimension labeled by `keys`, over entries of equal shape."""
    if len(keys) != len(items):
        raise DataError("keys and values differ in number")
    parts = [i if isinstance(i, AnnotatedData) else _literal(i) for i in items]
    if not parts:
        return AnnotatedData(np.zeros(0), [list(keys)])
    first = parts[0]
    for k, p in zip(keys, parts):
        if p.shape != first.shape:
            raise DataError(f"entry {k!r} has shape {p.shape}, different from {first.shape}")
        if p.is_string != first.is_string:
            raise DataError("numbers and strings cannot be mixed in one data block")
    return AnnotatedData(np.stack([p.values for p in parts]), [list(keys)] + first.labels, [""] + first.dims)


def _literal(x: Any) -> AnnotatedData:
    return AnnotatedData.from_constant(x)


def relabel(data: AnnotatedData, labels: Sequence[str]) -> AnnotatedData:
    """RelabelData: replace the labels of the topmost dimension."""
    if data.ndim == 0:
        raise DataError("0-dimensional data has no dimension to relabel")
    labels = [str(l) for l in labels]
    if len(labels) != data.shape[0]:
        raise DataError(f"{len(labels)} labels given for a dimension of size {data.shape[0]}")
    out = data.copy()
    out.labels[0] = labels
    return out


# --------------------------------------------------------------------------- strings

def number_text(x: float) -> str:
    """How a number appears in a formed string: integer values without a decimal point ('3'), others by repr."""
    if math.isnan(x):
        return "nan"
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    if x == math.floor(x) and abs(x) < 1e15:
        return str(int(x))
    return repr(x)


def _text_of(item: Any) -> AnnotatedData:
    """An item of StringFormation.concatenate as string-valued AnnotatedData."""
    if isinstance(item, AnnotatedData):
        if item.is_string:
            return item
        out = np.empty(item.shape, dtype=object)
        for idx, v in np.ndenumerate(item.values):
            out[idx] = number_text(float(v))
        return AnnotatedData(out, item.labels, item.dims)
    if isinstance(item, bool):
        return AnnotatedData(np.asarray("true" if item else "false", dtype=object))
    if isinstance(item, (int, float)):
        return AnnotatedData(np.asarray(number_text(float(item)), dtype=object))
    if isinstance(item, str):
        return AnnotatedData(np.asarray(item, dtype=object))
    raise DataError(f"cannot turn {item!r} into text")


def string_formation(items: Sequence[Any]) -> AnnotatedData:
    """StringFormation: convert each item to text and concatenate.  Items with dimensions must all have the same
    shape and are combined element by element; scalar items are repeated in every element."""
    parts = [_text_of(i) for i in items]
    shapes = {p.shape for p in parts if p.ndim > 0}
    if len(shapes) > 1:
        raise DataError(f"list elements to concatenate have different shapes: {sorted(shapes)}")
    shape = next(iter(shapes)) if shapes else ()
    ref = next((p for p in parts if p.ndim > 0), None)
    out = np.empty(shape, dtype=object)
    for idx in np.ndindex(*shape) if shape else [()]:
        out[idx] = "".join(str(p.values[idx] if p.ndim > 0 else p.values[()]) for p in parts)
    if ref is None:
        return AnnotatedData(out)
    return AnnotatedData(out, ref.labels, ref.dims)


def string_data(items: Sequence[str]) -> AnnotatedData:
    """1-D string AnnotatedData from a Python list of strings."""
    arr = np.empty(len(items), dtype=object)
    for i, v in enumerate(items):
        arr[i] = str(v)
    return AnnotatedData(arr)
