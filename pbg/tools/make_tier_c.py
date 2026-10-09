#!/usr/bin/env python3
"""Write the tier C cases into ../tests/native/: for each case the document, the case sidecar, the rows process-bigraph produces
(`expected_framework`), and, for each scheduling reading, the script translated by pbg2py and the rows it prints.

    cd pbg/tools && python make_tier_c.py          (needs process-bigraph 1.8.5, roadrunner and cobra for C3)

C5 is different: the document is the one the engine writes for suite case 00282 (a cosimulation Loop), exported with its Steps only.
It has no rows; the case compares the report files of `pysed2translate-pbg run` and of the exported script (tests/native/test_tier_c.py).
"""
import copy
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NATIVE = os.path.abspath(os.path.join(HERE, "..", "tests", "native"))
sys.path.insert(0, HERE)
sys.path.insert(0, NATIVE)

from process_bigraph import Composite, allocate_core  # noqa: E402

import pbg2py  # noqa: E402

A = "local:!procs."
core = allocate_core()


def emitter(watch):
    return {"_type": "step", "address": "local:RAMEmitter", "config": {"emit": {"t": "float", **{w: "float" for w in watch}}},
            "inputs": {"t": ["global_time"], **{w: [w] for w in watch}}}


def xy(i2, with_sum=False):
    d = {"x": 1.0, "y": 0.0,
         "p1": {"_type": "process", "address": A + "P1", "interval": 1.0, "inputs": {"x": ["x"], "y": ["y"]}, "outputs": {"x": ["x"]}},
         "p2": {"_type": "process", "address": A + "P2", "interval": i2, "inputs": {"x": ["x"], "y": ["y"]}, "outputs": {"y": ["y"]}}}
    watch = ["x", "y"]
    if with_sum:
        d["s"] = 0.0
        d["sum"] = {"_type": "step", "address": A + "Sum", "config": {}, "inputs": {"x": ["x"], "y": ["y"]}, "outputs": {"s": ["s"]}}
        watch.append("s")
    d["emitter"] = emitter(watch)
    return d, watch


def monod():
    u0 = -50.0 / 12.0
    d = {"S": 10.0, "B": 0.02, "u": u0, "mu": -u0 * 0.1, "lb": u0,
         "ode": {"_type": "process", "address": A + "OdeProc", "interval": 1.0, "config": {},
                 "inputs": {"S": ["S"], "B": ["B"], "u": ["u"], "mu": ["mu"]}, "outputs": {"S": ["S"], "B": ["B"], "lb": ["lb"]}},
         "fba": {"_type": "process", "address": A + "FbaProc", "interval": 1.0, "config": {},
                 "inputs": {"lb": ["lb"]}, "outputs": {"u": ["u"], "mu": ["mu"]}}}
    watch = ["S", "B", "lb", "u", "mu"]
    d["emitter"] = emitter(watch)
    return d, watch


def rows_of(c, watch):
    return [[r["t"]] + [round(r[w], 6) for w in watch] for r in c.state["emitter"]["instance"].query()]


def dump(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")


def main() -> int:
    cases = {"c1_equal_intervals": (xy(1.0), 3.0), "c2_unequal_intervals": (xy(2.0), 4.0),
             "c3_ode_fba_processes": (monod(), 8.0), "c4_step_reads_process": (xy(1.0, True), 3.0)}
    env = {**os.environ, "PYTHONPATH": NATIVE + os.pathsep + os.environ.get("PYTHONPATH", "")}
    for name, ((d, watch), end) in cases.items():
        dump(f"{NATIVE}/{name}.pbg.composite.json", {"state": d})
        dump(f"{NATIVE}/{name}.case.json", {"end": end, "watch": watch, "modules": ["procs"]})
        c = Composite({"state": copy.deepcopy(d)}, core=core)
        c.run(end)
        framework = rows_of(c, watch)
        dump(f"{NATIVE}/{name}.expected_framework.json", framework)
        for mode in ("start", "event"):
            src = pbg2py.export(d, end, mode, watch)
            with open(f"{NATIVE}/{name}.script_{mode}.py", "w", encoding="utf-8", newline="\n") as f:
                f.write(src)
            r = subprocess.run([sys.executable, f"{NATIVE}/{name}.script_{mode}.py"], capture_output=True, text=True, env=env)
            if r.returncode:
                print(r.stderr, file=sys.stderr)
                raise SystemExit(f"{name} {mode}: the script failed")
            rows = [[row[0]] + [round(v, 6) for v in row[1:]] for row in json.loads(r.stdout.strip().splitlines()[-1])]
            dump(f"{NATIVE}/{name}.expected_{mode}.json", rows)
            print(name, mode, "agrees with the framework" if rows == framework else "DIFFERS from the framework")
    c5()
    return 0


def c5():
    """The cosimulation of suite case 00282 as the engine writes it (clock-form Loop), exported as a script of Steps."""
    from pysed2translate_pbg import host
    from pysed2translate_pbg.api import Options
    from pysed2translate_pbg.engines import v1

    data = os.path.join(NATIVE, "data")
    document = host.load_document(os.path.join(data, "00282.sed2.json"))
    result = v1.translate(document, Options(backend={"*": "roadrunner"}, prefix="00282", source_name="00282.sed2.json", engine={"wrappers": "off"}))
    text = next(iter(result.files.values()))
    path = os.path.join(NATIVE, "c5_cosimulation_clock.pbg.composite.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    state = json.loads(text)["state"]
    with open(os.path.join(NATIVE, "c5_cosimulation_clock.script.py"), "w", encoding="utf-8", newline="\n") as f:
        f.write(pbg2py.export(state, 0.0, "start", []))
    print("c5_cosimulation_clock written (compare with tests/native/test_tier_c.py)")


if __name__ == "__main__":
    sys.exit(main())
