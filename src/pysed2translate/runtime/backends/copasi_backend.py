"""COPASI backend (through basico)."""
from __future__ import annotations

import logging

import numpy as np

from ... import kisao
from ..annotated import DataError
from ..model import SbmlModel
from .base import Backend, JacobianResult, SteadyState, SteadyStateResult, TimeCourse, TimeCourseResult

_SETTING_NAMES = {"relativeTolerance": "r_tol", "absoluteTolerance": "a_tol", "maxNumberOfSteps": "max_steps"}


COPASI_STEADY_STATE_RESOLUTION = 1e-12   # COPASI's default is 1e-9
COPASI_JACOBIAN_FACTOR = 1e-6            # relative step for differences; basico's 1e-12 loses ~5e-5 to rounding


def _without_names(text: str) -> str:
    """COPASI names objects after the SBML `name` when there is one; remove the names so that every object is
    called by its SBML id."""
    import libsbml

    doc = libsbml.readSBMLFromString(text)
    for i in range(doc.getModel().getNumSpecies()):
        doc.getModel().getSpecies(i).unsetName()
    model = doc.getModel()
    for lst in (model.getListOfCompartments(), model.getListOfParameters(), model.getListOfReactions(),
                model.getListOfSpecies()):
        for e in lst:
            e.unsetName()
    return libsbml.writeSBMLToString(doc)


class _Columns:
    """The COPASI output columns needed for a list of SED2 variables, and how to combine them."""

    def __init__(self, model: SbmlModel):
        import libsbml

        self.model = model
        self.sbml = libsbml.readSBMLFromString(model.text).getModel()
        self.names: list = []        # COPASI output selection names, without 'Time'
        self.recipes: dict = {}      # variable -> ("direct", name) | ("amount", conc name, volume name)

    def _need(self, name: str) -> str:
        if name not in self.names:
            self.names.append(name)
        return name

    def add(self, variable: str) -> None:
        if variable in self.recipes:
            return
        if variable == "time":
            self.recipes[variable] = ("time",)
            return
        kind = self.model.kind_of(variable)
        if kind == "species_concentration":
            self.recipes[variable] = ("direct", self._need(f"[{variable}]"))
        elif kind == "species_amount":
            comp = self.sbml.getSpecies(variable).getCompartment()
            self.recipes[variable] = ("amount", self._need(f"[{variable}]"), self._need(f"Compartments[{comp}]"))
        elif kind == "compartment":
            self.recipes[variable] = ("direct", self._need(f"Compartments[{variable}]"))
        elif kind == "parameter":
            self.recipes[variable] = ("direct", self._need(f"Values[{variable}]"))
        elif kind == "reaction":
            self.recipes[variable] = ("direct", self._need(f"({variable}).Flux"))
        else:
            raise DataError(f"the model has no species, compartment, parameter or reaction {variable!r}")

    def value(self, frame, variable: str) -> np.ndarray:
        recipe = self.recipes[variable]
        if recipe[0] == "time":
            return frame["Time"].to_numpy(dtype=float)
        if recipe[0] == "direct":
            return frame[recipe[1]].to_numpy(dtype=float)
        return frame[recipe[1]].to_numpy(dtype=float) * frame[recipe[2]].to_numpy(dtype=float)


class CopasiBackend(Backend):
    name = "copasi"

    def _time_course(self, model: SbmlModel, tc: TimeCourse) -> TimeCourseResult:
        import basico

        try:
            solver, _ = kisao.solver_for("copasi", tc.algorithm)
        except ValueError as e:
            raise DataError(str(e)) from e
        kwargs = {"method": solver, "r_tol": kisao.DEFAULT_RELATIVE_TOLERANCE, "a_tol": kisao.DEFAULT_ABSOLUTE_TOLERANCE}
        for name, value in tc.settings.items():
            if name not in _SETTING_NAMES:
                raise DataError(f"COPASI's {solver} method cannot honor {name}")
            kwargs[_SETTING_NAMES[name]] = value

        cols = _Columns(model)
        cols.add("time")
        for v in tc.output_variables:
            cols.add(v)
        for v in model.state_variables():
            cols.add(v)

        if tc.points is not None:
            points = [float(p) for p in tc.points]
            if any(b < a for a, b in zip(points, points[1:])):
                raise DataError("the output points must not decrease")
            start = tc.start if tc.start is not None else (points[0] if points else 0.0)
            if points and points[0] < start:
                raise DataError(f"the first output point {points[0]} is before the start {start}")
            times = points if points and points[0] == start else [start] + points
            drop_first = times is not points
        elif tc.span is not None:
            a, b = float(tc.span[0]), float(tc.span[1])
            if tc.start not in (None, 0.0) and tc.start != a:
                raise DataError("independentVariableInit must equal the span's start")
            start, times, drop_first = a, None, False
        else:
            start = float(tc.start or 0.0)
            times, drop_first = [start, start + float(tc.step)], False

        before = logging.getLogger("basico").level
        logging.getLogger("basico").setLevel(logging.CRITICAL)
        dm = basico.load_model_from_string(_without_names(model.text))
        try:
            import COPASI

            cmodel = dm.getModel()
            cmodel.setInitialTime(start)
            cmodel.compileIfNecessary()
            cmodel.updateInitialValues(COPASI.CCore.Framework_Concentration)  # makes the new initial time effective
            if times is not None:
                frame = basico.run_time_course_with_output(
                    output_selection=["Time"] + cols.names, values=times, use_initial_values=True,
                    update_model=False, **kwargs)
            else:
                frame = basico.run_time_course_with_output(
                    output_selection=["Time"] + cols.names, start_time=a, duration=b - a, automatic=True,
                    use_values=False, use_initial_values=True, update_model=False, **kwargs)
        finally:
            basico.remove_datamodel(dm)
            logging.getLogger("basico").setLevel(before)
        if frame is None or len(frame) == 0:
            raise DataError("COPASI could not run the time course")
        if times is not None and len(times) == 1:  # a lone point at the start: COPASI also writes a second row
            frame = frame.iloc[:1]
        if times is not None and len(frame) != len(times):
            raise DataError(f"COPASI returned {len(frame)} rows for {len(times)} output points")
        if drop_first:
            frame = frame.iloc[1:]
        t = cols.value(frame, "time")
        values = (np.column_stack([cols.value(frame, v) for v in tc.output_variables])
                  if tc.output_variables else np.zeros((len(frame), 0)))
        if tc.step is not None:
            t, values = t[-1:], values[-1:]
        end_state = {v: float(cols.value(frame, v)[-1]) for v in model.state_variables()}
        return TimeCourseResult(t, values, end_state)


    # ------------------------------------------------------------------ steady state and Jacobian

    @staticmethod
    def _value(basico, dm, cols: _Columns, variable: str) -> float:
        recipe = cols.recipes[variable]
        if recipe[0] == "direct":
            return float(basico.get_value(recipe[1], model=dm))
        return float(basico.get_value(recipe[1], model=dm)) * float(basico.get_value(recipe[2], model=dm))

    def _steady_state(self, model: SbmlModel, request: SteadyState) -> SteadyStateResult:
        import basico

        problem = kisao.steady_state_problem("copasi", request.algorithm)
        if problem:
            raise DataError(problem)
        cols = _Columns(model)
        for v in list(request.output_variables) + model.state_variables():
            cols.add(v)
        before = logging.getLogger("basico").level
        logging.getLogger("basico").setLevel(logging.CRITICAL)
        dm = basico.load_model_from_string(_without_names(model.text))
        try:
            settings = {"method": {"Resolution": COPASI_STEADY_STATE_RESOLUTION, "Accept Negative Concentrations": True}}
            status = basico.run_steadystate(model=dm, settings=settings)
            if status not in (1, 2):
                raise DataError("COPASI did not find a steady state")
            values = np.array([self._value(basico, dm, cols, v) for v in request.output_variables], dtype=float)
            end_state = {v: self._value(basico, dm, cols, v) for v in model.state_variables()}
        finally:
            basico.remove_datamodel(dm)
            logging.getLogger("basico").setLevel(before)
        return SteadyStateResult(values, end_state)

    def _jacobian(self, model: SbmlModel, reduced: bool) -> JacobianResult:
        import basico
        import COPASI

        before = logging.getLogger("basico").level
        logging.getLogger("basico").setLevel(logging.CRITICAL)
        dm = basico.load_model_from_string(_without_names(model.text))
        try:
            cmodel = dm.getModel()
            cmodel.applyInitialValues()
            template = cmodel.getStateTemplate()
            # the matrix is in COPASI's state order (independent variables, then dependent ones), which is not the
            # model's species order: name its rows and columns from the state template
            names = [template.getIndependent(i).getObjectName() for i in range(template.getNumIndependent())]
            if not reduced:
                names += [template.getDependent(i).getObjectName() for i in range(template.getNumDependent())]
            floating = set(model.floating_species())
            for name in names:
                # COPASI differentiates by relative steps, so a variable whose value is 0 gets a derivative of 0
                if name in floating and float(basico.get_value(f"[{name}]", model=dm)) == 0.0:
                    raise DataError(f"COPASI cannot differentiate with respect to {name!r}: its value is 0")
            jac = COPASI.FloatMatrix()
            cmodel.getMathContainer().calculateJacobian(jac, COPASI_JACOBIAN_FACTOR, bool(reduced), False)
            n = len(names)
            if jac.numRows() != n or jac.numCols() != n:
                raise DataError(f"COPASI returned a {jac.numRows()}x{jac.numCols()} Jacobian for {n} variables")
            matrix = np.array([[jac.get(i, j) for j in range(n)] for i in range(n)], dtype=float)
        finally:
            basico.remove_datamodel(dm)
            logging.getLogger("basico").setLevel(before)
        return JacobianResult(names, matrix, "amount")


def create() -> CopasiBackend:
    return CopasiBackend()
