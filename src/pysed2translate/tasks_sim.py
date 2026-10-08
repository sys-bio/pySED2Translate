"""Translation of the ODE time-course simulations.  Importing this module registers the handlers.

The generated code asks the backend (rt.backends.get(BACKEND)) for the time course and keeps two values: the
AnnotatedData result and the model at the end of the run (`#tasks:id.model`).
"""
from __future__ import annotations

from . import kisao
from .core import Translator, TaskValues, task_handler
from .tasks import _snake, _text, number_expr, orref, range_expr, static_value
from .errors import TranslationError

_BOOLEAN_SETTINGS = {"forcePhysicalCorrectness", "integrateReducedModel", "useReducedModel", "useStiffSolver",
                     "variableStepSize"}
_INTEGER_SETTINGS = {"maxInternalSteps", "maxBDForder", "maxAdamsOrder", "maxOutputRows", "maxNumberOfSteps"}


def _setting_expr(tr: Translator, sim, name: str) -> str:
    kind, v = orref(sim, name)
    if kind == "ref":
        scalar = f"rt.ops.scalar({tr.ref(v)})"
        if name in _BOOLEAN_SETTINGS:
            return f"bool({scalar})"
        if name in _INTEGER_SETTINGS:
            return f"int({scalar})"
        return scalar
    if name in _BOOLEAN_SETTINGS:
        return repr(bool(v))
    if name in _INTEGER_SETTINGS:
        return repr(int(v))
    return repr(float(v))


def _settings(tr: Translator, sim) -> str:
    items = []
    for name in kisao.ALL_SETTINGS:
        if name == "absoluteToleranceVector":
            if orref(sim, name) is not None:
                raise TranslationError("absoluteToleranceVector is not supported")
            continue
        if orref(sim, name) is not None:
            items.append(f"{name!r}: {_setting_expr(tr, sim, name)}")
    return "{" + ", ".join(items) + "}"


def _algorithm(tr: Translator, task_id: str, sim) -> str:
    algs = sim.get_working_algorithms()
    if not algs:
        return "None"
    kind, v = orref(algs[0], "algorithm")
    if kind == "ref":
        v = static_value(tr, v, f"task {task_id!r} working algorithm")
    return repr(v)


def _output_variables(tr: Translator, sim) -> str:
    kind, v = orref(sim, "outputVariables")
    return f"rt.ops.strings_from({tr.ref(v)})" if kind == "ref" else repr(list(v))


def _independent_variable(tr: Translator, task_id: str, sim) -> str:
    text = _text(tr, sim, "independentVariable", f"task {task_id!r} independentVariable")
    return "time" if text in ("time", "urn:sedml:symbol:time") else text


def _time_course(tr: Translator, task_id: str, sim, where: str) -> None:
    model = tr.ref(sim.get_model())
    init = orref(sim, "independentVariableInit")
    args = [f"independent_variable={_independent_variable(tr, task_id, sim)!r}",
            f"output_variables={_output_variables(tr, sim)}"]
    if init is not None:
        args.append(f"start={number_expr(tr, init)}")
    if where == "points":
        args.append(f"points=rt.ops.numbers_from({range_expr(tr, sim.get_independent_variable_range())})")
    elif where == "span":
        span = sim.get_independent_variable_span()
        args.append(f"span=({number_expr(tr, orref(span, 'start'))}, {number_expr(tr, orref(span, 'end'))})")
    else:
        args.append(f"step={number_expr(tr, orref(sim, 'independentStep'))}")
    args.append(f"settings={_settings(tr, sim)}")
    args.append(f"algorithm={_algorithm(tr, task_id, sim)}")
    data, end_model = tr.ident("task", task_id), tr.ident("task", task_id) + "_model"
    tr.cb.line(f"{data}, {end_model} = rt.backends.get(BACKEND).time_course({model}, "
               f"rt.backends.TimeCourse({', '.join(args)}))")
    tr.register_task(task_id, TaskValues({None: data, "model": end_model}))


@task_handler("explicitODESimulation")
def explicit_ode(tr: Translator, task_id: str, sim) -> None:
    _time_course(tr, task_id, sim, "points")


@task_handler("boundedODESimulation")
def bounded_ode(tr: Translator, task_id: str, sim) -> None:
    _time_course(tr, task_id, sim, "span")


@task_handler("oneStepODESimulation")
def one_step_ode(tr: Translator, task_id: str, sim) -> None:
    _time_course(tr, task_id, sim, "step")


# --------------------------------------------------------------------------- steady state and Jacobians

@task_handler("steadyState")
def steady_state(tr: Translator, task_id: str, task) -> None:
    model = tr.ref(task.get_model())
    iv = "time" if orref(task, "independentVariable") is None else _independent_variable(tr, task_id, task)
    data, end_model = tr.ident("task", task_id), tr.ident("task", task_id) + "_model"
    args = [f"independent_variable={iv!r}", f"output_variables={_output_variables(tr, task)}",
            f"algorithm={_algorithm(tr, task_id, task)}"]
    tr.cb.line(f"{data}, {end_model} = rt.backends.get(BACKEND).steady_state({model}, "
               f"rt.backends.SteadyState({', '.join(args)}))")
    tr.register_task(task_id, TaskValues({None: data, "model": end_model}))


def _jacobian(tr: Translator, task_id: str, task, reduced: bool) -> None:
    model = tr.ref(task.get_model())
    data = tr.ident("task", task_id)
    tr.cb.line(f"{data} = rt.backends.get(BACKEND).jacobian({model}, reduced={reduced})")
    tr.register_task(task_id, TaskValues({None: data}))


@task_handler("jacobianFull")
def jacobian_full(tr: Translator, task_id: str, task) -> None:
    _jacobian(tr, task_id, task, False)


@task_handler("jacobianReduced")
def jacobian_reduced(tr: Translator, task_id: str, task) -> None:
    _jacobian(tr, task_id, task, True)
