"""The Step classes of engine v1.  Each is thin: it reads its inputs, calls the host runtime (`host.rt`), and returns outputs.

Conventions (shared with `builder.py`, which writes the documents these steps run in):

* a step's config is `{"id": <task id>, "refs": {port: {"const": bool, "index": brackets|None}}, "args": {...},
  "guard": bool, "context": bool, "backend": str}`; `refs` names one input port per distinct reference and says how to turn
  the stored value into data: a constant is JSON (`AnnotatedData.from_constant`), anything else is the object a task stored;
  `index` are the bracket indices to apply afterwards;
* a step's output ports are its class attribute `OUT`;
* `guard`: a step inside a repeat reads the store `guard`, which is -1 until the repeat's clock has ticked; a negative guard
  makes the step do nothing (process-bigraph fires every step once at the start of a run, whatever its inputs; plan 3.8, rule 2);
* all ports are typed `quote`, which passes any Python object (AnnotatedData, SbmlModel) and nested JSON unchanged.
"""
from __future__ import annotations

import json

import numpy as np
from process_bigraph import Step

from pysed2translate_pbg import host

rt = host.rt


# the types the viva wrappers declare for their output ports (a store takes one type: the reader must use the writer's)
RAW_TYPES = {"time_series": "overwrite[list]", "species_trajectories": "overwrite[map[list]]",
             "steady_state_concentrations": "overwrite[map[float]]", "result": "numeric_result", "results": "any"}


class SedStep(Step):
    config_schema = {"id": "string", "refs": "quote", "args": "quote", "guard": "boolean", "context": "boolean",
                     "backend": "string", "provider": "string", "raw": "quote"}
    OUT: tuple = ()

    # ------------------------------------------------------------------ ports

    def inputs(self):
        ports = {p: "quote" for p in (self.config.get("refs") or {})}
        if self.config.get("guard"):
            ports["guard"] = "quote"
        if self.config.get("context"):
            ports["context"] = "quote"
        for p in self.config.get("raw") or []:
            ports["raw_" + p] = RAW_TYPES[p]       # the type of the wrapper's own output port, or the store's types would clash
        return ports

    def outputs(self):
        return {o: "quote" for o in self.OUT}

    def update(self, state):
        if self.config.get("guard"):
            g = state.get("guard")
            if g is None or g < 0:
                return {}
        return self.run(state, self.config.get("args") or {})

    def run(self, state, args):  # pragma: no cover - overridden
        raise NotImplementedError

    # ------------------------------------------------------------------ reading references

    def val(self, state, port):
        """The data a reference stands for: the stored object, with the reference's bracket indices applied."""
        spec = (self.config.get("refs") or {})[port]
        v = state[port]
        if spec.get("const"):
            v = rt.AnnotatedData.from_constant(v)
        index = spec.get("index")
        if index:
            v = v.index([[(k, tuple(x) if k == "range" else x) for k, x in group] for group in index])
        return v

    def ctx(self, state):
        c = state["context"]
        return rt.Context(c["inputDir"], c["outputDir"], c["prefix"], png=bool(c.get("png", True)))

    # ------------------------------------------------------------------ attributes that are a literal or a reference

    def num(self, state, item):
        return rt.ops.scalar(self.val(state, item["ref"])) if "ref" in item else float(item["value"])

    def text(self, state, item):
        return rt.ops.string_scalar(self.val(state, item["ref"])) if "ref" in item else str(item["value"])

    def flag(self, state, item):
        return bool(rt.ops.scalar(self.val(state, item["ref"]))) if "ref" in item else bool(item["value"])

    def integer(self, state, item):
        return int(rt.ops.scalar(self.val(state, item["ref"]))) if "ref" in item else int(item["value"])

    def strings(self, state, item):
        """A list of strings; None for an attribute that is not set."""
        if item is None:
            return None
        return rt.ops.strings_from(self.val(state, item["ref"])) if "ref" in item else [str(x) for x in item["value"]]

    def numbers(self, state, item):
        if "ref" in item:
            return rt.ops.numbers_from(self.val(state, item["ref"]))
        return [self.num(state, e) for e in item["value"]]

    # ------------------------------------------------------------------ templates (data written as JSON that may hold references)

    def template(self, state, t):
        """AnnotatedData for a template: {"const": json} | {"ref": port} | {"array": [t...]} | {"block": {"keys": [...], "items": [t...]}}."""
        if "const" in t:
            return rt.AnnotatedData.from_constant(t["const"])
        if "ref" in t:
            return self.val(state, t["ref"])
        if "array" in t:
            return rt.m.array(*[self.template(state, x) for x in t["array"]])
        if "block" in t:
            return rt.ops.block(list(t["block"]["keys"]), [self.template(state, x) for x in t["block"]["items"]])
        raise ValueError(f"unknown template {t!r}")

    # ------------------------------------------------------------------ math

    def math(self, state, t):
        if "num" in t:
            return float(t["num"])
        if "ref" in t:
            return self.val(state, t["ref"])
        if "name" in t:
            return getattr(rt.m, t["name"])
        if "call" in t:
            return getattr(rt.m, rt.m.python_name(t["call"]))(*[self.math(state, a) for a in t["args"]])
        if "array" in t:
            return rt.m.array(*[self.math(state, a) for a in t["array"]])
        if "op" in t:
            args = [self.math(state, a) for a in t["args"]]
            if t["op"] == "neg":
                return rt.m.neg(args[0])
            if t["op"] == "pos":
                return args[0]
            acc = args[0]
            for k in args[1:]:
                acc = getattr(rt.m, t["op"])(acc, k)
            return acc
        raise ValueError(f"unknown math node {t!r}")

    # ------------------------------------------------------------------ ranges

    def range_data(self, state, spec):
        """AnnotatedData of a NumericRange/ParameterRange spec (see builder.range_spec) or of a plain Range."""
        if spec["kind"] == "plain":
            return self.template(state, spec["template"])
        kw = {}
        for name in ("start", "end", "interval", "number_of_steps"):
            if name in spec["items"]:
                kw[name] = self.num(state, spec["items"][name])
        if "scale" in spec["items"]:
            kw["scale"] = self.text(state, spec["items"]["scale"])
        if "values" in spec["items"]:
            kw["values"] = self.numbers(state, spec["items"]["values"])
        return rt.ops.numeric_range(**kw)


# ---------------------------------------------------------------------------- data tasks

class SedCalculation(SedStep):
    OUT = ("data",)

    def run(self, state, args):
        return {"data": rt.m.to_data(self.math(state, args["math"]))}


class SedCreateDataBlock(SedStep):
    OUT = ("data",)

    def run(self, state, args):
        keys = list(args["keys"])
        return {"data": rt.ops.block(keys, [self.template(state, t) for t in args["items"]])}


class SedRelabelData(SedStep):
    OUT = ("data",)

    def run(self, state, args):
        return {"data": rt.ops.relabel(self.val(state, args["input"]), self.strings(state, args["labels"]))}


class SedStringFormation(SedStep):
    OUT = ("data", "strings")

    def run(self, state, args):
        items = [x["lit"] if "lit" in x else self.template(state, x) for x in args["items"]]
        data = rt.ops.string_formation(items)
        return {"data": data, "strings": data}


class SedRange(SedStep):
    OUT = ("data",)

    def run(self, state, args):
        return {"data": self.range_data(state, args["range"])}


class SedModelElementList(SedStep):
    OUT = ("strings",)

    def run(self, state, args):
        model = self.val(state, args["model"])
        found = model.element_ids(include_elements=self.strings(state, args.get("includeElements")),
                                  include_types=self.strings(state, args.get("includeTypes")),
                                  exclude_elements=self.strings(state, args.get("excludeElements")),
                                  exclude_types=self.strings(state, args.get("excludeTypes")))
        return {"strings": rt.ops.string_data(found)}


class SedCsvImport(SedStep):
    OUT = ("data",)

    def run(self, state, args):
        def opt(name, how):
            item = args.get(name)
            return None if item is None else how(state, item)

        location = self.text(state, args["location"])
        data = rt.ops.csv_import(self.ctx(state).input_path(location), separator=opt("separator", self.text),
                                 headers=opt("headers", self.flag), column_names=opt("columnNames", self.strings),
                                 ncols=opt("ncols", self.integer), nrows=opt("nrows", self.integer))
        return {"data": data}


# ---------------------------------------------------------------------------- models

class SedModelImport(SedStep):
    OUT = ("model",)

    def run(self, state, args):
        return {"model": rt.SbmlModel.load(self.ctx(state).input_path(args["location"]), args["language"])}


class SedModelChange(SedStep):
    OUT = ("model",)

    def run(self, state, args):
        model = self.val(state, args["inputModel"])
        sv = args.get("setValues")
        if sv is not None:
            if "ref" in sv:
                values = rt.ops.mapping_from(self.val(state, sv["ref"]))
            else:
                values = {k: (float(x["num"]) if "num" in x else rt.ops.scalar(self.template(state, x["t"])))
                          for k, x in sv["value"].items()}
            model = model.with_values(values)
        rm = args.get("removeElements")
        if rm is not None:
            model = model.without(self.strings(state, rm))
        return {"model": model}


# ---------------------------------------------------------------------------- simulations

class SedOdeSimulation(SedStep):
    OUT = ("data", "model")

    def _settings(self, state, specs):
        out = {}
        for name, (kind, item) in specs.items():
            out[name] = {"bool": self.flag, "int": self.integer, "float": self.num}[kind](state, item)
        return out

    def run(self, state, args):
        tc = dict(independent_variable=args["independentVariable"], output_variables=self.strings(state, args["outputVariables"]),
                  label=args["label"], settings=self._settings(state, args["settings"]), algorithm=args["algorithm"])
        if args.get("init") is not None:
            tc["start"] = self.num(state, args["init"])
        mode = args["mode"]
        if mode == "points":
            tc["points"] = rt.ops.numbers_from(self.range_data(state, args["range"]))
        elif mode == "span":
            tc["span"] = (self.num(state, args["spanStart"]), self.num(state, args["spanEnd"]))
        else:
            tc["step"] = self.num(state, args["step"])
        model = self.val(state, args["model"])
        data, end_model = rt.backends.get(self.config["backend"]).time_course(model, rt.backends.TimeCourse(**tc))
        return {"data": data, "model": end_model}


class SedSteadyState(SedStep):
    OUT = ("data", "model")

    def run(self, state, args):
        req = rt.backends.SteadyState(independent_variable=args["independentVariable"],
                                      output_variables=self.strings(state, args["outputVariables"]), algorithm=args["algorithm"])
        data, end_model = rt.backends.get(self.config["backend"]).steady_state(self.val(state, args["model"]), req)
        return {"data": data, "model": end_model}


class SedFba(SedStep):
    OUT = ("data", "model")

    def run(self, state, args):
        req = rt.backends.FbaRequest(output_variables=self.strings(state, args["outputVariables"]), algorithm=args["algorithm"])
        data, model = rt.backends.get(self.config["backend"]).fba(self.val(state, args["model"]), req)
        return {"data": data, "model": model}


class SedJacobian(SedStep):
    OUT = ("data",)

    def run(self, state, args):
        return {"data": rt.backends.get(self.config["backend"]).jacobian(self.val(state, args["model"]), reduced=bool(args["reduced"]))}


# ---------------------------------------------------------------------------- simulations run by a community wrapper

class SedViva(SedStep):
    """Adapter for a viva wrapper step: the wrapper wrote its own result to the stores `raw_*`; this step turns it into the
    task's `data`, with the labels and layout the host runtime gives.  What a wrapper does not return is refused with the
    ledger id (pbg/upstream), never reconstructed."""
    OUT = ("data",)
    WHO = {"tellurium": "viva-tellurium (TelluriumUTCStep / TelluriumSteadyStateStep)", "copasi": "viva-copasi (CopasiUTCStep / CopasiSteadyStateStep)"}

    def concentrations(self, model, names, available, args):
        """Check that every requested variable is something the wrapper returns: a column named by the variable's id (floating
        species as concentrations, and the variables a rule drives).  An amount, and anything else the wrapper leaves out, is
        refused with W-7."""
        who = self.WHO[args["family"]]
        for v in names:
            if v == "time":
                continue
            kind = model.kind_of(v)
            if kind in ("species_amount", "unknown"):
                what = "not in the model" if kind == "unknown" else "an amount (the wrapper returns concentrations)"
                raise rt.BackendCannotRun(f"W-7: {who} cannot return {v!r}: {what}", backend=args["family"])
            if v not in available:
                raise rt.BackendCannotRun(f"W-7: {who} did not return {v!r} ({kind.replace('_', ' ')}; it returns floating "
                                          "species and the variables rules drive)", backend=args["family"])


class SedVivaOde(SedViva):
    def run(self, state, args):
        model = self.val(state, args["model"])
        names = self.strings(state, args["outputVariables"])
        if args["family"] == "tellurium":
            times = [float(x) for x in state["raw_time_series"]]
            columns = {k: [float(x) for x in v] for k, v in state["raw_species_trajectories"].items()}
        else:
            res = state["raw_result"]
            times = [float(x) for x in res["time"]]
            rows = np.asarray(res["values"], dtype=float).reshape(len(times), -1)
            columns = {c: rows[:, i] for i, c in enumerate(res["columns"])}
        self.concentrations(model, names, columns, args)
        cols = [np.asarray(times if v == "time" else columns[v], dtype=float) for v in names]
        table = np.column_stack([np.asarray(times, dtype=float)] + cols) if cols else np.asarray(times, dtype=float)[:, None]
        return {"data": rt.AnnotatedData(table, [None, [args["label"]] + list(names)], ["", ""])}


class SedVivaSteady(SedViva):
    def run(self, state, args):
        model = self.val(state, args["model"])
        names = self.strings(state, args["outputVariables"])
        if "time" in names:
            raise rt.DataError("'time' has no value at a steady state")
        if args["family"] == "tellurium":
            values = {k: float(v) for k, v in state["raw_steady_state_concentrations"].items()}
        else:
            values = {k: float(v[0]) for k, v in state["raw_results"]["species_concentrations"].items()}
        self.concentrations(model, names, values, args)
        return {"data": rt.AnnotatedData(np.array([values[v] for v in names], dtype=float), [list(names)], [""])}


# ---------------------------------------------------------------------------- outputs

class SedOutput(SedStep):
    """An output step: a failure is recorded and printed, and the other outputs still run (the script contract)."""
    OUT = ("manifest", "failures")

    def run(self, state, args):
        ctx = self.ctx(state)
        with ctx.step(self.config["id"]):
            self.write(ctx, state, args)
        return {"manifest": ctx.manifest, "failures": [list(f) for f in ctx.failures]}

    def write(self, ctx, state, args):  # pragma: no cover
        raise NotImplementedError


class SedReport(SedOutput):
    def write(self, ctx, state, args):
        rt.write_report(ctx, self.config["id"], self.val(state, args["data"]))


class SedPlot2D(SedOutput):
    def write(self, ctx, state, args):
        curves = []
        for c in args["curves"]:
            curves.append({"id": c["id"], "position": c["position"], "type": self._opt(state, c["type"], self.text),
                           "order": self._opt(state, c["order"], self.integer), "y_axis": self._opt(state, c["yAxis"], self.text),
                           "fields": {k: self.val(state, p) for k, p in c["fields"].items()}})
        rt.plots.plot2d(ctx, self.config["id"], curves, self._options(state, args["options"]))

    def _opt(self, state, item, how):
        return None if item is None else how(state, item)

    def _options(self, state, spec):
        axes = {}
        for key, axis in spec["axes"].items():
            axes[key] = {a: {"scale": self.text, "min": self.num, "max": self.num, "grid": self.flag, "reverse": self.flag}[a](state, item)
                         for a, item in axis.items()}
        out = {"axes": axes}
        for attr, how in (("legend", self.flag), ("width", self.num), ("height", self.num)):
            out[attr] = self._opt(state, spec.get(attr), how)
        return out


class SedPlot3D(SedPlot2D):
    def write(self, ctx, state, args):
        surfaces = []
        for s in args["surfaces"]:
            surfaces.append({"id": s["id"], "position": s["position"], "type": self._opt(state, s["type"], self.text),
                             "order": self._opt(state, s["order"], self.integer),
                             "fields": {k: self.val(state, p) for k, p in s["fields"].items()}})
        rt.plots.plot3d(ctx, self.config["id"], surfaces, self._options(state, args["options"]))
