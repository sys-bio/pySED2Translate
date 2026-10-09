#!/usr/bin/env python3
"""Scheduler exporter: a process-bigraph document -> a standalone Python script (tier C oracle, route 2).

    python pbg2py.py DOC.pbg.composite.json --end 4 --reading start --watch x,y -o script.py
    python pbg2py.py DOC.pbg.composite.json --steps-only -o script.py        # a document of Steps only (engine output)

The script contains the document's store values, calls the `update` methods of the document's process and step classes, and
schedules them itself.  It does NOT use `Composite` or its scheduler (the classes themselves still import process-bigraph's
`Process`/`Step` base and `allocate_core`).  The scheduling rule is a stated reading, chosen with --reading:

  start  a process reads its inputs at the start of its interval and its update is applied at the end (what process-bigraph 1.8.5
         does, measured)
  event  a process reads its inputs at its event time and its update is applied at once (one reading of the formal rule; for
         unequal intervals it differs from the framework, see pbg/upstream/P-3.md)

Steps: every step runs once at time 0 and again after an event batch has changed a store it reads (steps that read what other steps
wrote follow in dependency order).  A step's outputs replace the stores they are wired to.  Emitter steps are not run; the script
records the stores named by --watch at time 0 and after every event batch.

The exporter lives outside the engine package (rule M3: the engine never imports it).
"""
import argparse
import json
import sys

TEMPLATE = '''#!/usr/bin/env python3
# generated from a process-bigraph document by pbg2py; reading: {mode}
import importlib, json, sys
{path_setup}from process_bigraph import allocate_core
core = allocate_core()
END = {end!r}
MODE = {mode!r}
WATCH = {watch!r}
STATE = json.loads({state!r})
NODES = json.loads({nodes!r})        # name -> {{kind, address, config, interval, inputs, outputs}}
ORDER = {order!r}                     # step names in dependency order
if len(sys.argv) > 2 and "context" in STATE:       # script INPUT_DIR OUTPUT_DIR: where an engine document finds models and writes reports
    STATE["context"].update(inputDir=sys.argv[1], outputDir=sys.argv[2], png=False)

def get(path):
    v = STATE
    for k in path: v = v[k]
    return v
def put(path, value):
    d = STATE
    for k in path[:-1]: d = d.setdefault(k, {{}})
    d[path[-1]] = value

inst = {{}}
for name, n in NODES.items():
    mod, cls = n["address"].split("!")[1].rsplit(".", 1)
    inst[name] = getattr(importlib.import_module(mod), cls)(n["config"], core=core)
PROCS = [k for k, n in NODES.items() if n["kind"] == "process"]
STEPS = ORDER

def read(name):
    return {{port: get(path) for port, path in NODES[name]["inputs"].items()}}

def merge(deltas):
    """combine all deltas aimed at one store, then apply: overwrite[...] replaces, numbers add"""
    out = {{}}
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
            for port, value in (result or {{}}).items():
                if port in NODES[name]["outputs"]:
                    path = NODES[name]["outputs"][port]; put(path, value); changed.add(tuple(path))
    return changed

def row(t):
    return [t] + [get(p) for p in WATCH]

rows = []
if STEPS: run_steps(set(), first=True)
rows.append(row(0.0))
t = 0.0
tnext = {{n: NODES[n]["interval"] for n in PROCS}}
stash = {{}}
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
'''


def _order_steps(steps: dict) -> list:
    """Step names so that a step comes after the steps that write what it reads."""
    def touches(a, b):
        n = min(len(a), len(b)); return list(a[:n]) == list(b[:n])
    done, order, left = set(), [], dict(steps)
    while left:
        ready = [k for k, s in left.items()
                 if not any(touches(o, i) for j, t in left.items() if j != k for o in t["outputs"].values() for i in s["inputs"].values())]
        if not ready:
            raise ValueError("the steps depend on each other in a cycle: " + ", ".join(left))
        for k in ready:
            order.append(k); del left[k]
    return order


def export(doc_state: dict, end: float, reading: str, watch: list, python_path: list = ()) -> str:
    nodes, stores = {}, {}
    for k, v in doc_state.items():
        if isinstance(v, dict) and v.get("_type") in ("process", "step"):
            if v.get("address", "").endswith("RAMEmitter") or v.get("address", "").endswith("Emitter"):
                continue
            nodes[k] = {"kind": v["_type"], "address": v["address"], "interval": v.get("interval"), "config": v.get("config", {}),
                        "inputs": v.get("inputs", {}), "outputs": v.get("outputs", {})}
        else:
            stores[k] = v
    steps = {k: n for k, n in nodes.items() if n["kind"] == "step"}
    setup = "".join(f"sys.path.insert(0, {p!r})\n" for p in python_path)
    return TEMPLATE.format(mode=reading, end=end, watch=[list(w) if isinstance(w, (list, tuple)) else [w] for w in watch],
                           state=json.dumps(stores), nodes=json.dumps(nodes), order=_order_steps(steps), path_setup=setup)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("document")
    ap.add_argument("--end", type=float, default=0.0)
    ap.add_argument("--reading", choices=("start", "event"), default="start")
    ap.add_argument("--watch", default="", help="comma-separated top-level store names recorded in the rows")
    ap.add_argument("--python-path", action="append", default=[], help="folder put on the script's sys.path (for the process classes)")
    ap.add_argument("-o", "--output")
    args = ap.parse_args(argv)
    with open(args.document, encoding="utf-8") as f:
        state = json.load(f)["state"]
    text = export(state, args.end, args.reading, [w for w in args.watch.split(",") if w], args.python_path)
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
