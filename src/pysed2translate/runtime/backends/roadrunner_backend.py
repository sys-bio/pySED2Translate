"""libroadrunner backend."""
from __future__ import annotations

import numpy as np

from ... import kisao
from ..annotated import DataError
from ..model import SbmlModel
from .base import Backend, JacobianResult, SteadyState, SteadyStateResult, TimeCourse, TimeCourseResult

# SED2 setting -> roadrunner integrator setting, per integrator
_SETTING_NAMES = {
    "cvode": {"relativeTolerance": "relative_tolerance", "absoluteTolerance": "absolute_tolerance",
              "initialStepSize": "initial_time_step", "maxNumberOfSteps": "maximum_num_steps",
              "maxInternalStepSize": "maximum_time_step", "minInternalStepSize": "minimum_time_step",
              "useStiffSolver": "stiff", "maxBDForder": "maximum_bdf_order", "maxAdamsOrder": "maximum_adams_order",
              "variableStepSize": "variable_step_size", "maxOutputRows": "max_output_rows"},
    "rk4": {},
}


STEADY_STATE_RESIDUAL = 1e-6   # largest acceptable norm of the rates of change at a reported steady state


def selector(model: SbmlModel, variable: str) -> str:
    """The roadrunner selection string for a SED2 variable id (SBML id semantics)."""
    if variable == "time":
        return "time"
    kind = model.kind_of(variable)
    if kind == "species_concentration":
        return f"[{variable}]"
    if kind == "unknown":
        raise DataError(f"the model has no species, compartment, parameter or reaction {variable!r}")
    return variable


class RoadRunnerBackend(Backend):
    name = "roadrunner"

    def _integrator(self, rr, tc: TimeCourse) -> str:
        try:
            found = kisao.solver_for("roadrunner", tc.algorithm)
        except ValueError as e:
            raise DataError(str(e)) from e
        solver, options = found
        rr.setIntegrator(solver)
        names = _SETTING_NAMES[solver]
        applied = dict(options)
        for sed2_name, value in tc.settings.items():
            if sed2_name not in names:
                raise DataError(f"roadrunner's {solver} integrator cannot honor {sed2_name}")
            applied[names[sed2_name]] = value
        if solver == "cvode":
            applied.setdefault("relative_tolerance", kisao.DEFAULT_RELATIVE_TOLERANCE)
            applied.setdefault("absolute_tolerance", kisao.DEFAULT_ABSOLUTE_TOLERANCE)
        if "variable_step_size" in rr.integrator.getSettings():
            applied["variable_step_size"] = False  # explicit output points and steps; spans switch it on themselves
        for key, value in applied.items():
            rr.integrator.setValue(key, value)
        return solver

    def _time_course(self, model: SbmlModel, tc: TimeCourse) -> TimeCourseResult:
        import roadrunner

        rr = roadrunner.RoadRunner(model.text)
        solver = self._integrator(rr, tc)
        rr.timeCourseSelections = ["time"] + [selector(model, v) for v in tc.output_variables]
        n = len(tc.output_variables)

        if tc.points is not None:
            points = [float(p) for p in tc.points]
            if any(b < a for a, b in zip(points, points[1:])):
                raise DataError("the output points must not decrease")
            start = tc.start if tc.start is not None else (points[0] if points else 0.0)
            if points and points[0] < start:
                raise DataError(f"the first output point {points[0]} is before the start {start}")
            rr.model.setTime(start)
            times = points if points and points[0] == start else [start] + points
            table = self._run(rr, times)
            if times is not points:
                table = table[1:]
        elif tc.span is not None:
            if solver in kisao.FIXED_STEP_SOLVERS["roadrunner"]:
                raise DataError(f"roadrunner's {solver} integrator cannot choose its own output points")
            a, b = float(tc.span[0]), float(tc.span[1])
            if tc.start not in (None, 0.0) and tc.start != a:
                raise DataError("independentVariableInit must equal the span's start")
            rr.model.setTime(a)
            rr.integrator.setValue("variable_step_size", True)
            table = np.array(rr.simulate(a, b))
            # roadrunner's last variable-step row (at the span's end) is interpolated and less accurate than the
            # others (relative error ~5e-5 against tolerances of 1e-10), so the end point is integrated on its own
            rr.reset()
            rr.integrator.setValue("variable_step_size", False)
            rr.model.setTime(a)
            last = self._run(rr, [a, b])[-1]
            table = np.vstack([table[table[:, 0] < b], last])
        else:
            start = float(tc.start or 0.0)
            rr.model.setTime(start)
            table = self._run(rr, [start, start + float(tc.step)])[-1:]

        table = np.asarray(table, dtype=float).reshape(-1, 1 + n)
        end_state = {v: float(rr[selector(model, v)]) for v in model.state_variables()}
        return TimeCourseResult(table[:, 0], table[:, 1:], end_state)

    def _steady_state(self, model: SbmlModel, request: SteadyState) -> SteadyStateResult:
        import roadrunner

        problem = kisao.steady_state_problem("roadrunner", request.algorithm)
        if problem:
            raise DataError(problem)
        rr = roadrunner.RoadRunner(model.text)
        selections = [selector(model, v) for v in request.output_variables]
        try:
            residual = rr.steadyState()
        except RuntimeError as e:
            raise DataError(f"roadrunner did not find a steady state: {e}") from e
        if not residual <= STEADY_STATE_RESIDUAL:
            raise DataError(f"roadrunner's steady state is not steady: the rates have norm {residual:g}")
        values = np.array([float(rr[s]) for s in selections], dtype=float)
        end_state = {v: float(rr[selector(model, v)]) for v in model.state_variables()}
        return SteadyStateResult(values, end_state)

    def _jacobian(self, model: SbmlModel, reduced: bool) -> JacobianResult:
        import roadrunner

        rr = roadrunner.RoadRunner(model.text)
        if reduced:
            rr.conservedMoietyAnalysis = True
            matrix = rr.getReducedJacobian()
        else:
            matrix = rr.getFullJacobian()
        return JacobianResult(list(matrix.colnames), np.array(matrix, dtype=float), "concentration")

    @staticmethod
    def _run(rr, times: list) -> np.ndarray:
        if len(times) == 1:  # nothing to integrate: the initial state
            return np.array([rr.getSelectedValues()]) if hasattr(rr, "getSelectedValues") else np.array(rr.simulate(times=times))
        return np.array(rr.simulate(times=times))


def create() -> RoadRunnerBackend:
    return RoadRunnerBackend()
