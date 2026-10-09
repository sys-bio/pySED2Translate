"""Run the SED2 test suite through the translator: translate, run, compare, report.

    python -m pysed2translate.suite_runner                       # every semantic case, every backend
    python -m pysed2translate.suite_runner 00200 00201 -b copasi # chosen cases and backends
    python -m pysed2translate.suite_runner --crosscheck          # also compare the backends with one another
    python -m pysed2translate.suite_runner --log-draft           # print draft disagreement-log entries
    python -m pysed2translate.suite_runner 00100 --promote roadrunner   # record a backend's results as the case's

For each case and backend the runner translates the case's SED2 document (prefix = case number), runs the script
in a separate Python process with `--input-dir <case>`, `--output-dir <work>/<case>/<backend>`, `--no-png` and
`--manifest`, and compares the files written with the case's expected results (sed2suite's `compare_case`).  Every
cell of the result matrix is one of

    PASS    ran, and agrees with the expected results
    FAIL    ran, and differs (or is missing an output), or: unsupported by the translator for a backend that the
            case's settings.json records as having produced canonical results
    SKIP    the translator reports that the backend cannot perform something in the document (exit status 11)
    ERROR   the document does not validate, translation failed, or the script failed or timed out

The rule for canonical backends: a backend listed in `backends` of the case's settings.json produced canonical
results, so the translator must support it for that case; "unsupported" there is a FAIL, not a SKIP.

Exit status: 0 if there is no FAIL and no ERROR, 1 if there is, 2 for usage errors.

The suite is found with --suite, $SED2SUITE, or a sibling `sed2-test-suite` folder.
"""
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Optional

from .backends import BACKENDS
from .errors import InvalidDocumentError, TranslationError, UnsupportedTaskError
from .translate import translate_file

PASS, FAIL, SKIP, ERROR = "PASS", "FAIL", "SKIP", "ERROR"
DEFAULT_TIMEOUT = 600.0
PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------- the suite

@dataclasses.dataclass
class Suite:
    root: str
    compare: object
    settings: object
    disagreements: object

    @property
    def cases_dir(self) -> str:
        return os.path.join(self.root, "cases", "semantic")

    @property
    def log_path(self) -> str:
        return os.path.join(self.root, "disagreements.json")


def locate_suite(path: Optional[str] = None) -> Suite:
    """Find the suite folder and import its tools.  Raises FileNotFoundError if there is none."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [path] if path else [os.environ.get("SED2SUITE"), os.path.join(here, "..", "..", "..", "sed2-test-suite")]
    for c in candidates:
        if c and os.path.isdir(os.path.join(c, "tools", "sed2suite")):
            root = os.path.abspath(c)
            tools = os.path.join(root, "tools")
            if tools not in sys.path:
                sys.path.insert(0, tools)
            from sed2suite import compare, disagreements, settings

            return Suite(root, compare, settings, disagreements)
    raise FileNotFoundError("cannot find the sed2-test-suite folder (use --suite or set SED2SUITE)")


def list_cases(suite: Suite, selectors: list) -> list:
    """Case folders: all of cases/semantic, or the chosen numbers, folders or .sed2.json files."""
    base = suite.cases_dir
    if not selectors:
        if not os.path.isdir(base):
            return []
        return sorted(os.path.join(base, d) for d in os.listdir(base)
                      if os.path.isdir(os.path.join(base, d)) and d.isdigit())
    out = []
    for s in selectors:
        for c in (s, os.path.join(base, s)):
            if os.path.isdir(c):
                out.append(os.path.abspath(c))
                break
            if os.path.isfile(c) and c.endswith(".sed2.json"):
                out.append(os.path.dirname(os.path.abspath(c)))
                break
        else:
            raise FileNotFoundError(f"cannot find case {s!r}")
    return out


def document_path(case_dir: str) -> str:
    return os.path.join(case_dir, os.path.basename(case_dir) + ".sed2.json")


# --------------------------------------------------------------------------- one run

@dataclasses.dataclass
class RunResult:
    case: str
    backend: str
    status: str
    reason: str = ""
    canonical: bool = False
    out_dir: str = ""
    seconds: float = 0.0
    items: list = dataclasses.field(default_factory=list)   # failing/passing items from compare_case
    manifest: dict = dataclasses.field(default_factory=dict)

    def to_json(self) -> dict:
        d = {"case": self.case, "backend": self.backend, "status": self.status, "canonical": self.canonical,
             "seconds": round(self.seconds, 2)}
        if self.reason:
            d["reason"] = self.reason
        return d


def _tail(text: str, n: int = 6) -> str:
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    return " | ".join(lines[-n:])


def run_script(script: str, case_dir: str, out_dir: str, manifest: str, timeout: float) -> tuple:
    """Run a generated script in a new interpreter; returns (returncode or None on timeout, stderr text)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [PACKAGE_ROOT, env.get("PYTHONPATH", "")]))
    env["MPLBACKEND"] = "Agg"
    cmd = [sys.executable, script, "--input-dir", case_dir, "--output-dir", out_dir, "--no-png", "--manifest", manifest]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout, cwd=out_dir)
    except subprocess.TimeoutExpired as e:
        err = e.stderr.decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        return None, err
    return r.returncode, r.stderr


def run_case(suite: Suite, case_dir: str, backend: str, work_dir: str, timeout: float = DEFAULT_TIMEOUT,
             new_case: bool = False) -> RunResult:
    """Translate and run one case on one backend, and compare with the expected results.

    With `new_case`, a case that has no settings.json yet is run and not compared (status PASS, a reason saying
    so), which is what promoting its first results needs."""
    case = os.path.basename(case_dir)
    started = time.monotonic()
    res = RunResult(case, backend, ERROR)

    def done(status, reason="") -> RunResult:
        res.status, res.reason, res.seconds = status, reason, time.monotonic() - started
        return res

    try:
        settings = suite.settings.load_settings(suite.settings.find_settings_file(case_dir))
    except FileNotFoundError as e:
        if not new_case:
            return done(ERROR, f"no usable settings.json: {e}")
        settings = None
    except (OSError, ValueError) as e:
        return done(ERROR, f"no usable settings.json: {e}")
    res.canonical = settings is not None and backend in settings.get("backends", [])
    doc_path = document_path(case_dir)
    if not os.path.exists(doc_path):
        return done(ERROR, f"{os.path.basename(doc_path)} does not exist")

    try:
        text = translate_file(doc_path, backend, prefix=case, input_dir=case_dir)
    except UnsupportedTaskError as e:
        if res.canonical:
            return done(FAIL, f"unsupported, but {backend} is recorded as having produced canonical results: {e}")
        return done(SKIP, str(e))
    except InvalidDocumentError as e:
        return done(ERROR, "the document is not valid: " + "; ".join(f"{r or '-'} {m}" for r, _, m in e.problems[:3]))
    except (TranslationError, ImportError) as e:
        return done(ERROR, f"translation failed: {e}")

    out_dir = os.path.join(work_dir, case, backend)
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir)
    res.out_dir = out_dir
    script = os.path.join(out_dir, f"{case}.{backend}.py")
    with open(script, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    manifest = os.path.join(out_dir, "manifest.json")
    code, err = run_script(script, case_dir, out_dir, manifest, timeout)
    if os.path.exists(manifest):
        with contextlib.suppress(OSError, ValueError):
            with open(manifest, "r", encoding="utf-8") as f:
                res.manifest = json.load(f)
    if code is None:
        return done(ERROR, f"the script did not finish within {timeout:g} s")
    if code != 0:
        return done(ERROR, f"the script failed (exit {code}): {_tail(err)}")

    if settings is None:
        return done(PASS, "ran; the case has no settings.json yet, so nothing was compared")
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


# --------------------------------------------------------------------------- cross-checks and the log

@dataclasses.dataclass
class Disagreement:
    case: str
    backends: tuple          # (a, b); b may be "expected"
    report: str
    measure: dict

    def message(self) -> str:
        m = self.measure
        size = (f"abs {m['maxAbsolute']:.3g}, rel {m['maxRelative']:.3g}" if m.get("comparable")
                else m.get("reason", "not comparable"))
        return f"{self.case}{' ' + self.report if self.report else ''}: {' vs '.join(self.backends)}: {size}"


def _settings_or_none(suite: Suite, case_dir: str):
    try:
        return suite.settings.load_settings(suite.settings.find_settings_file(case_dir))
    except (OSError, ValueError):
        return None


def disagreements_with_expected(suite: Suite, case_dir: str, results: list) -> list:
    """For each backend that FAILed or ERRORed after producing output (or failed for want of support it should have),
    how far it is from the expected results; a run that produced nothing to measure gets its reason as the symptom.
    A backend that was merely unsupported (SKIP) is not a disagreement."""
    case = os.path.basename(case_dir)
    settings = _settings_or_none(suite, case_dir)
    out = []
    for r in results:
        if settings is None or r.case != case or r.status not in (FAIL, ERROR):
            continue
        measured = suite.compare.measure_case(case_dir, r.out_dir, settings) if r.out_dir and r.status == FAIL else []
        bad = [m for m in measured if not m["ok"]]
        if bad:
            out += [Disagreement(case, (r.backend, "expected"), m["name"], m) for m in bad]
        elif r.status == ERROR and not r.out_dir:
            continue          # the document or the translation is at fault, whatever the backend: not a disagreement
        else:
            out.append(Disagreement(case, (r.backend, "expected"), "", {"comparable": False, "reason": r.reason}))
    return out


def crosscheck(suite: Suite, case_dir: str, results: list) -> list:
    """Compare every pair of backends that produced outputs for the case, using the case's own tolerances.
    Returns the pairs that differ by more than the tolerance."""
    case = os.path.basename(case_dir)
    settings = _settings_or_none(suite, case_dir)
    ran = [r for r in results if settings is not None and r.case == case and r.out_dir and r.status in (PASS, FAIL)]
    out = []
    for i, a in enumerate(ran):
        for b in ran[i + 1:]:
            for m in suite.compare.measure_case(a.out_dir, b.out_dir, settings):
                if not m["ok"]:
                    out.append(Disagreement(case, (a.backend, b.backend), m["name"], m))
    return out


def draft_entries(suite: Suite, found: list) -> list:
    """Draft log entries (not yet in the log) for disagreements that the log does not already cover."""
    log = suite.disagreements.load_log(suite.log_path)
    drafts = []
    for d in found:
        if suite.disagreements.find(log, d.case, list(d.backends), d.report or None):
            continue
        entry = suite.disagreements.draft_entry(log, d.case, list(d.backends), d.measure, report=d.report or None)
        log["entries"].append(entry)       # so that the next draft gets the next id
        drafts.append(entry)
    return drafts


# --------------------------------------------------------------------------- promoting results

def simulator_version(backend: str) -> str:
    modules = {"roadrunner": "roadrunner", "copasi": "basico", "opencor": "libopencor"}
    try:
        import importlib

        mod = importlib.import_module(modules[backend])
        version = getattr(mod, "__version__", None)
        if version is None:
            import importlib.metadata as md

            version = md.version({"roadrunner": "libroadrunner", "copasi": "copasi-basico", "opencor": "libopencor"}[backend])
        return str(version)
    except Exception:  # noqa: BLE001
        return "unknown"


def promote(suite: Suite, case_dir: str, result: RunResult, force: bool = False) -> list:
    """Make the results this run produced the case's expected results, and record the backend in settings.json.

    Creates NNNNN.settings.json if the case has none; otherwise keeps its tolerances and compare settings.
    Refuses to replace existing result files without `force`.  Returns the names of the files written."""
    case = os.path.basename(case_dir)
    if result.status in (SKIP, ERROR) or not result.manifest:
        raise ValueError(f"nothing to promote for {case} on {result.backend}: {result.status} {result.reason}".strip())
    entries = {**{("reports", k): v for k, v in result.manifest.get("reports", {}).items()},
               **{("plots", k): v for k, v in result.manifest.get("plots", {}).items()}}
    if not force:
        existing = [e["file"] for e in entries.values() if os.path.exists(os.path.join(case_dir, e["file"]))]
        if existing:
            raise ValueError(f"{case} already has result files ({', '.join(sorted(existing))}); use --force to replace them")
    try:
        path = suite.settings.find_settings_file(case_dir)
        settings = suite.settings.load_settings(path)
    except FileNotFoundError:
        path = os.path.join(case_dir, f"{case}.settings.json")
        settings = {"schemaVersion": 1, "tolerances": {"absolute": 1e-7, "relative": 1e-4},
                    "provenance": {"source": "simulation", "simulators": []}, "backends": []}
    settings["provenance"]["source"] = "simulation"
    sims = settings["provenance"].setdefault("simulators", [])
    sims[:] = [s for s in sims if s["name"] != result.backend]
    sims.append({"name": result.backend, "version": simulator_version(result.backend)})
    settings["backends"] = sorted(set(settings.get("backends", [])) | {result.backend}, key=BACKENDS.index)
    written = []
    for (section, rid), entry in sorted(entries.items()):
        shutil.copyfile(os.path.join(result.out_dir, entry["file"]), os.path.join(case_dir, entry["file"]))
        written.append(entry["file"])
        old = settings.setdefault(section, {}).get(rid, {})
        new = dict(entry)
        for keep in ("tolerances", "compare"):
            if keep in old:
                new[keep] = old[keep]
        settings[section][rid] = new
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    return written + [os.path.basename(path)]


# --------------------------------------------------------------------------- output

def format_matrix(results: list, backends: list) -> str:
    """A table: one row per case, one column per backend.  A star marks a backend with canonical results."""
    cases = sorted({r.case for r in results})
    by = {(r.case, r.backend): r for r in results}
    width = max([len(b) for b in backends] + [6]) + 2
    lines = ["case   " + "".join(b.ljust(width) for b in backends)]
    for c in cases:
        cells = []
        for b in backends:
            r = by.get((c, b))
            cells.append(((r.status + ("*" if r.canonical else "")) if r else "-").ljust(width))
        lines.append(f"{c:<7}" + "".join(cells))
    return "\n".join(lines)


def format_report(results: list, backends: list) -> str:
    lines = [format_matrix(results, backends), ""]
    for r in results:
        if r.reason:
            lines.append(f"{r.status:<5} {r.case} {r.backend}: {r.reason}")
    counts = {s: sum(1 for r in results if r.status == s) for s in (PASS, FAIL, SKIP, ERROR)}
    lines.append("")
    lines.append(", ".join(f"{n} {s}" for s, n in counts.items()) + "   (* = backend recorded in settings.json as canonical)")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="pysed2translate-suite", description="Run the SED2 test suite through the translator.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("cases", nargs="*", help="case numbers, folders or .sed2.json files (default: every semantic case)")
    ap.add_argument("--suite", help="the sed2-test-suite folder")
    ap.add_argument("-b", "--backend", action="append", choices=BACKENDS, help="backend to run (repeatable; default: all)")
    ap.add_argument("--work-dir", help="keep the generated scripts and outputs here (default: a temporary folder)")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="seconds allowed per script run")
    ap.add_argument("--crosscheck", action="store_true", help="also compare the backends' outputs with one another")
    ap.add_argument("--log-draft", action="store_true",
                    help="print draft disagreement-log entries for the differences found (implies --crosscheck)")
    ap.add_argument("--promote", metavar="BACKEND", choices=BACKENDS,
                    help="record BACKEND's results as the expected results of the chosen cases and add it to settings.json")
    ap.add_argument("--force", action="store_true", help="with --promote: replace existing result files")
    ap.add_argument("--json", action="store_true", help="write the results as JSON")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        suite = locate_suite(args.suite)
        cases = list_cases(suite, args.cases)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.promote and not args.cases:
        print("error: --promote needs the cases to promote to be named", file=sys.stderr)
        return 2
    backends = args.backend or ([args.promote] if args.promote else list(BACKENDS))
    if args.promote and backends != [args.promote]:
        print("error: --promote runs only the backend it names; leave out -b or use the same one", file=sys.stderr)
        return 2
    if not cases:
        print("no cases found")
        return 0

    own_work = args.work_dir is None
    work = os.path.abspath(args.work_dir) if args.work_dir else tempfile.mkdtemp(prefix="sed2suite-")
    os.makedirs(work, exist_ok=True)
    results: list = []
    found: list = []
    try:
        for case_dir in cases:
            case_results = []
            for backend in backends:
                r = run_case(suite, case_dir, backend, work, args.timeout, new_case=bool(args.promote))
                case_results.append(r)
                if args.promote:
                    try:
                        written = promote(suite, case_dir, r, args.force)
                        r.reason = (r.reason + "; " if r.reason else "") + "promoted: " + ", ".join(written)
                    except ValueError as e:
                        r.status, r.reason = ERROR, str(e)
            results += case_results
            found += disagreements_with_expected(suite, case_dir, case_results)
            if args.crosscheck or args.log_draft:
                found += crosscheck(suite, case_dir, case_results)
        drafts = draft_entries(suite, found) if args.log_draft else []
        if args.json:
            print(json.dumps({"results": [r.to_json() for r in results],
                              "disagreements": [{"case": d.case, "backends": list(d.backends), "report": d.report,
                                                 "message": d.message()} for d in found],
                              "draftEntries": drafts}, indent=2))
        else:
            print(format_report(results, backends))
            if found:
                print("\ndifferences found:")
                for d in found:
                    print("  " + d.message())
            if drafts:
                print("\ndraft entries for disagreements.json (add them by hand once looked at):")
                print(json.dumps(drafts, indent=2))
    finally:
        if own_work:
            shutil.rmtree(work, ignore_errors=True)
    return 1 if any(r.status in (FAIL, ERROR) for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
