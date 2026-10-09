"""Writes the first two tier C cases into ../tests/native/ : the document, the translated script (both scheduling readings),
the case sidecar, and the expected rows (the framework's rows; the other reading's rows).
Run from this folder:  PYTHONPATH=. python make_tier_c.py     (needs process-bigraph 1.8.5)"""
import json, os, subprocess, sys
from process_bigraph import Composite, allocate_core
import pbg2py
OUT = os.path.join('..', 'tests', 'native'); os.makedirs(OUT, exist_ok=True)
core = allocate_core(); A = 'local:!loopsteps2.'

def doc(i2):
    return {"x": 1.0, "y": 0.0,
      "p1": {"_type": "process", "address": A + "P1", "interval": 1.0, "inputs": {"x": ["x"], "y": ["y"]}, "outputs": {"x": ["x"]}},
      "p2": {"_type": "process", "address": A + "P2", "interval": i2, "inputs": {"x": ["x"], "y": ["y"]}, "outputs": {"y": ["y"]}},
      "emitter": {"_type": "step", "address": "local:RAMEmitter", "config": {"emit": {"t": "float", "x": "float", "y": "float"}},
                  "inputs": {"t": ["global_time"], "x": ["x"], "y": ["y"]}}}

def rows_of(c): return [[r['t'], round(r['x'], 6), round(r['y'], 6)] for r in c.state['emitter']['instance'].query()]

cases = {'c1_equal_intervals': (1.0, 3.0), 'c2_unequal_intervals': (2.0, 4.0)}
for name, (i2, end) in cases.items():
    d = doc(i2)
    json.dump({"state": d}, open(f'{OUT}/{name}.pbg.composite.json', 'w'), indent=2); open(f'{OUT}/{name}.pbg.composite.json', 'a').write('\n')
    json.dump({"end": end, "watch": ["x", "y"], "modules": ["loopsteps2"]}, open(f'{OUT}/{name}.case.json', 'w'), indent=2)
    c = Composite({"state": d}, core=core); c.run(end)
    json.dump(rows_of(c), open(f'{OUT}/{name}.expected_framework.json', 'w'))
    for mode in ('start', 'event'):
        src = pbg2py.export(d, end, mode, ['x', 'y'])
        open(f'{OUT}/{name}.script_{mode}.py', 'w').write(src)
        r = subprocess.run([sys.executable, f'{OUT}/{name}.script_{mode}.py'], capture_output=True, text=True,
                           env={**os.environ, 'PYTHONPATH': '.'})
        rows = [[a, round(b, 6), round(cc, 6)] for a, b, cc in json.loads(r.stdout.strip().splitlines()[-1])]
        json.dump(rows, open(f'{OUT}/{name}.expected_{mode}.json', 'w'))
        print(name, mode, 'agrees with the framework' if rows == rows_of(c) else 'DIFFERS from the framework')
