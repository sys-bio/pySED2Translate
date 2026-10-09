"""Providers: who executes a simulation task (process-bigraph.md, section 5).

A *provider* is either the host runtime (`host.rt.backends`, the same code the generated scripts use) or a community wrapper
from the viva-* family (viva-tellurium: libroadrunner; viva-copasi: COPASI).  `--wrappers` chooses:

    strict   (default) a simulation task must be run by a wrapper; a task the wrapper cannot do is refused (exit status 11)
             with the ledger ids of the gaps.  Nothing is silently run elsewhere.
    prefer   a wrapper when it can do the task, else the host runtime; every fallback is reported as a note.
    off      the host runtime only.

Every reason a wrapper cannot do something is a ledger entry (`LEDGER`): `W-n` entries are gaps in the wrappers, with a draft
report in `pbg/upstream/W-n.md` (never filed by an assistant); `L-n` entries are limits of this provider that could be lifted.
The translator never works around a gap: it states the entry and stops (CLAUDE.md, "never hide a problem").
"""
from __future__ import annotations

import posixpath
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from pysed2translate_pbg import host

MODES = ("strict", "prefer", "off")
DEFAULT_MODE = "strict"            # the one default, in one place (rule M9)

# id -> (where, title).  W: a gap in a community package (drafts in pbg/upstream); L: a limit of this provider.
LEDGER = {
    "W-1": ("viva-tellurium", "the UTC and steady-state steps ignore tolerances and seed (and have no other solver settings)"),
    "W-2": ("viva-copasi", "a time course cannot start at a time other than 0"),
    "W-3": ("viva-copasi", "no way to choose the method or tolerances"),
    "W-4": ("viva-copasi", "model_source accepts only a path or URL, not SBML text"),
    "W-5": ("both", "output times must be uniform (n_points); no explicit time vector, no solver-chosen points"),
    "W-6": ("both", "no model input and no end-state model output"),
    "W-7": ("both", "output variables cannot be selected (floating species concentrations only)"),
    "W-8": ("both", "the steady-state steps have no solver settings; no Jacobian step"),
    "W-9": ("vivarium-collective", "no OpenCOR / CellML wrapper"),
    "W-10": ("both", "the UTC steps are not idempotent and take no guard (a repeat cannot hold them)"),
    "W-11": ("vivarium-collective", "no flux balance analysis wrapper"),
    "W-12": ("viva-copasi", "the COPASI steps use schema types that only register_copasi() registers"),
    "W-13": ("viva-copasi / viva-tellurium", "a COPASI step after a Tellurium step in one process crashes the interpreter"),
    "W-14": ("viva-copasi", "a model without species cannot be loaded (get_species returns None)"),
    "L-1": ("provider", "oneStepODESimulation is not mapped to a wrapper"),
    "L-2": ("provider", "a value is known only while running (the wrapper's configuration is fixed when the document is written)"),
    "L-3": ("provider", "the model language is not SBML"),
    "L-4": ("provider", "independentVariableInit differs from the first output point"),
    "L-5": ("provider", "an algorithm other than the default CVODE is not mapped to the Tellurium wrapper"),
}
# entries the translation rules never raise: observations about using the wrappers, or found only while running (W-7 by the
# adapter steps; W-14 is an error inside the wrapper)
NOTES_ONLY = ("W-4", "W-12", "W-14")

FAMILY = {"roadrunner": "tellurium", "copasi": "copasi"}
WRAPPER = {("tellurium", "ode"): "viva_tellurium.processes.TelluriumUTCStep",
           ("tellurium", "steady"): "viva_tellurium.processes.TelluriumSteadyStateStep",
           ("copasi", "ode"): "viva_copasi.processes.CopasiUTCStep",
           ("copasi", "steady"): "viva_copasi.processes.CopasiSteadyStateStep"}
RAW_PORTS = {("tellurium", "ode"): ("time_series", "species_trajectories"),
             ("tellurium", "steady"): ("steady_state_concentrations",),
             ("copasi", "ode"): ("result",),
             ("copasi", "steady"): ("results",)}
SBML_PREFIX = "urn:sedml:language:sbml"
TIME_SYMBOL = "time"


def gap(ident: str, detail: str = ""):
    text = LEDGER[ident][1]
    return (ident, f"{text} ({detail})" if detail else text)


class WrapperRefusal(host.UnsupportedTaskError):
    """Strict mode: the wrappers cannot perform these tasks.  `gaps` is {task id: [(ledger id, text), ...]}."""

    provider_gap = True      # the suite runner: not a statement about the canonical backend

    def __init__(self, backend: str, gaps: dict):
        self.gaps = {k: list(v) for k, v in gaps.items()}
        names = ", ".join(repr(t) for t in self.gaps)
        one = len(self.gaps) == 1
        reason = "; ".join(("" if one else f"task {t!r}: ") + "; ".join(f"{i} {text}" for i, text in g) for t, g in self.gaps.items())
        super().__init__(f"viva wrappers (--wrappers strict, for {backend})", ("task " if one else "tasks ") + names, reason)

    def ids(self) -> list:
        return sorted({i for g in self.gaps.values() for i, _ in g})


class WrapperModelUse(Exception):
    """A reference to the `.model` of a task that a wrapper ran (the wrappers hand on no model: W-6)."""

    def __init__(self, tid: str, reference: str):
        self.tid, self.reference = tid, reference
        super().__init__(f"{reference} refers to the model a wrapper would have to hand on")


@dataclass
class Request:
    """What the builder found out about a simulation task, as plain values (the rules below know nothing of libsed2)."""
    tid: str
    kind: str                           # ode, steady, jacobian, fba
    backend: str                        # the host backend name[:variant] chosen for the task
    mode: str = "points"                # ode: points | span | step
    guarded: bool = False               # inside a repeat
    model_task: Optional[str] = None    # the modelImport task that the model reference names, if it is exactly '#tasks:T.model'
    location: Optional[str] = None
    language: Optional[str] = None
    independent_variable: str = TIME_SYMBOL
    algorithm: Optional[str] = None
    settings: list = field(default_factory=list)       # names of the solver settings the task sets
    init: Optional[float] = None
    points: Optional[list] = None
    points_problem: Optional[str] = None


@dataclass
class Plan:
    family: str
    kind: str
    address: str
    config: dict
    model_task: str
    location: str
    model_file: str
    raw: tuple


def family_of(backend: str) -> Optional[str]:
    return FAMILY.get(backend.split(":")[0])


def _uniform(points: list) -> Optional[str]:
    if len(points) < 2:
        return "a wrapper needs at least two output points"
    p = np.asarray(points, dtype=float)
    d = np.diff(p)
    if not d[0] > 0 or not np.allclose(d, d[0], rtol=1e-9, atol=0.0):
        return "the output points are not evenly spaced and increasing"
    return None


def gaps_for(req: Request, used_family: Optional[str] = None, input_dir: str = "."):
    """(plan or None, [gaps]).  An empty list of gaps means a plan."""
    fam = family_of(req.backend)
    base = req.backend.split(":")[0]
    if fam is None:
        if base == "opencor":
            return None, [gap("W-9")]
        if base == "cobra":
            return None, [gap("W-11")]
        return None, [gap("W-9", f"no wrapper for {base}")]
    gaps: list = []
    if req.kind == "fba":
        return None, [gap("W-11")]
    if req.kind == "jacobian":
        return None, [gap("W-8", "no Jacobian step")]
    if req.guarded:
        gaps.append(gap("W-10", "the task is inside a repeat"))
    if used_family is not None and used_family != fam:
        gaps.append(gap("W-13", f"the document already uses the {used_family} wrapper"))
    if req.model_task is None:
        gaps.append(gap("W-6", "the model is not the plain result of a modelImport task"))
    elif req.language is not None and not req.language.startswith(SBML_PREFIX):
        gaps.append(gap("L-3", req.language))
    if req.kind == "ode":
        _ode_gaps(req, fam, gaps)
    else:
        if req.algorithm is not None:
            gaps.append(gap("W-8", f"algorithm {req.algorithm}"))
    if gaps:
        return None, gaps
    return _plan(req, fam, input_dir), []


def _ode_gaps(req: Request, fam: str, gaps: list) -> None:
    if req.mode == "span":
        gaps.append(gap("W-5", "boundedODESimulation lets the solver choose the output points"))
    elif req.mode == "step":
        gaps.append(gap("L-1"))
    if req.independent_variable != TIME_SYMBOL:
        gaps.append(gap("L-4", f"independent variable {req.independent_variable!r}"))
    if req.algorithm is not None:
        if fam == "copasi":
            gaps.append(gap("W-3", f"algorithm {req.algorithm}"))
        else:
            try:
                solver = host.kisao.solver_for("roadrunner", req.algorithm)
            except ValueError:
                solver = None
            if solver != ("cvode", {}):
                gaps.append(gap("L-5", req.algorithm))
    if req.settings:
        gaps.append(gap("W-3" if fam == "copasi" else "W-1", "settings " + ", ".join(sorted(req.settings))))
    if req.mode != "points":
        return
    if req.points is None:
        gaps.append(gap("L-2", req.points_problem or "the output points"))
        return
    problem = _uniform(req.points)
    if problem:
        gaps.append(gap("W-5", problem))
        return
    if req.init is not None and req.init != req.points[0]:
        gaps.append(gap("L-4", f"init {req.init:g}, first point {req.points[0]:g}"))
    if fam == "copasi" and req.points[0] != 0.0:
        gaps.append(gap("W-2", f"the output starts at {req.points[0]:g}"))


def provider_for(kind: str, backend: str) -> str:
    """Who runs tasks of a kind on a backend under --wrappers strict or prefer: the wrapper's package, or 'runtime' (the host's
    runtime) when there is no wrapper for it (W-8: no Jacobian step; W-9: no OpenCOR; W-11: no FBA)."""
    fam = family_of(backend)
    if fam is None or kind not in ("ode", "steady"):
        return "runtime"
    return {"tellurium": "viva-tellurium", "copasi": "viva-copasi"}[fam]


def model_path(input_dir: str, location: str) -> str:
    """Where the wrapper looks for the model: the location below the input directory the document was translated for."""
    loc = location.replace("\\", "/")
    if posixpath.isabs(loc):
        return loc
    return posixpath.normpath(posixpath.join((input_dir or ".").replace("\\", "/"), loc))


def _plan(req: Request, fam: str, input_dir: str) -> Plan:
    config: dict = {}
    if req.kind == "ode":
        p = req.points
        if fam == "tellurium":
            config = {"start_time": float(p[0]), "end_time": float(p[-1]), "n_points": len(p), "model_format": "sbml"}
        else:
            config = {"time": float(p[-1]), "n_points": len(p)}
    elif fam == "tellurium":
        config = {"model_format": "sbml"}
    else:
        config = {"time": 1.0}        # kept by the step "for symmetry, not used"
    model_file = model_path(input_dir, req.location)
    config[model_file_key(fam)] = model_file
    return Plan(fam, req.kind, WRAPPER[(fam, req.kind)], config, req.model_task, req.location, model_file, RAW_PORTS[(fam, req.kind)])


def model_file_key(family: str) -> str:
    return "model_file" if family == "tellurium" else "model_source"
