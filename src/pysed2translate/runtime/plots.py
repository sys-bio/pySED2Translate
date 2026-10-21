"""Plot outputs.

For every Plot2D / Plot3D the script writes the data the plot is drawn from (the form the test suite compares), a
plotly figure of the same arrays (`<prefix>.<plot id>.plotly.json`, always written) and, if matplotlib is available and
PNG output is enabled, a picture.  The data file is written first and is exactly what the drawing code receives.  A
failure to draw or to write the figure is reported on stderr but does not fail the output.

Plot2D data (sed2-test-suite docs/FORMATS.md): `<prefix>.<plot id>_as_data.csv`; each curve, in ascending `order`
(ties by position in the document), contributes the columns x, y, xErrorLower, xErrorUpper, yErrorLower,
yErrorUpper, yFrom, yTo that it defines, headed `<curve id>.<field>`; shorter columns are padded with empty cells.
Plot3D data: `<prefix>.<plot id>_as_data.h5` with a group per surface holding datasets x, y, z and the attributes
surfaceType and index (the surface's position in the document).
"""
from __future__ import annotations

import os

import csv
import io
import json
import sys
from typing import Any, Optional

import numpy as np

from .annotated import AnnotatedData, DataError
from .writers import format_number

CURVE_FIELDS = ("x", "y", "xErrorLower", "xErrorUpper", "yErrorLower", "yErrorUpper", "yFrom", "yTo")


# --------------------------------------------------------------------------- the data behind a plot

def _column(owner: str, data: AnnotatedData) -> list:
    if not isinstance(data, AnnotatedData):
        raise DataError(f"{owner}: data was expected")
    if data.ndim > 1:
        raise DataError(f"{owner} is {data.ndim}-dimensional; a curve needs 0-D or 1-D data")
    values = data.values.reshape(-1)
    return [str(v) if data.is_string else float(v) for v in values]


def _ordered(items: list) -> list:
    """Ascending `order` (unset counts as 0), ties by position in the document."""
    return sorted(items, key=lambda it: (it.get("order") or 0, it["position"]))


def curve_columns(curves: list) -> dict:
    """Plot2D: ordered mapping 'curve.field' -> list of float / str."""
    columns: dict = {}
    for c in _ordered(curves):
        for field in CURVE_FIELDS:
            if field in c["fields"]:
                columns[f"{c['id']}.{field}"] = _column(f"curve {c['id']!r} {field}", c["fields"][field])
    return columns


def plot2d_csv_text(columns: dict) -> str:
    out = io.StringIO()
    w = csv.writer(out, delimiter=",", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    names = list(columns)
    w.writerow(names)
    rows = max((len(c) for c in columns.values()), default=0)
    for i in range(rows):
        w.writerow([("" if i >= len(columns[n]) else (columns[n][i] if isinstance(columns[n][i], str)
                                                      else format_number(columns[n][i]))) for n in names])
    return out.getvalue()


def write_plot3d_h5(path: str, surfaces: list) -> None:
    import h5py

    # creation order is tracked, so that readers list the surfaces in the order written (ascending `order`)
    with h5py.File(path, "w", track_order=True) as f:
        for s in _ordered(surfaces):
            g = f.create_group(s["id"])
            for name in ("x", "y", "z"):
                d = s["fields"][name]
                if not isinstance(d, AnnotatedData):
                    raise DataError(f"surface {s['id']!r} {name}: data was expected")
                if d.is_string:
                    g.create_dataset(name, data=np.asarray(d.values, dtype=object), dtype=h5py.string_dtype("utf-8"))
                else:
                    g.create_dataset(name, data=d.values.astype(np.float64))
            g.attrs["surfaceType"] = str(s["type"])
            g.attrs["index"] = int(s["position"])


# --------------------------------------------------------------------------- entry points

def plot2d(ctx, plot_id: str, curves: list, options: dict) -> None:
    columns = curve_columns(curves)
    path = ctx.output_path(f"{plot_id}_as_data.csv")
    ctx.manifest["plots"][plot_id] = {"file": os.path.basename(path), "format": "csv", "type": "plot2D"}
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(plot2d_csv_text(columns))
    write_plotly(ctx, plot_id, lambda: plot2d_figure(plot_id, curves, options))
    _picture(ctx, plot_id, lambda: _draw2d(ctx.output_path(f"{plot_id}.png"), curves, options))


def plot3d(ctx, plot_id: str, surfaces: list, options: dict) -> None:
    path = ctx.output_path(f"{plot_id}_as_data.h5")
    ctx.manifest["plots"][plot_id] = {"file": os.path.basename(path), "format": "h5", "type": "plot3D"}
    write_plot3d_h5(path, surfaces)
    write_plotly(ctx, plot_id, lambda: plot3d_figure(plot_id, surfaces, options))
    _picture(ctx, plot_id, lambda: _draw3d(ctx.output_path(f"{plot_id}.png"), surfaces, options))


def _picture(ctx, plot_id: str, draw) -> None:
    if not getattr(ctx, "png", True):
        return
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print(f"warning: matplotlib is not installed, so there is no picture of plot {plot_id!r}", file=sys.stderr)
        return
    try:
        draw()
    except Exception as e:  # noqa: BLE001 - the picture is an illustration only
        print(f"warning: could not draw plot {plot_id!r}: {type(e).__name__}: {e}", file=sys.stderr)


# --------------------------------------------------------------------------- plotly figures

BAR_KINDS = ("bar", "barStacked", "horizontalBar", "horizontalBarStacked")


def _numbers(values) -> list:
    """Nested lists of floats for JSON; nan and the infinities become null (strict JSON has no such values)."""
    arr = np.atleast_1d(np.asarray(values, dtype=float))
    out = arr.astype(object)
    out[~np.isfinite(arr)] = None
    return out.tolist()


def _values(data: AnnotatedData) -> list:
    """A curve field as a flat JSON list; strings stay strings."""
    flat = data.values.reshape(-1)
    return [str(v) for v in flat] if data.is_string else _numbers(flat)


def _axis_layout(spec: Optional[dict]) -> dict:
    """Plotly axis settings for an axis description.  A range needs both bounds; one bound alone is dropped."""
    out: dict = {}
    if not spec:
        return out
    log = spec.get("scale") == "log10"
    if log:
        out["type"] = "log"
    lo, hi = spec.get("min"), spec.get("max")
    if lo is not None and hi is not None:
        if not log:
            out["range"] = [float(lo), float(hi)]
        elif lo > 0 and hi > 0:
            out["range"] = [float(np.log10(lo)), float(np.log10(hi))]    # plotly gives log axis ranges as exponents
    if spec.get("grid"):
        out["showgrid"] = True
    if spec.get("reverse"):
        if "range" in out:
            out["range"].reverse()
        else:
            out["autorange"] = "reversed"
    return out


def _base_layout(plot_id: str, options: dict) -> dict:
    layout: dict = {"title": {"text": plot_id}, "showlegend": bool(options.get("legend"))}
    for key in ("width", "height"):
        if options.get(key):
            layout[key] = options[key]
    return layout


def plot2d_figure(plot_id: str, curves: list, options: dict) -> dict:
    """The plotly figure (a dict that serializes to plotly JSON) of a Plot2D, from the arrays the data file holds."""
    axes = options.get("axes", {})
    layout = _base_layout(plot_id, options)
    for key, spec in (("xaxis", axes.get("x")), ("yaxis", axes.get("y"))):
        if _axis_layout(spec):
            layout[key] = _axis_layout(spec)
    if any(c.get("y_axis") == "right" for c in curves):
        layout["yaxis2"] = {"overlaying": "y", "side": "right", **_axis_layout(axes.get("right"))}
    traces: list = []
    for c in _ordered(curves):
        f = {k: _values(v) for k, v in c["fields"].items()}
        kind, name = c["type"], c["id"]
        x, y = f.get("x"), f.get("y")
        side = {"yaxis": "y2"} if c.get("y_axis") == "right" else {}
        meta = {"curveType": kind}
        if kind in BAR_KINDS:
            trace = {"type": "bar", "name": name, **side, "meta": meta}
            if kind.startswith("horizontal"):
                trace.update(orientation="h", x=y, y=x)
            else:
                trace.update(x=x, y=y)
            if kind.endswith("Stacked"):
                layout["barmode"] = "stack"
            traces.append(trace)
        elif kind == "shadedArea":
            traces.append({"type": "scatter", "mode": "lines", "name": f"{name}.yFrom", "x": x, "y": f.get("yFrom", y),
                           "line": {"width": 0}, "showlegend": False, **side, "meta": meta})
            traces.append({"type": "scatter", "mode": "lines", "name": name, "x": x, "y": f.get("yTo", y),
                           "fill": "tonexty", "line": {"width": 0}, **side, "meta": meta})
        else:
            trace = {"type": "scatter", "mode": "lines+markers", "name": name, "x": x, "y": y, **side, "meta": meta}
            for axis, lo, hi, n in (("x", "xErrorLower", "xErrorUpper", len(x or [])),
                                    ("y", "yErrorLower", "yErrorUpper", len(y or []))):
                if lo in f or hi in f:
                    trace[f"error_{axis}"] = {"type": "data", "symmetric": False, "array": f.get(hi, [0.0] * n),
                                              "arrayminus": f.get(lo, [0.0] * n)}
            traces.append(trace)
    return {"data": traces, "layout": layout, "meta": {"plotType": "plot2D"}}


def plot3d_figure(plot_id: str, surfaces: list, options: dict) -> dict:
    """The plotly figure of a Plot3D, from the arrays the data file holds.  Plotly has no 3-D bars, so those are markers."""
    axes = options.get("axes", {})
    flat = all(s["type"] in ("contour", "heatMap") for s in surfaces)
    layout = _base_layout(plot_id, options)
    names = ("x", "y") if flat else ("x", "y", "z")
    styled = {f"{n}axis": _axis_layout(axes.get(n)) for n in names if _axis_layout(axes.get(n))}
    if flat:
        layout.update(styled)
    elif styled:
        layout["scene"] = styled
    traces: list = []
    for s in _ordered(surfaces):
        kind, name = s["type"], s["id"]
        meta = {"surfaceType": kind}
        if kind == "parametricCurve":
            x, y, z = (_numbers(s["fields"][k].values.reshape(-1)) for k in ("x", "y", "z"))
            traces.append({"type": "scatter3d", "mode": "lines", "name": name, "x": x, "y": y, "z": z, "meta": meta})
            continue
        if kind not in ("stackedCurves", "bar", "surfaceMesh", "surfaceContour", "contour", "heatMap"):
            raise DataError(f"unknown surface type {kind!r}")
        x2, y2, z2 = _grid(s)                           # meshed coordinates; z has one row per y
        axis_1d = np.ndim(s["fields"]["x"].values) == 1 and np.ndim(s["fields"]["y"].values) == 1 and z2.ndim == 2
        x_arg, y_arg = (_numbers(x2[0]), _numbers(y2[:, 0])) if axis_1d else (_numbers(x2), _numbers(y2))
        if kind == "stackedCurves":
            for i in range(z2.shape[0]):
                traces.append({"type": "scatter3d", "mode": "lines", "name": name, "legendgroup": name,
                               "showlegend": i == 0, "x": _numbers(x2[i]), "y": _numbers(y2[i]), "z": _numbers(z2[i]),
                               "meta": meta})
        elif kind == "bar":
            traces.append({"type": "scatter3d", "mode": "markers", "name": name, "x": _numbers(x2.ravel()),
                           "y": _numbers(y2.ravel()), "z": _numbers(z2.ravel()), "meta": meta})
        elif kind in ("contour", "heatMap") and flat:
            if axis_1d:
                traces.append({"type": "contour" if kind == "contour" else "heatmap", "name": name, "x": x_arg,
                               "y": y_arg, "z": _numbers(z2), "meta": meta})
            else:
                traces.append({"type": "scatter", "mode": "markers", "name": name, "x": _numbers(x2.ravel()),
                               "y": _numbers(y2.ravel()), "marker": {"color": _numbers(z2.ravel())}, "meta": meta})
        else:
            trace = {"type": "surface", "name": name, "x": x_arg, "y": y_arg, "z": _numbers(z2), "meta": meta}
            if kind == "surfaceContour":
                trace["contours"] = {"z": {"show": True}}
            traces.append(trace)
    return {"data": traces, "layout": layout, "meta": {"plotType": "plot3D"}}


def write_plotly(ctx, plot_id: str, build) -> None:
    """Write <plot id>.plotly.json from build().  A failure is reported on stderr and does not fail the output."""
    try:
        text = json.dumps(build(), allow_nan=False)
        with open(ctx.output_path(f"{plot_id}.plotly.json"), "w", encoding="utf-8", newline="") as f:
            f.write(text + "\n")
    except Exception as e:  # noqa: BLE001 - the figure is an illustration only
        print(f"warning: could not write the plotly figure of plot {plot_id!r}: {type(e).__name__}: {e}", file=sys.stderr)


# --------------------------------------------------------------------------- pictures

def _array(data: Optional[AnnotatedData]):
    if data is None:
        return None
    return data.values.reshape(-1) if data.ndim <= 1 else data.values


def _style_axis(ax, which: str, spec: Optional[dict]) -> None:
    if not spec:
        return
    if spec.get("scale") == "log10":
        getattr(ax, f"set_{which}scale")("log")
    lo, hi = spec.get("min"), spec.get("max")
    if lo is not None or hi is not None:
        getattr(ax, f"set_{which}lim")(lo, hi)
    if spec.get("grid"):
        getattr(ax, f"{which}axis").grid(True)
    if spec.get("reverse"):
        getattr(ax, f"invert_{which}axis")()


def _figure(options: dict, projection: Optional[str] = None):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    w, h = options.get("width"), options.get("height")
    fig = plt.figure(figsize=(w / 100.0, h / 100.0) if w and h else None, dpi=100)
    return plt, fig, fig.add_subplot(projection=projection) if projection else fig.add_subplot()


def _draw2d(path: str, curves: list, options: dict) -> None:
    plt, fig, ax = _figure(options)
    axes = options.get("axes", {})
    right = ax.twinx() if any(c.get("y_axis") == "right" for c in curves) else None
    stack: dict = {}
    for c in _ordered(curves):
        target = right if (c.get("y_axis") == "right" and right is not None) else ax
        f = {k: _array(v) for k, v in c["fields"].items()}
        x, y, kind, label = f.get("x"), f.get("y"), c["type"], c["id"]
        if kind in ("bar", "barStacked", "horizontalBar", "horizontalBarStacked"):
            horizontal = kind.startswith("horizontal")
            base = stack.get((kind, id(target)), np.zeros(len(y))) if kind.endswith("Stacked") else None
            if horizontal:
                target.barh(x, y, left=base, label=label)
            else:
                target.bar(x, y, bottom=base, label=label)
            if base is not None:
                stack[(kind, id(target))] = base + np.asarray(y, dtype=float)
        elif kind == "shadedArea":
            target.fill_between(x, f.get("yFrom", y), f.get("yTo", y), alpha=0.4, label=label)
        else:
            def err(lo, hi):
                return None if lo not in f and hi not in f else np.vstack([f.get(lo, 0 * y), f.get(hi, 0 * y)])
            xerr, yerr = err("xErrorLower", "xErrorUpper"), err("yErrorLower", "yErrorUpper")
            if xerr is not None or yerr is not None:
                target.errorbar(x, y, xerr=xerr, yerr=yerr, fmt="-o", label=label)
            else:
                target.plot(x, y, "-o", label=label)
    _style_axis(ax, "x", axes.get("x"))
    _style_axis(ax, "y", axes.get("y"))
    if right is not None:
        _style_axis(right, "y", axes.get("right"))
    if options.get("legend"):
        ax.legend()
    fig.savefig(path)
    plt.close(fig)


def _grid(s: dict):
    x, y, z = (np.asarray(s["fields"][k].values, dtype=float) for k in ("x", "y", "z"))
    if x.ndim == 1 and y.ndim == 1 and z.ndim == 2:
        if z.shape == (len(x), len(y)) and z.shape != (len(y), len(x)):
            z = z.T
        x, y = np.meshgrid(x, y)
    return x, y, z


def _draw3d(path: str, surfaces: list, options: dict) -> None:
    flat = all(s["type"] in ("contour", "heatMap") for s in surfaces)
    plt, fig, ax = _figure(options, None if flat else "3d")
    axes = options.get("axes", {})
    for s in _ordered(surfaces):
        kind, label = s["type"], s["id"]
        if kind == "parametricCurve":
            x, y, z = (np.asarray(s["fields"][k].values, dtype=float).reshape(-1) for k in ("x", "y", "z"))
            ax.plot(x, y, z, label=label)
        elif kind == "stackedCurves":
            x, y, z = _grid(s)
            for i in range(z.shape[0]):
                ax.plot(x[i], y[i], z[i], label=label if i == 0 else None)
        elif kind == "bar":
            x, y, z = _grid(s)
            ax.bar3d(x.ravel(), y.ravel(), np.zeros(z.size), 0.8, 0.8, z.ravel())
        elif kind == "surfaceMesh":
            x, y, z = _grid(s)
            ax.plot_surface(x, y, z, alpha=0.8)
        elif kind == "surfaceContour":
            x, y, z = _grid(s)
            ax.contour(x, y, z)
        elif kind == "contour":
            x, y, z = _grid(s)
            ax.contour(x, y, z)
        elif kind == "heatMap":
            x, y, z = _grid(s)
            fig.colorbar(ax.pcolormesh(x, y, z, shading="auto"), ax=ax)
        else:
            raise DataError(f"unknown surface type {kind!r}")
    for which in ("x", "y") + (() if flat else ("z",)):
        _style_axis(ax, which, axes.get(which))
    if options.get("legend") and not flat:
        ax.legend()
    fig.savefig(path)
    plt.close(fig)
