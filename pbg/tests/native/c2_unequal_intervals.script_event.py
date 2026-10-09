# generated from a process-bigraph document by pbg2py (prototype); reading mode: event
import importlib, json
from process_bigraph import allocate_core
core = allocate_core()
END = 4.0
MODE = "event"
STATE = json.loads('{"x": 1.0, "y": 0.0, "global_time": 0.0}')
PROCS = json.loads('{"p1": {"address": "local:!loopsteps2.P1", "interval": 1.0, "config": {}, "inputs": {"x": ["x"], "y": ["y"]}, "outputs": {"x": ["x"]}}, "p2": {"address": "local:!loopsteps2.P2", "interval": 2.0, "config": {}, "inputs": {"x": ["x"], "y": ["y"]}, "outputs": {"y": ["y"]}}}')

def get(path):
    v = STATE
    for k in path: v = v[k]
    return v
def put(path, value):
    d = STATE
    for k in path[:-1]: d = d[k]
    d[path[-1]] = value

inst, order = {}, list(PROCS)
for name in order:
    mod, cls = PROCS[name]["address"].split("!")[1].rsplit(".", 1)
    inst[name] = getattr(importlib.import_module(mod), cls)(PROCS[name]["config"], core=core)

def read(name):
    return {port: get(path) for port, path in PROCS[name]["inputs"].items()}

def run(name, state, interval):
    return inst[name].update(state, interval)

def merge(deltas):
    """combine all deltas aimed at one store, then apply: overwrite[...] replaces, numbers add"""
    out = {}
    for name, delta in deltas:
        outs = inst[name].outputs()
        for port, d in delta.items():
            key = tuple(PROCS[name]["outputs"][port])
            kind = "replace" if str(outs[port]).startswith("overwrite") else "add"
            out.setdefault(key, []).append((kind, d))
    for key, items in out.items():
        cur = get(list(key))
        reps = [d for k, d in items if k == "replace"]
        if reps: cur = reps[-1]
        cur = cur + sum(d for k, d in items if k == "add")
        put(list(key), cur)

def row(t):
    return [t] + [get(p) for p in [['x'], ['y']]]

rows, t = [row(0.0)], 0.0
tnext = {n: PROCS[n]["interval"] for n in order}
stash = {}
if MODE == "start":     # read at the start of the interval, apply at its end (process-bigraph 1.8.5, measured)
    for n in order: stash[n] = run(n, read(n), PROCS[n]["interval"])
while True:
    t_star = min(tnext.values())
    if t_star > END + 1e-12: break
    due = [n for n in order if abs(tnext[n] - t_star) < 1e-12]
    if MODE == "start":
        merge([(n, stash[n]) for n in due]); t = t_star
        for n in due:
            stash[n] = run(n, read(n), PROCS[n]["interval"]); tnext[n] = t + PROCS[n]["interval"]
    else:               # "event": read at the event time, apply at once (formal rule of S1 3.8.2, one reading)
        deltas = [(n, run(n, read(n), PROCS[n]["interval"])) for n in due]
        merge(deltas); t = t_star
        for n in due: tnext[n] = t + PROCS[n]["interval"]
    rows.append(row(t))
print(json.dumps(rows))
