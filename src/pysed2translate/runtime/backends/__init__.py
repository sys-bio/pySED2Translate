"""Simulator backends.  `get(name)` returns the backend object for 'roadrunner', 'copasi' or 'opencor'; the
simulator itself is imported only when its backend is first used."""
from __future__ import annotations

import importlib

from ..annotated import DataError
from .base import Backend, JacobianResult, SteadyState, SteadyStateResult, TimeCourse, TimeCourseResult

_MODULES = {"roadrunner": ".roadrunner_backend", "copasi": ".copasi_backend", "opencor": ".opencor_backend"}
_cache: dict = {}


def get(name: str) -> Backend:
    if name not in _MODULES:
        raise DataError(f"unknown backend {name!r}")
    if name not in _cache:
        try:
            module = importlib.import_module(_MODULES[name], __package__)
        except ModuleNotFoundError as e:
            if e.name and e.name.startswith(__package__):
                raise DataError(f"backend {name!r} is not implemented yet") from e
            raise
        _cache[name] = module.create()
    return _cache[name]


__all__ = ["get", "Backend", "JacobianResult", "SteadyState", "SteadyStateResult", "TimeCourse", "TimeCourseResult"]
