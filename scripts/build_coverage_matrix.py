"""Generate docs/task-coverage-matrix.md from the SED2 specsheets.

Reads every class under SED2/specsheets/{core,tasks,outputs,auxiliary}/<Class>/<version>/ and lists:
category, _type discriminator (blank = abstract/mixin), required attributes, output keys from
outputs.json, plus hand-maintained columns (expected backend support, planned test series, status).

Usage:  python scripts/build_coverage_matrix.py [SPECSHEETS_DIR] [OUT_MD]
Defaults: ../SED2/specsheets  and  docs/task-coverage-matrix.md

The hand-maintained columns live in the MANUAL dict below.  Backend entries are EXPECTATIONS to be
checked against the implemented backends (P2); where a cell names a limit, see GAPS.md and docs/environment-notes.md.
"""
import json
import os
import re
import sys

CATS = ["core", "tasks", "outputs", "auxiliary"]

# class -> (roadrunner, copasi, opencor, test series, status)
# Backend codes: Y expected, N expected not, ? unknown/verify, - not applicable (backend independent)
# Status: active, deferred (later phase), placeholder (spec not finished)
MANUAL = {
    "ModelImport": ("Y", "Y", "Y (via sbml2cellml)", "P4.3", "active"),
    "ExplicitODESimulation": ("Y", "Y", "Y", "P4.3", "active"),
    "OneStepODESimulation": ("Y", "Y", "Y", "P4.3", "active"),
    "BoundedODESimulation": ("Y", "Y", "N (uniform time courses only)", "P4.3", "active"),
    "SteadyState": ("Y", "Y", "N (libopencor issue 604)", "P4.4", "active"),
    "JacobianFull": ("Y", "Y (not at 0 values)", "N", "P4.4", "active"),
    "JacobianReduced": ("Y", "Y (not at 0 values)", "N", "P4.4", "active"),
    "ModelChange": ("Y", "Y", "Y (setValues, removeElements)", "P4.6", "active"),
    "Loop": ("Y", "Y", "Y", "P4.5", "active"),
    "Scatter": ("Y", "Y", "Y", "P4.5", "active"),
    "ParameterScan": ("Y", "Y", "Y", "P4.5", "active"),
    "Repeat": ("-", "-", "-", "P4.5", "abstract mixin"),
    "Range": ("-", "-", "-", "P4.5", "active"),
    "NumericRange": ("-", "-", "-", "P4.5", "active"),
    "ParameterRange": ("-", "-", "-", "P4.5", "active"),
    "Calculation": ("-", "-", "-", "P4.2", "active"),
    "AggregationCalculation": ("N", "N", "N (no function selector, S-006)", "P4.2", "active"),
    "RelabelData": ("-", "-", "-", "P4.2", "active"),
    "StringFormation": ("-", "-", "-", "P4.2", "active"),
    "CreateDataBlock": ("-", "-", "-", "P4.2", "active"),
    "ModelElementList": ("-", "-", "-", "P4.2", "active"),
    "DataImport": ("N", "N", "N (no formats defined, S-012)", "P4.6", "active"),
    "CsvImport": ("-", "-", "-", "P4.6", "active"),
    "Report": ("-", "-", "-", "P4.1", "active"),
    "Plot2D": ("-", "-", "-", "P4.6", "active"),
    "Plot3D": ("-", "-", "-", "P4.6", "active"),
    "Surface": ("-", "-", "-", "P4.6", "active"),
    "Curve": ("-", "-", "-", "P4.6", "active"),
    "Axis": ("-", "-", "-", "P4.6", "active"),
    "LoopVariable": ("-", "-", "-", "P4.5", "active"),
    "TaskParameter": ("-", "-", "-", "P4.5", "active"),
    "WorkingAlgorithm": ("-", "-", "-", "P4.3", "active"),
    "OutputParameter": ("-", "-", "-", "P4.1", "active"),
    "BoundedStochasticSimulation": ("?", "?", "?", "stochastic (later)", "deferred"),
    "ExplicitStochasticSimulation": ("?", "?", "?", "stochastic (later)", "deferred"),
    "OneStepStochasticSimulation": ("?", "?", "?", "stochastic (later)", "deferred"),
    "DrawFromDistribution": ("-", "-", "-", "stochastic (later)", "deferred"),
    "FluxBalanceAnalysis": ("N", "N", "N", "later phase", "deferred"),
    "Style": ("-", "-", "-", "none", "placeholder"),
    "Annotation": ("-", "-", "-", "tags (generate_tags.py)", "active"),
    "Span": ("-", "-", "-", "P4.3 (BoundedODESimulation)", "active"),
    # abstract bases / document-level classes: tested indirectly through the concrete classes
    "SEDBase": ("-", "-", "-", "all", "base"),
    "SEDDocument": ("-", "-", "-", "all", "base"),
    "Types": ("-", "-", "-", "P4.1", "base"),
    "AbstractTask": ("-", "-", "-", "all", "base"),
    "AbstractSimulation": ("-", "-", "-", "P4.3", "base"),
    "AbstractODESimulation": ("-", "-", "-", "P4.3", "base"),
    "AbstractStochasticSimulation": ("-", "-", "-", "stochastic (later)", "base"),
    "AbstractOutput": ("-", "-", "-", "all", "base"),
    "Plot": ("-", "-", "-", "P4.6", "base"),
    "AbstractCurve": ("-", "-", "-", "P4.6", "base"),
}


def latest_version_dir(class_dir):
    vs = [d for d in os.listdir(class_dir) if re.match(r"v\d", d)]
    vs.sort(key=lambda v: [int(x) for x in re.findall(r"\d+", v)])
    return os.path.join(class_dir, vs[-1]) if vs else None


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def parse_description(text):
    m = re.search(r"\*\*`_type` discriminator:\*\*\s*`\"([^\"]+)\"`", text)
    disc = m.group(1) if m else ""
    req, opt = [], []
    for line in text.splitlines():
        m = re.match(r"\|\s*`([^`]+)`\s*\|\s*([^|]*)\|\s*(yes|no)\s*\|", line)
        if m:
            (req if m.group(3) == "yes" else opt).append(m.group(1))
    return disc, req, opt


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, ".."))
    specs = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "..", "SED2", "specsheets")
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(root, "docs", "task-coverage-matrix.md")
    rows, missing_manual = [], []
    for cat in CATS:
        cdir = os.path.join(specs, cat)
        for cls in sorted(os.listdir(cdir)):
            vdir = latest_version_dir(os.path.join(cdir, cls))
            if not vdir:
                continue
            desc_path = os.path.join(vdir, "description.md")
            disc, req, opt = parse_description(read(desc_path)) if os.path.exists(desc_path) else ("", [], [])
            outs = []
            op = os.path.join(vdir, "outputs.json")
            if os.path.exists(op):
                for k, v in json.loads(read(op)).get("outputs", {}).items():
                    outs.append(f"{k}:{v.get('type')}")
            manual = MANUAL.get(cls)
            if manual is None:
                missing_manual.append(cls)
                manual = ("?", "?", "?", "unassigned", "unassigned")
            rows.append((cat, cls, disc, req, outs, manual))
    lines = [
        "# SED2 class coverage matrix",
        "",
        "Generated by `scripts/build_coverage_matrix.py` from the SED2 specsheets.  Do not hand-edit the",
        "generated columns; edit the MANUAL table in the script.  Backend columns are expectations to be",
        "verified when each backend is implemented (Y expected, N expected not, ? unknown, - backend independent).",
        "A `_type` of - means the class has no discriminator of its own (abstract base, mixin, or auxiliary child object).",
        "",
        "| Category | Class | _type | Required attributes | Outputs | Roadrunner | COPASI | OpenCOR | Test series | Status |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for cat, cls, disc, req, outs, m in rows:
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            cat, cls, disc or "-", ", ".join(req) or "-", ", ".join(outs) or "-",
            m[0], m[1], m[2], m[3], m[4]))
    lines.append("")
    lines.append("Test series: P4.1 constants/reports, P4.2 calculations, P4.3 ODE time courses, P4.4 steady state and")
    lines.append("Jacobian, P4.5 ranges/loops/scans, P4.6 ModelChange/imports/plots.")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {out}: {len(rows)} classes")
    if missing_manual:
        print("NOT IN MANUAL TABLE:", ", ".join(missing_manual))


if __name__ == "__main__":
    main()
