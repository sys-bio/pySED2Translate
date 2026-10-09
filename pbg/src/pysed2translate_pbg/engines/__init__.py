"""Engine discovery (rule M4): every sub-folder of this package that has an `__init__.py` defining NAME is an engine.
There is no list to edit: adding an engine is adding a folder, removing one is deleting it."""
from __future__ import annotations

import importlib
import os
import pkgutil

_HERE = os.path.dirname(os.path.abspath(__file__))


def names() -> list:
    """Names of the engine folders present, in alphabetical order."""
    found = []
    for info in pkgutil.iter_modules([_HERE]):
        if info.ispkg and os.path.exists(os.path.join(_HERE, info.name, "__init__.py")):
            found.append(info.name)
    return sorted(found)


def load(name: str):
    """The engine module `name`.  Raises KeyError if there is no such engine."""
    if name not in names():
        raise KeyError(f"no engine {name!r}; engines found: {', '.join(names()) or 'none'}")
    return importlib.import_module(f"{__name__}.{name}")


def discover() -> dict:
    """{name: module} for every engine that imports (an engine that fails to import is reported by `broken()`)."""
    out = {}
    for n in names():
        try:
            out[n] = load(n)
        except Exception:  # noqa: BLE001 - listed by broken()
            pass
    return out


def broken() -> dict:
    """{name: error text} for engine folders that cannot be imported."""
    bad = {}
    for n in names():
        try:
            load(n)
        except Exception as e:  # noqa: BLE001
            bad[n] = f"{type(e).__name__}: {e}"
    return bad
