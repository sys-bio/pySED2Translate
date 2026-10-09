"""COBRApy backend: flux balance analysis of SBML models with the FBC package.

The model's objective and flux bounds are those of the SBML file (fbc:listOfObjectives, fbc:lowerFluxBound and
fbc:upperFluxBound, which refer to parameters).  Ids are read as the SBML file gives them (reaction `R_EX_glc__D_e`
stays `R_EX_glc__D_e`; COBRApy's own renaming of the `R_` and `M_` prefixes is switched off).

The variant of the backend names the LP solver: `cobra:glpk` or `cobra:scipy` (the default is COBRApy's own default).
The solution of a linear program is not always unique; a document whose result is to be compared across solvers
must have a unique optimum for the variables it reports.
"""
from __future__ import annotations

import io

import numpy as np

from ... import kisao
from ..annotated import DataError
from ..model import SbmlModel
from .base import Backend, BackendCannotRun, FbaRequest


class CobraBackend(Backend):
    name = "cobra"

    def __init__(self, solver: str = ""):
        self.solver = solver

    @staticmethod
    def _require_fbc(model: SbmlModel) -> None:
        """A flux balance analysis needs the objective and the bounds that the FBC package carries; without them COBRApy
        would quietly optimize nothing."""
        import libsbml

        doc = libsbml.readSBMLFromString(model.text)
        plugin = doc.getModel().getPlugin("fbc") if doc.getModel() is not None else None
        if plugin is None:
            raise BackendCannotRun("the model does not use the SBML FBC package, so it has no objective or flux bounds",
                                   "cobra")
        if plugin.getNumObjectives() == 0:
            raise BackendCannotRun("the model has no objective (fbc:listOfObjectives is empty)", "cobra")

    def _read(self, model: SbmlModel):
        self._require_fbc(model)
        try:
            import cobra
            from cobra.io.sbml import read_sbml_model
        except ImportError as e:
            raise DataError("the cobra backend needs the cobra package (COBRApy)") from e
        try:
            cmodel = read_sbml_model(io.StringIO(model.text), f_replace={})
        except Exception as e:
            raise BackendCannotRun(f"cobra cannot read the model as a constraint-based model: {e}", self.name) from e
        if not len(cmodel.reactions):
            raise BackendCannotRun("the model has no reactions", self.name)
        if self.solver:
            try:
                cmodel.solver = self.solver
            except Exception as e:
                raise DataError(f"cobra cannot use the solver {self.solver!r}: {e}") from e
        return cobra, cmodel

    @staticmethod
    def _model_value(model: SbmlModel, variable: str) -> float:
        """The value a model gives a non-reaction id: a parameter, a compartment size or a species' initial value."""
        import libsbml

        sbml = libsbml.readSBMLFromString(model.text).getModel()
        element = sbml.getParameter(variable) or sbml.getCompartment(variable)
        if element is not None:
            return element.getValue() if hasattr(element, "getValue") else element.getSize()
        species = sbml.getSpecies(variable)
        if species is not None:
            if species.isSetInitialConcentration() and not species.getHasOnlySubstanceUnits():
                return species.getInitialConcentration()
            if species.isSetInitialAmount():
                return species.getInitialAmount()
        raise DataError(f"the model has no reaction, parameter, compartment or species {variable!r}")

    def _fba(self, model: SbmlModel, request: FbaRequest) -> np.ndarray:
        problem = kisao.fba_problem("cobra", request.algorithm)
        if problem:
            raise DataError(problem)
        _cobra, cmodel = self._read(model)
        solution = cmodel.optimize(raise_error=False)
        if solution.status != "optimal":
            raise DataError(f"the flux balance analysis has no optimum: the solver reports '{solution.status}' "
                            "(the bounds and constraints of the model leave no feasible flux distribution, "
                            "or the objective is unbounded)")
        out = []
        for variable in request.output_variables:
            if variable in cmodel.reactions:
                out.append(solution.fluxes[variable])
            else:
                out.append(self._model_value(model, variable))
        return np.array(out, dtype=float)


def create(variant: str = "") -> CobraBackend:
    return CobraBackend(variant)
