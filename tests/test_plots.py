"""Plot2D and Plot3D: the plot-as-data files, and the pictures."""
import json
import os
import subprocess
import sys

import numpy as np
import pytest

pytest.importorskip("libsed2")
results_io = pytest.importorskip("sed2suite.results_io")

from pysed2translate.translate import translate_file  # noqa: E402

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
CONSTANTS = {"x": [1, 2, 3, 4], "y": [10, 20, 30, 40], "e": [0.5, 0.5, 0.5, 0.5], "one": 7,
             "labels": ["a", "b", "c", "d"], "grid_z": [[1, 2, 3], [4, 5, 6]], "gx": [0, 1, 2], "gy": [0, 1],
             "yes": True, "ct": "bar", "hi": 100, "lo": 0}


def run(tmp_path, outputs, args=(), expect=0, constants=None):
    doc = {"version": "v1.0.0", "constants": constants or CONSTANTS, "tasks": {}, "outputs": outputs}
    path = tmp_path / "doc.sed2.json"
    path.write_text(json.dumps(doc))
    script = tmp_path / "run.py"
    script.write_text(translate_file(str(path), "roadrunner"))
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [SRC, os.environ.get("PYTHONPATH", "")])))
    r = subprocess.run([sys.executable, str(script), "--output-dir", str(tmp_path / "out"), *args],
                       capture_output=True, text=True, env=env)
    assert r.returncode == expect, r.stderr
    return r, tmp_path / "out"


def curve(**kw):
    c = {"_type": "curve", "curveType": "points", "x": "#constants:x", "y": "#constants:y"}
    c.update(kw)
    return c


def test_plot2d_data_columns_order_and_padding(tmp_path):
    outputs = {"p": {"_type": "plot2D", "legend": True,
                     "curves": {"late": curve(order=2, y="#constants:e"),
                                "first": curve(order=1, yErrorLower="#constants:e", yErrorUpper="#constants:e",
                                               yFrom="#constants:one"),
                                "tied": curve(order=1, x="#constants:one", y="#constants:one")}}}
    _, out = run(tmp_path, outputs)
    plot = results_io.read_plot2d_csv(str(out / "doc.p_as_data.csv"))
    assert list(plot.columns) == ["first.x", "first.y", "first.yErrorLower", "first.yErrorUpper", "first.yFrom",
                                  "tied.x", "tied.y", "late.x", "late.y"]
    assert plot.columns["first.x"] == [1, 2, 3, 4]
    assert plot.columns["first.yFrom"] == [7, None, None, None]    # 0-D counts as length 1; padded below
    assert plot.columns["tied.y"] == [7, None, None, None]
    assert plot.columns["late.y"] == [0.5] * 4
    text = (out / "doc.p_as_data.csv").read_text()
    assert text.splitlines()[0] == "first.x,first.y,first.yErrorLower,first.yErrorUpper,first.yFrom,tied.x,tied.y,late.x,late.y"
    assert text.splitlines()[2].startswith("2.0,20.0,0.5,0.5,,,,2.0,0.5")


def test_plot2d_strings_and_special_values(tmp_path):
    consts = dict(CONSTANTS, withnan=[1, "nan", "inf"])
    outputs = {"p": {"_type": "plot2D", "curves": {"c": curve(x="#constants:labels", y="#constants:withnan")}}}
    _, out = run(tmp_path, outputs, constants=consts)
    lines = (out / "doc.p_as_data.csv").read_text().splitlines()
    assert lines == ["c.x,c.y", "a,1.0", "b,nan", "c,inf", "d,"]


def test_plot2d_higher_dimensional_data_fails_the_output(tmp_path):
    outputs = {"p": {"_type": "plot2D", "curves": {"c": curve(y="#constants:grid_z")}},
               "r": {"_type": "report", "data": "#constants:x"}}
    r, out = run(tmp_path, outputs, expect=1)
    assert "2-dimensional" in r.stderr
    assert (out / "doc.r.csv").exists()           # the other outputs still run


def test_plot3d_data(tmp_path):
    h5py = pytest.importorskip("h5py")
    outputs = {"q": {"_type": "plot3D",
                     "surfaces": {"b": {"surfaceType": "heatMap", "x": "#constants:gx", "y": "#constants:gy",
                                        "z": "#constants:grid_z", "order": 2},
                                  "a": {"surfaceType": "surfaceMesh", "x": "#constants:gx", "y": "#constants:gy",
                                        "z": "#constants:grid_z", "order": 1},
                                  "c": {"surfaceType": "parametricCurve", "x": "#constants:x", "y": "#constants:y",
                                        "z": "#constants:e", "order": 1}}}}
    _, out = run(tmp_path, outputs)
    plot = results_io.read_plot3d_h5(str(out / "doc.q_as_data.h5"))
    assert set(plot.surfaces) == {"a", "b", "c"}
    s = plot.surfaces["a"]
    assert s.surface_type == "surfaceMesh" and s.index == 1
    assert s.x.shape == (3,) and s.y.shape == (2,) and s.z.shape == (2, 3)
    np.testing.assert_allclose(s.z, [[1, 2, 3], [4, 5, 6]])
    assert plot.surfaces["b"].index == 0 and plot.surfaces["c"].index == 2
    with h5py.File(out / "doc.q_as_data.h5") as f:
        assert list(f) == ["a", "c", "b"]            # ascending `order`, ties by position; not alphabetical, not by index


@pytest.mark.parametrize("kind", ["points", "bar", "barStacked", "horizontalBar", "horizontalBarStacked", "shadedArea"])
def test_every_curve_type_is_drawn(tmp_path, kind):
    outputs = {"p": {"_type": "plot2D", "legend": True, "width": 400, "height": 300,
                     "xAxis": {"scale": "linear", "min": 0, "max": 10, "grid": True, "reverse": False},
                     "yAxis": {"scale": "log10"}, "rightYAxis": {"min": 0},
                     "curves": {"c1": curve(curveType=kind, yFrom="#constants:e", yTo="#constants:y"),
                                "c2": curve(curveType=kind, yAxis="right", xErrorLower="#constants:e") if kind == "points"
                                else curve(curveType=kind, yFrom="#constants:e", yTo="#constants:y")}}}
    r, out = run(tmp_path, outputs)
    assert "could not draw" not in r.stderr, r.stderr
    assert (out / "doc.p.png").stat().st_size > 0


def test_curve_type_and_attributes_by_reference(tmp_path):
    outputs = {"p": {"_type": "plot2D", "legend": "#constants:yes", "height": "#constants:hi", "width": "#constants:hi",
                     "yAxis": {"min": "#constants:lo", "max": "#constants:hi"},
                     "curves": {"c": curve(curveType="#constants:ct", order="#constants:lo")}}}
    r, out = run(tmp_path, outputs)
    assert "could not draw" not in r.stderr, r.stderr
    assert (out / "doc.p.png").exists()


@pytest.mark.parametrize("kind", ["parametricCurve", "surfaceMesh", "surfaceContour", "contour", "heatMap",
                                  "stackedCurves", "bar"])
def test_every_surface_type_is_drawn(tmp_path, kind):
    if kind == "parametricCurve":
        s = {"surfaceType": kind, "x": "#constants:x", "y": "#constants:y", "z": "#constants:e"}
    else:
        s = {"surfaceType": kind, "x": "#constants:gx", "y": "#constants:gy", "z": "#constants:grid_z"}
    outputs = {"q": {"_type": "plot3D", "legend": True, "zAxis": {"min": 0}, "surfaces": {"s": s}}}
    r, out = run(tmp_path, outputs)
    assert "could not draw" not in r.stderr, r.stderr
    assert (out / "doc.q.png").stat().st_size > 0
    assert (out / "doc.q_as_data.h5").exists()


def test_no_png_option(tmp_path):
    outputs = {"p": {"_type": "plot2D", "curves": {"c": curve()}}}
    _, out = run(tmp_path, outputs, args=("--no-png",))
    assert (out / "doc.p_as_data.csv").exists() and not (out / "doc.p.png").exists()


def figure(out, name):
    return json.loads((out / name).read_text())


def test_plot2d_plotly_figure(tmp_path):
    consts = dict(CONSTANTS, third=[0.1234567890123456789, 1, 2, 3], withnan=[1, "nan", "inf", 4])
    outputs = {"p": {"_type": "plot2D", "legend": True, "width": 400, "height": 300,
                     "yAxis": {"scale": "log10", "min": 1, "max": 100, "grid": True},
                     "curves": {"c": curve(y="#constants:withnan", yErrorLower="#constants:e"),
                                "d": curve(order=2, curveType="bar", y="#constants:third")}}}
    _, out = run(tmp_path, outputs, constants=consts)
    fig = figure(out, "doc.p.plotly.json")
    c, d = fig["data"]
    assert (c["name"], c["type"], c["x"], c["y"]) == ("c", "scatter", [1.0, 2.0, 3.0, 4.0], [1.0, None, None, 4.0])
    assert c["error_y"] == {"type": "data", "symmetric": False, "array": [0.0] * 4, "arrayminus": [0.5] * 4}
    assert "error_x" not in c
    assert (d["name"], d["type"], d["y"][0]) == ("d", "bar", 0.1234567890123456789)
    assert fig["layout"]["title"] == {"text": "p"} and fig["layout"]["showlegend"] is True
    assert (fig["layout"]["width"], fig["layout"]["height"]) == (400, 300)
    assert fig["layout"]["yaxis"] == {"type": "log", "range": [0.0, 2.0], "showgrid": True}
    assert "xaxis" not in fig["layout"]
    assert fig["meta"] == {"plotType": "plot2D"}


@pytest.mark.parametrize("kind", ["points", "bar", "barStacked", "horizontalBar", "horizontalBarStacked", "shadedArea"])
def test_plot2d_plotly_every_curve_type(tmp_path, kind):
    outputs = {"p": {"_type": "plot2D", "curves": {"c": curve(curveType=kind, yFrom="#constants:e",
                                                               yTo="#constants:y")}}}
    _, out = run(tmp_path, outputs)
    fig = figure(out, "doc.p.plotly.json")
    traces = fig["data"]
    assert all(t["meta"] == {"curveType": kind} for t in traces)
    if kind == "shadedArea":
        assert [t.get("fill") for t in traces] == [None, "tonexty"]
        assert traces[0]["y"] == [0.5] * 4 and traces[1]["y"] == [10.0, 20.0, 30.0, 40.0]
    elif kind.startswith("horizontal"):
        assert traces[0]["orientation"] == "h" and traces[0]["x"] == [10.0, 20.0, 30.0, 40.0]
    else:
        assert len(traces) == 1 and traces[0]["x"] == [1.0, 2.0, 3.0, 4.0]
    assert (fig["layout"].get("barmode") == "stack") == kind.endswith("Stacked")


def test_plot2d_plotly_right_axis_and_x_errors(tmp_path):
    outputs = {"p": {"_type": "plot2D", "rightYAxis": {"min": 0, "max": 5},
                     "curves": {"a": curve(), "b": curve(yAxis="right", xErrorUpper="#constants:e")}}}
    _, out = run(tmp_path, outputs)
    fig = figure(out, "doc.p.plotly.json")
    assert "yaxis" not in fig["data"][0] and fig["data"][1]["yaxis"] == "y2"
    assert fig["layout"]["yaxis2"] == {"overlaying": "y", "side": "right", "range": [0.0, 5.0]}
    assert fig["data"][1]["error_x"]["array"] == [0.5] * 4 and fig["data"][1]["error_x"]["arrayminus"] == [0.0] * 4


def test_plot2d_plotly_string_x_values(tmp_path):
    outputs = {"p": {"_type": "plot2D", "curves": {"c": curve(x="#constants:labels", curveType="bar")}}}
    _, out = run(tmp_path, outputs)
    assert figure(out, "doc.p.plotly.json")["data"][0]["x"] == ["a", "b", "c", "d"]


def test_plotly_figure_is_written_with_no_png_and_not_when_the_data_fails(tmp_path):
    outputs = {"p": {"_type": "plot2D", "curves": {"c": curve()}}}
    _, out = run(tmp_path, outputs, args=("--no-png",))
    assert (out / "doc.p.plotly.json").exists() and not (out / "doc.p.png").exists()
    bad = {"p": {"_type": "plot2D", "curves": {"c": curve(y="#constants:grid_z")}}}
    (tmp_path / "bad").mkdir()
    _, out = run(tmp_path / "bad", bad, expect=1)
    assert not (out / "doc.p.plotly.json").exists()


def test_plot3d_plotly_grid_orientation(tmp_path):
    consts = dict(CONSTANTS, grid_t=[[1, 4], [2, 5], [3, 6]])         # z[x][y]: transposed to one row per y
    outputs = {"q": {"_type": "plot3D", "surfaces": {
        "a": {"surfaceType": "surfaceMesh", "x": "#constants:gx", "y": "#constants:gy", "z": "#constants:grid_z"},
        "b": {"surfaceType": "surfaceContour", "x": "#constants:gx", "y": "#constants:gy", "z": "#constants:grid_t"}}}}
    _, out = run(tmp_path, outputs, constants=consts)
    a, b = figure(out, "doc.q.plotly.json")["data"]
    assert a["type"] == "surface" and a["x"] == [0.0, 1.0, 2.0] and a["y"] == [0.0, 1.0]
    assert a["z"] == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]] and b["z"] == a["z"]
    assert b["contours"] == {"z": {"show": True}}


def test_plot3d_plotly_flat_plot_uses_2d_axes(tmp_path):
    outputs = {"q": {"_type": "plot3D", "xAxis": {"scale": "log10"}, "zAxis": {"min": 0, "max": 9},
                     "surfaces": {"h": {"surfaceType": "heatMap", "x": "#constants:gx", "y": "#constants:gy",
                                        "z": "#constants:grid_z"},
                                  "k": {"surfaceType": "contour", "x": "#constants:gx", "y": "#constants:gy",
                                        "z": "#constants:grid_z"}}}}
    _, out = run(tmp_path, outputs)
    fig = figure(out, "doc.q.plotly.json")
    assert [t["type"] for t in fig["data"]] == ["heatmap", "contour"]
    assert fig["layout"]["xaxis"] == {"type": "log"} and "scene" not in fig["layout"] and "zaxis" not in fig["layout"]


def test_plot3d_plotly_scene_axes_and_mixed_types(tmp_path):
    outputs = {"q": {"_type": "plot3D", "zAxis": {"min": 0, "max": 9},
                     "surfaces": {"h": {"surfaceType": "heatMap", "x": "#constants:gx", "y": "#constants:gy",
                                        "z": "#constants:grid_z"},
                                  "c": {"surfaceType": "parametricCurve", "x": "#constants:x", "y": "#constants:y",
                                        "z": "#constants:e"}}}}
    _, out = run(tmp_path, outputs)
    fig = figure(out, "doc.q.plotly.json")
    assert [t["type"] for t in fig["data"]] == ["surface", "scatter3d"]     # a heat map in a 3-D scene is a surface
    assert fig["layout"]["scene"] == {"zaxis": {"range": [0.0, 9.0]}}


@pytest.mark.parametrize("kind", ["parametricCurve", "surfaceMesh", "surfaceContour", "contour", "heatMap",
                                  "stackedCurves", "bar"])
def test_plot3d_plotly_every_surface_type(tmp_path, kind):
    if kind == "parametricCurve":
        s = {"surfaceType": kind, "x": "#constants:x", "y": "#constants:y", "z": "#constants:e"}
    else:
        s = {"surfaceType": kind, "x": "#constants:gx", "y": "#constants:gy", "z": "#constants:grid_z"}
    r, out = run(tmp_path, {"q": {"_type": "plot3D", "surfaces": {"s": s}}})
    assert "plotly figure" not in r.stderr, r.stderr
    traces = figure(out, "doc.q.plotly.json")["data"]
    assert traces and all(t["meta"] == {"surfaceType": kind} for t in traces)
    assert len(traces) == (2 if kind == "stackedCurves" else 1)
