"""pysed2translate-pbg: translate SED2 documents to process-bigraph composite documents, and run them.

    pysed2translate-pbg translate X.sed2.json --backend roadrunner -o X.pbg.composite.json
    pysed2translate-pbg run X.pbg.composite.json --input-dir . --output-dir results
    pysed2translate-pbg engines
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from . import __version__, engines, host
from .api import Options

DEFAULT_ENGINE = "v1"      # rule M9: the one default, in one place

EPILOG = """\
exit status (the same as pysed2translate):
  0   done
  1   a task or output failed while running
  2   bad command line
  10  the SED2 document is unreadable or invalid
  11  the chosen backend cannot perform a task or run the model (a skip, not a failure)
  12  any other translation error
"""


def default_engine() -> str:
    return os.environ.get("PYSED2TRANSLATE_PBG_ENGINE") or DEFAULT_ENGINE


def parse_backends(values) -> dict:
    """['roadrunner', 'fba=cobra:scipy'] -> {'*': 'roadrunner', 'fba': 'cobra:scipy'}"""
    out: dict = {}
    for v in values or []:
        if "=" in v:
            kind, name = v.split("=", 1)
            out[kind.strip()] = name.strip()
        else:
            out["*"] = v.strip()
    return out


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="pysed2translate-pbg", description=__doc__, epilog=EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"pysed2translate-pbg {__version__} (host {host.HOST_VERSION})")
    ap.add_argument("--engine", default=None, help=f"engine to use (default {default_engine()}); see 'engines'")
    ap.add_argument("-v", "--verbose", action="count", default=0)
    ap.add_argument("--backend-list", action="store_true", help="print kinds x backends (supported, provider, installed, version) and exit")
    sub = ap.add_subparsers(dest="command", required=True)
    t = sub.add_parser("translate", help="SED2 document -> process-bigraph document")
    t.add_argument("file")
    t.add_argument("--backend", "-b", action="append", metavar="[KIND=]NAME",
                   help="simulator: NAME for every kind it can do, or KIND=NAME[:VARIANT] (kinds: ode, steady, jacobian, fba); repeatable")
    t.add_argument("-o", "--output", metavar="OUT.pbg.composite.json", help="write here (default: standard output)")
    t.add_argument("--prefix", help="prefix of the result file names (default: the file name up to .sed2.json)")
    t.add_argument("--input-dir", help="default input directory written into the document")
    t.add_argument("--output-dir", help="default output directory written into the document")
    r = sub.add_parser("run", help="run a translated document")
    r.add_argument("file")
    r.add_argument("--input-dir", default=None, help="where relative model and data locations are found (default: the document's folder)")
    r.add_argument("--output-dir", default=".", help="where result files are written")
    r.add_argument("--no-png", action="store_true")
    r.add_argument("--manifest", metavar="FILE")
    sub.add_parser("engines", help="list the engines found")
    from . import suite as _suite
    _suite.add_arguments(sub.add_parser("suite", help="run sed2-test-suite cases through an engine and compare with the canonical data"))
    return ap


def add_engine_options(ap, name: str):
    """Engine options are added to the sub-parsers by the engine itself."""


# module (to import) and distribution (for the version) of each simulator, and of the wrapper that provides it
SIMULATORS = {"roadrunner": ("roadrunner", "libroadrunner"), "copasi": ("basico", "copasi-basico"),
              "opencor": ("libopencor", "libopencor"), "cobra": ("cobra", "cobra")}
WRAPPER_PACKAGES = {"viva-tellurium": ("viva_tellurium", "viva-tellurium"), "viva-copasi": ("viva_copasi", "viva-copasi")}


def _installed(module: str, dist: str) -> str:
    import importlib.util
    from importlib import metadata

    if importlib.util.find_spec(module) is None:
        return "no"
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return "yes"


def backend_list(engine) -> str:
    """Kinds x backends: supported (from the capability table), provider under --wrappers strict/prefer, installed, version."""
    table = host.capability_table()
    provider_for = getattr(getattr(engine, "providers", None), "provider_for", None) if engine is not None else None
    rows = [("kind", "backend", "supported", "provider", "provider installed", "simulator installed")]
    for kind in host.KINDS:
        for name in host.ALL_BACKENDS:
            supported = "yes" if name in table.serving(kind) else "no"
            prov = provider_for(kind, name) if provider_for else "runtime"
            pkg = WRAPPER_PACKAGES.get(prov)
            rows.append((kind, name, supported, prov, _installed(*pkg) if pkg else "-", _installed(*SIMULATORS[name])))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # engine options belong to the engine: parse --engine first, let that engine add its arguments, then parse for real
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--engine", default=None)
    known, _ = pre.parse_known_args(argv)
    ap = build_parser()
    name = known.engine or default_engine()
    engine = None
    try:
        engine = engines.load(name)
    except KeyError:
        pass
    if "--backend-list" in argv:
        print(backend_list(engine))
        return host.EXIT_OK
    choices = ap._subparsers._group_actions[0].choices
    if engine is not None:
        engine.add_arguments(choices["translate"])
        engine.add_arguments(choices["suite"])
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING - 10 * min(args.verbose, 2), format="%(levelname)s: %(message)s", stream=sys.stderr)

    if args.command == "engines":
        for n in engines.names():
            mod = engines.discover().get(n)
            print(f"{n}\t{getattr(mod, 'VERSION', '?') if mod else 'cannot be imported: ' + engines.broken().get(n, '')}"
                  f"{'\t(default)' if n == default_engine() else ''}")
        return host.EXIT_OK
    if engine is None:
        print(f"error: no engine {name!r}; engines found: {', '.join(engines.names()) or 'none'}", file=sys.stderr)
        return host.EXIT_USAGE

    if args.command == "translate":
        backends = parse_backends(args.backend)
        if not backends:
            ap.error("translate: --backend is required")
        for kind, b in backends.items():
            if kind != "*" and kind not in host.KINDS:
                ap.error(f"unknown kind {kind!r} in --backend; choose from {', '.join(host.KINDS)}")
            problem = host.backend_problem(b)
            if problem:
                ap.error(problem)
        try:
            document = host.load_document(args.file)
            prefix = args.prefix if args.prefix is not None else host.default_prefix(args.file)
            opts = Options(backend=backends, prefix=prefix, source_name=os.path.basename(args.file),
                           input_dir=args.input_dir, output_dir=args.output_dir,
                           engine=engine.engine_options(args) if hasattr(engine, "engine_options") else {})
            result = engine.translate(document, opts)
        except host.InvalidDocumentError as e:
            print(f"error: {e.path} is not a valid SED2 document:", file=sys.stderr)
            for rule, loc, msg in e.problems:
                print(f"  {rule or '-'} {loc or '-'}: {msg}", file=sys.stderr)
            return e.exit_code
        except host.UnsupportedTaskError as e:
            print(f"skip: {e}", file=sys.stderr)
            return host.EXIT_UNSUPPORTED
        except host.PySED2TranslateError as e:
            print(f"error: {e}", file=sys.stderr)
            return e.exit_code
        for note in (result.manifest or {}).get("notes", []):
            print(f"note: {note}", file=sys.stderr)
        text = next(iter(result.files.values()))
        if args.output:
            with open(args.output, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        else:
            sys.stdout.write(text)
        return host.EXIT_OK

    if args.command == "suite":
        from . import suite as _suite
        return _suite.main(args, name, engine.engine_options(args) if hasattr(engine, "engine_options") else {})

    if args.command == "run":
        input_dir = args.input_dir if args.input_dir is not None else os.path.dirname(os.path.abspath(args.file))
        os.makedirs(args.output_dir, exist_ok=True)
        return engine.run(args.file, input_dir, args.output_dir, png=not args.no_png, manifest=args.manifest)
    return host.EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
