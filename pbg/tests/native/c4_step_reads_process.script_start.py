#!/usr/bin/env python3
# generated from a process-bigraph document by pbg2py; reading: start
import importlib, json, sys
from process_bigraph import allocate_core
core = allocate_core()
END = 3.0
MODE = 'start'
WATCH = [['x'], ['y'], ['s']]
STATE = json.loads('{"x": 1.0, "y": 0.0, "s": 0.0}')
NODES = json.loads('{"p1": {"kind": "process", "address": "local:!procs.P1", "interval": 1.0, "config": {}, "inputs": {"x": ["x"], "y": ["y"]}, "outputs": {"x": ["x"]}}, "p2": {"kind": "process", "address": "local:!procs.P2", "interval": 1.0, "config": {}, "inputs": {"x": ["x"], "y": ["y"]}, "outputs": {"y": ["y"]}}, "sum": {"kind": "step", "address": "local:!procs.Sum", "interval": null, "config": {}, "inputs": {"x": ["x"], "y": ["y"]}, "outputs": {"s": ["s"]}}}')        # name -> {kind, address, config, interval, inputs, outputs}
ORDER = ['sum']                     # step names in dependency order
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
