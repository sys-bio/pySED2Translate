"""Repeats in engine v1: clock-form Loop, nested form, Scatter, ParameterScan, nesting, and the structural rules of plan 3.8."""
import numpy as np
import pytest

from helpers import data_of, run_in_process, translate


def loop_doc(n_steps=3, extra_tasks=None, sub=None):
    doc = {
        "version": "v1.0.0",
        "tasks": {
            "lp": {
                "_type": "loop",
                "range": {"_type": "numericRange", "start": 1, "numberOfSteps": n_steps, "interval": 1},
                "loopVariables": {"acc": {"initialValue": 1.0, "subsequentValues": "#tasks:lp:subTasks:d"}},
                "subTasks": {
                    "d": {"_type": "calculation", "math": "1 * #tasks:lp:loopVariables:acc * 2"},
                    "r": {"_type": "calculation", "math": "1 * #tasks:lp.range"},
                    "i": {"_type": "calculation", "math": "1 * #tasks:lp.index"},
                },
                "outputVariableMap": {"D": "#tasks:lp:subTasks:d", "R": "#tasks:lp:subTasks:r", "I": "#tasks:lp:subTasks:i"},
            },
            "after": {"_type": "calculation", "math": "1 * #tasks:lp[3, 'D'] + 1"},
        },
        "outputs": {"loop": {"_type": "report", "data": "#tasks:lp"}},
    }
    return doc


@pytest.mark.parametrize("form", ["clock", "nested"])
def test_loop_carries_the_variable_and_orders_iterations(tmp_path, form):
    doc, _ = translate(tmp_path, loop_doc(), loop_form=form)
    st = run_in_process(doc, tmp_path=tmp_path)
    d = data_of(st, "lp")
    assert d.shape == (4, 3)
    assert d.labels[1] == ["D", "R", "I"]
    # acc doubles each iteration: 2, 4, 8, 16; the range value is 1..4, the index 0..3
    assert d.values[:, 0].tolist() == [2.0, 4.0, 8.0, 16.0]
    assert d.values[:, 1].tolist() == [1.0, 2.0, 3.0, 4.0]
    assert d.values[:, 2].tolist() == [0.0, 1.0, 2.0, 3.0]
    assert float(data_of(st, "after").values) == 17.0


def test_clock_and_nested_forms_give_the_same_numbers(tmp_path):
    a, _ = translate(tmp_path, loop_doc(), loop_form="clock")
    b, _ = translate(tmp_path, loop_doc(), loop_form="nested", name="t2")
    da, db = data_of(run_in_process(a, tmp_path=tmp_path), "lp"), data_of(run_in_process(b, tmp_path=tmp_path), "lp")
    assert np.array_equal(da.values, db.values) and da.labels == db.labels


def test_task_after_a_loop_fires_once(tmp_path, monkeypatch):
    from pysed2translate_pbg.engines.v1 import steps

    seen = []
    original = steps.SedCalculation.run

    def counting(self, state, args):
        seen.append(self.config["id"])
        return original(self, state, args)

    monkeypatch.setattr(steps.SedCalculation, "run", counting)
    doc, _ = translate(tmp_path, loop_doc())
    run_in_process(doc, tmp_path=tmp_path)
    assert seen.count("after") == 1
    assert seen.count("lp:subTasks:d") == 4          # once per iteration, and not at the start of the run


def test_one_iteration_loop(tmp_path):
    d = loop_doc()
    d["tasks"]["lp"]["range"] = {"_type": "range", "values": [5]}
    d["tasks"].pop("after")
    doc, _ = translate(tmp_path, d)
    st = run_in_process(doc, tmp_path=tmp_path)
    assert data_of(st, "lp").values.tolist() == [[2.0, 5.0, 0.0]]


def test_zero_iteration_loop_gives_an_empty_table(tmp_path):
    d = loop_doc()
    d["tasks"]["lp"]["range"] = {"_type": "range", "values": []}
    d["tasks"].pop("after")
    try:
        doc, _ = translate(tmp_path, d)
    except Exception as e:  # libsed2 may refuse an empty range; then there is nothing to translate
        pytest.skip(f"an empty range is not a valid document: {e}")
    st = run_in_process(doc, tmp_path=tmp_path)
    assert data_of(st, "lp").shape[0] == 0


def nested_doc():
    """Scatter inside a Loop, and a Loop inside a Loop (plan 3.8, rule 4)."""
    return {
        "version": "v1.0.0",
        "constants": {"k": 10},
        "tasks": {
            "outer": {
                "_type": "loop",
                "range": {"_type": "range", "values": [1, 2, 3]},
                "loopVariables": {"v": {"initialValue": 0, "subsequentValues": "#tasks:outer:subTasks:last"}},
                "subTasks": {
                    "inner": {
                        "_type": "loop",
                        "range": {"_type": "range", "values": [1, 2]},
                        "loopVariables": {"w": {"initialValue": "#tasks:outer:loopVariables:v",
                                                "subsequentValues": "#tasks:outer:subTasks:inner:subTasks:step"}},
                        "subTasks": {"step": {"_type": "calculation",
                                              "math": "1 * #tasks:outer:subTasks:inner:loopVariables:w + #tasks:outer.range * #constants:k"}},
                        "outputVariableMap": {"W": "#tasks:outer:subTasks:inner:subTasks:step"},
                    },
                    "last": {"_type": "calculation", "math": "1 * #tasks:outer:subTasks:inner[1, 'W']"},
                    "sc": {
                        "_type": "scatter",
                        "range": {"_type": "range", "values": [100, 200]},
                        "subTasks": {"x": {"_type": "calculation", "math": "1 * #tasks:outer:subTasks:sc.range + #tasks:outer.index"}},
                        "outputVariableMap": {"X": "#tasks:outer:subTasks:sc:subTasks:x"},
                    },
                },
                "outputVariableMap": {"I": "#tasks:outer:subTasks:inner", "S": "#tasks:outer:subTasks:sc"},
            },
        },
        "outputs": {"o": {"_type": "report", "data": "#tasks:outer"}},
    }


@pytest.mark.parametrize("form", ["clock", "nested"])
def test_loop_in_loop_and_scatter_in_loop(tmp_path, form):
    doc, _ = translate(tmp_path, nested_doc(), loop_form=form)
    d = data_of(run_in_process(doc, tmp_path=tmp_path), "outer")
    assert d.shape == (3, 2, 2, 1)     # iterations x entries x (inner iterations or scatter points) x one output
    # outer iteration i (range 1..3) starts the inner loop from v; the inner loop adds range*k twice per outer iteration:
    # v0 = 0; inner: w = 0 + 10*i, then + 10*i again; the inner result (last W) becomes v for the next outer iteration
    v = 0.0
    for i in range(3):
        w = v
        expect = []
        for _ in range(2):
            w = w + (i + 1) * 10.0
            expect.append(w)
        assert d.values[i, 0, :, 0].tolist() == expect
        assert d.values[i, 1, :, 0].tolist() == [100.0 + i, 200.0 + i]
        v = w
    assert d.labels[1] == ["I", "S"]


def test_parallel_sibling_subtasks_and_a_merge(tmp_path):
    doc = {
        "version": "v1.0.0",
        "tasks": {
            "sc": {
                "_type": "scatter",
                "range": {"_type": "range", "values": [1, 2, 3]},
                "subTasks": {
                    "a": {"_type": "calculation", "math": "1 * #tasks:sc.range * 2"},
                    "b": {"_type": "calculation", "math": "1 * #tasks:sc.range * 3"},
                    "m": {"_type": "calculation", "math": "#tasks:sc:subTasks:a + #tasks:sc:subTasks:b"},
                },
                "outputVariableMap": {"M": "#tasks:sc:subTasks:m"},
            }
        },
        "outputs": {"o": {"_type": "report", "data": "#tasks:sc"}},
    }
    d = data_of(run_in_process(translate(tmp_path, doc)[0], tmp_path=tmp_path), "sc")
    assert d.values[:, 0].tolist() == [5.0, 10.0, 15.0]
