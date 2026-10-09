#!/usr/bin/env python3
# generated from a process-bigraph document by pbg2py; reading: start
import importlib, json, sys
from process_bigraph import allocate_core
core = allocate_core()
END = 0.0
MODE = 'start'
WATCH = []
STATE = json.loads('{"constants": {"ode_interval": 1.0}, "context": {"inputDir": ".", "outputDir": "results", "prefix": "00282", "png": true}}')
NODES = json.loads('{"task_ODEmodel": {"kind": "step", "address": "local:!pysed2translate_pbg.engines.v1.steps.SedModelImport", "interval": null, "config": {"id": "ODEmodel", "args": {"location": "00282.ode.sbml", "language": "urn:sedml:language:sbml"}, "context": true}, "inputs": {"context": ["context"]}, "outputs": {"model": ["tasks", "ODEmodel", "model"]}}, "task_FBAmodel": {"kind": "step", "address": "local:!pysed2translate_pbg.engines.v1.steps.SedModelImport", "interval": null, "config": {"id": "FBAmodel", "args": {"location": "00282.fba.sbml", "language": "urn:sedml:language:sbml"}, "context": true}, "inputs": {"context": ["context"]}, "outputs": {"model": ["tasks", "FBAmodel", "model"]}}, "task_repeat": {"kind": "step", "address": "local:!pysed2translate_pbg.engines.v1.loop.SedLoop", "interval": null, "config": {"id": "repeat", "refs": {"r0": {"const": false, "index": null}, "r1": {"const": false, "index": null}}, "args": {"range": {"kind": "numeric", "items": {"start": {"value": 1.0}, "interval": {"value": 1.0}, "number_of_steps": {"value": 7.0}}}, "keys": ["species_trace"], "loopVars": [{"name": "ODE_model", "initial": {"ref": "r0"}}, {"name": "FBA_model", "initial": {"ref": "r1"}}]}, "document": {"nodes": {"task_repeat_subTasks_odesim": {"_type": "step", "address": "local:!pysed2translate_pbg.engines.v1.steps.SedOdeSimulation", "config": {"id": "repeat:subTasks:odesim", "refs": {"r0": {"const": false, "index": null}, "r1": {"const": true, "index": null}}, "args": {"mode": "points", "model": "r0", "independentVariable": "time", "label": "urn:sedml:symbol:time", "outputVariables": {"value": ["S", "B", "R_EX_S_lower_bound"]}, "algorithm": "KISAO:0000694", "settings": {}, "init": {"value": 0.0}, "range": {"kind": "numeric", "items": {"start": {"value": 0.0}, "end": {"ref": "r1"}, "number_of_steps": {"value": 4.0}, "scale": {"value": "linear"}}}}, "guard": true, "backend": "roadrunner"}, "inputs": {"guard": ["guard"], "r0": ["tasks", "repeat:loopVariables:ODE_model", "data"], "r1": ["constants", "ode_interval"]}, "outputs": {"data": ["tasks", "repeat:subTasks:odesim", "data"], "model": ["tasks", "repeat:subTasks:odesim", "model"]}}, "task_repeat_subTasks_new_fba": {"_type": "step", "address": "local:!pysed2translate_pbg.engines.v1.steps.SedModelChange", "config": {"id": "repeat:subTasks:new_fba", "refs": {"r0": {"const": false, "index": null}, "r1": {"const": false, "index": [[["int", -1], ["label", "R_EX_S_lower_bound"]]]}}, "args": {"inputModel": "r0", "setValues": {"value": {"R_EX_S_lower_bound": {"t": {"ref": "r1"}}}}}, "guard": true}, "inputs": {"guard": ["guard"], "r0": ["tasks", "repeat:loopVariables:FBA_model", "data"], "r1": ["tasks", "repeat:subTasks:odesim", "data"]}, "outputs": {"model": ["tasks", "repeat:subTasks:new_fba", "model"]}}, "task_repeat_subTasks_fbasim": {"_type": "step", "address": "local:!pysed2translate_pbg.engines.v1.steps.SedFba", "config": {"id": "repeat:subTasks:fbasim", "refs": {"r0": {"const": false, "index": null}}, "args": {"model": "r0", "outputVariables": {"value": ["R_EX_S", "R_BIOMASS"]}, "algorithm": "KISAO:0000437"}, "guard": true, "backend": "cobra"}, "inputs": {"guard": ["guard"], "r0": ["tasks", "repeat:subTasks:new_fba", "model"]}, "outputs": {"data": ["tasks", "repeat:subTasks:fbasim", "data"], "model": ["tasks", "repeat:subTasks:fbasim", "model"]}}, "task_repeat_subTasks_new_ode": {"_type": "step", "address": "local:!pysed2translate_pbg.engines.v1.steps.SedModelChange", "config": {"id": "repeat:subTasks:new_ode", "refs": {"r0": {"const": false, "index": null}, "r1": {"const": false, "index": [[["label", "R_EX_S"]]]}, "r2": {"const": false, "index": [[["label", "R_BIOMASS"]]]}}, "args": {"inputModel": "r0", "setValues": {"value": {"R_EX_S": {"t": {"ref": "r1"}}, "R_BIOMASS": {"t": {"ref": "r2"}}}}}, "guard": true}, "inputs": {"guard": ["guard"], "r0": ["tasks", "repeat:subTasks:odesim", "model"], "r1": ["tasks", "repeat:subTasks:fbasim", "data"], "r2": ["tasks", "repeat:subTasks:fbasim", "data"]}, "outputs": {"model": ["tasks", "repeat:subTasks:new_ode", "model"]}}, "collect": {"_type": "step", "address": "local:!pysed2translate_pbg.engines.v1.loop.SedCollect", "config": {"id": "repeat:collect", "refs": {"r0": {"const": false, "index": null}}, "args": {"order": ["r0"]}, "guard": true}, "inputs": {"guard": ["guard"], "r0": ["tasks", "repeat:subTasks:odesim", "data"]}, "outputs": {}}, "clock": {"_type": "process", "address": "local:!pysed2translate_pbg.engines.v1.loop.SedClock", "interval": 1.0, "config": {"loopVars": [{"name": "ODE_model", "index": null}, {"name": "FBA_model", "index": null}]}, "inputs": {"init_ODE_model": ["loopinit", "ODE_model"], "subs_ODE_model": ["tasks", "repeat:subTasks:new_ode", "model"], "init_FBA_model": ["loopinit", "FBA_model"], "subs_FBA_model": ["tasks", "repeat:subTasks:fbasim", "model"]}, "outputs": {"range": ["tasks", "repeat", "range"], "index": ["tasks", "repeat", "index"], "guard": ["guard"], "lv_ODE_model": ["tasks", "repeat:loopVariables:ODE_model", "data"], "lv_FBA_model": ["tasks", "repeat:loopVariables:FBA_model", "data"]}}}, "free": {"f0": ["constants", "ode_interval"]}}}, "inputs": {"r0": ["tasks", "ODEmodel", "model"], "r1": ["tasks", "FBAmodel", "model"], "f0": ["constants", "ode_interval"]}, "outputs": {"data": ["tasks", "repeat", "data"]}}, "output_cosim_output": {"kind": "step", "address": "local:!pysed2translate_pbg.engines.v1.steps.SedReport", "interval": null, "config": {"id": "cosim_output", "refs": {"r0": {"const": false, "index": [[["range", [null, null]], ["label", "species_trace"]]]}}, "args": {"data": "r0"}, "context": true}, "inputs": {"context": ["context"], "r0": ["tasks", "repeat", "data"]}, "outputs": {"manifest": ["manifest", "cosim_output"], "failures": ["failures", "cosim_output"]}}}')        # name -> {kind, address, config, interval, inputs, outputs}
ORDER = ['task_ODEmodel', 'task_FBAmodel', 'task_repeat', 'output_cosim_output']                     # step names in dependency order
if len(sys.argv) > 2 and "context" in STATE:       # script INPUT_DIR OUTPUT_DIR: where an engine document finds models and writes reports
    STATE["context"].update(inputDir=sys.argv[1], outputDir=sys.argv[2], png=False)

def get(path):
    v = STATE
    for k in path: v = v[k]
    return v
def put(path, value):
    d = STATE
    for k in path[:-1]: d = d.setdefault(k, {})
    d[path[-1]] = value

inst = {}
for name, n in NODES.items():
    mod, cls = n["address"].split("!")[1].rsplit(".", 1)
    inst[name] = getattr(importlib.import_module(mod), cls)(n["config"], core=core)
PROCS = [k for k, n in NODES.items() if n["kind"] == "process"]
STEPS = ORDER

def read(name):
    return {port: get(path) for port, path in NODES[name]["inputs"].items()}

def merge(deltas):
    """combine all deltas aimed at one store, then apply: overwrite[...] replaces, numbers add"""
    out = {}
    for name, delta in deltas:
        outs = inst[name].outputs()
        for port, d in delta.items():
            key = tuple(NODES[name]["outputs"][port])
            kind = "replace" if str(outs[port]).startswith("overwrite") else "add"
            out.setdefault(key, []).append((kind, d))
    changed = set()
    for key, items in out.items():
        cur = get(list(key))
        reps = [d for k, d in items if k == "replace"]
        if reps: cur = reps[-1]
        cur = cur + sum(d for k, d in items if k == "add")
        put(list(key), cur); changed.add(key)
    return changed

def touches(a, b):
    n = min(len(a), len(b)); return tuple(a[:n]) == tuple(b[:n])

def run_steps(changed, first=False):
    """run the steps that read a changed store (all of them the first time), in dependency order"""
    for name in STEPS:
        ins = NODES[name]["inputs"].values()
        if first or any(touches(i, c) for i in ins for c in changed):
            result = inst[name].update(read(name))
            for port, value in (result or {}).items():
                if port in NODES[name]["outputs"]:
                    path = NODES[name]["outputs"][port]; put(path, value); changed.add(tuple(path))
    return changed

def row(t):
    return [t] + [get(p) for p in WATCH]

rows = []
if STEPS: run_steps(set(), first=True)
rows.append(row(0.0))
t = 0.0
tnext = {n: NODES[n]["interval"] for n in PROCS}
stash = {}
if MODE == "start":
    for n in PROCS: stash[n] = inst[n].update(read(n), NODES[n]["interval"])
while PROCS:
    t_star = min(tnext.values())
    if t_star > END + 1e-12: break
    due = [n for n in PROCS if abs(tnext[n] - t_star) < 1e-12]
    if MODE == "start":
        changed = merge([(n, stash[n]) for n in due]); t = t_star
        run_steps(changed)
        for n in due:
            stash[n] = inst[n].update(read(n), NODES[n]["interval"]); tnext[n] = t + NODES[n]["interval"]
    else:
        deltas = [(n, inst[n].update(read(n), NODES[n]["interval"])) for n in due]
        changed = merge(deltas); t = t_star
        run_steps(changed)
        for n in due: tnext[n] = t + NODES[n]["interval"]
    rows.append(row(t))
print(json.dumps(rows))
