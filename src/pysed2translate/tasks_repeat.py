"""Translation of the Repeat family: Loop, Scatter and ParameterScan.  Importing this module registers the handlers.

A repeat becomes a Python `for` statement.  Its sub-tasks are translated inside it, under the ids
`<repeat>:subTasks:<id>` (the same path a `#tasks:repeat:subTasks:id` reference has), and the values they and the
repeat's per-iteration outputs (`.range`, `.index`, `.ranges`, `.indexes`, `.model`, `:loopVariables:v`) have are
visible only while the repeat is being translated.  Iterations run one after the other, in range order.

The result of a repeat (see the Loop, Scatter and ParameterScan descriptions): dimension 0 is the iteration (Loop, Scatter) or one dimension per scanned
range (ParameterScan), labeled by the range values; then the outputVariableMap entries, labeled by their keys; then
the dimensions of the entries themselves.

Not translated (the capability check skips such documents): `aggregateOutputVariables` (AggregationCalculation has no
function, GAPS.md S-006) and `taskParameters` (their meaning is not defined, S-011).
"""
from __future__ import annotations

from .core import Translator, TaskValues, task_handler
from .errors import TranslationError
from .tasks import _text, data_expr, orref, range_data_expr, range_expr, static_value


def _output_map(tr: Translator, task_id: str, task) -> dict:
    got = orref(task, "outputVariableMap")
    if got is None:
        return {}
    kind, v = got
    if kind == "ref":
        v = static_value(tr, v, f"task {task_id!r} outputVariableMap")
    if not isinstance(v, dict):
        raise TranslationError(f"task {task_id!r}: outputVariableMap must be an object of references")
    return dict(v)


def _sub_tasks(tr: Translator, task_id: str, task) -> None:
    for sid in task.get_sub_tasks():
        tr.translate_task(f"{task_id}:subTasks:{sid}", task.get_sub_tasks_item(sid))


def _entries(tr: Translator, task_id: str, out_map: dict) -> str:
    items = []
    for key, ref in out_map.items():
        import libsed2

        if not (isinstance(ref, str) and libsed2.is_reference(ref)):
            raise TranslationError(f"task {task_id!r}: outputVariableMap[{key!r}] must be a reference")
        items.append(tr.ref(ref))
    return "[" + ", ".join(items) + "]"


def _loop_variables(tr: Translator, task_id: str, task, cb) -> list:
    """Create the loop variables before the `for` (their first value) and register them for the sub-tasks.
    Returns [(name, python variable, subsequentValues reference)]."""
    out = []
    for name in task.get_loop_variables():
        lv = task.get_loop_variables_item(name)
        var = tr.ident("loopvar", f"{task_id}:loopVariables:{name}")
        cb.line(f"{var} = {data_expr(tr, lv.get_initial_value())}")
        tr.register_task(f"{task_id}:loopVariables:{name}", TaskValues({None: var}))
        out.append((name, var, lv.get_subsequent_values()))
    return out


def _range_repeat(tr: Translator, task_id: str, task, with_loop_variables: bool) -> None:
    cb = tr.cb
    points, rows = tr.ident("rep_points", task_id), tr.ident("rep_rows", task_id)
    i, value = tr.ident("rep_i", task_id), tr.ident("rep_value", task_id)
    cur_range, cur_index = tr.ident("rep_range", task_id), tr.ident("rep_index", task_id)
    out_map = _output_map(tr, task_id, task)
    cb.line(f"{points} = rt.ops.numbers_from({range_data_expr(tr, task.get_range())})")
    cb.line(f"{rows} = []")
    loop_vars = _loop_variables(tr, task_id, task, cb) if with_loop_variables else []
    tr.register_task(task_id, TaskValues({"range": cur_range, "index": cur_index}))
    with cb.block(f"for {i}, {value} in enumerate({points}):"):
        cb.line(f"{cur_range} = rt.AnnotatedData({value})")
        cb.line(f"{cur_index} = rt.AnnotatedData(float({i}))")
        _sub_tasks(tr, task_id, task)
        cb.line(f"{rows}.append({_entries(tr, task_id, out_map)})")
        if loop_vars:
            names = ", ".join(v for _, v, _ in loop_vars)
            values = ", ".join(tr.ref(ref) for _, _, ref in loop_vars)
            cb.line(f"{names} = {values}")
    tr.unregister_tasks(task_id)
    result = tr.ident("task", task_id)
    cb.line(f"{result} = rt.ops.repeat_table({points}, {rows}, {list(out_map)!r})")
    tr.register_task(task_id, TaskValues({None: result}))


@task_handler("scatter")
def scatter(tr: Translator, task_id: str, task) -> None:
    _range_repeat(tr, task_id, task, False)


@task_handler("loop")
def loop(tr: Translator, task_id: str, task) -> None:
    _range_repeat(tr, task_id, task, True)


@task_handler("parameterScan")
def parameter_scan(tr: Translator, task_id: str, task) -> None:
    cb = tr.cb
    ranges, names = tr.ident("rep_ranges", task_id), tr.ident("rep_names", task_id)
    rows, ix, vals = tr.ident("rep_rows", task_id), tr.ident("rep_ix", task_id), tr.ident("rep_vals", task_id)
    model, cur_ranges, cur_indexes = (tr.ident("rep_model", task_id), tr.ident("rep_ranges_now", task_id),
                                      tr.ident("rep_indexes_now", task_id))
    elements = [_text(tr, pr, "modelElement", f"task {task_id!r} parameterRanges[{n}] modelElement")
                for n, pr in enumerate(task.get_parameter_ranges())]
    if len(set(elements)) != len(elements):
        raise TranslationError(f"task {task_id!r}: the parameterRanges must scan distinct model elements")
    out_map = _output_map(tr, task_id, task)
    base = tr.ref(task.get_model())
    cb.line(f"{names} = {elements!r}")
    cb.line(f"{ranges} = [" + ", ".join(f"rt.ops.numbers_from({range_expr(tr, pr)})"
                                         for pr in task.get_parameter_ranges()) + "]")
    cb.line(f"{rows} = []")
    tr.register_task(task_id, TaskValues({"ranges": cur_ranges, "indexes": cur_indexes, "model": model}))
    with cb.block(f"for {ix} in rt.ops.grid([len(r) for r in {ranges}]):"):
        cb.line(f"{vals} = [r[k] for r, k in zip({ranges}, {ix})]")
        cb.line(f"{model} = {base}.with_values(dict(zip({names}, {vals})))")
        cb.line(f"{cur_ranges} = rt.ops.labeled_vector({names}, {vals})")
        cb.line(f"{cur_indexes} = rt.ops.labeled_vector({names}, [float(k) for k in {ix}])")
        _sub_tasks(tr, task_id, task)
        cb.line(f"{rows}.append({_entries(tr, task_id, out_map)})")
    tr.unregister_tasks(task_id)
    result = tr.ident("task", task_id)
    cb.line(f"{result} = rt.ops.scan_table({rows}, {ranges}, {names}, {list(out_map)!r})")
    tr.register_task(task_id, TaskValues({None: result}))
