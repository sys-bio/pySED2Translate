"""What every simulator backend provides to generated scripts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..annotated import AnnotatedData, DataError
from ..model import SbmlModel


EXIT_CANNOT_RUN = 11   # same as errors.EXIT_UNSUPPORTED: a generated script exits with it when the backend cannot run the model


class BackendCannotRun(Exception):
    """The backend cannot run this model correctly (a feature of the model that the simulator does not support, found
    only when the model is read).  The generated script reports it as a skip (exit status 11), never as a result.
    `backend` names the backend that cannot (default: the script's BACKEND)."""

    def __init__(self, message: str = "", backend: Optional[str] = None):
        super().__init__(message)
        self.backend = backend


@dataclass
class TimeCourse:
    """A request for a time course, already evaluated (no references left).

    Exactly one of `points`, `span` and `step` is set:
      points  explicit output values of the independent variable (ExplicitODESimulation)
      span    (start, end): the solver chooses the output points (BoundedODESimulation)
      step    one output point after advancing the independent variable by `step` (OneStepODESimulation)
    `start` is where the independent variable begins (independentVariableInit, else the first point / span start).
    `settings` holds the solver settings the document gave, by SED2 attribute name (relativeTolerance, ...).
    `algorithm` is the KiSAO term of the working algorithm, if the document named one.
    `independent_variable` is what the backend integrates over ("time"); `label` is the independentVariable attribute as
    the document wrote it (`urn:sedml:symbol:time`), which the specification makes the label of the first column.
    """
    independent_variable: str
    output_variables: list
    start: float = 0.0
    points: Optional[list] = None
    span: Optional[tuple] = None
    step: Optional[float] = None
    settings: dict = field(default_factory=dict)
    algorithm: Optional[str] = None
    label: Optional[str] = None   # the label of the independent variable's column: the attribute as written


@dataclass
class SteadyState:
    """A request for a steady state, already evaluated (no references left).  `algorithm` is the KiSAO term of the
    working algorithm, if the document named one."""
    independent_variable: str
    output_variables: list
    algorithm: Optional[str] = None


@dataclass
class FbaRequest:
    """A request for a flux balance analysis, already evaluated.  `output_variables` are the model ids whose values
    the result holds (reactions give their fluxes).  `algorithm` is the KiSAO term of the working algorithm, if the
    document named one."""
    output_variables: list
    algorithm: Optional[str] = None


@dataclass
class SteadyStateResult:
    values: np.ndarray           # (len(output_variables),)
    end_state: dict              # id -> value for the model's state variables at the steady state


@dataclass
class JacobianResult:
    """A Jacobian as the backend computed it.  `native` says what its variables are: 'concentration' (each species
    is its concentration) or 'amount' (each species is its amount)."""
    species: list
    matrix: np.ndarray
    native: str


@dataclass
class TimeCourseResult:
    times: np.ndarray            # (rows,)
    values: np.ndarray           # (rows, len(output_variables))
    end_state: dict              # id -> value for the model's state variables at the end


class Backend:
    """A simulator.  Subclasses implement `_time_course`; the rest is shared."""
    name = ""

    def _time_course(self, model: SbmlModel, tc: TimeCourse) -> TimeCourseResult:
        raise DataError(f"backend {self.name} cannot run time courses")

    def _steady_state(self, model: SbmlModel, request: SteadyState) -> SteadyStateResult:
        raise DataError(f"backend {self.name} cannot compute steady states")

    def _jacobian(self, model: SbmlModel, reduced: bool) -> JacobianResult:
        raise DataError(f"backend {self.name} cannot compute Jacobians")

    def _fba(self, model: SbmlModel, request: FbaRequest) -> np.ndarray:
        raise DataError(f"backend {self.name} cannot do flux balance analysis")

    def fba(self, model: SbmlModel, request: FbaRequest):
        """Returns (AnnotatedData of the output variables at the optimum, the model).  The FBA changes nothing in the
        model, so the model handed on as `.model` is the one that went in (docs/capability-table.md)."""
        values = np.asarray(self._fba(model, request), dtype=float)
        return AnnotatedData(values, [list(request.output_variables)], [""]), model

    def steady_state(self, model: SbmlModel, request: SteadyState):
        """Returns (AnnotatedData of the output variables at the steady state, the model at the steady state)."""
        if request.independent_variable != "time":
            raise DataError(f"independent variable {request.independent_variable!r} is not supported (only 'time')")
        if "time" in request.output_variables:
            raise DataError("'time' has no value at a steady state")
        result = self._steady_state(model, request)
        data = AnnotatedData(result.values, [list(request.output_variables)], [""])
        return data, model.with_state(result.end_state)

    def jacobian(self, model: SbmlModel, reduced: bool = False) -> AnnotatedData:
        """The Jacobian at the model's current state: d(dx_i/dt)/dx_j for the model's floating species x (an id
        means a concentration, or an amount if the species has hasOnlySubstanceUnits), rows and columns in the
        model's species order.  The reduced Jacobian keeps only the independent species."""
        found = self._jacobian(model, reduced)
        order = {s: i for i, s in enumerate(model.floating_species())}
        keep = [k for k, s in enumerate(found.species) if s in order]
        missing = set(order) - {found.species[k] for k in keep}
        if missing and not reduced:
            raise DataError(f"{self.name} did not report the Jacobian for the species {sorted(missing)}")
        keep.sort(key=lambda k: order[found.species[k]])
        labels = [found.species[k] for k in keep]
        scale = model.jacobian_scales(labels, found.native)
        f = np.array([scale[s] for s in labels])
        matrix = np.asarray(found.matrix, dtype=float)[np.ix_(keep, keep)] * f[:, None] / f[None, :] + 0.0  # + 0.0: no negative zeros
        return AnnotatedData(matrix, [labels, labels], ["", ""])

    def time_course(self, model: SbmlModel, tc: TimeCourse):
        """Returns (AnnotatedData, end-of-run model).  Rows by columns for points and span (the first column is the
        independent variable); one row of the output variables for a step."""
        if tc.independent_variable != "time":
            raise DataError(f"independent variable {tc.independent_variable!r} is not supported (only 'time')")
        result = self._time_course(model, tc)
        end_model = model.with_state(result.end_state, time=float(result.times[-1]) if len(result.times) else None)
        if tc.step is not None:
            data = AnnotatedData(result.values[-1], [list(tc.output_variables)], [""])
        else:
            table = np.column_stack([result.times, result.values]) if result.values.size else result.times[:, None]
            data = AnnotatedData(table, [None, [tc.label or tc.independent_variable] + list(tc.output_variables)], ["", ""])
        return data, end_model
