"""KiSAO algorithm terms and solver settings, per backend.

A simulation's `workingAlgorithms` may name a KiSAO term (`KISAO:0000019`).  This module says which solver of each
backend implements each term, and which of the document's solver settings each backend can honor.  The capability
check (capabilities/checks.py) uses it to skip a task the backend cannot run exactly as written; the backends
(runtime/backends) use the same data to configure their solver.

Sources: roadrunner's mapping is tellurium's own (tellurium/sedml/tesedml.py); the OpenCOR ids were read from
libopencor (Solver.id); COPASI's are from the COPASI/basico method names.  Entries marked `verified: False` have
not yet been confirmed by running that backend (see docs/capability-table.md).
"""
from __future__ import annotations

import re
from typing import Optional

GENERIC_ODE_SOLVER = 694   # KISAO:0000694 'ODE solver': any solver; the backend uses its default
GENERIC_STEADY_STATE = 407  # KISAO:0000407 'steady-state root-finding method'

# term number -> (solver name, options) for each backend.  Options are for the backend module to interpret.
ODE_ALGORITHMS = {
    "roadrunner": {
        694: ("cvode", {}), 19: ("cvode", {}), 433: ("cvode", {}),
        288: ("cvode", {"stiff": True}),    # BDF
        280: ("cvode", {"stiff": False}),   # Adams-Moulton
        32: ("rk4", {}),
    },
    "copasi": {
        694: ("lsoda", {}), 88: ("lsoda", {}),
        304: ("radau5", {}),
    },
    "opencor": {
        694: ("cvode", {}), 19: ("cvode", {}), 433: ("cvode", {}),
        288: ("cvode", {"integration_method": "Bdf"}),
        280: ("cvode", {"integration_method": "AdamsMoulton"}),
        30: ("forward_euler", {}), 261: ("forward_euler", {}),
        32: ("rk4", {}),
        301: ("heun", {}),
        381: ("rk2", {}),
    },
}

# steady-state root finders: term number -> solver name.  Only the generic term is mapped: each backend uses its own
# default method (roadrunner: NLEQ2; COPASI: its enhanced Newton method).  OpenCOR has none that can be called (below).
STEADY_STATE_ALGORITHMS = {
    "roadrunner": {GENERIC_STEADY_STATE: "nleq2"},
    "copasi": {GENERIC_STEADY_STATE: "enhanced_newton"},
    "opencor": {},
}

# why some well-known terms are not available on a backend
ALGORITHM_NOTES = {
    "roadrunner": {30: "roadrunner 2.10 has no Euler integrator", 261: "roadrunner 2.10 has no Euler integrator",
                   88: "roadrunner has no LSODA solver",
                   **{n: "roadrunner 2.10's rk45 integrator returns wrong values at fixed output points"
                      for n in (86, 87, 321, 434, 435)}},
    "copasi": {19: "COPASI has no CVODE solver", 32: "COPASI has no fixed-step Runge-Kutta solver",
               30: "COPASI has no Euler solver"},
    "opencor": {88: "libopencor has no LSODA solver"},
}

# SED2 solver attributes (AbstractODESimulation) each backend's solver honors
_RR_CVODE = {"relativeTolerance", "absoluteTolerance", "initialStepSize", "maxNumberOfSteps", "maxInternalStepSize",
             "minInternalStepSize", "useStiffSolver", "maxBDForder", "maxAdamsOrder", "variableStepSize", "maxOutputRows"}
SETTINGS_SUPPORTED = {
    "roadrunner": {"cvode": _RR_CVODE,
                   "rk4": set()},
    "copasi": {"lsoda": {"relativeTolerance", "absoluteTolerance", "maxNumberOfSteps"},
               "radau5": {"relativeTolerance", "absoluteTolerance", "maxNumberOfSteps"}},
    "opencor": {"cvode": {"relativeTolerance", "absoluteTolerance", "maxNumberOfSteps", "maxInternalStepSize",
                          "useStiffSolver"},
                "forward_euler": {"initialStepSize"}, "rk4": {"initialStepSize"}, "heun": {"initialStepSize"},
                "rk2": {"initialStepSize"}},
}
# solvers that cannot choose their own output points (no BoundedODESimulation)
FIXED_STEP_SOLVERS = {"roadrunner": {"rk4"}, "copasi": set(), "opencor": {"forward_euler", "rk4", "heun", "rk2"}}
ALL_SETTINGS = ("relativeTolerance", "absoluteTolerance", "absoluteToleranceVector", "absoluteToleranceAdjustmentFactor",
                "toleranceForRootFinder", "initialStepSize", "maxNumberOfSteps", "maxInternalSteps", "maxInternalStepSize",
                "minInternalStepSize", "forcePhysicalCorrectness", "integrateReducedModel", "useReducedModel",
                "useStiffSolver", "maxBDForder", "maxAdamsOrder", "variableStepSize", "maxOutputRows")

# tolerances used when the document gives none (tight enough for the suite's comparisons; see docs/environment-notes.md)
DEFAULT_ABSOLUTE_TOLERANCE = 1e-12
DEFAULT_RELATIVE_TOLERANCE = 1e-10

_TERM = re.compile(r"^KISAO[:_](\d{7})$", re.IGNORECASE)


def term_number(text: str) -> Optional[int]:
    """'KISAO:0000019' -> 19; None if the text is not a KiSAO term."""
    m = _TERM.match(text.strip()) if isinstance(text, str) else None
    return int(m.group(1)) if m else None


def ode_solver(backend: str, term: Optional[int]):
    """(solver, options) a backend uses for a KiSAO term (None means 'no algorithm named': the generic solver)."""
    return ODE_ALGORITHMS[backend].get(GENERIC_ODE_SOLVER if term is None else term)


def solver_for(backend: str, algorithm: Optional[str]):
    """(solver, options) for the algorithm text of a task (None: the generic solver).  Raises ValueError if the
    backend has no solver for it."""
    if algorithm is None:
        return ode_solver(backend, None)
    problem = algorithm_problem(backend, algorithm)
    if problem:
        raise ValueError(problem)
    return ode_solver(backend, term_number(algorithm))


def algorithm_problem(backend: str, algorithm: str) -> Optional[str]:
    """Why a backend cannot use this `algorithm` text, or None if it can."""
    n = term_number(algorithm)
    if n is None:
        return f"algorithm {algorithm!r} is not a KiSAO term (KISAO:nnnnnnn)"
    if n in ODE_ALGORITHMS[backend]:
        return None
    note = ALGORITHM_NOTES.get(backend, {}).get(n)
    return f"KISAO:{n:07d} is not available: {note}" if note else f"KISAO:{n:07d} is not available in {backend}"


def settings_problem(backend: str, task_json: dict, solver: Optional[str] = None) -> Optional[str]:
    """Why a backend's solver cannot honor the solver settings given in a simulation task, or None.
    `solver` defaults to the one for the task's working algorithm (or the backend's generic solver)."""
    if solver is None:
        algs = task_json.get("workingAlgorithms") or []
        n = term_number(algs[0].get("algorithm")) if algs and isinstance(algs[0], dict) else None
        found = ode_solver(backend, n)
        solver = found[0] if found else None
    allowed = SETTINGS_SUPPORTED[backend].get(solver, set())
    unsupported = [s for s in ALL_SETTINGS if s in task_json and s not in allowed]
    if unsupported:
        return f"{backend}'s {solver} solver cannot honor the setting(s) {', '.join(unsupported)}"
    return None


def step_problem(backend: str, task_json: dict) -> Optional[str]:
    """Why a BoundedODESimulation (the solver chooses its output points) cannot be run by the backend's solver."""
    algs = task_json.get("workingAlgorithms") or []
    n = term_number(algs[0].get("algorithm")) if algs and isinstance(algs[0], dict) else None
    found = ode_solver(backend, n)
    if found and found[0] in FIXED_STEP_SOLVERS[backend]:
        return f"{backend}'s {found[0]} solver has a fixed step and cannot choose its own output points"
    return None


def steady_state_problem(backend: str, algorithm: Optional[str]) -> Optional[str]:
    """Why a backend cannot use this `algorithm` text for a SteadyState task, or None if it can (None: no algorithm)."""
    if algorithm is None:
        return None
    n = term_number(algorithm)
    if n is None:
        return f"algorithm {algorithm!r} is not a KiSAO term (KISAO:nnnnnnn)"
    if n in STEADY_STATE_ALGORITHMS[backend]:
        return None
    return (f"KISAO:{n:07d} is not available for steady states in {backend} "
            f"(only the generic KISAO:{GENERIC_STEADY_STATE:07d} is mapped)")
