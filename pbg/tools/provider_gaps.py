"""The expected gaps of the viva wrappers over the whole sed2-test-suite (`tests/providers/expected_gaps.json`).

For every case and every wrapper-backed backend (roadrunner -> viva-tellurium, copasi -> viva-copasi), `--wrappers strict` either
translates (some simulation tasks run in a wrapper) or refuses with ledger ids (pbg/upstream).  The file records which, and what
the translated documents did when run (PASS, SKIP with the ledger id found while running, FAIL).  The test fails on any
difference: a case that starts to pass, or to be refused, or to fail, is news that has to be read and recorded here, never absorbed.

    python tools/provider_gaps.py --check          translation only (fast)
    python tools/provider_gaps.py --check --run    also run the wrapper-backed cases (a few minutes)
    python tools/provider_gaps.py --write          rewrite tests/providers/expected_gaps.json (translation and runs)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from pysed2translate_pbg import engines, host, suite as pbg_suite  # noqa: E402
from pysed2translate_pbg.api import Options  # noqa: E402

EXPECTED = os.path.abspath(os.path.join(HERE, "..", "tests", "providers", "expected_gaps.json"))
BACKENDS = ("roadrunner", "copasi")


def versions() -> dict:
    from importlib import metadata

    out = {}
    for name in ("viva-tellurium", "viva-copasi", "process-bigraph", "bigraph-schema", "libroadrunner", "copasi-basico"):
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


def survey_case(case_dir: str, backend: str) -> dict:
    """{} when the case has no simulation task; {"wrapped": {task: class}} or {"refused": {task: [ids]}} (strict mode)."""
    v1 = engines.load("v1")
    case = os.path.basename(case_dir)
    document = host.load_document(host.document_path(case_dir))
    try:
        result = v1.translate(document, Options(backend={"*": backend}, prefix=case, source_name=case + ".sed2.json",
                                                input_dir=case_dir, engine={"wrappers": "strict"}))
    except host.UnsupportedTaskError as e:
        gaps = getattr(e, "gaps", None)
        if gaps is None:
            return {"host_unsupported": str(e)[:200]}
        return {"refused": {t: sorted({i for i, _ in g}) for t, g in sorted(gaps.items())}}
    doc = json.loads(next(iter(result.files.values())))
    w = doc["sed2"].get("wrappers")
    if not w:
        return {}
    return {"wrapped": {t: a.rsplit(".", 1)[-1] for t, a in sorted(w["tasks"].items())}}


def survey(suite, backends=BACKENDS, cases=None) -> dict:
    out: dict = {b: {} for b in backends}
    for case_dir in host.list_cases(suite, cases or []):
        for b in backends:
            entry = survey_case(case_dir, b)
            if entry:
                out[b][os.path.basename(case_dir)] = entry
    return out


def run_wrapped(suite, found: dict, jobs: int = 4) -> None:
    """Run the translated cases and add "run": "PASS" | "SKIP W-7" | "FAIL ..." to their entries."""
    from concurrent.futures import ThreadPoolExecutor

    work = tempfile.mkdtemp(prefix="pbgviva-")
    try:
        jobs_list = [(b, c) for b, cs in found.items() for c, e in cs.items() if "wrapped" in e]

        def one(item):
            b, c = item
            r = pbg_suite.run_case(suite, "v1", os.path.join(suite.cases_dir, c), {"*": b}, work, 900.0, f"{b}", {"wrappers": "strict"})
            return item, r

        with ThreadPoolExecutor(max_workers=jobs) as pool:
            for (b, c), r in pool.map(one, jobs_list):
                found[b][c]["run"] = describe(r)
    finally:
        shutil.rmtree(work, ignore_errors=True)


# errors inside a wrapper that are a recorded gap (pbg/upstream): (text in the error, ledger id)
KNOWN_ERRORS = (("spec_df[\"sbml_id\"]", "W-14"),)


def describe(r) -> str:
    if r.status == host.PASS:
        return "PASS"
    if r.status == host.ERROR:
        for text, ident in KNOWN_ERRORS:
            if text in (r.reason or ""):
                return f"ERROR {ident}"
    ids = sorted(set(re.findall(r"\b([WL]-\d+)\b", r.reason or "")))
    return f"{r.status} {' '.join(ids)}".strip() if r.status == host.SKIP else f"{r.status}: {(r.reason or '')[:160]}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--run", action="store_true", help="with --check: also run the wrapper-backed cases")
    ap.add_argument("--suite")
    ap.add_argument("-j", "--jobs", type=int, default=4)
    args = ap.parse_args(argv)
    if not (args.check or args.write):
        ap.error("--check or --write")
    suite = host.locate_suite(args.suite)
    found = survey(suite)
    if args.write or args.run:
        run_wrapped(suite, found, args.jobs)
    doc = {"description": "viva wrappers, --wrappers strict, over sed2-test-suite (tools/provider_gaps.py)", "versions": versions(),
           "backends": found}
    if args.write:
        os.makedirs(os.path.dirname(EXPECTED), exist_ok=True)
        with open(EXPECTED, "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, indent=1, sort_keys=True)
            f.write("\n")
        print(f"wrote {EXPECTED}")
        return 0
    with open(EXPECTED, encoding="utf-8") as f:
        expected = json.load(f)["backends"]
    bad = 0
    for b in found:
        for c in sorted(set(found[b]) | set(expected.get(b, {}))):
            a, e = found[b].get(c), expected.get(b, {}).get(c)
            if not args.run and a is not None and e is not None:
                a = {k: v for k, v in a.items() if k != "run"}
                e = {k: v for k, v in e.items() if k != "run"}
            if a != e:
                bad += 1
                print(f"{b} {c}: found {a}, expected {e}")
    print("expected gaps: " + ("all as recorded" if not bad else f"{bad} differences"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
