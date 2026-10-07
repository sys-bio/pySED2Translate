"""Smoke test: run one analytic model on all three backends and compare to the exact answer.

Model: S1 -> S2 with rate k1*S1 (k1 = 1), S1(0) = 1.5e-4.  Exact: S1(t) = S1(0) * exp(-t).
Tolerance (SBML test suite style): |actual - exact| <= abs + rel * |exact|, abs = 1e-7, rel = 1e-4.
Solver tolerances are set explicitly on every backend; OpenCOR's defaults were not tight enough.

Usage:  python scripts/smoke_test.py
Exit code 0 if every backend passes.
"""
import os
import sys
import tempfile

import numpy as np

ABS_TOL, REL_TOL = 1e-7, 1e-4
S1_0, K1, T_END, STEPS = 1.5e-4, 1.0, 5.0, 50

ANTIMONY = f"""
model smoke
  compartment C = 1
  species S1 in C = {S1_0}, S2 in C = 0
  k1 = {K1}
  J0: S1 -> S2; k1*S1*C
end
"""


def scaled_error(actual, exact):
    return float(np.max(np.abs(actual - exact) / (ABS_TOL + REL_TOL * np.abs(exact))))


def run_roadrunner(sbml_path):
    import roadrunner
    r = roadrunner.RoadRunner(sbml_path)
    r.integrator.absolute_tolerance = 1e-12
    r.integrator.relative_tolerance = 1e-10
    return np.array(r.simulate(0, T_END, STEPS + 1, ["time", "S1"]))[:, 1]


def run_copasi(sbml_path):
    import basico
    basico.load_model(sbml_path)
    tc = basico.run_time_course(duration=T_END, intervals=STEPS, method="deterministic",
                                use_initial_values=True, update_model=False)
    col = [c for c in tc.columns if "S1" in c][0]
    return tc[col].values


def run_opencor(sbml_path, workdir):
    import libopencor as oc
    import sbml2cellml
    cellml_path = os.path.join(workdir, "smoke.cellml")
    sbml2cellml.convert_sbml2cellml(sbml_path, cellml_path)
    doc = oc.SedDocument(oc.File(cellml_path))
    sim = doc.simulations[0]
    sim.initial_time = 0
    sim.output_start_time = 0
    sim.output_end_time = T_END
    sim.number_of_steps = STEPS
    sim.ode_solver.absolute_tolerance = 1e-12
    sim.ode_solver.relative_tolerance = 1e-10
    inst = doc.instantiate()
    inst.run()
    task = inst.tasks[0]
    names = [task.state_name(i) for i in range(task.state_count)]
    idx = [i for i, n in enumerate(names) if n.endswith("S1")][0]
    return np.array(task.state(idx))


def main():
    import antimony
    antimony.loadAntimonyString(ANTIMONY)
    sbml = antimony.getSBMLString("smoke")
    t = np.linspace(0, T_END, STEPS + 1)
    exact = S1_0 * np.exp(-K1 * t)
    ok = True
    with tempfile.TemporaryDirectory() as d:
        sbml_path = os.path.join(d, "smoke.xml")
        with open(sbml_path, "w") as f:
            f.write(sbml)
        for name, fn in (("roadrunner", lambda: run_roadrunner(sbml_path)),
                         ("copasi", lambda: run_copasi(sbml_path)),
                         ("opencor", lambda: run_opencor(sbml_path, d))):
            try:
                err = scaled_error(fn(), exact)
                status = "PASS" if err <= 1.0 else "FAIL"
                ok &= err <= 1.0
                print(f"{name:11s} {status}  max scaled error = {err:.3g}")
            except Exception as e:  # report and keep going
                ok = False
                print(f"{name:11s} ERROR {type(e).__name__}: {e}")
    print(f"python {sys.version.split()[0]}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
