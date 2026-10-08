"""Models for generated scripts.

A model value is an `SbmlModel`: the text of an SBML document whose initial values are the model's current state.
Everything that changes a model (ModelChange, the end state a simulation hands on as `.model`) returns a new
SbmlModel; the originals are never modified.  Backends (runtime/backends) turn the SBML text into a simulator's own
model when they run it.

Identifier semantics follow SBML: the id of a species means its concentration, or its amount if the species has
`hasOnlySubstanceUnits`; the id of a compartment its size; of a parameter its value; of a reaction its flux.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

from .annotated import DataError

SBML_LANGUAGE_PREFIX = "urn:sedml:language:sbml"

# model element types understood by ModelElementList, in the order they are listed
ELEMENT_TYPES = ("functionDefinition", "unitDefinition", "compartment", "species", "parameter", "reaction", "event")


def _libsbml():
    try:
        import libsbml
    except ImportError as e:  # pragma: no cover
        raise DataError("python-libsbml is required to work with SBML models") from e
    return libsbml


def _lists(model):
    return {
        "functionDefinition": model.getListOfFunctionDefinitions(),
        "unitDefinition": model.getListOfUnitDefinitions(),
        "compartment": model.getListOfCompartments(),
        "species": model.getListOfSpecies(),
        "parameter": model.getListOfParameters(),
        "reaction": model.getListOfReactions(),
        "event": model.getListOfEvents(),
    }


class SbmlModel:
    def __init__(self, text: str, source: str = "", time: float = 0.0):
        self.text = text
        self.source = source
        self.time = float(time)   # the model's time: where the last time course ended (0 for a model never run)

    # ------------------------------------------------------------------ loading

    @classmethod
    def load(cls, path: str, language: str) -> "SbmlModel":
        if not language.startswith(SBML_LANGUAGE_PREFIX):
            raise DataError(f"model language {language!r} is not supported (only SBML)")
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            raise DataError(f"cannot read the model file {path}: {e}") from e
        model = cls(text, path)
        model._document()  # checks that it parses
        return model

    def _document(self):
        libsbml = _libsbml()
        doc = libsbml.readSBMLFromString(self.text)
        if doc.getNumErrors(libsbml.LIBSBML_SEV_FATAL) or doc.getNumErrors(libsbml.LIBSBML_SEV_ERROR) and doc.getModel() is None:
            raise DataError(f"cannot read the SBML in {self.source or 'the model'}: {doc.getErrorLog().toString()}")
        if doc.getModel() is None:
            raise DataError(f"{self.source or 'the model'} contains no SBML model")
        return doc

    def _edited(self, edit) -> "SbmlModel":
        libsbml = _libsbml()
        doc = self._document()
        edit(doc.getModel())
        return SbmlModel(libsbml.writeSBMLToString(doc), self.source, self.time)

    # ------------------------------------------------------------------ inspection

    def element_ids(self, include_elements: Optional[Sequence[str]] = None, include_types: Optional[Sequence[str]] = None,
                    exclude_elements: Optional[Sequence[str]] = None,
                    exclude_types: Optional[Sequence[str]] = None) -> list:
        """ModelElementList: ids of the elements selected by the four filters, in model order.  With no include
        filter every element is included; an element in both an include and an exclude filter is excluded."""
        model = self._document().getModel()
        lists = _lists(model)
        ordered = [(t, e.getId()) for t in ELEMENT_TYPES for e in lists[t] if e.getId()]
        known = {i for _, i in ordered}
        for t in list(include_types or []) + list(exclude_types or []):
            if t not in ELEMENT_TYPES:
                raise DataError(f"unknown SBML element type {t!r}; known types: {', '.join(ELEMENT_TYPES)}")
        for i in list(include_elements or []) + list(exclude_elements or []):
            if i not in known:
                raise DataError(f"the model has no element {i!r}")
        if include_elements is None and include_types is None:
            chosen = {i for _, i in ordered}
        else:
            chosen = set(include_elements or []) | {i for t, i in ordered if t in (include_types or [])}
        chosen -= set(exclude_elements or [])
        chosen -= {i for t, i in ordered if t in (exclude_types or [])}
        return [i for _, i in ordered if i in chosen]

    def kind_of(self, element_id: str) -> str:
        """'species_concentration', 'species_amount', 'compartment', 'parameter', 'reaction', 'stoichiometry' (the id
        of a species reference) or 'unknown'."""
        model = self._document().getModel()
        sp = model.getSpecies(element_id)
        if sp is not None:
            return "species_amount" if sp.getHasOnlySubstanceUnits() else "species_concentration"
        if model.getCompartment(element_id) is not None:
            return "compartment"
        if model.getParameter(element_id) is not None:
            return "parameter"
        if model.getReaction(element_id) is not None:
            return "reaction"
        for reaction in model.getListOfReactions():
            for ref in list(reaction.getListOfReactants()) + list(reaction.getListOfProducts()):
                if ref.isSetId() and ref.getId() == element_id:
                    return "stoichiometry"
        return "unknown"

    def state_variables(self) -> list:
        """Ids whose value changes during a simulation (not constant, not set by an assignment rule)."""
        model = self._document().getModel()
        assigned = {r.getVariable() for r in model.getListOfRules() if r.isAssignment()}
        out = []
        for sp in model.getListOfSpecies():
            if not sp.getConstant() and sp.getId() not in assigned:
                out.append(sp.getId())
        for c in model.getListOfCompartments():
            if not c.getConstant() and c.getId() not in assigned:
                out.append(c.getId())
        for p in model.getListOfParameters():
            if not p.getConstant() and p.getId() not in assigned:
                out.append(p.getId())
        return out

    def floating_species(self) -> list:
        """Ids of the species that are not boundary species, in the model's order (the Jacobian's row order)."""
        model = self._document().getModel()
        return [sp.getId() for sp in model.getListOfSpecies() if not sp.getBoundaryCondition()]

    def jacobian_scales(self, species: Sequence[str], native: str) -> dict:
        """For each species, f with (the species' SED2 variable) = f * (the backend's variable), where the backend's
        variable is the species' concentration (native='concentration') or amount (native='amount').  The SED2
        variable is the concentration, or the amount if the species has hasOnlySubstanceUnits.  Needs constant
        compartment sizes."""
        model = self._document().getModel()
        out = {}
        for sid in species:
            sp = model.getSpecies(sid)
            comp = model.getCompartment(sp.getCompartment())
            if not comp.getConstant() or model.getRuleByVariable(comp.getId()) is not None:
                raise DataError(f"the Jacobian needs constant compartment sizes, but {comp.getId()!r} varies")
            size = comp.getSize() if comp.isSetSize() else float("nan")
            if model.getInitialAssignment(comp.getId()) is not None or not size > 0:
                raise DataError(f"cannot find the size of compartment {comp.getId()!r} to scale the Jacobian")
            only = sp.getHasOnlySubstanceUnits()
            if native == "concentration":
                out[sid] = size if only else 1.0
            else:
                out[sid] = 1.0 if only else 1.0 / size
        return out

    # ------------------------------------------------------------------ changes (each returns a new model)

    def with_values(self, values: dict) -> "SbmlModel":
        """Set the initial value of each id (an assignment replaces the element's initial assignment, if any).
        The keys `<species>.boundary` and `<species>.constant` set those flags (value 0 or 1)."""
        def edit(model):
            for key, value in values.items():
                _set_one(model, key, value)
        return self._edited(edit)

    def with_state(self, state: dict, time: Optional[float] = None) -> "SbmlModel":
        """The model with the given values (an end state) as its initial values, and `time` (if given) as its time.
        Ids the model does not have, or that are computed by assignment rules, are ignored."""
        def edit(model):
            assigned = {r.getVariable() for r in model.getListOfRules() if r.isAssignment()}
            for key, value in state.items():
                if key in assigned:
                    continue
                _set_one(model, key, value, strict=False)
        out = self._edited(edit)
        if time is not None:
            out.time = float(time)
        return out

    # ------------------------------------------------------------------ values of elements

    def index(self, brackets) -> "AnnotatedData":
        """`#tasks:id.model['S1']`: the current value of one element, by its SBML id (model_formats/SBML/labels.md).
        The value of a species is its concentration, or its amount if it has hasOnlySubstanceUnits; of a
        compartment its size; of a parameter its value; of a reaction its flux.  Only one label in one bracket is
        defined; a numerical index is not valid for SBML (SBML-0003).

        The value is read from the model's state (its values, plus its time) with libroadrunner, whichever simulator
        produced that state, so that anything the model computes (assignment rules, kinetic laws) is available."""
        from .annotated import AnnotatedData
        from .backends.roadrunner_backend import selector

        brackets = list(brackets)
        if brackets and not isinstance(brackets[0], list):
            brackets = [brackets]
        if len(brackets) != 1 or len(brackets[0]) != 1:
            raise DataError("a model can be indexed by one label only, such as .model['S1']")
        kind, label = brackets[0][0]
        if kind != "label":
            raise DataError("SBML models cannot be indexed numerically (SBML-0003); use the id of an element")
        if self.kind_of(label) == "unknown":
            raise DataError(f"the model has no species, compartment, global parameter or reaction with the id {label!r} "
                            "(SBML-0001; a local parameter cannot be named, SBML-0002)")
        import roadrunner

        rr = roadrunner.RoadRunner(self.text)
        rr.model.setTime(self.time)
        return AnnotatedData(float(rr[selector(self, label)]))

    def without(self, element_ids: Iterable[str]) -> "SbmlModel":
        def edit(model):
            for i in element_ids:
                removed = False
                for t, lst in _lists(model).items():
                    if lst.get(i) is not None:
                        lst.remove(i)
                        removed = True
                        break
                if not removed:
                    raise DataError(f"the model has no element {i!r} to remove")
        return self._edited(edit)


def _set_one(model, key: str, value: Any, strict: bool = True) -> None:
    value = float(value)
    base, _, flag = key.partition(".")
    if flag:
        sp = model.getSpecies(base)
        if sp is None or flag not in ("boundary", "constant"):
            raise DataError(f"cannot set {key!r}: only <species>.boundary and <species>.constant are understood")
        (sp.setBoundaryCondition if flag == "boundary" else sp.setConstant)(bool(value))
        return
    target = model.getSpecies(key)
    if target is not None:
        if target.getHasOnlySubstanceUnits():
            target.setInitialAmount(value)
        else:
            target.setInitialConcentration(value)
    else:
        target = model.getCompartment(key)
        if target is not None:
            target.setSize(value)
        else:
            target = model.getParameter(key)
            if target is None:
                if strict:
                    raise DataError(f"the model has no species, compartment or parameter {key!r}")
                return
            target.setValue(value)
    if model.getInitialAssignment(key) is not None:
        model.removeInitialAssignment(key)
