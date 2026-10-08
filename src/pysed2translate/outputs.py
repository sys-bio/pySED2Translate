"""Translation of outputs.  Importing this module registers the handlers."""
from __future__ import annotations

from .core import output_handler
from .tasks import _csv_arg, _snake, orref


@output_handler("report")
def report(tr, report_id: str, element) -> None:
    """Report: write the referenced AnnotatedData to <prefix>.<id>.csv (or .h5 for 3 or more dimensions)."""
    data = tr.ref(element.get_data())
    with tr.cb.block(f"with ctx.step({report_id!r}):"):
        tr.cb.line(f"rt.write_report(ctx, {report_id!r}, {data})")


# --------------------------------------------------------------------------- plots

_CURVE_FIELDS = (("x", "get_x"), ("y", "get_y"), ("xErrorLower", "get_x_error_lower"), ("xErrorUpper", "get_x_error_upper"),
                 ("yErrorLower", "get_y_error_lower"), ("yErrorUpper", "get_y_error_upper"),
                 ("yFrom", "get_y_from"), ("yTo", "get_y_to"))


def _fields(tr, element, names) -> str:
    items = []
    for field, getter in names:
        if getattr(element, f"is_set_{_snake(field)}")():
            items.append(f"{field!r}: {tr.ref(getattr(element, getter)())}")
    return "{" + ", ".join(items) + "}"


def _axis(tr, axis) -> str:
    items = [f"{attr!r}: {_csv_arg(tr, axis, attr, kind)}" for attr, kind in
             (("scale", "string"), ("min", "float"), ("max", "float"), ("grid", "bool"), ("reverse", "bool"))
             if orref(axis, attr) is not None]
    return "{" + ", ".join(items) + "}"


def _options(tr, plot, axis_names) -> str:
    axes = []
    for key, attr in axis_names:
        if getattr(plot, f"is_set_{_snake(attr)}")():
            axes.append(f"{key!r}: {_axis(tr, getattr(plot, 'get_' + _snake(attr))())}")
    items = [f"'axes': {{{', '.join(axes)}}}"]
    for attr, kind in (("legend", "bool"), ("width", "float"), ("height", "float")):
        items.append(f"{attr!r}: {_csv_arg(tr, plot, attr, kind)}")
    return "{" + ", ".join(items) + "}"


@output_handler("plot2D")
def plot2d(tr, plot_id: str, plot) -> None:
    """Plot2D: writes <id>_as_data.csv (and a PNG).  Styles are not applied (a `style` reference is ignored)."""
    curves = []
    for position, cid in enumerate(plot.get_curves()):
        c = plot.get_curves_item(cid)
        curves.append("{" + ", ".join([
            f"'id': {cid!r}", f"'position': {position}", f"'type': {_csv_arg(tr, c, 'curveType', 'string')}",
            f"'order': {_csv_arg(tr, c, 'order', 'int')}", f"'y_axis': {_csv_arg(tr, c, 'yAxis', 'string')}",
            f"'fields': {_fields(tr, c, _CURVE_FIELDS)}"]) + "}")
    options = _options(tr, plot, (("x", "xAxis"), ("y", "yAxis"), ("right", "rightYAxis")))
    with tr.cb.block(f"with ctx.step({plot_id!r}):"):
        tr.cb.line(f"rt.plots.plot2d(ctx, {plot_id!r}, [{', '.join(curves)}], {options})")


@output_handler("plot3D")
def plot3d(tr, plot_id: str, plot) -> None:
    """Plot3D: writes <id>_as_data.h5 (and a PNG)."""
    surfaces = []
    for position, sid in enumerate(plot.get_surfaces()):
        s = plot.get_surfaces_item(sid)
        surfaces.append("{" + ", ".join([
            f"'id': {sid!r}", f"'position': {position}", f"'type': {_csv_arg(tr, s, 'surfaceType', 'string')}",
            f"'order': {_csv_arg(tr, s, 'order', 'int')}",
            f"'fields': {_fields(tr, s, (('x', 'get_x'), ('y', 'get_y'), ('z', 'get_z')))}"]) + "}")
    options = _options(tr, plot, (("x", "xAxis"), ("y", "yAxis"), ("z", "zAxis")))
    with tr.cb.block(f"with ctx.step({plot_id!r}):"):
        tr.cb.line(f"rt.plots.plot3d(ctx, {plot_id!r}, [{', '.join(surfaces)}], {options})")
