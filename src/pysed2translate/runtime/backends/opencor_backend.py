"""OpenCOR backend (libopencor).  The SBML model is converted to CellML with sbml2cellml, which keeps SBML's
meaning of each id (a species is a concentration unless it has `hasOnlySubstanceUnits`).

libopencor runs uniform time courses only.  Output points that are evenly spaced are one run; other points are
reached segment by segment, each segment starting from the previous end state."""
from __future__ import annotations

import os
import re
import tempfile

import numpy as np

from ... import kisao
from ..annotated import DataError
from ..model import SbmlModel
from .base import Backend, TimeCourse, TimeCourseResult

_CVODE_SETTINGS = {"relativeTolerance": "relative_tolerance", "absoluteTolerance": "absolute_tolerance",
                   "maxNumberOfSteps": "maximum_number_of_steps", "maxInternalStepSize": "maximum_step"}
_FIXED_STEP = {"forward_euler", "rk4", "heun", "rk2"}


def _is_uniform(points: list) -> bool:
    if len(points) < 3:
        return True
    d = np.diff(points)
    return bool(np.all(d > 0) and np.allclose(d, d[0], rtol=1e-12, atol=0.0))


class _Run:
    """One CellML model, ready to run uniform time courses."""

    def __init__(self, cellml_text: str, solver: str, options: dict, settings: dict, step: float):
        import libopencor as oc

        self.oc = oc
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "model.cellml")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(cellml_text)
        self.doc = oc.SedDocument(oc.File(self.path))
        if self.doc.has_issues and self.doc.has_errors:
            raise DataError("OpenCOR cannot use the converted model: " + "; ".join(str(e) for e in self.doc.errors))
        self.sim = self.doc.simulations[0]
        self._configure(solver, options, settings, step)

    def _configure(self, solver: str, options: dict, settings: dict, step: float) -> None:
        oc, sim = self.oc, self.sim
        classes = {"cvode": oc.SolverCvode, "forward_euler": oc.SolverForwardEuler, "rk4": oc.SolverFourthOrderRungeKutta,
                   "heun": oc.SolverHeun, "rk2": oc.SolverSecondOrderRungeKutta}
        if solver != "cvode":
            sim.ode_solver = classes[solver]()
        s = sim.ode_solver
        if solver == "cvode":
            method = options.get("integration_method")
            if "useStiffSolver" in settings:
                method = "Bdf" if settings["useStiffSolver"] else "AdamsMoulton"
            if method:
                s.integration_method = getattr(oc.SolverCvode.IntegrationMethod, method)
            s.relative_tolerance = settings.get("relativeTolerance", kisao.DEFAULT_RELATIVE_TOLERANCE)
            s.absolute_tolerance = settings.get("absoluteTolerance", kisao.DEFAULT_ABSOLUTE_TOLERANCE)
            for sed2, attr in _CVODE_SETTINGS.items():
                if sed2 in settings and sed2 not in ("relativeTolerance", "absoluteTolerance"):
                    setattr(s, attr, settings[sed2])
        else:
            s.step = settings.get("initialStepSize", step)

    def run(self, initial: float, first: float, last: float, steps: int):
        sim = self.sim
        sim.initial_time, sim.output_start_time, sim.output_end_time, sim.number_of_steps = initial, first, last, steps
        inst = self.doc.instantiate()
        inst.run()
        if inst.has_errors:
            raise DataError("OpenCOR could not run the time course: " + "; ".join(str(e) for e in inst.errors))
        task = inst.tasks[0]
        columns, states = {}, []
        for kind in ("state", "algebraic_variable", "constant", "computed_constant"):
            for i in range(getattr(task, f"{kind}_count")):
                name = getattr(task, f"{kind}_name")(i).split("/")[-1]
                columns[name] = np.asarray(getattr(task, kind)(i), dtype=float)
                if kind == "state":
                    states.append(name)
        return np.asarray(task.voi, dtype=float), columns, states

    def close(self) -> None:
        self.dir.cleanup()


def _cellml_with_initial_values(text: str, values: dict) -> str:
    """The CellML text with new initial_value attributes for the named variables."""
    def repl(match):
        tag = match.group(0)
        name = re.search(r'\bname="([^"]+)"', tag).group(1)
        if name in values and "initial_value=" in tag:
            tag = re.sub(r'initial_value="[^"]*"', f'initial_value="{values[name]!r}"', tag)
        return tag
    return re.sub(r"<variable\b[^>]*>", repl, text)


class OpenCorBackend(Backend):
    name = "opencor"

    def _time_course(self, model: SbmlModel, tc: TimeCourse) -> TimeCourseResult:
        import sbml2cellml

        if tc.span is not None:
            raise DataError("libopencor runs uniform time courses only, so it cannot choose its own output points")
        try:
            solver, options = kisao.solver_for("opencor", tc.algorithm)
        except ValueError as e:
            raise DataError(str(e)) from e
        allowed = kisao.SETTINGS_SUPPORTED["opencor"][solver]
        for name in tc.settings:
            if name not in allowed:
                raise DataError(f"OpenCOR's {solver} solver cannot honor {name}")

        if tc.points is not None:
            points = [float(p) for p in tc.points]
            if any(b < a for a, b in zip(points, points[1:])):
                raise DataError("the output points must not decrease")
            start = tc.start if tc.start is not None else (points[0] if points else 0.0)
            if points and points[0] < start:
                raise DataError(f"the first output point {points[0]} is before the start {start}")
        else:
            start = float(tc.start or 0.0)
            points = [start, start + float(tc.step)]
        if not points:
            raise DataError("no output points")

        with tempfile.TemporaryDirectory() as d:
            sbml_path, cellml_path = os.path.join(d, "model.xml"), os.path.join(d, "model.cellml")
            with open(sbml_path, "w", encoding="utf-8") as f:
                f.write(model.text)
            try:
                sbml2cellml.convert_sbml2cellml(sbml_path, cellml_path)
            except Exception as e:  # noqa: BLE001
                raise DataError(f"the model cannot be converted to CellML for OpenCOR: {e}") from e
            with open(cellml_path, "r", encoding="utf-8") as f:
                cellml = f.read()

        spacing = min(np.diff(points)) if len(points) > 1 else 1.0
        step = spacing / 100.0 if spacing > 0 else 1e-3
        wanted = list(tc.output_variables)
        times: list = []
        rows: list = []
        end_values: dict = {}
        state_names: list = []

        def collect(t, cols, keep):
            for k in keep:
                times.append(t[k])
                rows.append([cols[v][k] if v != "time" else t[k] for v in wanted])

        def read(cols, name):
            if name not in cols:
                raise DataError(f"the model has no variable {name!r} that OpenCOR can report")
            return cols[name]

        if _is_uniform(points):
            run = _Run(cellml, solver, options, tc.settings, step)
            try:
                steps = len(points) - 1
                if steps == 0:  # one point: the initial state
                    t, cols, state_names = run.run(start, start, start + 1e-9 + abs(start) * 1e-12, 1)
                    keep = [0]
                else:
                    t, cols, state_names = run.run(start, points[0], points[-1], steps)
                    keep = range(len(t))
                for v in wanted:
                    if v != "time":
                        read(cols, v)
                collect(t, cols, keep)
                end_values = {n: float(cols[n][keep[-1]]) for n in cols}
            finally:
                run.close()
        else:
            current, now = cellml, start
            if points[0] > start:
                run = _Run(current, solver, options, tc.settings, step)
                try:
                    t, cols, state_names = run.run(now, now, points[0], 1)
                finally:
                    run.close()
                current = _cellml_with_initial_values(current, {n: float(cols[n][-1]) for n in state_names})
                now = points[0]
            first = True
            for target in points:
                if first:
                    run = _Run(current, solver, options, tc.settings, step)
                    try:
                        t, cols, state_names = run.run(now, now, now + 1e-9 + abs(now) * 1e-12, 1)
                    finally:
                        run.close()
                    for v in wanted:
                        if v != "time":
                            read(cols, v)
                    collect(t, cols, [0])
                    end_values = {n: float(cols[n][0]) for n in cols}
                    first = False
                    continue
                run = _Run(current, solver, options, tc.settings, step)
                try:
                    t, cols, state_names = run.run(now, now, target, 1)
                finally:
                    run.close()
                collect(t, cols, [len(t) - 1])
                end_values = {n: float(cols[n][-1]) for n in cols}
                current = _cellml_with_initial_values(current, {n: end_values[n] for n in state_names})
                now = target

        values = np.asarray(rows, dtype=float).reshape(len(times), len(wanted))
        if tc.step is not None:
            times, values = times[-1:], values[-1:]
        end_state = {v: end_values[v] for v in model.state_variables() if v in end_values}
        return TimeCourseResult(np.asarray(times, dtype=float), values, end_state)


def create() -> OpenCorBackend:
    return OpenCorBackend()
