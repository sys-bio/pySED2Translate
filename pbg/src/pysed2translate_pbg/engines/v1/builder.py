"""Turn a validated SED2 document (libsed2 object) into a process-bigraph composite document (a JSON-able dict).

One handler per element type.  Every SED2 task becomes a Step node, every task output a store `["tasks", <task path>, <output>]`,
every `#constants:` / `#tasks:` reference a wire (plus bracket indices in the step's config).  See process-bigraph.md, 3.3-3.8.

Scopes: the top level and each repeat's inner document are scopes.  A read of a store that the scope does not produce is a *free*
read: the repeat's Step gets an input port for it, and copies the value into the inner state at the same path.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from pysed2translate_pbg import host
from . import providers

libsed2 = host.libsed2
rt = host.rt
TranslationError = host.TranslationError

ADDR = "local:!pysed2translate_pbg.engines.v1."
BOOLEAN_SETTINGS = {"forcePhysicalCorrectness", "integrateReducedModel", "useReducedModel", "useStiffSolver", "variableStepSize"}
INTEGER_SETTINGS = {"maxInternalSteps", "maxBDForder", "maxAdamsOrder", "maxOutputRows", "maxNumberOfSteps"}
MATH_BINARY = {"ADD": "add", "SUB": "sub", "MUL": "mul", "DIV": "div", "POW": "power"}

TASK_HANDLERS: dict = {}
OUTPUT_HANDLERS: dict = {}


def task_handler(name):
    def deco(fn):
        TASK_HANDLERS[name] = fn
        return fn
    return deco


def output_handler(name):
    def deco(fn):
        OUTPUT_HANDLERS[name] = fn
        return fn
    return deco


def snake(name: str) -> str:
    return "".join("_" + c.lower() if c.isupper() else c for c in name)


def orref(obj, attr: str):
    """('ref', text) or ('value', v) for an attribute that may be a literal or a reference; None if unset."""
    s = snake(attr)
    if not getattr(obj, f"is_set_{s}")():
        return None
    if getattr(obj, f"is_{s}_ref")():
        return ("ref", getattr(obj, f"get_{s}_ref")())
    return ("value", getattr(obj, f"get_{s}_value")())


def has_reference(value: Any) -> bool:
    if isinstance(value, str):
        return libsed2.is_reference(value)
    if isinstance(value, list):
        return any(has_reference(v) for v in value)
    if isinstance(value, dict):
        return any(has_reference(v) for v in value.values())
    return False


# --------------------------------------------------------------------------- scopes and references

@dataclass
class Ref:
    store: tuple
    const: bool
    index: Optional[list]


class Scope:
    """The top level or the inside of a repeat."""

    def __init__(self, parent: Optional["Scope"] = None, guarded: bool = False):
        self.parent = parent
        self.guarded = guarded
        self.produced: set = set()
        self.free: dict = {}      # store tuple -> port name
        self.nodes: dict = {}

    def has(self, store: tuple) -> bool:
        s = self
        while s is not None:
            if store in s.produced:
                return True
            s = s.parent
        return False

    def known_task(self, tid: str) -> bool:
        s = self
        while s is not None:
            if any(len(p) == 3 and p[0] == "tasks" and p[1] == tid for p in s.produced):
                return True
            s = s.parent
        return False

    def note_read(self, store: tuple) -> None:
        """A node of this scope reads `store`; if the scope does not produce it, it is a free read (and the parent's)."""
        if store in self.produced:
            return
        if store not in self.free:
            self.free[store] = f"f{len(self.free)}"
        if self.parent is not None:
            self.parent.note_read(store)

    def node_name(self, base: str) -> str:
        name, n = base, 1
        while name in self.nodes:
            n += 1
            name = f"{base}_{n}"
        return name


def brackets_json(accessors) -> list:
    """Bracket groups of `index` accessors as JSON: [[["int", 3], ["label", "S1"]], ...]."""
    groups: list = []
    for kind, ix in accessors:
        if kind != "index":
            raise TranslationError(f"unexpected accessor {kind!r} in an index chain")
        if not groups or not ix.same_bracket:
            groups.append([])
        v = ix.value
        groups[-1].append([ix.kind, list(v) if ix.kind == "range" else v])
    return groups


class Node:
    """A step node being built."""

    def __init__(self, b: "Builder", scope: Scope, cls: str, tid: str, out: tuple, name: Optional[str] = None,
                 context: bool = False, backend: Optional[str] = None):
        self.b, self.scope, self.cls, self.tid = b, scope, cls, tid
        self.refs: dict = {}
        self.inputs: dict = {}
        self.outputs: dict = {}
        self.args: dict = {}
        self.extra: dict = {}
        self.backend = backend
        self.context = context
        self.name = scope.node_name(name or "task_" + re.sub(r"\W", "_", tid))
        self._seen: dict = {}
        for o in out:
            self.outputs[o] = ["tasks", tid, o]
            scope.produced.add(("tasks", tid, o))
        if context:
            self.inputs["context"] = ["context"]
            scope.note_read(("context",))
        if scope.guarded:
            self.inputs["guard"] = ["guard"]
        scope.nodes[self.name] = self

    def ref(self, text: str) -> str:
        r = self.b.resolve(self.scope, text)
        key = (r.store, json.dumps(r.index), r.const)
        if key in self._seen:
            return self._seen[key]
        port = f"r{len(self.refs)}"
        self._seen[key] = port
        self.refs[port] = {"const": r.const, "index": r.index}
        self.inputs[port] = list(r.store)
        self.scope.note_read(r.store)
        return port

    # items for attributes that are a literal or a reference
    def item(self, got, kind: str = "float"):
        k, v = got
        if k == "ref":
            return {"ref": self.ref(v)}
        if kind == "string":
            return {"value": str(v)}
        if kind == "bool":
            return {"value": bool(v)}
        if kind == "int":
            return {"value": int(v)}
        if kind == "list":
            return {"value": list(v)}
        return {"value": float(v)}

    def number_entry(self, item):
        """One entry of a list of numbers: a number or a reference."""
        if isinstance(item, str) and libsed2.is_reference(item):
            return {"ref": self.ref(item)}
        return {"value": float(item)}

    def template(self, value) -> dict:
        if not has_reference(value):
            return {"const": value}
        if isinstance(value, str):
            return {"ref": self.ref(value)}
        if isinstance(value, list):
            return {"array": [self.template(v) for v in value]}
        keys = list(value.keys())
        return {"block": {"keys": keys, "items": [self.template(value[k]) for k in keys]}}

    def to_json(self) -> dict:
        config: dict = {"id": self.tid}
        if self.refs:
            config["refs"] = self.refs
        if self.args:
            config["args"] = self.args
        if self.scope.guarded:
            config["guard"] = True
        if self.context:
            config["context"] = True
        if self.backend:
            config["backend"] = self.backend
        config.update(self.extra)
        return {"_type": "step", "address": ADDR + self.cls, "config": config, "inputs": self.inputs, "outputs": self.outputs}


# --------------------------------------------------------------------------- the builder

class Builder:
    def __init__(self, doc, options, excluded=()):
        self.doc = doc
        self.options = options
        self.constants: dict = {}
        self.engine_options = options.engine or {}
        self.wrappers = self.engine_options.get("wrappers", providers.DEFAULT_MODE)    # strict | prefer | off
        self.excluded = set(excluded)      # tasks that must run on the host runtime (prefer mode, after a late refusal)
        self.refusals: dict = {}           # strict mode: task id -> gaps
        self.notes: list = []
        self.plans: dict = {}              # task id -> providers.Plan, the tasks a wrapper runs
        self.family: Optional[str] = None

    # ---- backends
    def backend(self, task_type: str) -> str:
        """The backend (name[:variant]) for a task type: the one chosen for its kind, else the default if it serves the
        kind, else the only backend that does (flux balance analysis: cobra)."""
        table = host.capability_table()
        kind = table.kind_of(task_type)
        overrides = {k: v for k, v in self.options.backend.items() if k != "*"}
        default = self.options.backend.get("*")
        if default is None:
            serving = table.serving(kind)
            if kind not in overrides and len(serving) != 1:
                raise TranslationError(f"no backend chosen for tasks of kind {kind!r} (use --backend NAME or --backend {kind}=NAME)")
            default = serving[0] if serving else ""
        return table.backend_for(task_type, default, overrides)

    # ---- providers
    def provide(self, scope: "Scope", req: "providers.Request"):
        """The wrapper plan for a simulation task, or None when the host runtime runs it (mode off, a gap in prefer mode, and
        in strict mode a gap that is recorded and refused when the translation is complete)."""
        if self.wrappers == "off":
            return None
        req.guarded = scope.guarded
        if req.tid in self.excluded:
            self.notes.append(f"task {req.tid!r}: host runtime ({req.backend}): a later task uses its model, which "
                              f"{providers.gap('W-6')[0]} says a wrapper cannot hand on")
            return None
        plan, gaps = providers.gaps_for(req, self.family, self.options.input_dir or ".")
        if gaps:
            if self.wrappers == "strict":
                self.refusals[req.tid] = gaps
            else:
                self.notes.append(f"task {req.tid!r}: host runtime ({req.backend}), because "
                                  + "; ".join(f"{i} {t}" for i, t in gaps))
            return None
        self.family = plan.family
        self.plans[req.tid] = plan
        return plan

    # ---- references
    def resolve(self, scope: Scope, text: str, _seen: tuple = ()) -> Ref:
        if not libsed2.is_reference(text):
            raise TranslationError(f"{text!r} is not a reference")
        pr = libsed2.parse_reference(text)
        accessors = list(pr.accessors)
        if pr.collection == "constants":
            cid = pr.path[0]
            if len(pr.path) != 1:
                raise TranslationError(f"reference {pr.raw!r}: a constant has no sub-elements")
            if cid in _seen:
                raise TranslationError(f"constants refer to each other in a cycle: {' -> '.join(_seen + (cid,))}")
            if cid not in self.constants:
                raise TranslationError(f"reference {pr.raw!r}: no constant {cid!r}")
            value = self.constants[cid]
            if isinstance(value, str) and libsed2.is_reference(value):
                base = self.resolve(scope, value, _seen + (cid,))
            else:
                base = Ref(("constants", cid), True, None)
            if accessors:
                base = Ref(base.store, base.const, (base.index or []) + brackets_json(accessors))
            return base
        if pr.collection == "tasks":
            tid = ":".join(pr.path)
            suffix = None
            if accessors and accessors[0][0] == "dot":
                suffix = accessors.pop(0)[1]
            store = ("tasks", tid, suffix or "data")
            if not scope.known_task(tid):
                raise TranslationError(f"reference {pr.raw!r}: task {tid!r} produces no values here "
                                       "(not translated yet, a reference to a later task, or to the inside of a repeat)")
            if not scope.has(store) and suffix == "model" and tid in self.plans:
                raise providers.WrapperModelUse(tid, pr.raw)
            if not scope.has(store):
                raise TranslationError(f"reference {pr.raw!r}: task {tid!r} has no output {suffix or '[id]'!r}")
            if any(k != "index" for k, _ in accessors):
                raise TranslationError(f"reference {pr.raw!r}: .loc/.isel/.sel accessors are not implemented yet")
            return Ref(store, False, brackets_json(accessors) if accessors else None)
        raise TranslationError(f"reference {pr.raw!r}: only #constants: and #tasks: references can be used as data")

    def static_value(self, text: str, what: str):
        try:
            return libsed2.get_reference_value(self.doc, text)
        except Exception as e:  # noqa: BLE001
            raise TranslationError(f"{what}: {text!r} must refer to a constant, because its value is needed while "
                                   f"translating ({e})") from e

    def static_text(self, task, attr: str, what: str) -> str:
        kind, v = orref(task, attr)
        if kind == "ref":
            v = self.static_value(v, what)
        if not isinstance(v, str):
            raise TranslationError(f"{what} must be a string")
        return v

    # ---- tasks
    def task(self, scope: Scope, tid: str, element) -> None:
        handler = TASK_HANDLERS.get(element.get_type())
        if handler is None:
            raise TranslationError(f"task {tid!r}: translating '{element.get_type()}' is not implemented yet")
        handler(self, scope, tid, element)

    def build(self) -> dict:
        doc, opt = self.doc, self.options
        top = Scope()
        for cid in doc.get_constants():
            self.constants[cid] = doc.get_constants_item(cid)
            self._refuse_nested_references(cid, self.constants[cid])
            top.produced.add(("constants", cid))
        top.produced.add(("context",))
        for tid in doc.get_tasks():
            self.task(top, tid, doc.get_tasks_item(tid))
        for oid in doc.get_outputs():
            element = doc.get_outputs_item(oid)
            handler = OUTPUT_HANDLERS.get(element.get_type())
            if handler is None:
                raise TranslationError(f"output {oid!r}: translating '{element.get_type()}' is not implemented yet")
            handler(self, top, oid, element)
        if self.refusals:
            raise providers.WrapperRefusal(", ".join(sorted({v for v in opt.backend.values() if v})) or "the chosen backend",
                                           self.refusals)
        state: dict = {}
        if self.constants:
            state["constants"] = dict(self.constants)
        state["context"] = {"inputDir": opt.input_dir or ".", "outputDir": opt.output_dir or "results", "prefix": opt.prefix,
                            "png": True}
        for name, node in top.nodes.items():
            state[name] = node.to_json() if isinstance(node, Node) else node
        sed2 = {"version": "v1.0.0", "source": opt.source_name, "backend": dict(opt.backend), "engine": "v1",
                "engineVersion": "0.1"}
        if self.plans:
            sed2["wrappers"] = {"mode": self.wrappers, "family": self.family,
                                "tasks": {tid: p.address for tid, p in self.plans.items()},
                                "modelFiles": [{"task": tid, "modelTask": p.model_task, "location": p.location,
                                                "modelFile": p.model_file} for tid, p in self.plans.items()]}
        return {"name": opt.prefix,
                "description": f"Translated from {opt.source_name or 'a SED2 document'} by pysed2translate-pbg",
                "sed2": sed2,
                "state": state}

    @staticmethod
    def _refuse_nested_references(cid: str, value, top: bool = True) -> None:
        if isinstance(value, str):
            if not top and libsed2.is_reference(value):
                raise TranslationError(
                    f"constant {cid!r}: the reference {value!r} is inside a list or dictionary, which is not supported "
                    "(the specification does not say whether such entries are replaced by the value they refer to; "
                    "SED2/TODO.md: references inside list and dictionary constants)")
        elif isinstance(value, list):
            for item in value:
                Builder._refuse_nested_references(cid, item, False)
        elif isinstance(value, dict):
            for item in value.values():
                Builder._refuse_nested_references(cid, item, False)


# --------------------------------------------------------------------------- math

def math_tree(node: Node, text: str) -> dict:
    try:
        root = libsed2.parse_math(text)
    except libsed2.MathSyntaxError as e:
        raise TranslationError(f"math {text!r} is not valid: {e}") from e

    def gen(n) -> dict:
        t = n.node_type.name
        if t == "NUMBER":
            return {"num": float(n.text)}
        if t == "REFERENCE":
            return {"ref": node.ref(n.text)}
        if t == "NAME":
            if n.name in rt.m.CONSTANTS:
                return {"name": n.name}
            raise TranslationError(f"math {text!r}: unknown name {n.name!r}")
        kids = [gen(c) for c in n.children]
        if t == "FUNCTION_CALL":
            if n.name not in rt.m.FUNCTIONS:
                raise TranslationError(f"math {text!r}: function {n.name!r} is not implemented")
            return {"call": n.name, "args": kids}
        if t == "ARRAY":
            return {"array": kids}
        if t == "UMINUS":
            return {"op": "neg", "args": kids}
        if t == "UPLUS":
            return {"op": "pos", "args": kids}
        if t in MATH_BINARY:
            return {"op": MATH_BINARY[t], "args": kids}
        raise TranslationError(f"math {text!r}: unsupported construct {t}")

    return gen(root)


# --------------------------------------------------------------------------- data tasks

@task_handler("calculation")
def calculation(b: Builder, scope: Scope, tid: str, task) -> None:
    n = Node(b, scope, "steps.SedCalculation", tid, ("data",))
    n.args["math"] = math_tree(n, task.get_math_value())


@task_handler("createDataBlock")
def create_data_block(b: Builder, scope: Scope, tid: str, task) -> None:
    kind, v = orref(task, "data")
    if kind == "ref":
        v = b.static_value(v, f"task {tid!r} data")
    if not isinstance(v, dict):
        raise TranslationError(f"task {tid!r}: data must be a dictionary of labels to values")
    n = Node(b, scope, "steps.SedCreateDataBlock", tid, ("data",))
    n.args = {"keys": list(v.keys()), "items": [n.template(v[k]) for k in v]}


@task_handler("relabelData")
def relabel_data(b: Builder, scope: Scope, tid: str, task) -> None:
    n = Node(b, scope, "steps.SedRelabelData", tid, ("data",))
    kind, v = orref(task, "labels")
    labels = {"ref": n.ref(v)} if kind == "ref" else {"value": list(v)}
    n.args = {"input": n.ref(task.get_input()), "labels": labels}


@task_handler("stringFormation")
def string_formation(b: Builder, scope: Scope, tid: str, task) -> None:
    kind, v = orref(task, "concatenate")
    if kind == "ref":
        v = b.static_value(v, f"task {tid!r} concatenate")
    if not isinstance(v, list):
        raise TranslationError(f"task {tid!r}: concatenate must be a list")
    n = Node(b, scope, "steps.SedStringFormation", tid, ("data", "strings"))
    items = []
    for item in v:
        if isinstance(item, (str, bool, int, float)) and not has_reference(item):
            items.append({"lit": item})
        else:
            items.append(n.template(item))
    n.args = {"items": items}


def range_spec(n: Node, rng) -> dict:
    """A NumericRange / ParameterRange (computed) or a plain Range (its values)."""
    if not hasattr(rng, "is_set_start"):
        kind, v = orref(rng, "values")
        return {"kind": "plain", "template": {"ref": n.ref(v)} if kind == "ref" else n.template(v)}
    items: dict = {}
    for attr in ("start", "end", "interval", "numberOfSteps"):
        got = orref(rng, attr)
        if got is not None:
            items[snake(attr)] = n.item(got)
    scale = orref(rng, "scale")
    if scale is not None:
        items["scale"] = n.item(scale, "string")
    values = orref(rng, "values")
    if values is not None:
        kind, v = values
        items["values"] = {"ref": n.ref(v)} if kind == "ref" else {"value": [n.number_entry(e) for e in v]}
    return {"kind": "numeric", "items": items}


def _range_task(b: Builder, scope: Scope, tid: str, task, spec_fn) -> None:
    n = Node(b, scope, "steps.SedRange", tid, ("data",))
    n.args = {"range": spec_fn(n, task)}


task_handler("numericRange")(lambda b, s, t, task: _range_task(b, s, t, task, range_spec))
task_handler("parameterRange")(lambda b, s, t, task: _range_task(b, s, t, task, range_spec))
task_handler("range")(lambda b, s, t, task: _range_task(b, s, t, task, range_spec))


@task_handler("csvImport")
def csv_import(b: Builder, scope: Scope, tid: str, task) -> None:
    n = Node(b, scope, "steps.SedCsvImport", tid, ("data",), context=True)
    for attr, kind in (("location", "string"), ("separator", "string"), ("headers", "bool"), ("columnNames", "list"),
                       ("ncols", "int"), ("nrows", "int")):
        got = orref(task, attr)
        if got is not None:
            n.args[attr] = n.item(got, kind)


# --------------------------------------------------------------------------- models

@task_handler("modelImport")
def model_import(b: Builder, scope: Scope, tid: str, task) -> None:
    n = Node(b, scope, "steps.SedModelImport", tid, ("model",), context=True)
    n.args = {"location": b.static_text(task, "location", f"task {tid!r} location"),
              "language": b.static_text(task, "language", f"task {tid!r} language")}


def _string_list(n: Node, task, attr: str):
    got = orref(task, attr)
    return None if got is None else n.item(got, "list")


@task_handler("modelElementList")
def model_element_list(b: Builder, scope: Scope, tid: str, task) -> None:
    n = Node(b, scope, "steps.SedModelElementList", tid, ("strings",))
    n.args = {"model": n.ref(task.get_model())}
    for attr in ("includeElements", "includeTypes", "excludeElements", "excludeTypes"):
        n.args[attr] = _string_list(n, task, attr)


@task_handler("modelChange")
def model_change(b: Builder, scope: Scope, tid: str, task) -> None:
    n = Node(b, scope, "steps.SedModelChange", tid, ("model",))
    n.args["inputModel"] = n.ref(task.get_input_model())
    got = orref(task, "setValues")
    if got is not None:
        kind, v = got
        if kind == "ref":
            n.args["setValues"] = {"ref": n.ref(v)}
        else:
            items = {}
            for key, value in v.items():
                if isinstance(value, (bool, int, float)):
                    items[key] = {"num": float(value)}
                elif has_reference(value):
                    items[key] = {"t": n.template(value)}
                else:
                    raise TranslationError(f"task {tid!r}: setValues[{key!r}] = {value!r} is not a number")
            n.args["setValues"] = {"value": items}
    got = orref(task, "removeElements")
    if got is not None:
        n.args["removeElements"] = n.item(got, "list")


# --------------------------------------------------------------------------- simulations

def _independent_variable(b: Builder, tid: str, sim) -> str:
    text = b.static_text(sim, "independentVariable", f"task {tid!r} independentVariable")
    return "time" if text in ("time", "urn:sedml:symbol:time") else text


def _algorithm(b: Builder, tid: str, sim):
    algs = sim.get_working_algorithms()
    if not algs:
        return None
    kind, v = orref(algs[0], "algorithm")
    if kind == "ref":
        v = b.static_value(v, f"task {tid!r} working algorithm")
    return v


def _settings(n: Node, sim) -> dict:
    out = {}
    for name in host.kisao.ALL_SETTINGS:
        if name == "absoluteToleranceVector":
            if orref(sim, name) is not None:
                raise TranslationError("absoluteToleranceVector is not supported")
            continue
        got = orref(sim, name)
        if got is not None:
            kind = "bool" if name in BOOLEAN_SETTINGS else "int" if name in INTEGER_SETTINGS else "float"
            out[name] = [kind, n.item(got, kind)]
    return out


def _static(b: Builder, got, what: str):
    """The value of an attribute that is a literal or a constant; raises TranslationError if it is known only while running."""
    kind, v = got
    return b.static_value(v, what) if kind == "ref" else v


def _model_import(b: Builder, text: str):
    """(task id, location, language) when `text` is exactly '#tasks:T.model' for a modelImport task T, else (None, None, None)."""
    if not (isinstance(text, str) and libsed2.is_reference(text)):
        return None, None, None
    pr = libsed2.parse_reference(text)
    if pr.collection != "tasks" or [(k, v) for k, v in pr.accessors] != [("dot", "model")]:
        return None, None, None
    mid = ":".join(pr.path)
    if mid not in set(b.doc.get_tasks()):
        return None, None, None
    element = b.doc.get_tasks_item(mid)
    if element.get_type() != "modelImport":
        return None, None, None
    return mid, b.static_text(element, "location", f"task {mid!r} location"), b.static_text(element, "language", f"task {mid!r} language")


def _static_points(b: Builder, tid: str, rng):
    """(points, problem): the output points of an ExplicitODESimulation when they are known while translating."""
    try:
        if not hasattr(rng, "is_set_start"):
            got = orref(rng, "values")
            values = _static(b, got, f"task {tid!r} output points")
            return [float(x) for x in values], None
        kw = {}
        for attr, key in (("start", "start"), ("end", "end"), ("interval", "interval"), ("numberOfSteps", "number_of_steps")):
            got = orref(rng, attr)
            if got is not None:
                kw[key] = float(_static(b, got, f"task {tid!r} {attr}"))
        got = orref(rng, "scale")
        if got is not None:
            kw["scale"] = str(_static(b, got, f"task {tid!r} scale"))
        got = orref(rng, "values")
        if got is not None:
            kw["values"] = [float(b.static_value(e, "output points") if isinstance(e, str) and libsed2.is_reference(e) else e)
                            for e in _static(b, got, f"task {tid!r} values")]
        return rt.ops.numbers_from(rt.ops.numeric_range(**kw)), None
    except (TranslationError, host.DataError) as e:
        return None, str(e)


def _request(b: Builder, scope: Scope, tid: str, sim, kind: str, task_type: str, mode: str = "points"):
    """The providers.Request for a simulation task (None when wrappers are off)."""
    if b.wrappers == "off":
        return None
    mid, location, language = _model_import(b, sim.get_model()) if hasattr(sim, "get_model") else (None, None, None)
    req = providers.Request(tid=tid, kind=kind, backend=b.backend(task_type), mode=mode, model_task=mid, location=location,
                            language=language)
    if kind in ("ode", "steady"):
        req.independent_variable = "time" if orref(sim, "independentVariable") is None else _independent_variable(b, tid, sim)
        req.algorithm = _algorithm(b, tid, sim)
    if kind == "ode":
        req.settings = [n for n in host.kisao.ALL_SETTINGS if orref(sim, n) is not None]
        init = orref(sim, "independentVariableInit")
        if mode == "points":
            req.points, req.points_problem = _static_points(b, tid, sim.get_independent_variable_range())
        if init is not None:
            try:
                req.init = float(_static(b, init, f"task {tid!r} independentVariableInit"))
            except (TranslationError, ValueError) as e:
                req.points, req.points_problem = None, str(e)
    return req


def _wrapper_nodes(b: Builder, scope: Scope, tid: str, sim, plan: "providers.Plan") -> Node:
    """A wrapper step reading nothing and writing the stores ["wrappers", tid, port], and the adapter step that turns its
    output into the task's `data` (SED2 data with the labels the host runtime gives)."""
    name = scope.node_name("viva_" + re.sub(r"\W", "_", tid))
    outputs = {p: ["wrappers", tid, p] for p in plan.raw}
    scope.nodes[name] = {"_type": "step", "address": "local:!" + plan.address, "config": dict(plan.config), "inputs": {},
                         "outputs": outputs}
    for p in plan.raw:
        scope.produced.add(("wrappers", tid, p))
    cls = "steps.SedVivaOde" if plan.kind == "ode" else "steps.SedVivaSteady"
    n = Node(b, scope, cls, tid, ("data",), backend=b.backend("explicitODESimulation" if plan.kind == "ode" else "steadyState"))
    n.extra["provider"] = "viva"
    n.extra["raw"] = list(plan.raw)
    for p in plan.raw:
        n.inputs["raw_" + p] = ["wrappers", tid, p]
    n.args = {"family": plan.family, "model": n.ref(sim.get_model()), "outputVariables": n.item(orref(sim, "outputVariables"), "list"),
              "label": b.static_text(sim, "independentVariable", f"task {tid!r} independentVariable") if plan.kind == "ode" else None}
    return n


_ODE_TYPES = {"points": "explicitODESimulation", "span": "boundedODESimulation", "step": "oneStepODESimulation"}


def _ode(b: Builder, scope: Scope, tid: str, sim, mode: str) -> None:
    req = _request(b, scope, tid, sim, "ode", _ODE_TYPES[mode], mode)
    if req is not None:
        plan = b.provide(scope, req)
        if plan is not None:
            _wrapper_nodes(b, scope, tid, sim, plan)
            return
    n = Node(b, scope, "steps.SedOdeSimulation", tid, ("data", "model"), backend=b.backend(_ODE_TYPES[mode]))
    written = b.static_text(sim, "independentVariable", f"task {tid!r} independentVariable")
    n.args = {"mode": mode, "model": n.ref(sim.get_model()), "independentVariable": _independent_variable(b, tid, sim),
              "label": written, "outputVariables": n.item(orref(sim, "outputVariables"), "list"),
              "algorithm": _algorithm(b, tid, sim), "settings": _settings(n, sim)}
    init = orref(sim, "independentVariableInit")
    n.args["init"] = None if init is None else n.item(init)
    if mode == "points":
        n.args["range"] = range_spec(n, sim.get_independent_variable_range())
    elif mode == "span":
        span = sim.get_independent_variable_span()
        n.args["spanStart"] = n.item(orref(span, "start"))
        n.args["spanEnd"] = n.item(orref(span, "end"))
    else:
        n.args["step"] = n.item(orref(sim, "independentStep"))


task_handler("explicitODESimulation")(lambda b, s, t, task: _ode(b, s, t, task, "points"))
task_handler("boundedODESimulation")(lambda b, s, t, task: _ode(b, s, t, task, "span"))
task_handler("oneStepODESimulation")(lambda b, s, t, task: _ode(b, s, t, task, "step"))


@task_handler("steadyState")
def steady_state(b: Builder, scope: Scope, tid: str, task) -> None:
    req = _request(b, scope, tid, task, "steady", "steadyState")
    if req is not None:
        plan = b.provide(scope, req)
        if plan is not None:
            _wrapper_nodes(b, scope, tid, task, plan)
            return
    n = Node(b, scope, "steps.SedSteadyState", tid, ("data", "model"), backend=b.backend("steadyState"))
    iv = "time" if orref(task, "independentVariable") is None else _independent_variable(b, tid, task)
    n.args = {"model": n.ref(task.get_model()), "independentVariable": iv,
              "outputVariables": n.item(orref(task, "outputVariables"), "list"), "algorithm": _algorithm(b, tid, task)}


@task_handler("fluxBalanceAnalysis")
def flux_balance_analysis(b: Builder, scope: Scope, tid: str, task) -> None:
    if b.wrappers != "off":
        b.provide(scope, providers.Request(tid=tid, kind="fba", backend=b.backend("fluxBalanceAnalysis")))
    n = Node(b, scope, "steps.SedFba", tid, ("data", "model"), backend=b.backend("fluxBalanceAnalysis"))
    n.args = {"model": n.ref(task.get_model()), "outputVariables": n.item(orref(task, "outputVariables"), "list"),
              "algorithm": _algorithm(b, tid, task)}


def _jacobian(b: Builder, scope: Scope, tid: str, task, reduced: bool) -> None:
    if b.wrappers != "off":
        b.provide(scope, providers.Request(tid=tid, kind="jacobian", backend=b.backend("jacobianReduced" if reduced else "jacobianFull")))
    n = Node(b, scope, "steps.SedJacobian", tid, ("data",), backend=b.backend("jacobianReduced" if reduced else "jacobianFull"))
    n.args = {"model": n.ref(task.get_model()), "reduced": reduced}


task_handler("jacobianFull")(lambda b, s, t, task: _jacobian(b, s, t, task, False))
task_handler("jacobianReduced")(lambda b, s, t, task: _jacobian(b, s, t, task, True))


# --------------------------------------------------------------------------- repeats

def _output_map(b: Builder, tid: str, task) -> dict:
    got = orref(task, "outputVariableMap")
    if got is None:
        return {}
    kind, v = got
    if kind == "ref":
        v = b.static_value(v, f"task {tid!r} outputVariableMap")
    if not isinstance(v, dict):
        raise TranslationError(f"task {tid!r}: outputVariableMap must be an object of references")
    return dict(v)


def _inner_scope(parent: Scope) -> Scope:
    return Scope(parent, guarded=True)


def _inner_tasks(b: Builder, inner: Scope, tid: str, task) -> None:
    for sid in task.get_sub_tasks():
        b.task(inner, f"{tid}:subTasks:{sid}", task.get_sub_tasks_item(sid))


def _collector(b: Builder, inner: Scope, tid: str, out_map: dict) -> dict:
    """The collect step of an inner document.  Returns its args."""
    n = Node(b, inner, "loop.SedCollect", tid + ":collect", (), name="collect")
    order = []
    for key, ref in out_map.items():
        if not (isinstance(ref, str) and libsed2.is_reference(ref)):
            raise TranslationError(f"task {tid!r}: outputVariableMap[{key!r}] must be a reference")
        order.append(n.ref(ref))
    n.args = {"order": order}
    return n


def _finish_repeat(b: Builder, outer: Scope, inner: Scope, host_node: Node, extra_nodes: dict) -> None:
    """Move the inner nodes into the host node's document and add the free ports."""
    nodes = {name: (nd.to_json() if isinstance(nd, Node) else nd) for name, nd in inner.nodes.items()}
    nodes.update(extra_nodes)
    free = {}
    for store, port in inner.free.items():
        free[port] = list(store)
        host_node.inputs[port] = list(store)
        outer.note_read(store)
    host_node.extra["document"] = {"nodes": nodes, "free": free}


@task_handler("loop")
def loop(b: Builder, scope: Scope, tid: str, task) -> None:
    n = Node(b, scope, "loop.SedLoop", tid, ("data",))
    inner = _inner_scope(scope)
    for store in (("tasks", tid, "range"), ("tasks", tid, "index")):
        inner.produced.add(store)
    loop_vars = []
    clock_in, clock_out = {}, {"range": ["tasks", tid, "range"], "index": ["tasks", tid, "index"], "guard": ["guard"]}
    for name in task.get_loop_variables():
        lv = task.get_loop_variables_item(name)
        store = ("tasks", f"{tid}:loopVariables:{name}", "data")
        inner.produced.add(store)
        loop_vars.append((name, lv, store))
    out_map = _output_map(b, tid, task)
    _inner_tasks(b, inner, tid, task)
    collect = _collector(b, inner, tid, out_map)
    # the clock: reads the subsequent values (references inside the loop) and the initial values (placed in `loopinit`)
    clock_cfg = []
    for name, lv, store in loop_vars:
        sub = b.resolve(inner, lv.get_subsequent_values())
        inner.note_read(sub.store)
        clock_in["init_" + name] = ["loopinit", name]
        clock_in["subs_" + name] = list(sub.store)
        clock_out["lv_" + name] = list(store)
        clock_cfg.append({"name": name, "index": sub.index})
    loop_args = [{"name": name, "initial": n.template(lv.get_initial_value())} for name, lv, _ in loop_vars]
    if b.engine_options.get("loop_form") == "nested":
        # one inner composite per iteration; the loop variables are carried by the SedRepeat step (no clock)
        n.cls = "loop.SedRepeat"
        for a, (name, lv, store), cfg in zip(loop_args, loop_vars, clock_cfg):
            a["subsequent"] = {"store": clock_in["subs_" + name], "index": cfg["index"], "target": list(store)}
        n.args = {"kind": "loop", "rep": tid, "range": range_spec(n, task.get_range()), "keys": list(out_map), "loopVars": loop_args}
        _finish_repeat(b, scope, inner, n, {})
        return
    clock = {"_type": "process", "address": ADDR + "loop.SedClock", "interval": 1.0,
             "config": {"loopVars": clock_cfg}, "inputs": clock_in, "outputs": clock_out}
    n.args = {"range": range_spec(n, task.get_range()), "keys": list(out_map), "loopVars": loop_args}
    _finish_repeat(b, scope, inner, n, {"clock": clock})


@task_handler("scatter")
def scatter(b: Builder, scope: Scope, tid: str, task) -> None:
    n = Node(b, scope, "loop.SedRepeat", tid, ("data",))
    inner = _inner_scope(scope)
    for store in (("tasks", tid, "range"), ("tasks", tid, "index")):
        inner.produced.add(store)
    out_map = _output_map(b, tid, task)
    _inner_tasks(b, inner, tid, task)
    _collector(b, inner, tid, out_map)
    n.args = {"kind": "scatter", "rep": tid, "range": range_spec(n, task.get_range()), "keys": list(out_map)}
    _finish_repeat(b, scope, inner, n, {})


@task_handler("parameterScan")
def parameter_scan(b: Builder, scope: Scope, tid: str, task) -> None:
    n = Node(b, scope, "loop.SedRepeat", tid, ("data",))
    inner = _inner_scope(scope)
    for out in ("model", "ranges", "indexes"):
        inner.produced.add(("tasks", tid, out))
    elements = [b.static_text(pr, "modelElement", f"task {tid!r} parameterRanges[{i}] modelElement")
                for i, pr in enumerate(task.get_parameter_ranges())]
    if len(set(elements)) != len(elements):
        raise TranslationError(f"task {tid!r}: the parameterRanges must scan distinct model elements")
    out_map = _output_map(b, tid, task)
    _inner_tasks(b, inner, tid, task)
    _collector(b, inner, tid, out_map)
    n.args = {"kind": "scan", "rep": tid, "keys": list(out_map), "elements": elements, "model": n.ref(task.get_model()),
              "ranges": [range_spec(n, pr) for pr in task.get_parameter_ranges()]}
    _finish_repeat(b, scope, inner, n, {})


# --------------------------------------------------------------------------- outputs

def _output_node(b: Builder, scope: Scope, oid: str, cls: str) -> Node:
    n = Node(b, scope, cls, oid, (), name="output_" + re.sub(r"\W", "_", oid), context=True)
    n.outputs = {"manifest": ["manifest", oid], "failures": ["failures", oid]}
    return n


@output_handler("report")
def report(b: Builder, scope: Scope, oid: str, element) -> None:
    n = _output_node(b, scope, oid, "steps.SedReport")
    n.args = {"data": n.ref(element.get_data())}


CURVE_FIELDS = (("x", "get_x"), ("y", "get_y"), ("xErrorLower", "get_x_error_lower"), ("xErrorUpper", "get_x_error_upper"),
                ("yErrorLower", "get_y_error_lower"), ("yErrorUpper", "get_y_error_upper"),
                ("yFrom", "get_y_from"), ("yTo", "get_y_to"))


def _fields(n: Node, element, names) -> dict:
    out = {}
    for field, getter in names:
        if getattr(element, f"is_set_{snake(field)}")():
            out[field] = n.ref(getattr(element, getter)())
    return out


def _opt_item(n: Node, obj, attr: str, kind: str):
    got = orref(obj, attr)
    return None if got is None else n.item(got, kind)


def _axis(n: Node, axis) -> dict:
    out = {}
    for attr, kind in (("scale", "string"), ("min", "float"), ("max", "float"), ("grid", "bool"), ("reverse", "bool")):
        got = orref(axis, attr)
        if got is not None:
            out[attr] = n.item(got, kind)
    return out


def _plot_options(n: Node, plot, axis_names) -> dict:
    axes = {}
    for key, attr in axis_names:
        if getattr(plot, f"is_set_{snake(attr)}")():
            axes[key] = _axis(n, getattr(plot, "get_" + snake(attr))())
    out = {"axes": axes}
    for attr, kind in (("legend", "bool"), ("width", "float"), ("height", "float")):
        out[attr] = _opt_item(n, plot, attr, kind)
    return out


@output_handler("plot2D")
def plot2d(b: Builder, scope: Scope, oid: str, plot) -> None:
    n = _output_node(b, scope, oid, "steps.SedPlot2D")
    curves = []
    for position, cid in enumerate(plot.get_curves()):
        c = plot.get_curves_item(cid)
        curves.append({"id": cid, "position": position, "type": _opt_item(n, c, "curveType", "string"),
                       "order": _opt_item(n, c, "order", "int"), "yAxis": _opt_item(n, c, "yAxis", "string"),
                       "fields": _fields(n, c, CURVE_FIELDS)})
    n.args = {"curves": curves, "options": _plot_options(n, plot, (("x", "xAxis"), ("y", "yAxis"), ("right", "rightYAxis")))}


@output_handler("plot3D")
def plot3d(b: Builder, scope: Scope, oid: str, plot) -> None:
    n = _output_node(b, scope, oid, "steps.SedPlot3D")
    surfaces = []
    for position, sid in enumerate(plot.get_surfaces()):
        s = plot.get_surfaces_item(sid)
        surfaces.append({"id": sid, "position": position, "type": _opt_item(n, s, "surfaceType", "string"),
                         "order": _opt_item(n, s, "order", "int"),
                         "fields": _fields(n, s, (("x", "get_x"), ("y", "get_y"), ("z", "get_z")))})
    n.args = {"surfaces": surfaces, "options": _plot_options(n, plot, (("x", "xAxis"), ("y", "yAxis"), ("z", "zAxis")))}
