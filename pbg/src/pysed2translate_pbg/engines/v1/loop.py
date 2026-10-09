"""Repeats: Loop in the clock form (SedLoop + SedClock), Scatter and ParameterScan as nested repeats (SedRepeat).

Both are one Step of the outer document whose config holds an inner document (the sub-task steps, wired exactly as the
outer tasks are).  The inner document is run by a `Composite` that the Step builds, so the tasks after a repeat run once,
after it has finished (plan 3.8; tested in 2.9).  Inner store paths equal the outer ones: everything a sub-task reads from
outside (`document.free`) is copied into the inner state at the same path before the run.

Loop: a SedClock *process* (interval 1) ticks once per iteration.  Tick k + 1 shows iteration k: the process writes the range
value, the index, the guard (k) and the loop variables; the inner steps then run in dependency order; the process reads the
subsequent values at the start of its next interval and hands them on.  Until the first tick the guard is -1, which keeps
every inner step quiet (they all fire once at the start of a run).  A SedCollect step records the outputVariableMap entries
once per tick.

Scatter / ParameterScan: one inner Composite per iteration, with the guard at 0.
"""
from __future__ import annotations

import copy
import itertools

from process_bigraph import Composite, Process

from pysed2translate_pbg import host

from .steps import SedStep

rt = host.rt


def apply_index(value, index):
    """The bracket indices of a reference (as stored in configs) applied to data."""
    if index:
        value = value.index([[(k, tuple(x) if k == "range" else x) for k, x in group] for group in index])
    return value


def put(state: dict, path, value) -> None:
    node = state
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = value


class SedClock(Process):
    """Ticks once per iteration (interval 1).  Config: `points` (the range values), `loopVars` [{"name", "index"}]."""
    config_schema = {"points": "quote", "loopVars": "quote"}

    def __init__(self, config=None, core=None):
        super().__init__(config, core)
        self.k = 0

    def _names(self):
        return [lv["name"] for lv in (self.config.get("loopVars") or [])]

    def inputs(self):
        ports = {}
        for n in self._names():
            ports["init_" + n] = "quote"
            ports["subs_" + n] = "quote"
        return ports

    def outputs(self):
        ports = {"range": "quote", "index": "quote", "guard": "quote"}
        for n in self._names():
            ports["lv_" + n] = "quote"
        return ports

    def update(self, state, interval):
        k = self.k
        self.k += 1
        points = self.config.get("points") or []
        if k >= len(points):
            return {}
        out = {"range": rt.AnnotatedData(points[k]), "index": rt.AnnotatedData(float(k)), "guard": k}
        for lv in self.config.get("loopVars") or []:
            n = lv["name"]
            out["lv_" + n] = state["init_" + n] if k == 0 else apply_index(state["subs_" + n], lv.get("index"))
        return out


class SedCollect(SedStep):
    """Records the outputVariableMap entries once per tick (keyed by the guard, so a repeated firing replaces a row)."""
    OUT = ()

    def __init__(self, config=None, core=None):
        super().__init__(config, core)
        self._rows: dict = {}

    @property
    def rows(self) -> list:
        return [self._rows[k] for k in sorted(self._rows)]

    def run(self, state, args):
        self._rows[state["guard"]] = [self.val(state, p) for p in args["order"]]
        return {}


class _Repeat(SedStep):
    """Shared by SedLoop and SedRepeat: the inner document and the Composite that runs it."""
    OUT = ("data",)
    config_schema = {**SedStep.config_schema, "document": "quote"}

    def inputs(self):
        ports = super().inputs()
        for p in (self.config.get("document") or {}).get("free", {}):
            ports[p] = "quote"
        return ports

    def _inner(self, state, guard, extra=None):
        """A fresh inner state with the free values copied in."""
        doc = copy.deepcopy(self.config["document"])
        inner = {"guard": guard}
        for port, path in doc["free"].items():
            put(inner, path, state[port])
        for path, value in (extra or {}).items():
            put(inner, path, value)
        inner.update(doc["nodes"])
        return inner

    def _run_inner(self, inner, duration):
        c = Composite({"state": inner}, core=self.core)
        c.run(float(duration))
        return c


class SedLoop(_Repeat):
    def run(self, state, args):
        points = rt.ops.numbers_from(self.range_data(state, args["range"]))
        inner = self._inner(state, -1)
        inner["loopinit"] = {lv["name"]: self.template(state, lv["initial"]) for lv in args["loopVars"]}
        inner["clock"]["config"]["points"] = points
        c = self._run_inner(inner, len(points))
        rows = c.state["collect"]["instance"].rows
        return {"data": rt.ops.repeat_table(points, rows, args["keys"])}


class SedRepeat(_Repeat):
    def run(self, state, args):
        keys, rows = args["keys"], []
        rep = args["rep"]
        if args["kind"] == "loop":
            return self._run_nested_loop(state, args, rep)
        if args["kind"] == "scatter":
            points = rt.ops.numbers_from(self.range_data(state, args["range"]))
            for i, value in enumerate(points):
                inner = self._inner(state, 0, {("tasks", rep, "range"): rt.AnnotatedData(value),
                                               ("tasks", rep, "index"): rt.AnnotatedData(float(i))})
                rows.append(self._run_inner(inner, 0.0).state["collect"]["instance"].rows[0])
            return {"data": rt.ops.repeat_table(points, rows, keys)}
        names = list(args["elements"])
        ranges = [rt.ops.numbers_from(self.range_data(state, r)) for r in args["ranges"]]
        base = self.val(state, args["model"])
        for ix in rt.ops.grid([len(r) for r in ranges]):
            vals = [r[k] for r, k in zip(ranges, ix)]
            inner = self._inner(state, 0, {("tasks", rep, "model"): base.with_values(dict(zip(names, vals))),
                                           ("tasks", rep, "ranges"): rt.ops.labeled_vector(names, vals),
                                           ("tasks", rep, "indexes"): rt.ops.labeled_vector(names, [float(k) for k in ix])})
            rows.append(self._run_inner(inner, 0.0).state["collect"]["instance"].rows[0])
        return {"data": rt.ops.scan_table(rows, ranges, names, keys)}

    def _run_nested_loop(self, state, args, rep):
        """The Loop, one inner composite per iteration; the loop variables are carried from one iteration to the next here."""
        points = rt.ops.numbers_from(self.range_data(state, args["range"]))
        carried = {lv["name"]: self.template(state, lv["initial"]) for lv in args["loopVars"]}
        rows = []
        for i, value in enumerate(points):
            extra = {("tasks", rep, "range"): rt.AnnotatedData(value), ("tasks", rep, "index"): rt.AnnotatedData(float(i))}
            for lv in args["loopVars"]:
                extra[tuple(lv["subsequent"]["target"])] = carried[lv["name"]]
            c = self._run_inner(self._inner(state, 0, extra), 0.0)
            rows.append(c.state["collect"]["instance"].rows[0])
            nxt = {}
            for lv in args["loopVars"]:
                v = c.state
                for key in lv["subsequent"]["store"]:
                    v = v[key]
                nxt[lv["name"]] = apply_index(v, lv["subsequent"]["index"])
            carried = nxt
        return {"data": rt.ops.repeat_table(points, rows, args["keys"])}
