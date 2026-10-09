"""The `suite` command: run SED2 test-suite cases through an engine and compare with the canonical data.

For each case and backend: translate with the engine (in this process), run the document in a new interpreter
(`pysed2translate-pbg run`), and compare the files it writes with the case's expected results (the suite's own comparison, so
the acceptance rule |a-e| <= abs + rel*|e| applies unchanged).  Cell statuses are the host's: PASS, FAIL, SKIP, ERROR; a backend
that settings.json records as canonical must be supported, so "unsupported" there is a FAIL.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from . import engines, host
from .api import Options

PASS, FAIL, SKIP, ERROR = host.PASS, host.FAIL, host.SKIP, host.ERROR
DEFAULT_TIMEOUT = 900.0


def run_document(engine_name: str, doc_path: str, case_dir: str, out_dir: str, manifest: str, timeout: float):
    env = dict(os.environ)
    env["MPLBACKEND"] = "Agg"
    cmd = [sys.executable, "-m", "pysed2translate_pbg.cli", "--engine", engine_name, "run", doc_path, "--input-dir", case_dir,
           "--output-dir", out_dir, "--no-png", "--manifest", manifest]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout, cwd=out_dir)
    except subprocess.TimeoutExpired as e:
        err = e.stderr.decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        return None, err
    return r.returncode, r.stderr


def run_case(suite, engine_name: str, case_dir: str, backend: dict, work_dir: str, timeout: float = DEFAULT_TIMEOUT,
             label: Optional[str] = None, engine_options: Optional[dict] = None):
    """Translate and run one case with `backend` ({"*": "roadrunner"} or per kind); returns a RunResult whose `backend` is
    `label` (default: the backend text)."""
    case = os.path.basename(case_dir)
    label = label or "+".join(f"{k}={v}" if k != "*" else v for k, v in backend.items())
    started = time.monotonic()
    res = host.RunResult(case, label, ERROR)

    def done(status, reason=""):
        res.status, res.reason, res.seconds = status, reason, time.monotonic() - started
        return res

    try:
        settings = suite.settings.load_settings(suite.settings.find_settings_file(case_dir))
    except (OSError, ValueError) as e:
        return done(ERROR, f"no usable settings.json: {e}")
    res.canonical = bool(settings) and all(b.split(":")[0] in settings.get("backends", []) for b in backend.values())
    doc_path = host.document_path(case_dir)
    if not os.path.exists(doc_path):
        return done(ERROR, f"{os.path.basename(doc_path)} does not exist")
    engine = engines.load(engine_name)
    try:
        document = host.load_document(doc_path)
        result = engine.translate(document, Options(backend=backend, prefix=case, source_name=os.path.basename(doc_path),
                                                    input_dir=case_dir, engine=engine_options or {}))
    except host.UnsupportedTaskError as e:
        if res.canonical and not getattr(e, "provider_gap", False):     # a wrapper's gap says nothing about the canonical backend
            return done(FAIL, f"unsupported, but {label} is recorded as having produced canonical results: {e}")
        return done(SKIP, str(e))
    except host.InvalidDocumentError as e:
        return done(ERROR, "the document is not valid: " + "; ".join(f"{r or '-'} {m}" for r, _, m in e.problems[:3]))
    except (host.TranslationError, ImportError) as e:
        return done(ERROR, f"translation failed: {e}")
    if (result.manifest or {}).get("wrappers", "off") != "off":
        res.canonical = False      # the canonical data were produced by the host runtime, not by a community wrapper
    out_dir = os.path.join(work_dir, case, label.replace("=", "-").replace(":", "-"))
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir)
    res.out_dir = out_dir
    name, text = next(iter(result.files.items()))
    doc_out = os.path.join(out_dir, name)
    with open(doc_out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    manifest = os.path.join(out_dir, "manifest.json")
    code, err = run_document(engine_name, doc_out, case_dir, out_dir, manifest, timeout)
    if os.path.exists(manifest):
        with contextlib.suppress(OSError, ValueError):
            with open(manifest, "r", encoding="utf-8") as f:
                res.manifest = json.load(f)
    if code is None:
        return done(ERROR, f"the document did not finish within {timeout:g} s")
    if code == host.EXIT_UNSUPPORTED:
        if res.canonical:
            return done(FAIL, f"unsupported, but {label} is recorded as having produced canonical results: {host.suite_tail(err)}")
        return done(SKIP, host.suite_tail(err))
    if code != 0:
        return done(ERROR, f"the run failed (exit {code}): {host.suite_tail(err)}")
    try:
        res.items = suite.compare.compare_case(case_dir, out_dir, settings)
    except (OSError, ValueError, KeyError) as e:
        return done(ERROR, f"cannot compare: {e}")
    bad = [i for i in res.items if not i.ok]
    if bad:
        first = bad[0]
        extra = f" (+{len(bad) - 1} more)" if len(bad) > 1 else ""
        return done(FAIL, f"{first.kind} {first.name}: {first.mismatches[0]}{extra}")
    return done(PASS)


def add_arguments(sub) -> None:
    sub.add_argument("cases", nargs="*", help="case numbers, folders or .sed2.json files (default: every semantic case)")
    sub.add_argument("--suite", help="the sed2-test-suite folder")
    sub.add_argument("-b", "--backend", action="append", metavar="[KIND=]NAME",
                     help="backend (repeatable); each plain NAME is run on its own; KIND=NAME entries are combined with each plain "
                          "NAME (default: every backend of the host)")
    sub.add_argument("--matrix", action="append", metavar="KIND=A,B",
                     help="run every plain backend with each of these backends for one kind (repeatable; for example "
                          "fba=cobra:glpk,cobra:scipy)")
    sub.add_argument("--work-dir", help="keep the translated documents and outputs here (default: a temporary folder)")
    sub.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    sub.add_argument("--script", action="store_true",
                     help="also run each case through the Python-script target and report every difference in status "
                          "(meaningful with --wrappers off: wrappers are not what the script target runs)")
    sub.add_argument("--crosscheck", action="store_true", help="also compare the backends' outputs with one another")
    sub.add_argument("--log-draft", action="store_true", help="print draft disagreement-log entries (implies --crosscheck)")
    sub.add_argument("-j", "--jobs", type=int, default=1, help="cases run at the same time")
    sub.add_argument("--json", action="store_true")


def main(args, engine_name: str, engine_options: dict) -> int:
    try:
        suite = host.locate_suite(args.suite)
        cases = host.list_cases(suite, args.cases)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return host.EXIT_USAGE
    plain = [b for b in (args.backend or []) if "=" not in b]
    kinds = {b.split("=", 1)[0]: b.split("=", 1)[1] for b in (args.backend or []) if "=" in b}
    explicit = bool(plain or kinds)

    matrix: dict = {}
    for m in args.matrix or []:
        kind, _, names = m.partition("=")
        if kind not in host.KINDS or not names:
            print(f"error: --matrix expects KIND=A,B with a kind from {', '.join(host.KINDS)}, not {m!r}", file=sys.stderr)
            return host.EXIT_USAGE
        matrix[kind] = [n for n in names.split(",") if n]

    def combos_for(case_dir):
        """(backend spec, label) pairs to run for a case: the ones named, else the host's default backends for the case;
        each --matrix kind multiplies them."""
        extras = [{}]
        for kind, names in matrix.items():
            extras = [{**e, kind: n} for e in extras for n in names]
        combos = []
        for p in (plain or ["*"]) if (explicit or matrix) else host.default_backends(case_dir):
            for extra in extras:
                fixed = {**kinds, **extra}
                spec = dict(fixed)
                if p != "*":
                    spec["*"] = p
                parts = ([p] if p != "*" else []) + [f"{k}={v}" for k, v in fixed.items()]
                combos.append((spec, "+".join(parts)))
        return combos

    if not cases:
        print("no cases found")
        return 0
    work = os.path.abspath(args.work_dir) if args.work_dir else tempfile.mkdtemp(prefix="pbgsuite-")
    os.makedirs(work, exist_ok=True)
    results: list = []
    found: list = []
    script_differences: list = []

    def one(case_dir):
        out = []
        for spec, label in combos_for(case_dir):
            out.append(run_case(suite, engine_name, case_dir, spec, work, args.timeout, label, engine_options))
            if args.script:
                default = spec.get("*") or next((v for k, v in spec.items() if k != "*"), "")
                script = host.script_run_case(suite, case_dir, default, os.path.join(work, "script"), args.timeout,
                                              kind_backends={k: v for k, v in spec.items() if k != "*"})
                if script.status != out[-1].status:
                    script_differences.append(f"{out[-1].case} {label}: {engine_name} {out[-1].status} "
                                              f"({out[-1].reason[:120]}), script target {script.status} ({script.reason[:120]})")
        return out

    try:
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            for case_dir, case_results in zip(cases, pool.map(one, cases)):
                results += case_results
                found += host.disagreements_with_expected(suite, case_dir, case_results)
                if args.crosscheck or args.log_draft:
                    found += host.crosscheck(suite, case_dir, case_results)
        drafts = host.draft_entries(suite, found) if args.log_draft else []
        if args.json:
            print(json.dumps({"results": [r.to_json() for r in results],
                              "disagreements": [{"case": d.case, "backends": list(d.backends), "report": d.report,
                                                 "message": d.message()} for d in found], "draftEntries": drafts}, indent=2))
        else:
            print(host.format_report(results, host.result_columns(results)))
            if args.script:
                print("\nstatus differences from the script target: " + ("none" if not script_differences else ""))
                for d in script_differences:
                    print("  " + d)
            if found:
                print("\ndifferences found:")
                for d in found:
                    print("  " + d.message())
            if drafts:
                print("\ndraft entries for disagreements.json (add them by hand once looked at):")
                print(json.dumps(drafts, indent=2))
    finally:
        if not args.work_dir:
            shutil.rmtree(work, ignore_errors=True)
    return 1 if any(r.status in (FAIL, ERROR) for r in results) or script_differences else 0
