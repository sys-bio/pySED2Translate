"""Translation of the tasks that do not need a simulator: Calculation, CreateDataBlock, RelabelData,
StringFormation and the range tasks.  Importing this module registers the handlers.

(Model-dependent tasks are in tasks_model.py; AggregationCalculation and the stochastic tasks are not translated:
see capabilities.json.)
"""
from __future__ import annotations

from typing import Any

from .core import Translator, TaskValues, task_handler
from .errors import TranslationError


# --------------------------------------------------------------------------- helpers

def _snake(name: str) -> str:
    return "".join("_" + c.lower() if c.isupper() else c for c in name)


def orref(obj, attr: str):
    """('ref', text) or ('value', v) for an attribute that may be a literal or a reference; None if unset."""
    snake = _snake(attr)
    if not getattr(obj, f"is_set_{snake}")():
        return None
    if getattr(obj, f"is_{snake}_ref")():
        return ("ref", getattr(obj, f"get_{snake}_ref")())
    return ("value", getattr(obj, f"get_{snake}_value")())


def static_value(tr: Translator, text: str, what: str) -> Any:
    """The value a reference to a constant has, found while translating (for attributes that must be known then)."""
    import libsed2

    try:
        return libsed2.get_reference_value(tr.doc, text)
    except Exception as e:  # noqa: BLE001
        raise TranslationError(f"{what}: {text!r} must refer to a constant, because its value is needed while "
                               f"translating ({e})") from e


def has_reference(value: Any) -> bool:
    import libsed2

    if isinstance(value, str):
        return libsed2.is_reference(value)
    if isinstance(value, list):
        return any(has_reference(v) for v in value)
    if isinstance(value, dict):
        return any(has_reference(v) for v in value.values())
    return False


def data_expr(tr: Translator, value: Any) -> str:
    """Python expression giving AnnotatedData for a JSON literal in which strings may be references."""
    if not has_reference(value):
        return f"rt.AnnotatedData.from_constant({value!r})"
    if isinstance(value, str):
        return tr.ref(value)
    if isinstance(value, list):
        return "rt.m.array(" + ", ".join(data_expr(tr, v) for v in value) + ")"
    keys = list(value.keys())
    return f"rt.ops.block({keys!r}, [" + ", ".join(data_expr(tr, value[k]) for k in keys) + "])"


def number_expr(tr: Translator, item) -> str:
    """A float expression for ('value', number) or ('ref', text) or a list entry that is either."""
    import libsed2

    if isinstance(item, tuple):
        kind, v = item
    else:
        kind, v = ("ref", item) if isinstance(item, str) and libsed2.is_reference(item) else ("value", item)
    return f"rt.ops.scalar({tr.ref(v)})" if kind == "ref" else repr(float(v))


def range_expr(tr: Translator, rng) -> str:
    """Python expression for the AnnotatedData of a NumericRange / ParameterRange object."""
    args = []
    for attr in ("start", "end", "interval", "numberOfSteps"):
        got = orref(rng, attr)
        if got is not None:
            args.append(f"{_snake(attr)}={number_expr(tr, got)}")
    scale = orref(rng, "scale")
    if scale is not None:
        kind, v = scale
        args.append(f"scale={'rt.ops.string_scalar(' + tr.ref(v) + ')' if kind == 'ref' else repr(v)}")
    values = orref(rng, "values")
    if values is not None:
        kind, v = values
        if kind == "ref":
            args.append(f"values=rt.ops.numbers_from({tr.ref(v)})")
        else:
            args.append("values=[" + ", ".join(number_expr(tr, e) for e in v) + "]")
    return f"rt.ops.numeric_range({', '.join(args)})"


def range_data_expr(tr: Translator, rng) -> str:
    """Python expression for the AnnotatedData of any Range: a NumericRange or ParameterRange is computed, a plain
    Range (which has only `values`) is its list or reference."""
    if hasattr(rng, "is_set_start"):
        return range_expr(tr, rng)
    kind, v = orref(rng, "values")
    return tr.ref(v) if kind == "ref" else data_expr(tr, v)


def assign(tr: Translator, task_id: str, expr: str, suffixes=(None,)) -> str:
    var = tr.ident("task", task_id)
    tr.cb.line(f"{var} = {expr}")
    tr.register_task(task_id, TaskValues({s: var for s in suffixes}))
    return var


# --------------------------------------------------------------------------- handlers

@task_handler("calculation")
def calculation(tr: Translator, task_id: str, task) -> None:
    # A math string is always an expression, never a reference to a string (Calculation description): `#c:v` alone
    # is the expression consisting of that one reference, and `#c:v * 2` an expression that starts with one.
    text = task.get_math_value()
    assign(tr, task_id, f"rt.m.to_data({tr.math(text)})")


@task_handler("createDataBlock")
def create_data_block(tr: Translator, task_id: str, task) -> None:
    kind, v = orref(task, "data")
    if kind == "ref":
        v = static_value(tr, v, f"task {task_id!r} data")
    if not isinstance(v, dict):
        raise TranslationError(f"task {task_id!r}: data must be a dictionary of labels to values")
    keys = list(v.keys())
    items = ", ".join(data_expr(tr, v[k]) for k in keys)
    assign(tr, task_id, f"rt.ops.block({keys!r}, [{items}])")


@task_handler("relabelData")
def relabel_data(tr: Translator, task_id: str, task) -> None:
    source = tr.ref(task.get_input())
    kind, v = orref(task, "labels")
    labels = f"rt.ops.strings_from({tr.ref(v)})" if kind == "ref" else repr(list(v))
    assign(tr, task_id, f"rt.ops.relabel({source}, {labels})")


@task_handler("stringFormation")
def string_formation(tr: Translator, task_id: str, task) -> None:
    kind, v = orref(task, "concatenate")
    if kind == "ref":
        v = static_value(tr, v, f"task {task_id!r} concatenate")
    if not isinstance(v, list):
        raise TranslationError(f"task {task_id!r}: concatenate must be a list")
    items = []
    for item in v:
        if isinstance(item, (str, bool, int, float)) and not has_reference(item):
            items.append(repr(item))
        else:
            items.append(data_expr(tr, item))
    assign(tr, task_id, f"rt.ops.string_formation([{', '.join(items)}])", suffixes=(None, "strings"))


@task_handler("numericRange")
def numeric_range(tr: Translator, task_id: str, task) -> None:
    assign(tr, task_id, range_expr(tr, task))


@task_handler("parameterRange")
def parameter_range(tr: Translator, task_id: str, task) -> None:
    assign(tr, task_id, range_expr(tr, task))


@task_handler("range")
def plain_range(tr: Translator, task_id: str, task) -> None:
    assign(tr, task_id, range_data_expr(tr, task))


# --------------------------------------------------------------------------- models

def _text(tr: Translator, task, attr: str, what: str) -> str:
    """A string attribute whose value must be known while translating (literal, or a reference to a constant)."""
    kind, v = orref(task, attr)
    if kind == "ref":
        v = static_value(tr, v, what)
    if not isinstance(v, str):
        raise TranslationError(f"{what} must be a string")
    return v


@task_handler("modelImport")
def model_import(tr: Translator, task_id: str, task) -> None:
    location = _text(tr, task, "location", f"task {task_id!r} location")
    language = _text(tr, task, "language", f"task {task_id!r} language")
    assign(tr, task_id, f"rt.SbmlModel.load(ctx.input_path({location!r}), {language!r})", suffixes=("model",))


def _string_list(tr: Translator, task, attr: str):
    got = orref(task, attr)
    if got is None:
        return "None"
    kind, v = got
    return f"rt.ops.strings_from({tr.ref(v)})" if kind == "ref" else repr(list(v))


@task_handler("modelElementList")
def model_element_list(tr: Translator, task_id: str, task) -> None:
    model = tr.ref(task.get_model())
    args = ", ".join(f"{name}={_string_list(tr, task, attr)}" for name, attr in (
        ("include_elements", "includeElements"), ("include_types", "includeTypes"),
        ("exclude_elements", "excludeElements"), ("exclude_types", "excludeTypes")))
    assign(tr, task_id, f"rt.ops.string_data({model}.element_ids({args}))", suffixes=("strings",))


def _set_values_expr(tr: Translator, task_id: str, got) -> str:
    kind, v = got
    if kind == "ref":
        return f"rt.ops.mapping_from({tr.ref(v)})"
    items = []
    for key, value in v.items():
        if isinstance(value, bool) or isinstance(value, (int, float)):
            items.append(f"{key!r}: {float(value)!r}")
        elif has_reference(value):
            items.append(f"{key!r}: rt.ops.scalar({data_expr(tr, value)})")
        else:
            raise TranslationError(f"task {task_id!r}: setValues[{key!r}] = {value!r} is not a number")
    return "{" + ", ".join(items) + "}"


@task_handler("modelChange")
def model_change(tr: Translator, task_id: str, task) -> None:
    """The changes are applied in the order setValues, removeElements.  (addElements and replaceElements are
    unsupported: see capabilities.json.)"""
    expr = tr.ref(task.get_input_model())
    got = orref(task, "setValues")
    if got is not None:
        expr += f".with_values({_set_values_expr(tr, task_id, got)})"
    got = orref(task, "removeElements")
    if got is not None:
        kind, v = got
        expr += f".without({'rt.ops.strings_from(' + tr.ref(v) + ')' if kind == 'ref' else repr(list(v))})"
    assign(tr, task_id, expr, suffixes=("model",))


def _csv_arg(tr: Translator, task, attr: str, kind: str) -> str:
    """The Python expression for an optional CsvImport attribute that may be a literal or a reference."""
    got = orref(task, attr)
    if got is None:
        return "None"
    k, v = got
    if kind == "string":
        return f"rt.ops.string_scalar({tr.ref(v)})" if k == "ref" else repr(str(v))
    if kind == "bool":
        return f"bool(rt.ops.scalar({tr.ref(v)}))" if k == "ref" else repr(bool(v))
    if kind == "int":
        return f"int(rt.ops.scalar({tr.ref(v)}))" if k == "ref" else repr(int(v))
    if kind == "float":
        return f"rt.ops.scalar({tr.ref(v)})" if k == "ref" else repr(float(v))
    return f"rt.ops.strings_from({tr.ref(v)})" if k == "ref" else repr(list(v))


@task_handler("csvImport")
def csv_import(tr: Translator, task_id: str, task) -> None:
    """Reads the file with rt.ops.csv_import; `units` is accepted and ignored; `organization` other than
    'columns' and taskParameters are skipped by the capability table (SED2/TODO.md: CsvImport)."""
    args = [("separator", "separator", "string"), ("headers", "headers", "bool"), ("column_names", "columnNames", "list"),
            ("ncols", "ncols", "int"), ("nrows", "nrows", "int")]
    rest = ", ".join(f"{name}={_csv_arg(tr, task, attr, kind)}" for name, attr, kind in args)
    location = _csv_arg(tr, task, "location", "string")
    assign(tr, task_id, f"rt.ops.csv_import(ctx.input_path({location}), {rest})")
