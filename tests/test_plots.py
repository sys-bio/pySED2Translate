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
        assert list(f) == ["a", "c", "b"] or sorted(f) == ["a", "b", "c"]


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
