"""The backends the translator can generate scripts for.

BACKENDS are the simulators of differential equations (ODE time courses, steady states, Jacobians); FBA_BACKENDS do
flux balance analysis.  A backend name may carry a variant after a colon, which picks the solver the backend uses:
`cobra:glpk`, `cobra:scipy`.
"""
from typing import Optional

BACKENDS = ("roadrunner", "copasi", "opencor")
FBA_BACKENDS = ("cobra",)
ALL_BACKENDS = BACKENDS + FBA_BACKENDS

# kinds of work a backend can be chosen for separately (`--backend fba=cobra:scipy`); the names are those of the
# "kinds" map of the capability table
KINDS = ("ode", "steady", "jacobian", "fba")

VARIANTS = {"cobra": ("glpk", "scipy")}


def split_backend(spec: str) -> tuple:
    """'cobra:scipy' -> ('cobra', 'scipy'); 'roadrunner' -> ('roadrunner', None)."""
    name, _, variant = spec.partition(":")
    return name, (variant or None)


def backend_problem(spec: str) -> Optional[str]:
    """Why `spec` is not a backend (name[:variant]), or None if it is."""
    name, variant = split_backend(spec)
    if name not in ALL_BACKENDS:
        return f"unknown backend {name!r}; choose from {', '.join(ALL_BACKENDS)}"
    if variant is not None and variant not in VARIANTS.get(name, ()):
        known = ", ".join(VARIANTS[name]) if name in VARIANTS else "none"
        return f"backend {name!r} has no variant {variant!r} (variants: {known})"
    return None


def parse_backend_args(values: list) -> tuple:
    """The values of repeated `--backend` options -> (default backend, {kind: backend}).

    Each value is `NAME[:VARIANT]` (the default backend, for every kind of work) or `KIND=NAME[:VARIANT]` (the
    backend for one kind).  Raises ValueError with the reason for a bad value, a repeated kind, a second default, or
    no default at all.
    """
    default, kinds = None, {}
    for value in values:
        kind, eq, spec = value.rpartition("=") if "=" in value else ("", "", value)
        problem = backend_problem(spec)
        if problem:
            raise ValueError(problem)
        if not eq:
            if default is not None:
                raise ValueError(f"two default backends given ({default} and {spec}); name a kind for the second, "
                                 f"for example fba={spec}")
            default = spec
            continue
        if kind not in KINDS:
            raise ValueError(f"unknown kind {kind!r} in {value!r}; choose from {', '.join(KINDS)}")
        if kind in kinds:
            raise ValueError(f"the kind {kind!r} is given twice")
        kinds[kind] = spec
    if default is None:
        raise ValueError("no default backend: give --backend NAME (for example roadrunner, or cobra for a "
                         "document that only has flux balance analysis)")
    return default, kinds
