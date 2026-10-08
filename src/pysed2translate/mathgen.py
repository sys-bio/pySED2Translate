"""Translate SED2 infix math (as parsed by libsed2) into Python expressions that call pysed2translate.runtime.mathfn.

    code = math_to_python("1 + sin(#constants:x)", resolve_reference)

`resolve_reference(text)` returns the Python expression for a reference such as "#tasks:s1['S1']" (it
decides how the referenced value is obtained); `resolve_name(name)` may return an expression for a bare name
other than the predefined constants (return None if the name is unknown).
"""
from __future__ import annotations

from typing import Callable, Optional

from .errors import TranslationError
from .runtime import mathfn

_BINARY = {"ADD": "add", "SUB": "sub", "MUL": "mul", "DIV": "div", "POW": "power"}


def math_to_python(text: str, resolve_reference: Callable[[str], str],
                   resolve_name: Optional[Callable[[str], Optional[str]]] = None) -> str:
    import libsed2

    try:
        root = libsed2.parse_math(text)
    except libsed2.MathSyntaxError as e:
        raise TranslationError(f"math {text!r} is not valid: {e}") from e

    def gen(n) -> str:
        t = n.node_type.name
        if t == "NUMBER":
            return repr(float(n.text))
        if t == "REFERENCE":
            return resolve_reference(n.text)
        if t == "NAME":
            if n.name in mathfn.CONSTANTS:
                return f"rt.m.{n.name}"
            if resolve_name is not None:
                expr = resolve_name(n.name)
                if expr is not None:
                    return expr
            raise TranslationError(f"math {text!r}: unknown name {n.name!r}")
        kids = [gen(c) for c in n.children]
        if t == "FUNCTION_CALL":
            if n.name not in mathfn.FUNCTIONS:
                raise TranslationError(f"math {text!r}: function {n.name!r} is not implemented")
            return f"rt.m.{mathfn.python_name(n.name)}({', '.join(kids)})"
        if t == "ARRAY":
            return f"rt.m.array({', '.join(kids)})"
        if t == "UMINUS":
            return f"rt.m.neg({kids[0]})"
        if t == "UPLUS":
            return kids[0]
        if t in _BINARY:
            fn = _BINARY[t]
            acc = kids[0]
            for k in kids[1:]:
                acc = f"rt.m.{fn}({acc}, {k})"
            return acc
        raise TranslationError(f"math {text!r}: unsupported construct {t}")

    return gen(root)
