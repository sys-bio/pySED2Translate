"""Python checks for capability entries too complex to express as 'conditions'.

A capability entry may name one of these functions in its "check" field.  The function receives the task's
JSON (a dict) and the backend name, and returns None if the task is supported or a string giving the reason
if it is not.  Register new checks in CHECKS.
"""
from __future__ import annotations

from typing import Callable, Optional

CHECKS: dict[str, Callable[[dict, str], Optional[str]]] = {}


def _ode_simulation(task_json: dict, backend: str) -> Optional[str]:
    """Time-course tasks: the algorithm and every solver setting must be something the backend can honor."""
    from .. import kisao

    algorithms = task_json.get("workingAlgorithms") or []
    for wa in algorithms:
        alg = wa.get("algorithm") if isinstance(wa, dict) else None
        if not isinstance(alg, str) or alg.startswith("#"):
            return "a working algorithm given by reference (or missing) cannot be resolved while translating"
        reason = kisao.algorithm_problem(backend, alg)
        if reason:
            return reason
    if len(algorithms) > 1:
        return "more than one working algorithm is not supported"
    if task_json.get("taskParameters"):
        return "taskParameters are not supported yet"
    reason = kisao.settings_problem(backend, task_json)
    if reason is None and task_json.get("_type") == "boundedODESimulation":
        reason = kisao.step_problem(backend, task_json)
    return reason


def _steady_state(task_json: dict, backend: str) -> Optional[str]:
    """SteadyState: the algorithm, if named, must be one the backend maps."""
    from .. import kisao

    algorithms = task_json.get("workingAlgorithms") or []
    for wa in algorithms:
        alg = wa.get("algorithm") if isinstance(wa, dict) else None
        if not isinstance(alg, str) or alg.startswith("#"):
            return "a working algorithm given by reference (or missing) cannot be resolved while translating"
        reason = kisao.steady_state_problem(backend, alg)
        if reason:
            return reason
    if len(algorithms) > 1:
        return "more than one working algorithm is not supported"
    if task_json.get("taskParameters"):
        return "taskParameters are not supported yet"
    return None


def _jacobian(task_json: dict, backend: str) -> Optional[str]:
    """JacobianFull and JacobianReduced: nothing to configure except taskParameters, which are not supported yet."""
    if task_json.get("taskParameters"):
        return "taskParameters are not supported yet"
    return None


def _model_change(task_json: dict, backend: str) -> Optional[str]:
    """ModelChange: setValues and removeElements only (they are done on the SBML text, the same for every backend)."""
    for name in ("addElements", "replaceElements"):
        if task_json.get(name):
            return f"{name} is not supported: the specification does not define the form of its entries (SED2/TODO.md: ModelChange)"
    if task_json.get("taskParameters"):
        return "taskParameters are not supported yet"
    return None


def _repeat(task_json: dict, backend: str) -> Optional[str]:
    """Loop, Scatter and ParameterScan: no aggregates and no taskParameters (the sub-tasks are checked on their own)."""
    if task_json.get("aggregateOutputVariables"):
        return ("aggregateOutputVariables are not supported: AggregationCalculation has no way to name its function "
                "(SED2/TODO.md: AggregationCalculation)")
    if task_json.get("taskParameters"):
        return "taskParameters are not supported (their meaning is not defined, SED2/TODO.md: TaskParameter)"
    return None


def _csv_import(task_json: dict, backend: str) -> Optional[str]:
    """CsvImport: data in columns only (`organization` absent or "columns"); taskParameters are not supported."""
    organization = task_json.get("organization")
    if organization is not None and organization != "columns":
        return f"organization {organization!r} is not supported: the specification does not define it (SED2/TODO.md: CsvImport)"
    if task_json.get("taskParameters"):
        return "taskParameters are not supported (their meaning is not defined, SED2/TODO.md: TaskParameter)"
    return None


CHECKS["ode_simulation"] = _ode_simulation
CHECKS["csv_import"] = _csv_import
CHECKS["repeat"] = _repeat
CHECKS["model_change"] = _model_change
CHECKS["steady_state"] = _steady_state
CHECKS["jacobian"] = _jacobian
