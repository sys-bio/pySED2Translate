"""Command line: pysed2translate FILE --backend {roadrunner,copasi,opencor,cobra} [-o OUT.py]."""
from __future__ import annotations

import argparse
import logging
import sys

from . import __version__
from .backends import ALL_BACKENDS, KINDS, parse_backend_args
from .errors import (EXIT_OK, EXIT_TRANSLATION, EXIT_UNSUPPORTED, EXIT_USAGE, InvalidDocumentError, PySED2TranslateError,
                     UnsupportedTaskError)
from .translate import translate_file

log = logging.getLogger("pysed2translate")

EPILOG = """\
exit status:
  0   script written
  2   bad command line
  10  the SED2 document is unreadable or invalid (rule ids are listed)
  11  the chosen backend cannot perform a task in the document (the reason is given); a skip, not a failure
  12  any other translation error
"""


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="pysed2translate", description="Translate a SED2 document into a Python script.",
                                 epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="the SED2 document (NNNNN.sed2.json)")
    ap.add_argument("--backend", "-b", required=True, action="append", metavar="[KIND=]NAME[:VARIANT]",
                    help=f"simulator the script will use: {', '.join(ALL_BACKENDS)}; a variant picks a solver "
                         f"(cobra:glpk, cobra:scipy).  KIND= (one of {', '.join(KINDS)}) names the backend for one kind "
                         "of work, for example: -b roadrunner -b fba=cobra:scipy")
    ap.add_argument("-o", "--output", metavar="OUT.py", help="write the script here (default: standard output)")
    ap.add_argument("--prefix", help="prefix of the result file names (default: the document's file name up to .sed2.json)")
    ap.add_argument("--input-dir", help="default --input-dir of the generated script (default: the script's own directory)")
    ap.add_argument("--output-dir", help="default --output-dir of the generated script (default: the current directory)")
    ap.add_argument("-v", "--verbose", action="count", default=0, help="more logging")
    ap.add_argument("-q", "--quiet", action="store_true", help="only errors")
    ap.add_argument("--version", action="version", version=f"pysed2translate {__version__}")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.quiet:
        level = logging.ERROR
    elif args.verbose >= 2:
        level = logging.DEBUG
    elif args.verbose == 1:
        level = logging.INFO
    else:
        level = logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s", stream=sys.stderr)
    try:
        backend, kind_backends = parse_backend_args(args.backend)
    except ValueError as e:
        print(f"error: --backend: {e}", file=sys.stderr)
        return EXIT_USAGE
    try:
        text = translate_file(args.file, backend, prefix=args.prefix, input_dir=args.input_dir,
                              output_dir=args.output_dir, kind_backends=kind_backends)
    except InvalidDocumentError as e:
        print(f"error: {e.path} is not a valid SED2 document:", file=sys.stderr)
        for rule, loc, msg in e.problems:
            print(f"  {rule or '-'} {loc or '-'}: {msg}", file=sys.stderr)
        return e.exit_code
    except UnsupportedTaskError as e:
        print(f"skip: {e}", file=sys.stderr)
        return EXIT_UNSUPPORTED
    except PySED2TranslateError as e:
        print(f"error: {e}", file=sys.stderr)
        return e.exit_code
    except ImportError as e:
        print(f"error: a required package is missing: {e}", file=sys.stderr)
        return EXIT_TRANSLATION
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        log.info("wrote %s", args.output)
    else:
        sys.stdout.write(text)
    return EXIT_OK
