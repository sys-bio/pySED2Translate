"""Simulator backends.  `get(name)` returns the backend object for 'roadrunner', 'copasi', 'opencor' or 'cobra'
(flux balance analysis); a name may carry a variant, `cobra:scipy`.  The simulator itself is imported only when its
backend is first used."""
from __future__ import annotations

import importlib

from ..annotated import DataError
from .base import EXIT_CANNOT_RUN, Backend, BackendCannotRun, FbaRequest, JacobianResult, SteadyState, SteadyStateResult, TimeCourse, TimeCourseResult

_MODULES = {"roadrunner": ".roadrunner_backend", "copasi": ".copasi_backend", "opencor": ".opencor_backend",
            "cobra": ".cobra_backend"}
_cache: dict = {}


def get(spec: str) -> Backend:
    """The backend for `name` or `name:variant`."""
    name, _, variant = spec.partition(":")
    if name not in _MODULES:
        raise DataError(f"unknown backend {name!r}")
    if variant and name != "cobra":
        raise DataError(f"backend {name!r} has no variants")
    if spec not in _cache:
        try:
            module = importlib.import_module(_MODULES[name], __package__)
        except ModuleNotFoundError as e:
            if e.name and e.name.startswith(__package__):
                raise DataError(f"backend {name!r} is not implemented yet") from e
            raise
        _cache[spec] = module.create(variant) if variant else module.create()
    return _cache[spec]


__all__ = ["get", "Backend", "FbaRequest", "JacobianResult", "SteadyState", "SteadyStateResult", "TimeCourse", "TimeCourseResult"]
