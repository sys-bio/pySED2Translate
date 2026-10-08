"""Writing report files (CSV for 0-2 dimensions, HDF5 for more).

Format (sed2-test-suite docs/FORMATS.md):
* CSV: UTF-8, LF line endings, comma separator, RFC 4180 quoting.  0-D: one line, one value.  1-D: a column
  vector, labels (if any) as the first column, no header row.  2-D: rows by columns; column labels form a header
  row, row labels the first column, and the top-left cell is empty if both exist.
* Numbers use Python's repr; nan, inf and -inf are written in lower case.  Strings are written as they are.
* HDF5: dataset 'data'; dataset 'labels/<i>' for each labeled dimension; root attribute 'dims'.
"""
from __future__ import annotations

import csv
import io
import math
import os
from typing import Any

import numpy as np

from .annotated import AnnotatedData, DataError


def format_number(x: Any) -> str:
    x = float(x)
    if math.isnan(x):
        return "nan"
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    return repr(x)


def _cell(value: Any, is_string: bool) -> str:
    return str(value) if is_string else format_number(value)


def _label(lab: Any) -> str:
    if isinstance(lab, str):
        return lab
    return format_number(lab)


def csv_text(data: AnnotatedData) -> str:
    """The CSV text for data with at most two dimensions."""
    if data.ndim > 2:
        raise DataError(f"{data.ndim}-dimensional data cannot be written as CSV; use HDF5")
    out = io.StringIO()
    w = csv.writer(out, delimiter=",", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    s = data.is_string
    if data.ndim == 0:
        w.writerow([_cell(data.values[()], s)])
    elif data.ndim == 1:
        rows = data.labels[0]
        for i in range(data.shape[0]):
            row = [_cell(data.values[i], s)]
            if rows is not None:
                row.insert(0, _label(rows[i]))
            w.writerow(row)
    else:
        rows, cols = data.labels
        if cols is not None:
            header = [_label(c) for c in cols]
            if rows is not None:
                header.insert(0, "")
            w.writerow(header)
        for i in range(data.shape[0]):
            row = [_cell(v, s) for v in data.values[i]]
            if rows is not None:
                row.insert(0, _label(rows[i]))
            w.writerow(row)
    return out.getvalue()


def write_csv(path: str, data: AnnotatedData) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(csv_text(data))


def write_h5(path: str, data: AnnotatedData) -> None:
    import h5py

    str_dtype = h5py.string_dtype(encoding="utf-8")
    with h5py.File(path, "w") as f:
        if data.is_string:
            f.create_dataset("data", data=np.asarray(data.values, dtype=object), dtype=str_dtype)
        else:
            f.create_dataset("data", data=data.values.astype(np.float64))
        grp = f.create_group("labels")
        for i, lab in enumerate(data.labels):
            if lab is None:
                continue
            if all(isinstance(x, str) for x in lab):
                grp.create_dataset(str(i), data=np.asarray(lab, dtype=object), dtype=str_dtype)
            else:
                grp.create_dataset(str(i), data=np.asarray(lab, dtype=np.float64))
        f.attrs.create("dims", np.asarray(data.dims, dtype=object), dtype=str_dtype)


def write_report(ctx, report_id: str, data: AnnotatedData) -> str:
    """Write a report next to the other results; returns the path.  CSV for 0-2 dimensions, else HDF5."""
    if data.ndim <= 2:
        path = ctx.output_path(f"{report_id}.csv")
        write_csv(path, data)
    else:
        path = ctx.output_path(f"{report_id}.h5")
        write_h5(path, data)
    return path
